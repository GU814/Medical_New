# 大模型推理调用链检查清单（问诊对话）

> 按**调用顺序**排列，每步标注：文件路径、行号、函数/类名、关键代码。
> 逐项对照时重点看「排查点」。行号基于当前工作区代码（2026-09-22）。

---

## 总览图

```
小程序输入框
  └─① consult/index.tsx  runChatTurn()
      └─② services/sse.ts  streamChat()  (Taro.request + enableChunked)
          └─③ POST /api/chat  routers/consultation.py  chat()
              └─④ session_service.get_or_create()  ← 内存缓存/DB解密恢复
                  └─⑤ consultation.py  process_user_input_stream()
                      ├─ 空输入/紧急词/去重追加/意图路由（本地规则，无LLM）
                      ├─⑥ prompt 组装: _get_system_prompt + _build_context + 检索
                      ├─⑦ llm_client.chat_stream()  (AsyncOpenAI, stream=True)
                      ├─⑧ 流式解析: _split_think_stream → _VisibleStreamFilter → reply 事件
                      ├─⑨ _parse_llm_response() → JSON抽取 → 阶段推进 → end 事件
                      └─ 阶段5: _stream_report() → report/report_done 事件
```

---

## ① 请求入口（前端）

- **文件**: `miniapp/src/pages/consult/index.tsx`
- **函数**: `runChatTurn(messageText, userMsg)`（约 L194）
- **关键代码**:
  ```ts
  const controller = streamChat({
    url: '/api/chat',
    body: { message: messageText, session_id: sid },
    onEvent: (ev) => { switch (ev.event) { ... } },   // L215 起
  });
  ```
- **事件消费**（L216-270）: `thinking` → 拼到气泡 thinking 字段；`reply` → 拼正文；
  `report` → 报告模式；`end` → **用 `endData.reply_clean` 整体覆盖气泡正文**（L253-260）。
- **排查点**:
  - 最终显示以 `end.reply_clean` 为准——若后端 `reply_clean` 异常（如为旧文本），
    界面会直接被覆盖成旧内容。怀疑"复读"时先打印 end 事件里 `reply_clean` 是多少。

## ② 前端 SSE 传输与解析

- **文件**: `miniapp/src/services/sse.ts`
- **函数**: `streamChat()`（L22）、`parseBuffer()`（L38）、`parseEventBlock()`（L115）、`arrayBufferToString()`（L131）
- **关键代码**:
  ```ts
  Taro.request({ url: fullUrl, method: 'POST', enableChunked: true,
    responseType: 'arraybuffer', header: { Authorization: `Bearer ${token}` } })
  // onChunkReceived → buffer += text → parseBuffer() 按 "\n\n" 切事件块
  ```
- **排查点**:
  - chunk 边界切坏 UTF-8 时 `arrayBufferToString` 的手动回退会出乱码；
  - 事件块以 `\n\n` 分隔，若后端一次 flush 多个事件也能正确切分，一般不是问题环节。

## ③ 后端路由入口

- **文件**: `app/routers/consultation.py`
- **函数**: `chat(req, request, user_id)`（L105-148）；SSE 格式化 `_sse()`（L23）
- **关键代码**:
  ```python
  if req.session_id:
      session = session_service.get_or_create(req.session_id, user_id, ConsultationSession)  # L122
  ...
  async def event_stream():
      session.conversation_history.append({"role": "user", "content": req.message})  # L132 ★
      session_service.persist(session)                                               # L135
      async for ev in session.process_user_input_stream(req.message):                # L138
          yield _sse(ev["event"], ev["data"])
      session_service.persist(session)                                               # L142
  ```
- **排查点**:
  - **★ L132 此处已把用户消息追加进 `conversation_history`**——这是后面
    ⑤ 步"去重保护"存在的原因，也是排查"模型收到重复消息"的第一站。

## ④ 会话恢复（状态从哪来）

- **文件**: `app/services/session_service.py`
- **函数**: `get_or_create()`（L49，内存缓存→DB 解密→新建）、`persist()`（L76，序列化+`crypto.encrypt_record` 加密落库）
- **排查点**:
  - 若 DB 恢复时 `conversation_history` 解密/反序列化失败，历史可能为空 →
    模型看不到上文，表现出"重复问同样的问题"。
    检查方法：`GET /api/sessions/{session_id}/history` 看返回的 items 是否完整。

## ⑤ 预处理与路由（consultation.py 主入口）

- **文件**: `consultation.py`
- **函数**: `process_user_input_stream(user_input)`（L940-1122）
- **关键代码与顺序**:
  1. 空输入兜底（L945-953）
  2. 紧急症状本地关键词检查 `_check_emergency()`（L426；调用点 L956）
  3. **去重保护**（L960-965）——因为③ L132 已追加过：
     ```python
     is_dup = (last is not None and last.get("role") == "user"
               and last.get("content") == user_input)
     if not is_dup:
         self.conversation_history.append({"role": "user", "content": user_input})
     ```
  4. `is_complete` → 直接结束（L968-977）
  5. 意图路由 `_classify_intent()`（L771，纯规则：问号/疑问词/咨询关键词 → "question"）；
     命中走 `_stream_direct_qa()`（L861-938），**不走 5 阶段**。
- **排查点**:
  - 截图中"之前的话也有，但是很少出现"这类输入含"吗/么"等疑问词且长度≥4 会被判为
    question → 走 `_stream_direct_qa` 分支。若发现"有时像问诊、有时像闲聊"，
    先在这里打断点确认 `intent` 是 "question" 还是 "intake"。
  - **两分支传给 LLM 的 history 都是 `self.conversation_history[-6:]`**
    （L895 / L1034），而当前用户消息**已在 history 里**（③ 追加），又作为
    `user_prompt` 再传一次 → **模型实际收到当前输入两遍**（一遍裸文本、一遍 enriched）。
    复读/答非所问时这是头号嫌疑。

## ⑥ Prompt 组装与模型参数配置

- **问诊分支**（intake）: `consultation.py` L993-1019
  ```python
  system_prompt = self._get_system_prompt()          # L993, 按阶段取 SYSTEM_PROMPT_STAGE_1~4
  # + CONSULT_BRIEF_HINT(简洁约束) + CONSULT_JSON_REMINDER(先追加到 system, L997-1001)
  context = self._build_context()                     # L1002, 已收集字段摘要(姓名/年龄/主诉...)
  enriched_input = f"{context}\n\n患者说：{user_input}"   # L1003
  # + 【历史对话记忆】(memory_reference) + 【知识库参考信息】(kb_reference)   L1004-1013
  # + 末尾再追加一次 CONSULT_JSON_REMINDER                                  L1018-1019
  ```
  - `_get_system_prompt()`: L415-424（`self.stage` → 提示词字典）
  - `_build_context()`: L1171-1206
  - 检索: `_retrieve_kb()` L796、`_retrieve_memory()` L811（异常安全，失败返回空串）
- **直接问答分支**（question）: `_stream_direct_qa()` L872-885，
  `DIRECT_QA_SYSTEM + DIRECT_QA_BRIEF_HINT`，enriched 结构同上。
- **参数来源**: `config.py`
  - `API_BASE_URL` L29（默认 `http://localhost:11434/v1`，`.env` 可覆盖）
  - `CONSULT_MODEL_NAME` L51（.env 现为 `qwen2.5:7b-instruct`）
  - `CONSULT_MAX_TOKENS` L57（.env 现为 1024）
  - `DEFAULT_TEMPERATURE` L45（0.3）、`LLM_TIMEOUT` L189（300s）、`LLM_MAX_RETRIES` L191（3）
  - `CONSULT_BRIEF_OUTPUT` L64 / `ENABLE_DIRECT_QA` L105 / `SHOW_THINKING` L111
- **排查点**:
  - `.env` 改动必须**重启后端**才生效（config 仅启动时读取）；
  - JSON 提醒同时出现在 system 尾部 + 每条用户消息尾部，prompt 噪音较大，
    模型行为异常时可先尝试去掉用户侧那份做对比。

## ⑦ 实际发起调用的封装层

- **文件**: `llm_client.py`
- **客户端单例**: `_get_client()` L24（同步 OpenAI）/ `_get_async_client()` L60（AsyncOpenAI），
  均 `base_url=config.API_BASE_URL`、显式 `proxy=None` 绕系统代理。
- **流式（问诊主链路）**: `chat_stream()` L322-406
  ```python
  model = model or config.CONSULT_MODEL_NAME       # L347
  max_tokens = max_tokens or config.CONSULT_MAX_TOKENS  # L348
  messages = [system] + history + [user]           # L351-354  ← 消息最终拼装点
  stream = await client.chat.completions.create(
      model=model, messages=messages, temperature=temperature,
      max_tokens=max_tokens, stream=True)          # L361-367
  async for chunk in stream:
      content = getattr(delta, "content", None) or ""          # L372
      reasoning = getattr(delta, "reasoning", None) or ""      # L376 新版Ollama思维链字段
      if return_raw: yield f"<think>{reasoning}</think>"; yield content  # 原样透出
  ```
  问诊链路调用点: `consultation.py` L892 / L1031，均 `return_raw=True`。
- **非流式**: `chat()` L96-157（`model`/`max_tokens` 可选参数，默认 `config.MODEL_NAME` /
  `config.MAX_TOKENS`；报告生成 `report_generator.py` 两阶段均显式传 `REPORT_MODEL_NAME`）。
  另有 `chat_json()` L160-224（低温度+代码块提取，供工具类调用）。
- **排查点**:
  - 确认实际用的模型：看后端日志 `LLM 客户端已初始化，地址: ... 模型: ...`，
    以及 Ollama 侧 `ollama ps`；
  - 流式默认参数里 `temperature` 用的是 `config.DEFAULT_TEMPERATURE`(0.3)。

## ⑧ 响应接收与结果解析（流式）

- **思维链拆分**: `llm_client._split_think_stream()` L273-319 —— 把原始流切成
  `("think", txt)` / `("content", txt)` 片段，跨 delta 的半截标签有缓存兜底。
- **可见正文过滤**: `consultation._VisibleStreamFilter` L26-193 ——
  剥离模型末尾的 JSON 结构块，只放行给用户的正文。
- **事件产出**: `consultation.py` L1040-1058
  ```python
  for kind, txt in llm_client._split_think_stream(raw, think_state):
      if kind == "think":
          if config.SHOW_THINKING: yield {"event": "thinking", "data": txt}
      else:
          visible = text_filter.feed(txt)
          if visible: yield {"event": "reply", "data": visible}
  ```
- **完整原文留存**: `full_reply.append(raw)`（L1039）→ `raw_reply`（L1060），
  供下一步 JSON 抽取用。
- **排查点**:
  - 用户看到的内容 = `reply` 事件流 + `end.reply_clean` 覆盖。
    若"界面显示与模型真实输出不一致"，比对 `raw_reply` 与 `display_text`。

## ⑨ 结构化解析与后处理

- **JSON 抽取**: `consultation._parse_llm_response()` L442-532
  匹配 ```json 代码块 → 【JSON块】中文标记 → 最后一个 `{...}`，并从显示文本中剔除。
- **患者信息更新**: `_update_patient_info()` L634（调用点 L1066-1070，包 try/except，
  脏数据不中断流程）；类型归一 `_normalize_age` L535 / `_as_bool` L555 / `_normalize_stage` L569。
- **阶段推进**: L1072-1081 —— 模型判定（`stage_complete`）优先，
  否则走确定性兜底 `_fallback_stage_advance()` L592（`ENABLE_STAGE_GUARD` 开时生效）。
- **历史追加**: L1097 `conversation_history.append({"role": "assistant", "content": display_text})`
  —— **入库的是剥离 JSON 后的显示文本**。
- **end 事件**: L1112-1117（未完成）或 `_stream_report()` L1124-1149（阶段5，
  report 逐段 + `report_done`；`_save_completed_record` L1151 落库）。
- **排查点**:
  - `display_text` 是 end 事件的 `reply_clean`，也是写入历史的内容——
    如果模型复读，复读文本会进入历史，下一轮又强化复读（自我模仿正反馈）。
    定位时可查 DB：`SELECT conversation_history FROM consultation_sessions`（需解密）。

## ⑩ 异常与兜底处理

| 层 | 位置 | 行为 |
|---|---|---|
| `llm_client.chat` | L146-157 | 失败重试 `LLM_MAX_RETRIES`(3) 次，间隔 `attempt*2`s；最终失败返回固定兜底文案（连接类→"无法连接 AI 服务"） |
| `llm_client.chat_stream` | L395-406 | 同上，兜底文案以 yield 透出 |
| 流式无正文 | L391-392 | `emitted_any=False` 时 yield "（模型未返回可见内容...）" |
| `_update_patient_info` | consultation.py L1067-1070 | try/except 吞掉类型异常，仅 warning |
| 报告生成 | `_stream_report` L1141-1149 | 失败 yield "⚠️ 报告生成过程中出现错误" + `report_done` |
| 路由层 | routers/consultation.py L143-145 | 整个 event_stream 包 try/except → `event: error` |
| 前端 | sse.ts L78-82, L96-100 | `fail` 回调 + enableChunked 不支持提示 |

- **排查点**: 兜底文案本身会被当作"assistant 回复"写进历史并展示——
  如果用户截图里的复读文本其实是某次兜底/旧缓存，看后端日志的 warning/error 即可分辨。

---

## 针对截图症状（同一句回复连续出现）的优先排查顺序

1. **⑤ 当前用户消息在 messages 里出现两遍**（history 末尾一份 + user_prompt 一份，
   consultation.py L132+L1034/L895）——先写个小脚本打印最终 `messages` 看是否如此。
2. **⑨ 复读文本已写入 conversation_history**，模型模仿自身历史形成正反馈——
   解密查看该 session 的 history，确认复读句是否在 assistant 历史里。
3. **⑤ 意图路由抖动**：同样的输入有时 question 走 QA 分支（无阶段推进、不更新采集字段），
   有时 intake 走问诊分支，两套提示词切换也会显得"答非所问"。
4. **① end 事件 `reply_clean` 覆盖**：确认覆盖用的字符串与本次流式内容一致。
5. **④ DB 恢复的历史是否完整**（解密失败→空历史→模型失忆）。
