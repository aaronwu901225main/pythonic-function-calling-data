#!/usr/bin/env python3
# python .\berkeley-function-call-leaderboard\bfcl_eval\scripts\stats_last_column_last_value.py ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\BFCL_v4_zh_multi_turn_base_result.json" --bins 30 --out ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\token_figure\BFCL_v4_zh_multi_turn_base_result_hist.png"
# python .\berkeley-function-call-leaderboard\bfcl_eval\scripts\stats_last_column_last_value.py ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\BFCL_v4_zh_multi_turn_long_context_result.json" --bins 30 --out ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\token_figure\BFCL_v4_zh_multi_turn_long_context_result_hist.png"
# python .\berkeley-function-call-leaderboard\bfcl_eval\scripts\stats_last_column_last_value.py ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\BFCL_v4_zh_multi_turn_miss_func_result.json" --bins 30 --out ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\token_figure\BFCL_v4_zh_multi_turn_miss_func_result_hist.png"
# python .\berkeley-function-call-leaderboard\bfcl_eval\scripts\stats_last_column_last_value.py ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\BFCL_v4_zh_multi_turn_miss_param_result.json" --bins 30 --out ".\berkeley-function-call-leaderboard\result\Salesforce_Llama-xLAM-2-8b-fc-r\multi_turn\token_figure\BFCL_v4_zh_multi_turn_miss_param_result_hist.png"

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
    parser.add_argument("--bins", type=int, default=30, help="Number of bins for histogram (default: 30)")
    parser.add_argument("--out", type=str, default=None, help="Output image path for histogram PNG (default: <json_basename>_hist.png next to JSON)")
    parser.add_argument("--title", type=str, default=None, help="Title for the histogram plot")
    parser.add_argument("--no-plot", action="store_true", help="Compute stats only without plotting")
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

    if not args.no_plot:
        # Lazy import for plotting to avoid hard dependency if not needed
        try:
            import matplotlib
            # Use a non-interactive backend for headless save
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as e:
            print(f"Warning: matplotlib is not available ({e}); skipping histogram plot.", file=sys.stderr)
            return 0

        # Determine output path
        out_path = args.out
        if not out_path:
            import os
            base, _ = os.path.splitext(args.json_path)
            out_path = base + "_hist.png"

        # Create histogram
        plt.figure(figsize=(8, 5))
        plt.hist(values, bins=max(1, args.bins), color="#81730DFF", edgecolor="white")
        plt.xlabel("token_count")
        plt.ylabel("Count")
        plt.grid(True, axis="y", alpha=0.25)
        title = args.title or args.json_path[:-5].split("\\")[-1]
        plt.title(title)
        # Annotate basic stats in the plot
        text = f"n={len(values)}\nmin={v_min:.2f}\nmax={v_max:.2f}\nmean={v_mean:.2f}"
        plt.gcf().text(0.965, 0.9, text, ha="right", va="top", fontsize=12, bbox=dict(boxstyle="round", facecolor="white", alpha=0.7))
        plt.tight_layout()
        plt.savefig(out_path, dpi=150)
        print(f"Histogram saved to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
