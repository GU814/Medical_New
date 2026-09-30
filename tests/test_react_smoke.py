"""
ReAct 端到端冒烟(手动执行,不纳入 pytest 默认回归):

  .venv/Scripts/python.exe tests/test_react_smoke.py

跑真实 Ollama(qwen2.5:7b-instruct),走完整链路:
  直接问答 -> ReAct 循环 -> step 事件 -> session_steps 落库 -> GET steps 接口返回值
并打印可人工核对的关键指标,用于确认:
- 步骤类型齐全且 seq 递增;
- 引用带稳定片段标识(doc_id);
- 终答带句子级溯源;
- 历史回放接口不再返回空态(有步骤 or 有 missing_reason)。
"""
import asyncio
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 独立临时库,避免污染开发库数据
os.environ.setdefault("DB_PATH", os.path.join(ROOT, "data", "_react_smoke.db"))
# 知识库指向真实开发库:冒烟的意义就是验证线上那份索引,
# 用独立副本就看不到「新导入的文档是否真的能被检索到」。
# 若多进程争用报 "Could not connect to tenant default_tenant",
# kb_search 内部有「重建客户端重试」兜底;此处也允许外部 CHROMA_PATH 覆盖。
os.environ.setdefault("CHROMA_PATH", os.path.join(ROOT, "data", "chroma_db"))

import config  # noqa: E402
import consultation  # noqa: E402
import knowledge_base  # noqa: E402
import llm_client  # noqa: E402
from app.db import migrations  # noqa: E402
from app.db import repositories  # noqa: E402
from app.services import session_service  # noqa: E402

QUESTION = "发烧 38.5 度可以吃对乙酰氨基酚吗？"
SMOKE_OPENID = "react-smoke-openid"
# 自播种用的种子文档(8 个片段,秒级完成,足以验证引用与句子级溯源)
SEED_FILE = os.path.join(ROOT, "data", "knowledge", "example.md")


async def main():
    print("=" * 60)
    print(f"模型: CONSULT_MODEL_NAME={config.CONSULT_MODEL_NAME}  "
          f"预算={config.REACT_BUDGET_MS}ms  步数上限={config.REACT_MAX_STEPS}")
    print(f"ReAct 开关: ENABLE_REACT={config.ENABLE_REACT}  "
          f"下发步骤={config.REACT_SHOW_STEPS}  落库={config.REACT_PERSIST}")
    print("=" * 60)

    # 临时库:先删掉上一轮残留再建表(删库必须在建连接之前,否则 sqlite 会报莫名的 FK 错误)
    if os.environ.get("DB_PATH", "").endswith("_react_smoke.db"):
        try:
            os.remove(os.environ["DB_PATH"])
        except OSError:
            pass
    migrations.run_migrations()

    # 自播种:独立 Chroma 目录可能为空(首次复制/清空),此时就地导入种子文档,
    # 保证「引用带 doc_id」「句子级溯源」两项断言始终有真实片段可挂。
    knowledge_base.init_knowledge_base()
    if knowledge_base.get_collection().count() == 0 and os.path.exists(SEED_FILE):
        knowledge_base.add_documents(os.path.join(ROOT, "data", "knowledge"))
        print(f"[知识库] 独立目录为空,已自播种,当前 "
              f"{knowledge_base.get_collection().count()} 个片段")

    # 走小程序真实路径:先建一个真用户(user_id>0),
    # 桌面模式的 user_id=0 会在加密层建 DEK 时撞 users 外键,不在本次验证范围。
    uid, is_new = repositories.upsert_user_by_openid(SMOKE_OPENID)
    print(f"\n[用户] user_id={uid} (新建={is_new})")

    s = consultation.ConsultationSession(session_id="smoke-session")
    s.user_id = uid

    t0 = time.perf_counter()
    events = []
    async for ev in s.process_user_input_stream(QUESTION):
        events.append(ev)
    cost = (time.perf_counter() - t0) * 1000

    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]
    replies = [e["data"] for e in events if e["event"] == "reply"]
    ends = [json.loads(e["data"]) for e in events if e["event"] == "end"]

    print(f"\n[耗时] 整轮 {cost:.0f}ms  step 事件 {len(steps)} 个  "
          f"reply 片段 {len(replies)} 个")

    print("\n[步骤序列]")
    for st in steps:
        cost_ms = f"{st.get('elapsed_ms', 0)}ms"
        print(f"  #{st['seq']} {st['type']:<12} {cost_ms:>7}  "
              f"{(st.get('text') or '')[:48]}")

    if os.environ.get("REACT_SMOKE_DEBUG"):
        for st in steps:
            print("[DEBUG]", json.dumps(st, ensure_ascii=False)[:900])

    types = [x["type"] for x in steps]
    seqs = [x["seq"] for x in steps]
    print("\n[断言]")
    print(f"  seq 递增且从 0 开始: {seqs == sorted(seqs) and seqs and seqs[0] == 0}")
    print(f"  含思考/动作/观察/终答: "
          f"{set(['thought', 'action', 'observation', 'final']) & set(types) == {'thought', 'action', 'observation', 'final'}}")

    final = next((x for x in reversed(steps) if x["type"] == "final"), None)
    # 只看终答引用池:记忆/就诊记录属「个人史」,不占 [n](B 期防幻觉约定),
    # 混在「全步骤 refs」里统计会把结论带偏。
    pool = [r for r in ((final or {}).get("refs") or []) if r.get("kind") == "kb"]
    print(f"  终答引用池(去重后): {len(pool)} 条  "
          f"带稳定片段标识: {bool(pool) and all(r.get('doc_id') for r in pool)}")
    print(f"    {[r.get('doc_id') for r in pool] or '空'}")
    ids = [r.get("doc_id") for r in pool]
    print(f"  引用池无重复片段: {len(ids) == len(set(ids))}")

    sentences = (final or {}).get("sentences") or []
    cited = [x for x in sentences if x.get("cited")]
    inferred = [x for x in sentences if x.get("inferred")]
    print(f"  句子级溯源: {len(sentences)} 句 = 显式引用 {len(cited)} 句 "
          f"+ 系统推断 {len(inferred)} 句 + 无来源 {len(sentences) - len(cited) - len(inferred)} 句")

    print(f"  终答非空: {bool(''.join(replies).strip())}")
    print(f"  end 事件带 react_enabled: "
          f"{bool(ends) and ends[-1].get('react_enabled') is True}")

    # 等后台落库任务跑完
    await asyncio.sleep(1.0)
    api = session_service.get_session_steps("smoke-session", uid)
    print("\n[历史回放接口 GET /sessions/{id}/steps]")
    print(f"  turns: {len(api['turns'])}  步骤总数: "
          f"{sum(len(t['steps']) for t in api['turns'])}  "
          f"missing_reason: {api.get('missing_reason')}")
    for t in api["turns"]:
        print(f"  第 {t['turn_index']} 轮 · {len(t['steps'])} 步 · "
              f"首步类型={t['steps'][0]['type'] if t['steps'] else '无'}")
        for st in t["steps"]:
            sents = st.get("sentences") or []
            nref = len(st.get("refs") or [])
            ok = f"   ↳ #{st['seq']} {st['type']} · "
            ok += f"{len(sents)} 句溯源" if sents else str(st.get("text", ""))[:32]
            if nref:
                ok += f"  · 引用 {nref} 条: " + \
                      ",".join(r.get("doc_id", "") for r in st["refs"])
            print(ok)

    total = sum(len(t["steps"]) for t in api["turns"])
    print("\n[回放断言]")
    print(f"  回放不为空态(有步骤或有 missing_reason): "
          f"{total > 0 or bool(api.get('missing_reason'))}")
    print(f"  回放步骤数与流式 step 事件一致: {total == len(steps)}")

    # ---------------- B/C 期:零命中防幻觉与范围边界 ----------------
    print("\n[零命中兜底验证]")
    # 只挡 search_for_consultation 不够:kb_search 现在走宽召回(直连 collection),
    # 漏掉它这条兜底验证会穿透到真实知识库,验出一个「假通过」。
    from react import tools as react_tools  # noqa: PLC0415
    _orig_search = knowledge_base.search_for_consultation
    _orig_wide = react_tools._wide_consultation_search
    knowledge_base.search_for_consultation = lambda **kw: []
    react_tools._wide_consultation_search = lambda q, n: []
    try:
        for question, expect in (
            (QUESTION, "no_evidence"),
            ("帮我写一首关于春天的诗", "out_of_scope"),
        ):
            s2 = consultation.ConsultationSession(session_id="smoke-session")
            s2.user_id = uid
            events2 = []
            async for ev in s2._stream_direct_qa(question, ""):
                events2.append(ev)
            reply2 = "".join(e["data"] for e in events2 if e["event"] == "reply")
            steps2 = [json.loads(e["data"]) for e in events2 if e["event"] == "step"]
            if expect == "no_evidence":
                hit = config.REACT_NO_EVIDENCE_REPLY in reply2
                detail = f"reply={reply2.strip()[:50]!r}"
            else:
                hit = "超出" in reply2 and "就医" in reply2
                detail = f"reply={reply2.strip()[:50]!r}"
            flagged = any(
                x["type"] == "final" and x.get("error") == expect for x in steps2
            )
            print(f"  [{expect}] 命中兜底话术={hit}  步骤标记={flagged}  {detail}")
    finally:
        knowledge_base.search_for_consultation = _orig_search
        react_tools._wide_consultation_search = _orig_wide


if __name__ == "__main__":
    asyncio.run(main())
