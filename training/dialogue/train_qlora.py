"""
对话/问诊模型微调 - QLoRA（8GB 显存友好）

基座：Qwen2.5-3B-Instruct，4bit 量化 + LoRA，单卡 8GB 可跑
输入：train.jsonl（messages 格式，见 prepare_data.py）
产出：./med-lora（LoRA 适配器权重）

用法：
  python train_qlora.py
环境变量（可选）：
  BASE_MODEL  默认 Qwen/Qwen2.5-3B-Instruct
  TRAIN_DATA  默认 train.jsonl
  LORA_OUT    默认 ./med-lora
"""
import os
import json
import logging
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_qlora")

BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
DATA_PATH = os.environ.get("TRAIN_DATA", "train.jsonl")
OUTPUT_DIR = os.environ.get("LORA_OUT", "./med-lora")

# 4bit 量化，把 3B 模型压进 8GB 显存
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
)

tok = AutoTokenizer.from_pretrained(BASE_MODEL)
tok.pad_token = tok.pad_token or tok.eos_token

logger.info("加载基座模型（4bit）: %s", BASE_MODEL)
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
model = prepare_model_for_kbit_training(model)
model.config.use_cache = False  # 训练时关闭 cache

# LoRA 注入所有线性层，覆盖 attention + MLP
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()


def tok_fn(ex):
    text = tok.apply_chat_template(
        ex["messages"], tokenize=False, add_generation_prompt=False
    )
    out = tok(text, truncation=True, max_length=1024, padding="max_length")
    out["labels"] = out["input_ids"].copy()
    return out


logger.info("加载数据集: %s", DATA_PATH)
ds = load_dataset("json", data_files=DATA_PATH)["train"]
ds = ds.map(tok_fn, remove_columns=["messages"])

args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=1,        # 8GB 下保持 1
    gradient_accumulation_steps=8,        # 等效 batch=8
    num_train_epochs=3,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    save_strategy="epoch",
    gradient_checkpointing=True,
    optim="paged_adamw_8bit",
    report_to=[],
)

trainer = Trainer(
    model=model,
    train_dataset=ds,
    args=args,
    data_collator=DataCollatorForLanguageModeling(tok, mlm=False),
)

logger.info("开始训练...")
trainer.train()
model.save_pretrained(OUTPUT_DIR)
tok.save_pretrained(OUTPUT_DIR)
logger.info("LoRA 训练完成，保存至 %s", OUTPUT_DIR)
