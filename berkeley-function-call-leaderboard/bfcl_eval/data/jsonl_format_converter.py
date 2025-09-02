#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON/JSONL Format Converter (enhanced)

- Reads every .jsonl or .json file in an input directory.
- Accepts NDJSON, JSON arrays, or a single JSON object per file.
- Normalizes each record to the target BFCL-style schema:
  * question -> [[{role, content}, ...]] (auto-detects and preserves if already in chat format)
  * function -> always a list[dict] (wraps dict into a list)
  * id -> optionally strip substrings (default: '_function') and/or replace the prefix with --target-prefix
- Writes NDJSON (.jsonl-compatible) lines to the output directory using the original file names.
- Keys/field names and function names are preserved; only structure is normalized.

Examples:
  python jsonl_format_converter_updated.py ./in ./out --target-prefix simple_python
  python jsonl_format_converter_updated.py ./in ./out --target-prefix zh_simple_python --strip-substr _function --strip-substr _test
  python jsonl_format_converter_updated.py ./in ./out --keep-id
"""

from __future__ import annotations
import json
from pathlib import Path
import argparse
import sys
from typing import Any, Dict, Iterable, List, Union

def looks_like_msg(d: Any) -> bool:
    return isinstance(d, dict) and "role" in d and "content" in d

def normalize_question(q: Any) -> List[List[Dict[str, Any]]]:
    if isinstance(q, str):
        return [[{ "role": "user", "content": q }]]
    if isinstance(q, dict) and looks_like_msg(q):
        return [[q]]
    if isinstance(q, list):
        # list[dict] => one turn
        if all(isinstance(m, dict) and looks_like_msg(m) for m in q):
            return [q]
        # list[list[dict]] => already chat of turns
        if all(isinstance(turn, list) for turn in q):
            return q
    raise ValueError(f"Unsupported question format: {type(q)} -> {q!r}")

def normalize_function(f: Any) -> List[Dict[str, Any]]:
    if isinstance(f, dict):
        return [f]
    if isinstance(f, list):
        if not all(isinstance(x, dict) for x in f):
            raise ValueError("Each item in 'function' list must be an object.")
        return f
    raise ValueError(f"Unsupported 'function' type: {type(f)}")

def normalize_id(src_id: Any, keep_id: bool, target_prefix: Union[str, None], strip_substrs: List[str]) -> str:
    if not isinstance(src_id, str):
        src_id = str(src_id)
    if keep_id:
        return src_id
    out = src_id
    for s in strip_substrs:
        if s:
            out = out.replace(s, "")
    if target_prefix:
        parts = out.split("_", 1)
        if len(parts) == 2:
            out = f"{target_prefix}_{parts[1]}"
        else:
            out = f"{target_prefix}_{out}"
    return out

def convert_record(src: Dict[str, Any], keep_id: bool = False, target_prefix: Union[str, None] = None, strip_substrs: List[str] = None) -> Dict[str, Any]:
    if strip_substrs is None:
        strip_substrs = ["_function"]
    if not isinstance(src, dict):
        raise ValueError("Each JSONL line must be a JSON object.")
    try:
        src_id = src["id"]
        src_question = src["question"]
        src_function = src["function"]
    except KeyError as e:
        raise KeyError(f"Missing required key: {e} in record: {src}") from e

    tgt_id = normalize_id(src_id, keep_id=keep_id, target_prefix=target_prefix, strip_substrs=strip_substrs)
    tgt_question = normalize_question(src_question)
    tgt_function = normalize_function(src_function)

    return {
        "id": tgt_id,
        "question": tgt_question,
        "function": tgt_function,
    }

def iter_json_records_from_path(p: Path) -> Iterable[Dict[str, Any]]:
    text = p.read_text(encoding="utf-8")
    # Try parse whole file as JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for obj in parsed:
                if isinstance(obj, dict):
                    yield obj
                else:
                    raise ValueError("Array items must be JSON objects.")
            return
        elif isinstance(parsed, dict):
            # Optional: use 'data' array if present
            if "data" in parsed and isinstance(parsed["data"], list):
                for obj in parsed["data"]:
                    if isinstance(obj, dict):
                        yield obj
                    else:
                        raise ValueError("'data' array items must be JSON objects.")
                return
            else:
                yield parsed
                return
    except Exception:
        # Fallback: NDJSON
        pass

    for ln, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception as e:
            print(f"[WARN] {p.name}:{ln}: JSON decode error: {e}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            print(f"[WARN] {p.name}:{ln}: not a JSON object; skipping", file=sys.stderr)
            continue
        yield obj

def process_file(inp: Path, outp: Path, keep_id: bool = False, target_prefix: Union[str, None] = None, strip_substrs: List[str] = None) -> int:
    count = 0
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as fout:
        for ln, obj in enumerate(iter_json_records_from_path(inp), start=1):
            try:
                conv = convert_record(obj, keep_id=keep_id, target_prefix=target_prefix, strip_substrs=strip_substrs)
                fout.write(json.dumps(conv, ensure_ascii=False) + "\n")
                count += 1
            except Exception as e:
                print(f"[WARN] {inp.name}:{ln}: {e}", file=sys.stderr)
                continue
    return count

def discover_files(input_dir: Path) -> List[Path]:
    return sorted([f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in (".jsonl", ".json")])

def main(argv=None):
    p = argparse.ArgumentParser(description="Convert JSON/JSONL datasets into normalized JSONL (NDJSON) for BFCL-style evaluators.")
    p.add_argument("input_dir", type=Path, help="Directory containing source .jsonl/.json files")
    p.add_argument("output_dir", type=Path, help="Directory to write converted .jsonl files")
    p.add_argument("--keep-id", action="store_true", help="Keep the original 'id' unchanged (do not strip substrings or change prefix)")
    p.add_argument("--target-prefix", type=str, default=None, help="Replace the id prefix (before the first underscore) with this value, e.g., 'simple_python' or 'zh_simple_python'")
    p.add_argument("--strip-substr", action="append", default=["_function"], help="Substring(s) to remove from id (may be passed multiple times). Default: '_function'")
    args = p.parse_args(argv)

    if not args.input_dir.exists() or not args.input_dir.is_dir():
        p.error(f"Input directory not found or not a directory: {args.input_dir}")

    files = discover_files(args.input_dir)
    if not files:
        print(f"[INFO] No .jsonl/.json files found in {args.input_dir}", file=sys.stderr)

    total_lines = 0
    for f in files:
        out_file = args.output_dir / f.name
        n = process_file(f, out_file, keep_id=args.keep_id, target_prefix=args.target_prefix, strip_substrs=args.strip_substr)
        print(f"[OK] {f.name} -> {out_file}  ({n} lines converted)")
        total_lines += n

    print(f"[DONE] Converted {len(files)} files, {total_lines} lines total.")

if __name__ == "__main__":
    main()
