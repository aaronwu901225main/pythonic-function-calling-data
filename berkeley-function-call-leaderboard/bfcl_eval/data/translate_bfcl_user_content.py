#!/usr/bin/env python3
"""
translate_bfcl_user_content.py

說明:
- 讀取指定 JSON 檔（預期為 BFCL 多物件或單物件皆可），只翻譯 question 欄位底下所有訊息物件的 content（不分 role）為繁體中文（臺灣）。
- 其他欄位維持原樣。
- 預設輸出為與輸入檔同資料夾、檔名在第一個「.json」之前插入「_zh_」。
  例如: BFCL_v4_multi_turn_base.json -> BFCL_v4_zh_multi_turn_base.json

環境變數:
- OPENAI_API_KEY: 必填
- OPENAI_TRANSLATE_MODEL: 預設 "gpt-4o-mini"

使用:
    python translate_bfcl_user_content.py --input <path/to/file.json> [--output <out.json>]

注意:
- 本工具僅翻 question 欄位內所有訊息物件的 content（不分 role）；不會動其他欄位。
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


def walk_and_translate(obj: Any, translate_fn, only_under_question: bool = False) -> Any:
    """深度走訪結構，翻譯 question 欄位底下所有訊息物件的 content（不分 role）。

    參數 only_under_question 表示目前是否位於 question 節點以下。
    """
    if isinstance(obj, dict):
        # 當前層級是否是 question 鍵
        result = {}
        for k, v in obj.items():
            if k == "question":
                result[k] = walk_and_translate(v, translate_fn, only_under_question=True)
            else:
                result[k] = walk_and_translate(v, translate_fn, only_under_question=only_under_question)
        return result
    elif isinstance(obj, list):
        new_list = []
        for v in obj:
            if only_under_question and isinstance(v, dict) and isinstance(v.get("content"), str):
                # 位於 question 下且有 content 字串則翻譯
                nv = {**v}
                nv["content"] = translate_fn(v["content"])
                new_list.append(nv)
            else:
                new_list.append(walk_and_translate(v, translate_fn, only_under_question=only_under_question))
        return new_list
    else:
        return obj


def count_question_contents(obj: Any, only_under_question: bool = False) -> int:
    """計算 question 欄位底下所有訊息物件中 content（字串）的數量。"""
    if isinstance(obj, dict):
        cnt = 0
        for k, v in obj.items():
            if k == "question":
                cnt += count_question_contents(v, only_under_question=True)
            else:
                cnt += count_question_contents(v, only_under_question=only_under_question)
        return cnt
    if isinstance(obj, list):
        total = 0
        for v in obj:
            if only_under_question and isinstance(v, dict) and isinstance(v.get("content"), str):
                total += 1
            else:
                total += count_question_contents(v, only_under_question=only_under_question)
        return total
    return 0


class Progress:
    def __init__(self, total: int, width: int = 40):
        self.total = total
        self.current = 0
        self.width = width

    def update(self, step: int = 1):
        if self.total <= 0:
            return
        self.current += step
        self.current = min(self.current, self.total)
        ratio = self.current / self.total
        done = int(self.width * ratio)
        bar = "#" * done + "-" * (self.width - done)
        print(f"\r翻譯進度: [{bar}] {self.current}/{self.total} ({ratio*100:.1f}%)", end="", flush=True)

    def finish(self):
        if self.total > 0:
            print()  # newline


def make_translator(client: "OpenAI", model: str, usage_accum: Dict[str, int], progress: Progress | None):
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
        # 累計 token 使用量
        try:
            u = getattr(resp, "usage", None)
            if u is not None:
                usage_accum["prompt"] += getattr(u, "prompt_tokens", 0) or 0
                usage_accum["completion"] += getattr(u, "completion_tokens", 0) or 0
                usage_accum["total"] += getattr(u, "total_tokens", 0) or 0
        except Exception:
            pass
        # 更新進度條
        if progress is not None:
            progress.update(1)
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

    # 第一階段：先統計所有輸入檔中需要翻譯的句數，用於顯示進度條
    total_to_translate = 0
    for input_path_str in args.input:
        in_path = Path(input_path_str)
        if not in_path.exists():
            raise SystemExit(f"找不到輸入檔: {in_path}")
        text = in_path.read_text(encoding="utf-8")
        parts = split_concatenated_json(text)
        for chunk in parts:
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                try:
                    data = json.loads(chunk.strip(','))
                except Exception:
                    continue
            total_to_translate += count_question_contents(data)

    progress = Progress(total=total_to_translate)
    usage_accum = {"prompt": 0, "completion": 0, "total": 0}
    translator = make_translator(client, model, usage_accum, progress)

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

    # 完成進度條並輸出用量
    progress.finish()
    print("本次翻譯 Token 使用量：")
    print(f"  prompt_tokens:    {usage_accum['prompt']}")
    print(f"  completion_tokens:{usage_accum['completion']}")
    print(f"  total_tokens:     {usage_accum['total']}")


if __name__ == "__main__":
    main()
