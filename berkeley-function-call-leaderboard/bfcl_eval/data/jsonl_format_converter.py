#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSONL Format Converter

- Reads every .jsonl file in an input directory.
- Converts each line from the source schema to the target schema.
- Writes same-named .jsonl files to an output directory.
- Keys/field names and function names are preserved.
- Only structure is changed; content of question is not translated or modified.
- By default, if the "id" contains the substring "_function", that substring is removed
  to match the example output. You can disable this behavior with --keep-id.
"""

from __future__ import annotations
import json
from pathlib import Path
import argparse
import sys
from typing import Dict, Any

def convert_record(src: Dict[str, Any], keep_id: bool = False) -> Dict[str, Any]:
    """Convert a single record from source to target schema."""
    if not isinstance(src, dict):
        raise ValueError("Each JSONL line must be a JSON object.")
    # Required fields
    try:
        src_id = src["id"]
        src_question = src["question"]
        src_function = src["function"]
    except KeyError as e:
        raise KeyError(f"Missing required key: {e} in record: {src}") from e

    if not keep_id and isinstance(src_id, str):
        # Follow the example: remove the literal substring "_function" if present.
        tgt_id = src_id.replace("_function", "")
    else:
        tgt_id = src_id

    # Wrap question into the target chat format without changing its content
    tgt_question = [[{"role": "user", "content": src_question}]]
    tgt = {
        "id": tgt_id,
        "question": tgt_question,
        "function": src_function,  # pass-through; do not alter names or schemas
    }
    return tgt

def process_file(inp: Path, outp: Path, keep_id: bool = False) -> int:
    """Process a single .jsonl file. Returns number of lines converted."""
    count = 0
    outp.parent.mkdir(parents=True, exist_ok=True)
    with inp.open("r", encoding="utf-8") as fin, outp.open("w", encoding="utf-8") as fout:
        for ln, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                conv = convert_record(obj, keep_id=keep_id)
                fout.write(json.dumps(conv, ensure_ascii=False) + "\n")
                count += 1
            except Exception as e:
                # Write an error to stderr but continue processing other lines
                print(f"[WARN] {inp.name}:{ln}: {e}", file=sys.stderr)
                continue
    return count

def main(argv=None):
    p = argparse.ArgumentParser(description="Convert JSONL files to the target schema.")
    p.add_argument("input_dir", type=Path, help="Directory containing source .jsonl files")
    p.add_argument("output_dir", type=Path, help="Directory to write converted .jsonl files")
    p.add_argument("--keep-id", action="store_true",
                   help="Keep the original 'id' unchanged (do not strip '_function')")
    args = p.parse_args(argv)

    if not args.input_dir.exists() or not args.input_dir.is_dir():
        p.error(f"Input directory not found or not a directory: {args.input_dir}")

    files = sorted([f for f in args.input_dir.iterdir() if f.suffix.lower() in (".jsonl", ".json")])
    if not files:
        print(f"[INFO] No .jsonl files found in {args.input_dir}", file=sys.stderr)

    total_lines = 0
    for f in files:
        out_file = args.output_dir / f.name
        n = process_file(f, out_file, keep_id=args.keep_id)
        print(f"[OK] {f.name} -> {out_file}  ({n} lines converted)")
        total_lines += n

    print(f"[DONE] Converted {len(files)} files, {total_lines} lines total.")

if __name__ == "__main__":
    main()
