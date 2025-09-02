#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Remap ID prefix in a BFCL possible_answer NDJSON file.
# Usage:
#   python remap_answers_prefix.py INPUT.json OUTPUT.json zh_simple_python
#
# Notes:
# - Keeps everything else identical (including ground_truth).
# - If an id doesn't contain an underscore, it will be rewritten as <new_prefix>_<id>.

import sys, json

def remap_line(obj, new_prefix: str):
    _id = str(obj.get("id", ""))
    if _id:
        parts = _id.split("_", 1)
        if len(parts) == 2:
            obj["id"] = f"{new_prefix}_{parts[1]}"
        else:
            obj["id"] = f"{new_prefix}_{_id}"
    return obj

def main():
    if len(sys.argv) < 4:
        print("Usage: python remap_answers_prefix.py INPUT.json OUTPUT.json <new_prefix>")
        sys.exit(1)
    inp, outp, new_prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    n = 0
    with open(inp, "r", encoding="utf-8") as fin, open(outp, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            obj = remap_line(obj, new_prefix)
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n += 1
    print(f"[OK] {inp} -> {outp} ({n} lines)")

if __name__ == "__main__":
    main()
