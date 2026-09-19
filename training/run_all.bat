@echo off
REM ============================================================
REM  自训模型训练一键引导（8GB 显存：3B 对话 + bge-small 嵌入）
REM  分步执行，遇到 [pause] 会停下来等你确认/人工校正
REM ============================================================
cd /d %~dp0

REM ---- 建独立 venv（别用项目 .venv）----
if not exist venv (
    echo [0] 创建训练专用虚拟环境 venv ...
    python -m venv venv
)
call venv\Scripts\activate

echo [1] 安装依赖（对话 + 嵌入）...
pip install -r dialogue\requirements.txt
pip install -r embedding\requirements.txt

echo.
echo ============================================================
echo [2] 生成对话训练数据（抽取 data/knowledge + 大模型生成）
echo ============================================================
python dialogue\prepare_data.py
echo.
echo >>> 请人工校正 dialogue\data_generated\REVIEW_me.jsonl
echo >>> 删掉不合格样本、修正医生提问，满意后执行下面这行：
echo     copy dialogue\data_generated\REVIEW_me.jsonl dialogue\train.jsonl
echo.
pause

echo.
echo ============================================================
echo [3] 微调对话模型 QLoRA（约 8GB 显存，耗时较长）
echo ============================================================
python dialogue\train_qlora.py

echo.
echo ============================================================
echo [4] 合并 LoRA -> HF 格式
echo ============================================================
python dialogue\merge_export.py
echo.
echo >>> 需手动用 llama.cpp 转 GGUF + 量化（见 README/merge_export 末尾提示），
echo >>> 得到 med-q4_k_m.gguf 放到 dialogue\ 后执行：
echo     ollama create med-consult -f dialogue\Modelfile
echo.
pause

echo.
echo ============================================================
echo [5] 生成嵌入训练数据 + 微调嵌入模型
echo ============================================================
python embedding\prepare_embed_data.py
python embedding\train_embed.py

echo.
echo ============================================================
echo [6] 启动自定义嵌入服务（http://127.0.0.1:8002/v1）
echo ============================================================
start "embed-server" /b python embedding\serve_embed.py
echo 嵌入服务已在后台启动。
echo.
echo >>> 最后按 INTEGRATE.md 修改 config.py：
echo     MODEL_NAME/CONSULT_MODEL_NAME/REPORT_MODEL_NAME = med-consult
echo     EMBEDDING_MODEL = med-embed
echo     EMBEDDING_API_BASE_URL = http://127.0.0.1:8002/v1
echo     EMBEDDING_DIMENSION = 512
echo >>> 并删除 data\chroma_db 让项目重建索引，再启动 medical_bot。
echo.
pause
echo 完成。
