# 医学问诊智能体 · ReAct 循环与推理可解释性改造方案

> 状态：**方案待确认，尚未改动任何代码**
> 代码根：`C:\Users\lenovo\Desktop\作品集\medical_bot`
> 所有行号基于 2026-09-27 的代码快照

---

## 一、现状梳理

### 1.1 涉及模块

| 层 | 文件 | 职责 |
|---|---|---|
| 路由（小程序） | `app/routers/consultation.py:141` `chat()` | SSE 入口，`event_stream()` 纯透传 |
| 路由（桌面） | `main.py:313` `chat()` / `:363` `event_gen()` | 桌面模式入口，同样透传 |
| **状态机核心** | `consultation.py:1102` `ConsultationSession.process_user_input_stream` | **改造主落点** |
| 直接问答分支 | `consultation.py:1015` `_stream_direct_qa` | RAG 问答，不走 5 阶段 |
| 同步回退 | `consultation.py:832` `process_user_input` | 非流式路径 |
| LLM 封装 | `llm_client.py:322` `chat_stream` / `:96` `chat` / `:160` `chat_json` | 无 tools、无 token 统计、无耗时 |
| 知识库 | `knowledge_base.py:408` `search` / `:479` `search_for_consultation` | ChromaDB，`medical_knowledge` |
| 长记忆 | `memory_store.py:168` `search_memories` | ChromaDB，`consultation_memory` |
| 会话持久化 | `app/services/session_service.py:103` `persist` | 列级加密 |
| 小程序前端 | `miniapp/src/pages/consult/index.tsx:319`、`components/ChatBubble/index.tsx:42`、`services/sse.ts:142` | 事件消费与气泡渲染 |
| 桌面前端 | `static/chat.js:202` `handleSSEEvent` | **thinking 事件被 default 丢弃** |

### 1.2 完整调用链（流式主路径）

```
小程序/桌面
  └─ POST /api/chat (app/routers/consultation.py:141)
      └─ session_service.get_or_create(:76)  → 解密还原 ConsultationSession
      └─ ConsultationSession.process_user_input_stream (consultation.py:1102)
          ├─ ① 空输入短路 (:1107)
          ├─ ② _check_emergency 紧急关键词（本地，无 LLM）(:1119)
          ├─ ③ 追加 user 消息到 conversation_history (:1128)
          ├─ ④ _classify_intent (:1144) ──命中 question──→ _stream_direct_qa (:1015)【分支 A】
          ├─ ⑤ asyncio.gather(to_thread _retrieve_kb :950, to_thread _retrieve_memory :965)
          │      └─ knowledge_base.search_for_consultation (top_k=2) → 仅返回格式化字符串
          ├─ ⑥ _get_system_prompt (:432) + CONSULT_BRIEF_HINT + CONSULT_JSON_REMINDER
          ├─ ⑦ _build_context (:1309) → enriched_input（上下文+记忆+知识库+JSON 提醒）
          ├─ ⑧ llm_client.chat_stream(return_raw=True) → 流式
          │      ├─ _split_think_stream → yield {thinking}（受 SHOW_THINKING 控制）
          │      └─ _VisibleStreamFilter 剥离 JSON 块 → yield {reply}
          ├─ ⑨ _parse_llm_response (:459) 正则回溯式提取 JSON → _update_patient_info
          ├─ ⑩ _apply_stage_transition (:691) + _fallback_stage_advance (:609) 兜底
          ├─ ⑪ conversation_history.append(assistant) ；_remember_turn 后台任务
          └─ ⑫ yield {end}（JSON: session_id/stage/is_complete/reply_clean/report_status）
              └─ 若 is_complete：maybe_start_report_task (:725) 后台生成报告，前端轮询
```

**关键事实**

1. 每轮**只调用 1 次 LLM**（历史上 3 次已合并优化），本机实测约 2.5~16 tok/s，延迟敏感。
2. 知识库检索**已在 LLM 之前**发生，但只取 `top_k=2`，且返回值被拼成字符串后**丢弃了 id / chunk_index**——`search()` 的 `include` 只有 `["documents","metadatas","distances"]`（`knowledge_base.py:438`），结果 dict 仅 4 字段（`:458-463`）。入库时其实生成了稳定 ID `{文件名}_chunk_{i}`（`:311`），只是没透出。
3. 现有 SSE 事件只有 `reply / thinking / end / error`（+已废弃的 report 系列）。**已有 thinking 通道**是天然可复用的 Thought 载体。
4. 前端：`ChatBubble` 只有 `content` + 一个扁平字符串 `thinking`（可折叠），**无步骤、无时间线、无引用**；桌面端连 thinking 都不显示。
5. `conversation_history` 只存 `{role, content}`，历史回放（`get_history`）拿不到任何过程数据。
6. 落库：`consultation_sessions` 表 17 个字段，**无 steps/trace、无耗时、无 token**；敏感字段列级加密（`crypto.py:266 SESSION_SENSITIVE_FIELDS`）。

---

## 二、ReAct 循环设计

### 2.1 设计原则（针对本项目约束）

| 约束 | 应对 |
|---|---|
| 小模型（qwen2.5:7b）指令遵循不稳定 | **结构化 JSON Planner**，不用自由文本 ReAct 协议；解析失败即降级为现有单次流程 |
| 延迟敏感（1 次 LLM ≈ 数秒） | **受控循环**：`MAX_STEPS=3`、有超时、有步预算；默认只在"直接问答"分支启用 |
| 5 阶段采集状态机不能被动摇 | ReAct **只接管工具编排**，阶段推进仍由 `_apply_stage_transition` 负责 |
| 现有链路不能一次性重写 | 全部收敛在 `process_user_input_stream` / `_stream_direct_qa` 内，路由层不动 |

### 2.2 循环形态

采用 **Plan → Act → Observe → (循环) → Answer** 的受控 ReAct：

```
        ┌───────────── 第 k 步（k = 0..MAX_STEPS-1）─────────────┐
        │  Thought   : 由 Planner LLM 的 thought 字段产出        │
        │  Action    : 由 Planner LLM 的 action 字段产出(JSON)   │
        │  Observation: 由工具真实返回值产出（非模型生成）        │
        └───────────────────────────────────────────────────────┘
                              ↓ 终止判定
                     最终答案 LLM（流式，复用现有 reply 通道）
```

**Planner 输出协议**（追加在现有 `CONSULT_JSON_REMINDER` 之后，沿用项目"提示词约束 + 正则/JSON 提取"的既有风格）：

```json
{
  "thought": "患者问的是腹痛伴腹泻的鉴别，需要先查知识库",
  "action": {"name": "kb_search", "args": {"query": "腹痛 腹泻 鉴别诊断", "top_k": 3}},
  "final_answer": null
}
```

`final_answer` 非空即视为 Planner 判定信息充足，进入终答阶段。

### 2.3 每一步的产生方式

| 元素 | 产生方式 | 数据来源 | 是否可信 |
|---|---|---|---|
| **Thought** | Planner LLM 的 `thought` 字段；新增 SSE 事件 `step`（`type:"thought"`）流式吐出 | 模型 | 中等（标注为"模型思考"，不参与医疗结论） |
| **Action** | Planner LLM 的 `action` 字段；校验工具名与参数白名单后执行；`step(type:"action")` 事件带 `tool` 与 `query` | 模型 + 白名单校验 | 高（参数受校验约束） |
| **Observation** | 工具真实返回；由**执行层**写入 `step(type:"observation")`，含 `elapsed_ms` 与 `refs` | 系统 | **最高（非模型编造）** |
| **Final Answer** | 终答 LLM（流式），沿用现有 `reply` 事件 + `_VisibleStreamFilter` | 模型 | 高（有引用约束） |

**第 0 步（确定性步骤，无 LLM）**也纳入同一时间线，保证可解释性完整：

- `emergency_check`（紧急关键词命中）
- `intent_classify`（intake / question）
- `kb_retrieve` / `memory_retrieve`（现有的并发双检索）
- 这步零成本，但让用户看到"为什么走了这条分支"。

### 2.4 工具集（Action 白名单）

| 工具 | 实现 | 返回 | 备注 |
|---|---|---|---|
| `kb_search` | `knowledge_base.search`（需先补 id，见 §4） | 命中片段 + doc_id/chunk_id/score | 主工具 |
| `patient_history` | `database.query_patient` / `repositories.query_patient_records` | 既往就诊日期/主诉/诊断 | 需姓名，属敏感数据 |
| `memory_search` | `memory_store.search_memories` | 跨会话记忆片段 | 需补 id（同 §4） |
| `finish` | — | — | 终止动作，进入终答 |
| `ask_user` | — | — | 终止动作，向用户追问（采集态专用） |

> 说明：项目里**没有**医院检索与联网搜索（此前探查确认未实现），本期不引入新外部依赖。

### 2.5 触发与终止条件

**触发**

- 总开关 `ENABLE_REACT`（默认 `false`，与 `ENABLE_DIRECT_QA`/`SHOW_THINKING` 同风格的环境变量开关）；
- 一期仅在 `_stream_direct_qa`（直接问答分支）启用；采集态（intake）保持现有单次流程；
- 满足其一即跳过 ReAct：已经在走紧急流程、输入为空、`is_complete`。

**终止（任一命中即进入终答）**

1. Planner 返回非空 `final_answer`；
2. `action.name == "finish"` 或 `"ask_user"`；
3. 步数达到 `REACT_MAX_STEPS`（默认 3）；
4. 累计耗时 > `REACT_BUDGET_MS`（默认 12000ms）——用 `time.perf_counter` 计时；
5. Planner 输出**连续 2 次**解析失败或工具名不在白名单（防止小模型空转）；
6. 工具抛异常累计 2 次。

**降级（Fallback，保证可用性优先）**

- Planner 一次都没产出合法 JSON → **静默回退**到现有单次 LLM 流程，仅记录一条 `step(type:"fallback")`；
- 终答阶段异常 → 直接把已观测到的内容拼成答案，仍走 `reply` 事件；
- 任何情况下 `end` 事件的字段结构与现在**完全一致**（新增字段可缺省），前端不受影响。

---

## 三、可解释性呈现

### 3.1 新增 SSE 事件：`step`

`_sse()`（`app/routers/consultation.py:23`）无需改动，`step` 与其他事件同格式透传。

```jsonc
// event: step
{
  "trace_id": "53b45a7a-7",          // session_id + "-" + turn_index
  "seq": 2,                           // 步骤序号，严格递增 → 保证顺序可追溯
  "type": "thought|action|observation|final|fallback",
  "turn": 7,
  "stage": 2,
  "ts": "2026-09-27T20:10:03.512+08:00",
  "elapsed_ms": 842,                  // 本步耗时
  "status": "ok|error|timeout|skipped",
  "text": "需要确认是否为急性胃肠炎……",   // thought/observation 摘要
  "tool": "kb_search",                // action 时
  "args": {"query": "腹痛 腹泻 鉴别"},   // action 参数（脱敏后）
  "refs": [                            // 本步引用的知识片段（详见 §4）
    {"n": 1, "doc_id": "消化系统疾病.md_chunk_12", "source": "消化系统疾病.md",
     "chunk_index": 12, "score": 0.83, "quote": "急性胃肠炎多由……"}
  ],
  "error": null
}
```

**顺序与耗时**：`seq` 由执行层单调递增发放；`elapsed_ms` 用 `time.perf_counter()` 在每步前后打点；`ts` 用系统时间（**禁止模型生成时间**，沿用项目"日期来自系统"的铁律）。

### 3.2 前端呈现

| 端 | 改动 | 呈现形态 |
|---|---|---|
| 小程序 | `types/index.ts` 增 `ReactStep` 与 `ChatMessage.steps`（顺带补上现已写入但未声明的 `thinking` 字段）；`sse.ts` 的 `SSEEvent` 联合类型加 `step`；`consult/index.tsx:319` 的 `onEvent` switch 增加 `step` 分支，按 `seq` 追加；`ChatBubble` 新增**折叠式步骤时间线** | 气泡下方「🧠 推理过程 (5 步 · 2.3s)」，展开后按顺序显示 思考 / 行动 / 观察；每步显示耗时与状态徽标；引用以 `[1][2]` 上标渲染，点击弹出来源卡片（文件名 + 片段号 + 相似度 + 原文摘录） |
| 桌面 | `static/chat.js:202` `handleSSEEvent` 增加 `step` 分支（当前 `thinking` 被 `default` 吞掉，顺手补上） | 与小程序一致的折叠时间线；桌面端无构建步骤，改完刷新即可 |

**兼容性**：`step` 是**增量事件**，老版本前端不认识会自动忽略（SSE 解析器只认 `event:`/`data:`，未知事件落到 default），不会破坏现有气泡；`end` 事件的 `reply_clean` 覆盖逻辑保持不变，但**覆盖发生在所有 step 之后**，steps 数组独立存储，不受 `reply_clean` 影响。

### 3.3 追溯信息一览（用户视角）

```
🧠 推理过程 · 5 步 · 2.34s
 ① 判断意图            question        12ms
 ② 思考  需要先查鉴别诊断…              0ms
 ③ 行动  kb_search("腹痛 腹泻 鉴别")     3ms
 ④ 观察  命中 3 篇 [1][2][3] 最高相关度 0.83   842ms
 ⑤ 思考  信息足够，可以作答             0ms
📎 引用来源
 [1] 消化系统疾病.md #12  相关度 0.83  「急性胃肠炎多由……」
 [2] 消化系统疾病.md #7   相关度 0.77  「鉴别要点：……」
```

---

## 四、知识溯源

### 4.1 前置改造（必须先做，否则溯源无从谈起）

`knowledge_base.py` 当前**丢弃了片段标识**，需三处小改（向后兼容，仅新增字段）：

1. `:438` `include` 增加 `"ids"`：`include=["documents","metadatas","distances","ids"]`
2. `:458` 结果 dict 增加：`"id"`（Chroma id）、`"chunk_index"`（来自 `metadata`）、`"metadata"`（透传，便于将来加标题/页码）
3. `:479` `search_for_consultation` 增加 `return_raw=True` 可选分支（返回 dict 列表），供 ReAct 保留引用；默认行为（返回字符串）不变，保证 `_get_knowledge_reference` 等旧调用方不受影响
4. 同样的处理应用到 `memory_store.py:214` 的返回结构（补 `id`，即 `{session_id}_t{n}` / `{session_id}_episode`）

**稳定标识**：`doc_id = {文件名}_chunk_{序号}`（`knowledge_base.py:311`，upsert 幂等）→ 天然可复现，可直接作为引用主键。

> ⚠️ 已知缺口：PDF 入库时 `_extract_text_from_pdf()`（`knowledge_base.py:212`）把所有页直接拼接，**页码信息丢失**。当前知识库全是 `.md` 文件，暂不影响；若将来加 PDF，需同时改造 `_split_text` 记录 `page`。

### 4.2 引用与答案的对应关系

两层绑定，缺一不可：

1. **引用编号下发**：Observation 阶段给每个命中片段分配本轮内序号 `[n]`，写入 `step.refs[n]`，同时把 `[n]` 标记连同片段文本一起注入终答提示词：
   ```
   【可用引用】
   [1] 消化系统疾病.md#12：急性胃肠炎多由……
   [2] 消化系统疾病.md#7：鉴别要点：……
   要求：正文中每处事实性表述后用 [n] 标注来源；不要引用未列出的编号。
   ```
2. **答案侧回校验（可选，默认开）**：终答产完后用正则抽取正文里的 `[n]`，与 `refs` 求交集：
   - 命中 → 生成 `citations` 列表，前端只展示真正被引用的来源；
   - 出现未定义编号 → 剥离该标记并记录 `step(type:"fallback", error:"citation_undefined")`；
   - 一个都没引用 → 不报错，仅标记 `citations: []`，前端不显示引用区（避免过度约束小模型）。

溯源数据表落地后，可回答"这句话来自哪个文件的第几段"。

---

## 五、数据结构、日志与持久化

### 5.1 核心数据结构（新增 `react/types.py`，dataclass 风格对齐项目现有写法）

```python
@dataclass
class Ref:            # 知识溯源引用
    n: int            # 本轮序号 [n]
    doc_id: str       # 消化系统疾病.md_chunk_12
    source: str       # 文件名
    chunk_index: int
    score: float
    quote: str        # 前 200 字摘录（用于展示，不落全文）

@dataclass
class Step:           # 一步推理
    seq: int
    type: str         # thought|action|observation|final|fallback
    text: str
    ts: str           # 系统时间 ISO8601
    elapsed_ms: int
    status: str       # ok|error|timeout|skipped
    tool: Optional[str] = None
    args: Optional[dict] = None
    refs: list[Ref] = field(default_factory=list)
    error: Optional[str] = None

@dataclass
class Trace:          # 一轮完整轨迹
    trace_id: str     # session_id-turn
    session_id: str
    turn_index: int
    steps: list[Step]
    total_ms: int
    final_citations: list[Ref]
    enabled: bool     # 是否走了 ReAct（false=降级）
```

### 5.2 配置开关（`config.py`，沿用现有 `os.environ.get(...).lower() in (...)` 风格）

| 开关 | 默认 | 说明 |
|---|---|---|
| `ENABLE_REACT` | `false` | 总开关 |
| `REACT_MAX_STEPS` | `3` | 步预算 |
| `REACT_BUDGET_MS` | `12000` | 单轮总耗时预算 |
| `REACT_TOOL_TIMEOUT_MS` | `4000` | 单工具超时 |
| `REACT_SHOW_STEPS` | `true` | 是否下发 step 事件（可只落库不展示） |
| `REACT_PERSIST` | `true` | 是否落库 |
| `REACT_CITATION_CHECK` | `true` | 引用编号回校验 |

### 5.3 持久化：新增迁移 v8（`app/db/migrations.py`，当前最新 v7）

```sql
CREATE TABLE IF NOT EXISTS session_steps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    session_id   TEXT NOT NULL,
    turn_index   INTEGER NOT NULL,
    seq          INTEGER NOT NULL,
    step_type    TEXT NOT NULL,          -- thought/action/observation/final/fallback
    status       TEXT,
    tool         TEXT,
    args_json    TEXT,                   -- 加密:含患者原话
    text         TEXT,                   -- 加密:thought/observation 内容
    refs_json    TEXT,                   -- 加密:引用片段与摘录
    elapsed_ms   INTEGER,
    created_at   TEXT NOT NULL,
    UNIQUE(session_id, turn_index, seq)
);
CREATE INDEX idx_steps_session ON session_steps(session_id, turn_index);
```

**加密决策**：steps 里含患者原话与病史片段，属敏感数据 → 三个 JSON/TEXT 列**纳入加密**（在 `crypto.py` 增 `STEP_SENSITIVE_FIELDS`，复用 `encrypt_record/decrypt_record`）；`user_id/session_id/seq/elapsed_ms/created_at` 保持明文以便统计与排序。

**写入时机**：与现有 `persist` 解耦，改为**轮次结束后一次性批量写入**（`asyncio.create_task` 后台，不阻塞 `end` 事件），失败只记日志不中断。

### 5.4 日志设计

- 新增 `logger = logging.getLogger("react")` 独立命名（与 `app.access` 同级风格），格式沿用 `main.py:48` 的 basicConfig；
- 每轮一条汇总：`react session=.. turn=.. steps=5 total_ms=2340 citations=2 fallback=false`；
- 每步一条 debug：`react step seq=2 type=action tool=kb_search elapsed_ms=842`；
- 关键事件（降级、超时、工具失败、引用未定义）用 `warning`，便于线上排查；
- `trace_id` 贯穿：`session_id-turn_index`，与前端 `step.trace_id` 一致，可用于日志 ↔ 界面 → 库的串联。

---

## 六、影响评估与回滚预案

### 6.1 对现有流程的影响

| 维度 | 影响 | 缓解 |
|---|---|---|
| **性能** | ReAct 额外 1 次 Planner LLM + N 次工具；首字延迟增加约 1 个 Planner 轮次（小模型约 1~3s） | ① 默认关闭；② 一期只在 QA 分支启用；③ `REACT_BUDGET_MS` 硬预算；④ 第 0 步复用已有检索结果不重复检索；⑤ 工具调用走 `asyncio.to_thread` 并自定义 executor，避免默认线程池串行 |
| **回答格式** | Planner 的 JSON 不进正文（走独立 `step` 事件）；终答仍经 `_VisibleStreamFilter`，`_parse_llm_response` 只作用于终答 | `end` 事件字段不变，仅新增可选字段；`reply_clean` 覆盖逻辑不动 |
| **状态机** | 采集态不启用 ReAct，`_apply_stage_transition` / `_fallback_stage_advance` 完全不受影响 | ReAct 只编排工具，不写 `stage` |
| **前端兼容** | 新增事件类型为增量；老前端忽略未知事件 | `step` 纯附加，不改 `reply/end` 语义 |
| **存储** | 新增一张表，写入后台异步 | 表不存在时自动跳过写入（try/except） |
| **提示词** | 只在 ReAct 开启时追加 Planner 协议 | 与现有 `CONSULT_JSON_REMINDER` 并存但分段，避免"简洁输出"约束把 JSON 挤掉（项目已知坑：提示词顺序是硬约束，简洁提示必须在 JSON 要求之前） |

### 6.2 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| 小模型 Planner 不输出合法 JSON | 高 | 连续 2 次失败即降级到现有流程，用户无感；记录 `fallback` 步骤便于调优提示词 |
| ReAct 循环让延迟不可接受 | 中 | 步预算 + 时间预算双闸；默认关闭；上线后按 `total_ms` 分布调参 |
| 引用编号乱标 | 中 | 回校验剥离未定义编号；不强制必须引用 |
| 加密列导致历史回放变慢 | 低 | steps 单独表 + 按需加载（点开"推理过程"时才请求 `/sessions/{id}/steps`） |

### 6.3 回滚预案（三档，可逐级）

1. **功能级**：`ENABLE_REACT=false`（或删掉 `.env` 里的该行，需重启后端）→ 立即回到现有单次 LLM 流程，**无需改任何代码**；
2. **展示级**：`REACT_SHOW_STEPS=false` → 后端仍落库但不下发 `step` 事件，前端回到现状；
3. **代码级**：`git revert` 相关提交；数据侧 `session_steps` 表是**新增表**，删除不影响任何既有表；`knowledge_base.search` 的改动是**纯新增字段**，旧调用方不受影响，回滚零成本。

> 迁移脚本按项目 v1~v7 的既有写法注册为 v8，`schema_migrations` 记录版本号；若需回退，删除 v8 记录并 DROP 新表即可。

---

## 七、实施步骤（确认后按序执行）

1. **P0 溯源前置**：`knowledge_base.py` 补 `ids`/`chunk_index`/`metadata` 与 `return_raw` 分支；`memory_store.py` 补 `id`。→ 单测：检索结果必含 `doc_id`。
2. **P1 数据结构与配置**：新增 `react/types.py` Step/Trace/Ref；`config.py` 加 7 个开关（默认关闭）。
3. **P2 执行层**：新增 `react/loop.py`（Planner 调用、工具白名单、步/时间预算、Observation 组装、引用编号下发）；`react/tools.py`（kb_search / patient_history / memory_search）。
4. **P3 接入**：`_stream_direct_qa`（`consultation.py:1015`）内插入循环，产出 `step` 事件；终答阶段插入引用约束；降级路径接通。
5. **P4 持久化**：`migrations.py` v8 建表 + `crypto.py` 加密字段 + `repositories` 写/读 + 后台批量落库；新增 `GET /sessions/{id}/steps` 接口（沿用现有路由与鉴权风格）。
6. **P5 前端**：小程序 `types` / `sse.ts` / `consult/index.tsx` / `ChatBubble`；桌面 `static/chat.js`。
7. **P6 验证**：见下方清单。

**验证清单**

- [ ] `ENABLE_REACT=false` 时，行为与改造前逐字一致（对比同一输入的 `reply_clean`）。
- [ ] `ENABLE_REACT=true` 时，前端能看到 ≥3 个步骤、`seq` 严格递增、耗时之和 ≈ `total_ms`。
- [ ] 伪造 Planner 返回非法 JSON ×2 → 自动降级，`end` 事件结构不变，用户看到正常回答。
- [ ] 引用溯源：点击 `[1]` 能定位到 `消化系统疾病.md#12`，摘录与库内片段一致。
- [ ] 超时：把 `REACT_BUDGET_MS` 设为 1ms → 立即进入终答，不卡死，SSE 仍正常 `end`。
- [ ] 落库：`session_steps` 有记录且密文；解密后 `steps` 顺序与前端一致。
- [ ] 回归：`pytest tests/` 全绿（注意环境**无 pytest-asyncio**，异步测试写 `asyncio.run`）。

---

## 八、需要你确认 / 尚缺的信息

1. **启用范围**：是否同意"一期只上直接问答分支（`_stream_direct_qa`）"？还是希望采集态（5 阶段问诊）也走 ReAct？（后者会牵动状态机，风险显著更高，建议二期）
2. **延迟容忍**：单轮可接受的最大额外延迟是多少？我按 12s 预算设计，若你能接受更少（如 6s），`REACT_MAX_STEPS` 应下调到 2。
3. **Planner 模型**：复用 `CONSULT_MODEL_NAME`（qwen2.5:7b）还是单独指定一个更强的模型？小模型做 Planner 的 JSON 遵循率是最大风险点。
4. **工具范围**：是否要我加上"医院/科室检索"或联网搜索？（当前项目**未实现**这两块，需新建，会显著扩大范围）
5. **溯源粒度**：是否要求**句子级**溯源（答案中每句话 ↔ 片段）？这需要在终答后做一次额外的对齐调用，延迟再 +1 次 LLM；当前方案是**片段级**（列出被引用的来源）。
6. **桌面端**：是否要求桌面 `static/chat.js` 也做步骤 UI？还是本期只做小程序？
7. **历史回放**：老会话（改造前）没有 steps，前端显示"暂无推理过程"是否可接受？

以上 7 点确认后，我按 §七 的步骤实现，全程保持现有代码风格（中文注释 + 环境变量开关 + 异常安全降级）。
