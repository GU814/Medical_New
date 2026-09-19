"""历史就诊记录路由 - 列表/详情/报告/PDF 导出"""

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.core.deps import get_current_user
from app.services import record_service

router = APIRouter(prefix="/api/records", tags=["历史记录"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_records(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    start: str = Query(None, description="起始日期 YYYY-MM-DD"),
    end: str = Query(None, description="结束日期 YYYY-MM-DD"),
    user_id: int = Depends(get_current_user),
):
    """历史记录列表(仅 preview,不含密文明细)"""
    return record_service.list_records(user_id, page=page, size=size, start=start, end=end)


@router.get("/{record_id}")
async def get_record(record_id: int, user_id: int = Depends(get_current_user)):
    """记录详情(解密全量字段)"""
    detail = record_service.get_record_detail(record_id, user_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在或无权访问")
    return detail


@router.get("/{record_id}/report")
async def get_report(record_id: int, user_id: int = Depends(get_current_user)):
    """获取报告全文(解密)"""
    detail = record_service.get_record_detail(record_id, user_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在或无权访问")
    return {"report": detail.get("full_report", ""), "visit_date": detail.get("visit_date")}


@router.get("/{record_id}/export")
async def export_record(
    record_id: int,
    format: str = Query("pdf"),
    user_id: int = Depends(get_current_user),
):
    """导出记录为 PDF(含完整大病历 + 免责声明)"""
    if format != "pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="暂仅支持 pdf 格式")

    detail = record_service.get_record_detail(record_id, user_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在或无权访问")

    try:
        pdf_bytes = _render_pdf(detail)
        filename = f"medical_report_{record_id}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error(f"PDF 导出失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="PDF 导出失败")


def _render_pdf(detail: dict) -> bytes:
    """用 reportlab 渲染 PDF(中文需注册字体,这里用 reportlab 内置 cid 支持)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # 注册中文字体(reportlab 内置 STSong-Light)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
    except Exception:
        font_name = "Helvetica"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CnTitle", parent=styles["Title"], fontName=font_name, fontSize=18)
    body_style = ParagraphStyle("CnBody", parent=styles["Normal"], fontName=font_name, fontSize=11, leading=18)

    story = [
        Paragraph("医学问诊报告", title_style),
        Spacer(1, 12),
    ]

    # 基本信息
    info = (
        f"姓名:{detail.get('patient_name', '未知')}　"
        f"性别:{detail.get('patient_gender', '未知')}　"
        f"年龄:{detail.get('patient_age', '未知')}"
    )
    story.append(Paragraph(info, body_style))
    story.append(Paragraph(f"就诊日期:{detail.get('visit_date', '未知')}", body_style))
    story.append(Spacer(1, 12))

    # 报告正文(按行渲染)
    report = detail.get("full_report", "")
    for line in report.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue
        # 转义 XML 特殊字符
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe, body_style))

    doc.build(story)
    return buf.getvalue()
