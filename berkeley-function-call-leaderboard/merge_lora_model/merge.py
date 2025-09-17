import os
import torch
from transformers import AutoModelForCausalLM
from peft import PeftModel

# 基礎模型路徑
BASE_MODEL = "Llama-xLAM-2-8b-fc-r"
# LoRA checkpoints 總資料夾
LORA_DIR = "xlam_lora_out_AA"   # 裡面應該有 checkpoint-1000, checkpoint-2000, ...
# 輸出完整模型的路徑
OUTPUT_DIR = "Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# 掃描資料夾內所有 checkpoint
for ckpt_name in sorted(os.listdir(LORA_DIR)):
    ckpt_path = os.path.join(LORA_DIR, ckpt_name)
    # 跳過不是資料夾的東西，或是明顯不是 checkpoint 的目錄
    if not os.path.isdir(ckpt_path):
        continue
    if ckpt_name.startswith(".") or "checkpoint" not in ckpt_name:
        continue

    print(f"正在處理 {ckpt_name}...")

    # 每次都重新載入 base model，避免 LoRA 疊加污染
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
    print(f"已儲存至 {save_path}")
