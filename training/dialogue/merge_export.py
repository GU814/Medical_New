"""
合并 LoRA 权重回基座，保存为 HuggingFace 格式
（之后用 llama.cpp 转 GGUF + 量化，才能被 Ollama 加载）

输入：./med-lora（train_qlora.py 产出）
产出：./med-merged（合并后的 HF 模型）

用法：
  python merge_export.py
环境变量：BASE_MODEL / LORA_OUT / MERGED_OUT
"""
import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
LORA_OUT = os.environ.get("LORA_OUT", "./med-lora")
MERGED_OUT = os.environ.get("MERGED_OUT", "./med-merged")

print(f"加载基座 {BASE_MODEL}（fp16, CPU）...")
base = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL, torch_dtype=torch.float16, device_map="cpu",
    trust_remote_code=True,
)
base = PeftModel.from_pretrained(base, LORA_OUT)
print("合并 LoRA -> 基座 ...")
base = base.merge_and_unload()

tok = AutoTokenizer.from_pretrained(BASE_MODEL)
base.save_pretrained(MERGED_OUT)
tok.save_pretrained(MERGED_OUT)
print(f"已合并保存至: {MERGED_OUT}")
print("\n下一步（需先 clone llama.cpp）：")
print(f"  python llama.cpp/convert_hf_to_gguf.py {MERGED_OUT} --outfile med-f16.gguf")
print(f"  ./llama.cpp/quantize med-f16.gguf med-q4_k_m.gguf q4_k_m")
print(f"  把 med-q4_k_m.gguf 放到本目录，然后: ollama create med-consult -f Modelfile")
