"""
数据库初始化脚本 - 医学问诊智能体
创建数据库表，可选插入测试数据
"""

import logging
import sys
import os

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def init_with_test_data():
    """初始化数据库并插入测试数据"""
    # 创建表
    database.init_database()
    logger.info("数据库表已创建")

    # 插入测试数据
    test_patient = {
        "patient_name": "张三",
        "patient_gender": "男",
        "patient_age": 35,
        "chief_complaint": "反复头痛3天",
        "present_illness": "患者3天前无明显诱因出现双侧颞部胀痛，呈持续性，伴恶心，无呕吐，无发热。疼痛在下午加重，休息后可稍缓解。未自行服药。",
        "past_history": "高血压病史2年，规律服用氨氯地平，血压控制尚可。否认糖尿病、心脏病史。",
        "personal_history": "吸烟10年，每日约10支。偶有饮酒。",
        "family_history": "父亲有高血压病史。",
        "system_review": "神经系统：无头晕、无意识障碍。心血管系统：无心悸、胸闷。",
        "diagnosis": "紧张型头痛可能，需排除高血压相关头痛",
        "full_report": "（测试数据 - 完整报告略）",
    }

    record_id = database.save_patient(test_patient)
    if record_id:
        logger.info(f"测试数据已插入，ID: {record_id}")
    else:
        logger.warning("测试数据插入失败")

    # 插入第二条测试数据（同一患者复诊）
    test_patient_2 = {
        "patient_name": "张三",
        "patient_gender": "男",
        "patient_age": 35,
        "chief_complaint": "头痛复诊，症状有所缓解",
        "present_illness": "患者上次就诊后按建议调整降压药物剂量，头痛较前减轻。目前偶有轻微头痛，无恶心。",
        "past_history": "高血压病史2年，规律服药。",
        "personal_history": "吸烟10年，每日约10支。偶有饮酒。",
        "family_history": "父亲有高血压病史。",
        "system_review": "神经系统：无新发症状。",
        "diagnosis": "高血压相关头痛，较前好转",
        "full_report": "（测试数据 - 完整报告略）",
    }

    record_id_2 = database.save_patient(test_patient_2)
    if record_id_2:
        logger.info(f"第二条测试数据已插入，ID: {record_id_2}")

    logger.info("数据库初始化完成！")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="医学问诊智能体 - 数据库初始化")
    parser.add_argument("--with-test-data", action="store_true", help="插入测试数据")
    args = parser.parse_args()

    if args.with_test_data:
        init_with_test_data()
    else:
        database.init_database()
        logger.info("数据库表已创建（未插入测试数据，使用 --with-test-data 参数插入测试数据）")
