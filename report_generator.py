"""
报告生成模块 - 医学问诊智能体
基于问诊信息、知识库参考和历史记录生成标准医学大病历报告
"""

import asyncio
import logging
from typing import Optional

import database
import knowledge_base
import llm_client
import config

logger = logging.getLogger(__name__)

# ==================== 报告生成提示词 ====================

DEEP_ANALYSIS_PROMPT = """你是一位经验丰富的医学专家。请基于以下问诊信息，进行深度诊断分析。

## 患者信息
- 姓名：{patient_name}
- 性别：{patient_gender}
- 年龄：{patient_age}
- 主诉：{chief_complaint}

## 现病史
{present_illness}

## 既往史
{past_history}

## 个人史
{personal_history}

## 家族史
{family_history}

## 系统回顾
{system_review}

## 知识库参考信息
{knowledge_reference}

## 历史就诊记录
{history_reference}

请进行深度分析，包括：
1. 症状分析：对主要症状进行详细分析
2. 鉴别诊断：列出可能的诊断及鉴别要点（至少3个）
3. 诊断倾向：最可能的诊断及理由
4. 建议检查：建议进行哪些辅助检查
5. 处理建议：一般处理和注意事项

注意：这是AI辅助分析，不能替代医生诊断。
"""

REPORT_GENERATION_PROMPT = """你是一位专业的医学文书写作者。请根据以下问诊信息和深度分析结果，严格按照大病历格式生成完整的医学报告。

## 患者基本信息
- 姓名：{patient_name}
- 性别：{patient_gender}
- 年龄：{patient_age}

## 主诉
{chief_complaint}

## 现病史
{present_illness}

## 既往史
{past_history}

## 个人史
{personal_history}

## 家族史
{family_history}

## 系统回顾
{system_review}

## 深度诊断分析
{deep_analysis}

## 历史就诊记录
{history_reference}

请严格按照以下大病历格式生成报告：

---
# 完整病历

## 基本信息
- 姓名：
- 性别：
- 年龄：
- 就诊日期：

## 主诉


## 现病史


## 既往史


## 个人史


## 家族史


## 体格检查
（如未问及相关内容，此节不写）

## 系统回顾


## 辅助检查
（如未问及相关内容，此节不写）

## 初步诊断分析
1. 症状分析
2. 鉴别诊断
3. 诊断倾向

## 建议
1. 建议检查
2. 处理建议
3. 注意事项

---
⚠️ 免责声明

---

重要规则：
1. 问过什么写什么，没问过的内容不写
2. 绝对禁止写"未见异常"、"未检查"、"无特殊"等占位文字
3. 如果某个板块没有对应信息，直接省略该板块，不要留空标题
4. 报告内容必须基于实际问诊收集的信息，不得编造
5. 末尾必须附免责声明
"""


def generate_report(patient_data: dict, user_id: int = 0) -> str:
    """
    生成完整的医学大病历报告
    流程：
    1. 查询知识库获取参考信息
    2. 调用 LLM 做深度诊断分析
    3. 调用 LLM 生成完整大病历报告
    4. 保存患者信息到数据库
    5. 返回报告文本
    Args:
        patient_data: 患者数据字典
        user_id: 用户标识(小程序模式>0 限定历史查询作用域;=0 桌面模式兼容)
    Returns:
        完整的报告文本
    """
    logger.info(f"开始为患者 '{patient_data.get('patient_name', '未知')}' 生成报告")

    # 1. 查询知识库获取参考信息
    knowledge_reference = _get_knowledge_reference(
        patient_data.get("chief_complaint", ""),
        patient_data.get("present_illness", ""),
    )

    # 2. 获取历史就诊记录参考
    history_reference = _get_history_reference(patient_data.get("patient_name", ""), user_id=user_id)

    # 3. 深度诊断分析
    deep_analysis = _do_deep_analysis(patient_data, knowledge_reference, history_reference)

    # 4. 生成完整报告
    report = _generate_full_report(patient_data, deep_analysis, history_reference)

    # 5. 保存患者记录到数据库
    _save_to_database(patient_data, report, deep_analysis, user_id=user_id)

    logger.info("报告生成完成")
    return report


def _prepare_references(patient_data: dict, user_id: int = 0) -> tuple:
    """准备知识库参考与历史就诊参考（供流式/非流式共用，线程安全）"""
    kr = _get_knowledge_reference(
        patient_data.get("chief_complaint", ""),
        patient_data.get("present_illness", ""),
    )
    hr = _get_history_reference(patient_data.get("patient_name", ""), user_id=user_id)
    return kr, hr


async def generate_report_stream(patient_data: dict, user_id: int = 0):
    """
    流式生成完整的医学大病历报告（异步生成器）。
    1. 知识库/历史参考在后台线程准备，避免阻塞事件循环
    2. 深度诊断分析在后台线程执行（同步 LLM 调用）
    3. 报告正文逐段 yield，首字即出，显著降低等待感
    Args:
        patient_data: 患者数据字典
        user_id: 用户标识(小程序模式>0 限定历史查询作用域)
    Yields:
        报告正文文本片段（str）
    """
    logger.info(f"开始为患者 '{patient_data.get('patient_name', '未知')}' 流式生成报告")

    # 1. 参考信息（后台线程）
    knowledge_reference, history_reference = await asyncio.to_thread(
        _prepare_references, patient_data, user_id
    )

    # 2. 深度诊断分析（后台线程，同步 LLM）
    deep_analysis = await asyncio.to_thread(
        _do_deep_analysis, patient_data, knowledge_reference, history_reference
    )

    # 3. 流式生成完整报告
    prompt = REPORT_GENERATION_PROMPT.format(
        patient_name=patient_data.get("patient_name", "未知"),
        patient_gender=patient_data.get("patient_gender", "未知"),
        patient_age=patient_data.get("patient_age", "未知"),
        chief_complaint=patient_data.get("chief_complaint", "未提供"),
        present_illness=patient_data.get("present_illness", "未提供"),
        past_history=patient_data.get("past_history", "未提供"),
        personal_history=patient_data.get("personal_history", "未提供"),
        family_history=patient_data.get("family_history", "未提供"),
        system_review=patient_data.get("system_review", "未提供"),
        deep_analysis=deep_analysis,
        history_reference=history_reference,
    )

    disclaimer = """
---

⚠️ **免责声明**

本报告由AI医学问诊助手基于问诊过程中收集的信息自动生成，仅供参考，**不能替代医生的面诊和正式诊断**。

- AI分析结果可能存在偏差或遗漏，不应作为医疗决策的唯一依据
- 如有不适或症状加重，请及时前往正规医疗机构就诊
- 本系统不对因使用本报告而产生的任何后果承担责任
- 本报告中的诊断建议需要由执业医师进一步确认

**请务必咨询专业医疗人员以获得准确诊断和治疗方案。**"""

    full = []
    async for chunk in llm_client.chat_stream(
        system_prompt="你是一位专业的医学文书写作者。请严格按照大病历格式生成报告，问过什么写什么，没问过不写，禁止写占位文字。",
        user_prompt=prompt,
        temperature=0.5,
        model=config.REPORT_MODEL_NAME,
        max_tokens=config.MAX_TOKENS,
    ):
        full.append(chunk)
        yield chunk

    report = "".join(full)
    if "免责声明" not in report:
        report += disclaimer

    # 4. 保存患者记录（后台线程）
    await asyncio.to_thread(_save_to_database, patient_data, report, deep_analysis, user_id)
    logger.info("报告生成完成（流式）")


def _get_knowledge_reference(chief_complaint: str, present_illness: str = "") -> str:
    """从知识库检索与主诉和现病史相关的参考信息"""
    if not chief_complaint:
        return "无相关参考信息"

    try:
        # 组合查询：主诉 + 现病史关键信息
        query = chief_complaint
        if present_illness:
            query = f"{chief_complaint} {present_illness[:200]}"
        
        results = knowledge_base.search(query, top_k=5)
        if not results:
            return "无相关参考信息"

        references = []
        for i, result in enumerate(results, 1):
            references.append(
                f"[参考{i}] (来源: {result['source']}, 相关度: {result.get('relevance_score', 'N/A')})\n{result['text']}"
            )

        return "\n\n".join(references)

    except Exception as e:
        logger.warning(f"知识库检索失败: {e}")
        return "知识库检索失败，无参考信息"


def _get_history_reference(patient_name: str, user_id: int = 0) -> str:
    """
    获取患者历史就诊记录。
    小程序模式(user_id>0):name 需先加密后查询,返回记录需解密展示。
    桌面模式(user_id=0):保持旧逻辑,明文查询。
    """
    if not patient_name:
        return "无历史就诊记录"

    try:
        # 小程序模式:加密患者姓名后精确匹配(库中存储的是密文)
        query_name = patient_name
        if user_id and user_id > 0:
            from app.core import crypto
            query_name = crypto.encrypt_field(user_id, patient_name)

        records = database.query_patient(query_name, user_id=user_id)
        if not records:
            return "无历史就诊记录"

        # 小程序模式:解密历史记录字段用于展示
        if user_id and user_id > 0:
            from app.core import crypto
            decrypted = []
            for rec in records[:3]:
                decrypted.append(crypto.decrypt_record(user_id, rec, crypto.PATIENT_SENSITIVE_FIELDS))
            records = decrypted
        else:
            records = records[:3]

        references = []
        for i, record in enumerate(records, 1):  # 最多取3条
            references.append(
                f"[就诊记录{i}] 日期: {record.get('visit_date', '未知')}, "
                f"主诉: {record.get('chief_complaint', '未知')}, "
                f"诊断: {record.get('diagnosis', '未知')}"
            )

        return "\n".join(references)

    except Exception as e:
        logger.warning(f"历史记录查询失败: {e}")
        return "历史记录查询失败"


def _do_deep_analysis(patient_data: dict, knowledge_reference: str, history_reference: str) -> str:
    """调用 LLM 进行深度诊断分析"""
    prompt = DEEP_ANALYSIS_PROMPT.format(
        patient_name=patient_data.get("patient_name", "未知"),
        patient_gender=patient_data.get("patient_gender", "未知"),
        patient_age=patient_data.get("patient_age", "未知"),
        chief_complaint=patient_data.get("chief_complaint", "未提供"),
        present_illness=patient_data.get("present_illness", "未提供"),
        past_history=patient_data.get("past_history", "未提供"),
        personal_history=patient_data.get("personal_history", "未提供"),
        family_history=patient_data.get("family_history", "未提供"),
        system_review=patient_data.get("system_review", "未提供"),
        knowledge_reference=knowledge_reference,
        history_reference=history_reference,
    )

    try:
        analysis = llm_client.chat(
            system_prompt="你是一位经验丰富的医学专家，请基于提供的问诊信息进行专业、客观的深度诊断分析。",
            user_prompt=prompt,
            temperature=0.5,
            # 原来这里不传 model，会回退到 config.MODEL_NAME(默认 deepseek-r1:8b)：
            # 推理模型的思维链会把报告生成拖到数百秒，且与 REPORT_MODEL_NAME 不一致
            # （深度分析用 A 模型、正文用 B 模型）。统一跟随 REPORT_MODEL_NAME。
            model=config.REPORT_MODEL_NAME,
            max_tokens=config.MAX_TOKENS,
        )
        return analysis
    except Exception as e:
        logger.error(f"深度诊断分析失败: {e}")
        return "深度分析生成失败"


def _generate_full_report(patient_data: dict, deep_analysis: str, history_reference: str) -> str:
    """调用 LLM 生成完整的大病历报告"""
    prompt = REPORT_GENERATION_PROMPT.format(
        patient_name=patient_data.get("patient_name", "未知"),
        patient_gender=patient_data.get("patient_gender", "未知"),
        patient_age=patient_data.get("patient_age", "未知"),
        chief_complaint=patient_data.get("chief_complaint", "未提供"),
        present_illness=patient_data.get("present_illness", "未提供"),
        past_history=patient_data.get("past_history", "未提供"),
        personal_history=patient_data.get("personal_history", "未提供"),
        family_history=patient_data.get("family_history", "未提供"),
        system_review=patient_data.get("system_review", "未提供"),
        deep_analysis=deep_analysis,
        history_reference=history_reference,
    )

    try:
        report = llm_client.chat(
            system_prompt="你是一位专业的医学文书写作者。请严格按照大病历格式生成报告，问过什么写什么，没问过不写，禁止写占位文字。",
            user_prompt=prompt,
            temperature=0.5,
            # 同上：非流式路径也统一用 REPORT_MODEL_NAME，避免回退到推理模型
            model=config.REPORT_MODEL_NAME,
            max_tokens=config.MAX_TOKENS,
        )

        # 确保报告末尾有免责声明
        disclaimer = """
---

⚠️ **免责声明**

本报告由AI医学问诊助手基于问诊过程中收集的信息自动生成，仅供参考，**不能替代医生的面诊和正式诊断**。

- AI分析结果可能存在偏差或遗漏，不应作为医疗决策的唯一依据
- 如有不适或症状加重，请及时前往正规医疗机构就诊
- 本系统不对因使用本报告而产生的任何后果承担责任
- 本报告中的诊断建议需要由执业医师进一步确认

**请务必咨询专业医疗人员以获得准确诊断和治疗方案。**"""
        if "免责声明" not in report:
            report += disclaimer

        return report

    except Exception as e:
        logger.error(f"报告生成失败: {e}")
        return f"报告生成失败: {e}\n\n请稍后重试或联系管理员。"


def _save_to_database(patient_data: dict, report: str, deep_analysis: str, user_id: int = 0):
    """
    保存患者记录到数据库。
    小程序模式(user_id>0):走加密记录服务(record_service),敏感字段 AES 加密存储。
    桌面模式(user_id=0):走旧 database.save_patient(明文,保持向后兼容)。
    """
    try:
        # 从深度分析中提取诊断
        diagnosis = _extract_diagnosis(deep_analysis)

        if user_id and user_id > 0:
            # 小程序模式:加密保存
            from app.services import record_service
            record_id = record_service.save_patient_record(
                user_id, patient_data, report, diagnosis
            )
            if record_id:
                logger.info(f"患者记录已加密保存，ID: {record_id} user_id={user_id}")
            else:
                logger.warning("患者记录保存失败(小程序模式)")
            return

        # 桌面模式:旧明文逻辑
        save_data = {
            "patient_name": patient_data.get("patient_name", ""),
            "patient_gender": patient_data.get("patient_gender", ""),
            "patient_age": patient_data.get("patient_age", 0),
            "chief_complaint": patient_data.get("chief_complaint", ""),
            "present_illness": patient_data.get("present_illness", ""),
            "past_history": patient_data.get("past_history", ""),
            "system_review": patient_data.get("system_review", ""),
            "personal_history": patient_data.get("personal_history", ""),
            "family_history": patient_data.get("family_history", ""),
            "diagnosis": diagnosis,
            "full_report": report,
        }

        record_id = database.save_patient(save_data)
        if record_id:
            logger.info(f"患者记录已保存，ID: {record_id}")
        else:
            logger.warning("患者记录保存失败")

    except Exception as e:
        logger.error(f"保存患者记录异常: {e}")


def _extract_diagnosis(deep_analysis: str) -> str:
    """从深度分析文本中提取诊断摘要"""
    # 简单提取：找"诊断倾向"部分
    if "诊断倾向" in deep_analysis:
        parts = deep_analysis.split("诊断倾向")
        if len(parts) > 1:
            # 取诊断倾向后到下一个主要标题之前的内容
            diagnosis_text = parts[1][:300].strip()
            # 去掉开头的冒号或换行
            while diagnosis_text and diagnosis_text[0] in "：:：\n":
                diagnosis_text = diagnosis_text[1:].strip()
            return diagnosis_text[:200]  # 限制长度

    # 如果没有明确的诊断倾向标题，取前200字
    return deep_analysis[:200].strip()
