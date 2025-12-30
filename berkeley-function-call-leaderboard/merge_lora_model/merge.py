import os
import shutil
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import argparse


# 基礎模型路徑可由參數指定
DEFAULT_BASE_MODEL = "Llama-xLAM-2-8b-fc-r"

# 解析命令列參數

parser = argparse.ArgumentParser(description="Merge LoRA checkpoints into full models.")
parser.add_argument('--BASE_MODEL', type=str, default=DEFAULT_BASE_MODEL, help='基礎模型路徑')
parser.add_argument('--LORA_DIR', type=str, required=True, help='LoRA checkpoints 資料夾')
parser.add_argument('--OUTPUT_DIR', type=str, required=True, help='輸出完整模型的資料夾')
args = parser.parse_args()


BASE_MODEL = args.BASE_MODEL
LORA_DIR = args.LORA_DIR
OUTPUT_DIR = args.OUTPUT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 載入 tokenizer（只要載一次）
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

# 掃描資料夾內所有 checkpoint
for ckpt_name in sorted(os.listdir(LORA_DIR)):
    ckpt_path = os.path.join(LORA_DIR, ckpt_name)
    if not os.path.isdir(ckpt_path):
        continue
    if ckpt_name.startswith(".") or "checkpoint" not in ckpt_name:
        continue

    print(f"正在處理 {ckpt_name}...")

    # 每次都重新載入 base model，避免 LoRA 疊加
    base_model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, torch_dtype=torch.float16)

    # 載入 LoRA
    model = PeftModel.from_pretrained(base_model, ckpt_path)

    # 合併並卸載 LoRA
    merged_model = model.merge_and_unload()

    # 確保用 float16 儲存
    merged_model = merged_model.to(torch.float16)

    # 存成完整模型
    save_path = os.path.join(OUTPUT_DIR, ckpt_name + "_merged")
    merged_model.save_pretrained(save_path)
    tokenizer.save_pretrained(save_path)  # 把 tokenizer 一起存

    print(f"已儲存至 {save_path}")
