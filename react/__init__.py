"""ReAct 受控循环与推理可解释性

模块职责:
- types: 推理步骤(Step)/引用(Ref)/轨迹(Trace)的数据结构,以及句子级溯源解析
- tools : 可被 Planner 调用的工具白名单(kb_search / memory_search / patient_history / finish / ask_user)
- loop  : 受控 ReAct 循环编排(Planner -> Action -> Observation -> 终答)

设计约束(与项目既有约定一致):
1. 不新增模型标识,Planner 与终答一律复用 config.CONSULT_MODEL_NAME;
2. Observation 只由工具真实返回值产生,模型不得自造;
3. 任何异常都降级为「现有单次 LLM 流程」,不影响用户拿到回答;
4. 不改动既有实体关系与数据结构,步骤数据写入独立新表 session_steps。
"""
