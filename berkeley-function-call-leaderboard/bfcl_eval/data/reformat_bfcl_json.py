#!/usr/bin/env python3
"""
reformat_bfcl_json.py

- 將 BFCL 資料檔（多物件串接、JSONL、或是單一 JSON 陣列/物件）正規化為 JSONL：一行一個 JSON 物件。
- 可批次處理多個檔案。
- 預設輸出會在同資料夾另寫一個 *_jsonl.json 檔，不覆寫原檔。可加 --inplace 覆寫。

使用：
  python reformat_bfcl_json.py --input <file1.json> [file2.json ...] [--inplace]

說明：
- 支援下列輸入格式：
  1) 正常 JSONL（每行一個物件）
  2) 多個 JSON 物件以空白或換行直接串接
  3) 一個 JSON 陣列，或單一 JSON 物件
- 會自動解析並輸出每行一個完整 JSON 物件。
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import List, Any


def decode_concatenated_json(text: str) -> List[Any]:
    """將一段可能包含多個 JSON 值（物件/陣列/字串/數字）的文字解析為值列表。
    類似 jsonlines 但更寬鬆：允許多個 JSON 彼此相連，中間僅由空白/換行分隔。
    """
    decoder = json.JSONDecoder()
    idx = 0
    n = len(text)
    values: List[Any] = []

    while True:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        val, next_idx = decoder.raw_decode(text, idx)
        values.append(val)
        idx = next_idx
    return values


def normalize_to_objects(values: List[Any]) -> List[dict]:
    """將解析到的 JSON 值統一轉成物件（dict）列表。
    - 若值是 dict，直接加入。
    - 若值是 list，且裡面元素是 dict，逐一加入。
    - 若值是其他型別（字串、數字等），包成 {"value": <原值>} 以免丟失。
    """
    objs: List[dict] = []
    for v in values:
        if isinstance(v, dict):
            objs.append(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    objs.append(item)
                else:
                    objs.append({"value": item})
        else:
            objs.append({"value": v})
    return objs


def write_jsonl(path: Path, objs: List[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for o in objs:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser(description="Reformat BFCL JSON into JSONL (one object per line)")
    p.add_argument("--input", nargs="+", required=True, help="One or more input JSON files")
    p.add_argument("--inplace", action="store_true", help="Overwrite the input file in-place")
    args = p.parse_args()

    for in_path_str in args.input:
        in_path = Path(in_path_str)
        if not in_path.exists():
            print(f"[skip] not found: {in_path}")
            continue
        text = in_path.read_text(encoding="utf-8")
        try:
            values = decode_concatenated_json(text)
        except json.JSONDecodeError as e:
            print(f"[error] JSON decode failed for {in_path}: {e}")
            continue
        objs = normalize_to_objects(values)
        if args.inplace:
            out_path = in_path
        else:
            out_path = in_path.with_name(in_path.stem + "_jsonl" + in_path.suffix)
        write_jsonl(out_path, objs)
        print(f"[ok] wrote {out_path} (objects: {len(objs)})")


if __name__ == "__main__":
    main()
