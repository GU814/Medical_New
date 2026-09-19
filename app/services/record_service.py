"""
记录服务 - 历史就诊记录管理(解密展示 + 加密存储)

列表只返回非敏感字段(id/visit_date/visit_count/chief_complaint_preview),
详情才解密全量。导出 PDF 在 records 路由中调用。
"""

import logging
from typing import Optional

from app.core import crypto
from app.db import repositories

logger = logging.getLogger(__name__)


def list_records(user_id: int, page: int = 1, size: int = 10,
                 start: str = None, end: str = None):
    """列表(不返回密文,仅 preview)"""
    items, total = repositories.list_records(user_id, page, size, start, end)
    return {"items": items, "total": total, "page": page, "size": size}


def get_record_detail(record_id: int, user_id: int) -> Optional[dict]:
    """详情:解密全量字段"""
    row = repositories.get_record(record_id, user_id)
    if not row:
        return None
    return crypto.decrypt_record(user_id, row, crypto.PATIENT_SENSITIVE_FIELDS)


def save_patient_record(user_id: int, patient_data: dict, report: str, diagnosis: str = "") -> int:
    """
    保存患者记录(报告生成完成时调用)。
    patient_data: ConsultationSession.get_patient_data() 返回的明文 dict
    """
    chief = patient_data.get("chief_complaint", "") or ""
    data = {
        "patient_name_enc": crypto.encrypt_field(user_id, patient_data.get("patient_name", "")),
        "patient_gender": patient_data.get("patient_gender", ""),
        "patient_age": patient_data.get("patient_age", 0),
        "chief_complaint_enc": crypto.encrypt_field(user_id, chief),
        "present_illness_enc": crypto.encrypt_field(user_id, patient_data.get("present_illness", "")),
        "past_history_enc": crypto.encrypt_field(user_id, patient_data.get("past_history", "")),
        "system_review_enc": crypto.encrypt_field(user_id, patient_data.get("system_review", "")),
        "personal_history_enc": crypto.encrypt_field(user_id, patient_data.get("personal_history", "")),
        "family_history_enc": crypto.encrypt_field(user_id, patient_data.get("family_history", "")),
        "diagnosis_enc": crypto.encrypt_field(user_id, diagnosis),
        "full_report_enc": crypto.encrypt_field(user_id, report),
        # 非密文 preview,供列表展示/搜索(前 20 字)
        "chief_complaint_preview": chief[:20] if chief else None,
    }
    return repositories.save_patient_record(user_id, data)
