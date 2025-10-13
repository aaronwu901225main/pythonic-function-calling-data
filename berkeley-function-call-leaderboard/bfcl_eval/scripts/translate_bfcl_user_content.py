#!/usr/bin/env python3
"""
translate_bfcl_user_content.py

說明:
- 讀取指定 JSON 檔（預期為 BFCL 多物件或單物件皆可），只翻譯所有 {"role": "user"} 節點的 content 字串為繁體中文（臺灣）。
- 其他欄位維持原樣。
- 預設輸出為與輸入檔同資料夾、檔名在第一個「.json」之前插入「_zh_」。
  例如: BFCL_v4_multi_turn_base.json -> BFCL_v4_zh_multi_turn_base.json

環境變數:
- OPENAI_API_KEY: 必填
- OPENAI_TRANSLATE_MODEL: 預設 "gpt-4o-mini"

使用:
    python translate_bfcl_user_content.py --input <path/to/file.json> [--output <out.json>]

注意:
- 本工具僅翻譯 role=user 的 content；不會動其他欄位或非 user 的訊息。
- 若輸入檔包含多個 JSON 物件（逐個以 { ... } 串在一起），也會逐個解析與翻譯並回寫成相同格式（物件間以換行分隔）。
"""

from __future__ import annotations
import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from openai import OpenAI
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "OpenAI 套件未安裝。請先安裝: pip install openai>=1.0.0\n"
        f"詳細錯誤: {e}"
    )


def split_concatenated_json(text: str) -> List[str]:
    """將可能連續的多個 JSON 物件分割成多段字串。保留原順序。"""
    parts: List[str] = []
    brace = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if brace == 0:
                start = i
            brace += 1
        elif ch == '}':
            brace -= 1
            if brace == 0 and start is not None:
                parts.append(text[start:i+1])
                start = None
    if not parts:  # 可能是單一 JSON 陣列或物件
        stripped = text.strip()
        if stripped:
            parts = [stripped]
    return parts


def walk_and_translate(obj: Any, translate_fn) -> Any:
    """深度走訪結構，翻譯所有 role=user 的 content 字串。"""
    if isinstance(obj, dict):
        # 檢測是否為一個訊息物件
        if obj.get("role") == "user" and isinstance(obj.get("content"), str):
            text = obj["content"]
            obj = {**obj}  # 淺拷貝
            obj["content"] = translate_fn(text)
            return obj
        # 一般 dict 遞迴
        return {k: walk_and_translate(v, translate_fn) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [walk_and_translate(v, translate_fn) for v in obj]
    else:
        return obj


def make_translator(client: "OpenAI", model: str):
    def _translate(text: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional translator to Traditional Chinese (Taiwan). "
                        "Translate precisely and naturally. Preserve quoted filenames and commands. "
                        "Do not add explanations; only output the translation."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Translate into zh-TW. Output only the translation.\n\n{text}",
                },
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    return _translate


def default_output_path(input_path: Path) -> Path:
    name = input_path.name
    if name.lower().endswith('.json'):
        base = name[:-5]
        out_name = base.replace('BFCL_v4_', 'BFCL_v4_zh_', 1)
        # 若沒有 BFCL_v4_ 前綴，就在第一個 .json 前插入 _zh
        if out_name == base:
            out_name = f"{base}_zh"
        out_name += '.json'
    else:
        out_name = name + '._zh.json'
    return input_path.with_name(out_name)


def main():
    parser = argparse.ArgumentParser(description="Translate role=user content in BFCL JSON to zh-TW")
    parser.add_argument(
        "--input",
        required=True,
        nargs='+',
        type=str,
        help="One or more input JSON file paths",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file path (optional, only valid when a single input is provided)",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("請先設定環境變數 OPENAI_API_KEY")

    model = os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini")
    client = OpenAI()
    translator = make_translator(client, model)

    multiple_inputs = len(args.input) > 1
    if multiple_inputs and args.output:
        raise SystemExit("多檔輸入時不可同時指定 --output，將自動為每個檔案產生對應 zh 檔名。")

    for input_path_str in args.input:
        in_path = Path(input_path_str)
        if not in_path.exists():
            raise SystemExit(f"找不到輸入檔: {in_path}")

        text = in_path.read_text(encoding="utf-8")
        parts = split_concatenated_json(text)

        translated_chunks: List[str] = []
        for chunk in parts:
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                # 也許是 json lines 或陣列，一律再嘗試
                try:
                    data = json.loads(chunk.strip(','))
                except Exception as e:
                    raise SystemExit(f"JSON 解析失敗: {e}\n片段:\n{chunk[:200]}...")
            data_zh = walk_and_translate(data, translator)
            translated_chunks.append(json.dumps(data_zh, ensure_ascii=False, indent=4))

        out_path = Path(args.output) if (args.output and not multiple_inputs) else default_output_path(in_path)
        out_path.write_text("\n".join(translated_chunks) + "\n", encoding="utf-8")
        print(f"已輸出: {out_path}")


if __name__ == "__main__":
    main()
