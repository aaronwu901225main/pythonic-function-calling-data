#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Possible-answer converter:
- Input can be a single file OR a directory.
- File content can be:
  * NDJSON/JSONL (one JSON object per line), even if the extension is .json
  * JSON array of objects
  * Single JSON object
- Output is always NDJSON (one JSON object per line). For directory mode, writes to output directory using same file names.
- Transforms:
  * ground_truth: object -> list of single-key objects
  * property: keep only the first item if it's a list
  * tolerance: numeric strings inside list -> numbers; "" kept
  * ID prefix remap per rules (simple_ -> zh_simple_python_, etc.)
- Function name numeric suffix: kept by default; use --strip-fn-suffix to remove trailing _<digits>.
"""
import sys, json, re, argparse
from pathlib import Path
from typing import Iterable, Dict, Any, List, Union

ID_PREFIX_MAP = [
    ("simple_", "zh_simple_python_"),
    ("parallel_multiple_function_", "zh_parallel_multiple"),
    ("parallel_function_", "zh_parallel_"),
    ("multiple_function_", "zh_multiple_"),
]

def remap_id_prefix(_id: str) -> str:
    for old, new in ID_PREFIX_MAP:
        if _id.startswith(old):
            return new + _id[len(old):]
    return _id

def maybe_strip_fn_suffix(name: str, strip_suffix: bool) -> str:
    if strip_suffix:
        return re.sub(r"_(\d+)$", "", name)
    return name

def convert_param_value(key, val):
    if key == "property" and isinstance(val, list) and val:
        return [val[0]]
    if key == "tolerance" and isinstance(val, list):
        out = []
        for x in val:
            if isinstance(x, str) and x != "":
                try:
                    if x.isdigit():
                        out.append(int(x))
                    else:
                        out.append(float(x))
                    continue
                except Exception:
                    pass
            out.append(x)
        return out
    return val

def transform_ground_truth(gt_obj: dict, strip_suffix: bool) -> list:
    items = []
    for fn, args in gt_obj.items():
        new_fn = maybe_strip_fn_suffix(fn, strip_suffix)
        if isinstance(args, dict):
            new_args = {k: convert_param_value(k, v) for k, v in args.items()}
        else:
            new_args = args
        items.append({new_fn: new_args})
    return items

def process_line(obj: dict, strip_suffix: bool) -> dict:
    if "id" not in obj or "ground_truth" not in obj:
        raise ValueError("Each object must contain 'id' and 'ground_truth'.")
    new_id = remap_id_prefix(str(obj["id"]))
    gt = obj["ground_truth"]
    if isinstance(gt, dict):
        gt_list = transform_ground_truth(gt, strip_suffix)
    elif isinstance(gt, list):
        # normalize each single-key dict item
        gt_list = []
        for item in gt:
            if isinstance(item, dict) and len(item) == 1:
                [(fn, args)] = item.items()
                new_fn = maybe_strip_fn_suffix(fn, strip_suffix)
                if isinstance(args, dict):
                    norm_args = {k: convert_param_value(k, v) for k, v in args.items()}
                else:
                    norm_args = args
                gt_list.append({new_fn: norm_args})
            else:
                gt_list.append(item)
    else:
        raise ValueError("'ground_truth' must be an object or list.")
    return {"id": new_id, "ground_truth": gt_list}

def iter_records_from_file(path: Path) -> Iterable[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    # Try parse as whole JSON first
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
            yield parsed
            return
    except Exception:
        pass  # fall back to NDJSON
    
    # NDJSON fallback
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception as e:
            print(f"[WARN] {path.name}:{i}: JSON decode error: {e}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            print(f"[WARN] {path.name}:{i}: not a JSON object; skipping", file=sys.stderr)
            continue
        yield obj

def convert_file(inp: Path, outp: Path, strip_suffix: bool) -> int:
    outp.parent.mkdir(parents=True, exist_ok=True)
    n_in = 0
    n_out = 0
    with outp.open("w", encoding="utf-8") as fout:
        for obj in iter_records_from_file(inp):
            n_in += 1
            try:
                out = process_line(obj, strip_suffix=strip_suffix)
                fout.write(json.dumps(out, ensure_ascii=False) + "\n")
                n_out += 1
            except Exception as e:
                print(f"[WARN] {inp.name} line {n_in}: {e}", file=sys.stderr)
                continue
    print(f"[OK] {inp.name} -> {outp}  ({n_out}/{n_in})")
    return n_out

def main():
    ap = argparse.ArgumentParser(description="Convert possible_answer JSON/JSONL to normalized NDJSON; supports file or directory input.")
    ap.add_argument("input", help="Input file (.json/.jsonl) OR directory")
    ap.add_argument("output", help="Output file OR directory (matches input mode)")
    ap.add_argument("--strip-fn-suffix", action="store_true", help="Strip trailing _<digits> from function names (default: keep)")
    args = ap.parse_args()

    inp = Path(args.input)
    outp = Path(args.output)

    if inp.is_dir():
        outp.mkdir(parents=True, exist_ok=True)
        total = 0
        for f in sorted(inp.iterdir()):
            if f.is_file() and f.suffix.lower() in (".json", ".jsonl"):
                total += 1
                out_f = outp / f.name
                convert_file(f, out_f, strip_suffix=args.strip_fn_suffix)
        print(f"[DONE] processed {total} files")
    else:
        convert_file(inp, outp, strip_suffix=args.strip_fn_suffix)

if __name__ == "__main__":
    main()
