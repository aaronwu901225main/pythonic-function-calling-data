# -*- coding: utf-8 -*-
import json, random
from pathlib import Path
from transformers import AutoTokenizer

MODEL_ID = "Salesforce/Llama-xLAM-2-8b-fc-r"

def render_one(ex, tok):
    messages = ex["messages"]
    tools = ex.get("tools")
    # 讓 template 幫你把 <|use_tool|>{"name":..., "arguments": {...}} 串成文字
    return tok.apply_chat_template(
        messages,
        tools=tools,
        tokenize=False,
        add_generation_prompt=False,  # 訓練資料不需要加 generation_prompt
    )

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="你的原始資料 jsonl")
    ap.add_argument("--output", required=True, help="輸出渲染後的 text.jsonl")
    ap.add_argument("--shuffle", action="store_true", help="是否隨機打散")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    inp = Path(args.input)
    out = Path(args.output)

    buf = []
    with inp.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ex = json.loads(line)
            text = render_one(ex, tok)
            buf.append({"id": ex.get("id"), "text": text})

    if args.shuffle:
        random.shuffle(buf)

    with out.open("w", encoding="utf-8") as f:
        for r in buf:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[OK] 渲染完成 → {out}（{len(buf)} 筆）")

if __name__ == "__main__":
    main()
