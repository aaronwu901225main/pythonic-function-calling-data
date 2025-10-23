#!/usr/bin/env python3
"""
Compute statistics (min, max, mean) over input_token_count[-1][-1] for each item in a BFCL result JSON file.

Usage:
  python stats_last_column_last_value.py <path_to_result_json>

Notes:
- Safely handles missing or malformed input_token_count entries.
- If input_token_count[-1] is not a list, will treat it as a scalar and use it directly.
- Skips items where the value cannot be determined (with a warning on stderr).
"""

import argparse
import json
import math
import sys
from statistics import mean
from typing import Any, List, Optional


def extract_last_last(value: Any) -> Optional[float]:
    """Extract input_token_count[-1][-1] with robustness.

    Accepts cases where:
    - value is a list of lists: take value[-1][-1]
    - value is a list of scalars: take value[-1]
    - value is a scalar: return as float if numeric
    Returns None if not extractable.
    """
    try:
        # None or missing
        if value is None:
            return None

        # If it's a list
        if isinstance(value, list):
            if not value:
                return None
            last = value[-1]
            # Nested list -> take its last element
            if isinstance(last, list):
                if not last:
                    return None
                final = last[-1]
                return float(final) if isinstance(final, (int, float)) else None
            # Scalar list -> take last
            return float(last) if isinstance(last, (int, float)) else None

        # If it's a number
        if isinstance(value, (int, float)):
            return float(value)

        return None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute stats over input_token_count[-1][-1] in BFCL result JSON")
    parser.add_argument("json_path", help="Path to BFCL result JSON file")
    args = parser.parse_args()

    # Load JSON (supports JSON array or JSON Lines)
    try:
        with open(args.json_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try JSON Lines (one JSON object per line)
            data = []
            for ln in content.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    data.append(json.loads(ln))
                except Exception:
                    # If a line cannot be parsed, surface a helpful error
                    raise
    except Exception as e:
        print(f"Error: failed to read JSON '{args.json_path}': {e}", file=sys.stderr)
        return 2

    # Expect list of items
    if not isinstance(data, list):
        print("Error: JSON root is not a list of items.", file=sys.stderr)
        return 2

    values: List[float] = []
    skipped = 0
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            skipped += 1
            continue
        raw = item.get("input_token_count")
        v = extract_last_last(raw)
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            skipped += 1
            continue
        values.append(v)

    count = len(values)
    print(f"Total items: {len(data)}")
    print(f"Valid values: {count}")
    print(f"Skipped: {skipped}")

    if count == 0:
        print("No valid input_token_count values found.")
        return 0

    v_min = min(values)
    v_max = max(values)
    v_mean = mean(values)

    print("--- Statistics for input_token_count[-1][-1] ---")
    print(f"Min:  {v_min}")
    print(f"Max:  {v_max}")
    print(f"Mean: {v_mean}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
