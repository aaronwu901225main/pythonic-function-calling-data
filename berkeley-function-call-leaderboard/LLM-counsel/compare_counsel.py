#!/usr/bin/env python
"""Compare兩個中文語義評估器 (judge) 產生的 decision 差異。

使用方式 (在 LLM-counsel 目錄下):
    python compare_judges.py \
        --dir-a score-gpt-4.1-mini \
        --dir-b score-Qwen3-8B \
        --output comparison.csv

輸出:
  1. 終端列印統計：
       both_true, both_false, a_true_b_false, b_true_a_false, different_null_cases, only_in_a, only_in_b
  2. 可選 CSV：每列 id, decision_a, decision_b, category

匹配邏輯:
  - 於各目錄遞迴尋找 *zhtw_semantic_judge* 內的 *_judge_log.jsonl 檔
  - 每行均為一個 JSON 物件，取欄位: id, decision, judge_model (僅做參考)
  - 同一 id 可能出現多次 (重試或多段 logging)。若 decision 相同直接採用；
    若同一 id 出現不一致 decision，採用『多數決』；若平手則取最後一筆。
  - decision 可為 true/false/None。None 視為 null (會單獨分類)。

注意:
  - 僅對同時出現在 A、B 的 id 進行四象限分類。
  - 缺失於其中一方的 id 會計入 only_in_a / only_in_b。
  - 若任一方 decision 為 None，計入 different_null_cases (不再細分)。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.rcParams['font.family'] = 'Microsoft JhengHei'
    matplotlib.rcParams['axes.unicode_minus'] = False
except Exception:
    pass


@dataclass(frozen=True)
class RecordKey:
    model_name: str
    test_category: str
    id: str

    def as_full(self) -> str:
        return f"{self.model_name}::{self.test_category}::{self.id}"


@dataclass
class JudgeRecord:
    key: RecordKey
    decision: Optional[bool]


def scan_judge_logs(root: Path) -> List[JudgeRecord]:
    """掃描所有 judge_log.jsonl，保留 (model_name, test_category, id) 粒度。"""
    out: List[JudgeRecord] = []
    for path in root.rglob("*zhtw_semantic_judge*/*_judge_log.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        print(f"[warn] JSON decode error: {path} line {line_no}")
                        continue
                    _id = obj.get("id")
                    if _id is None:
                        continue
                    model_name = obj.get("model_name") or "<unknown_model>"
                    test_category = obj.get("test_category") or "<unknown_cat>"
                    out.append(
                        JudgeRecord(
                            key=RecordKey(model_name=model_name, test_category=test_category, id=str(_id)),
                            decision=obj.get("decision"),
                        )
                    )
        except OSError as e:
            print(f"[warn] cannot read {path}: {e}")
    return out


def aggregate_records(records: List[JudgeRecord], key_mode: str) -> Dict[str, List[Optional[bool]]]:
    """依 key_mode 將多筆 decision 聚合。

    key_mode:
      full: model::category::id (預設，最精細)
      model_id: model::id (忽略 category)
      id: id (可能混淆不同模型，僅為向後相容)
    """
    bucket: Dict[str, List[Optional[bool]]] = defaultdict(list)
    for r in records:
        if key_mode == "id":
            k = r.key.id
        elif key_mode == "model_id":
            k = f"{r.key.model_name}::{r.key.id}"
        else:
            k = r.key.as_full()
        bucket[k].append(r.decision)
    return bucket


def reduce_decisions(values: List[Optional[bool]]) -> Optional[bool]:
    """多筆 decision 合併成單值。

    策略:
      - 若全部皆為 None -> None
      - 否則對 True/False 計數，多數決。
      - True/False 次數相同 -> 取最後一個非 None 的值。
    """
    if not values:
        return None
    # 過濾非 None
    votes = [v for v in values if v is not None]
    if not votes:
        return None
    counter = Counter(votes)
    if counter[True] > counter[False]:
        return True
    if counter[False] > counter[True]:
        return False
    # 平手：找最後一個非 None
    for v in reversed(values):
        if v is not None:
            return v
    return None  # 理論上不會到此


def build_final_map(raw: Dict[str, List[Optional[bool]]]) -> Dict[str, Optional[bool]]:
    return {k: reduce_decisions(v) for k, v in raw.items()}


def classify(a: Optional[bool], b: Optional[bool]) -> str:
    if a is None or b is None:
        return "different_null_cases"
    if a and b:
        return "both_true"
    if (not a) and (not b):
        return "both_false"
    if a and (not b):
        return "a_true_b_false"
    if (not a) and b:
        return "b_true_a_false"
    return "unknown"  # 理論保險


def main():
    parser = argparse.ArgumentParser(description="Compare two judge decision directories.")
    parser.add_argument("--dir-a", default="score-gpt-4.1-mini", help="Judge A 目錄 (預設: score-gpt-4.1-mini)")
    parser.add_argument("--dir-b", default="score-Qwen3-8B", help="Judge B 目錄 (預設: score-Qwen3-8B)")
    parser.add_argument("--output", default=None, help="輸出比較結果 CSV (可選)")
    parser.add_argument("--root", default=".", help="LLM-counsel 根目錄 (預設: 當前)")
    parser.add_argument("--key-mode", choices=["full", "model_id", "id"], default="full", help="決策配對 key 粒度")
    parser.add_argument("--by-model", action="store_true", help="輸出按 model_name 聚合統計")
    parser.add_argument("--by-category", action="store_true", help="輸出按 test_category 聚合統計")
    parser.add_argument("--by-model-category", action="store_true", help="輸出按 (model,category) 聚合")
    parser.add_argument("--matrix-dir", default=None, help="若提供，輸出每個 model 與 overall 的 2x2 矩陣圖與 CSV")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    dir_a = (root / args.dir_a).resolve()
    dir_b = (root / args.dir_b).resolve()

    if not dir_a.exists():
        raise SystemExit(f"dir-a 不存在: {dir_a}")
    if not dir_b.exists():
        raise SystemExit(f"dir-b 不存在: {dir_b}")

    print(f"[info] 掃描 A: {dir_a}")
    rec_a = scan_judge_logs(dir_a)
    print(f"[info] 掃描 B: {dir_b}")
    rec_b = scan_judge_logs(dir_b)

    raw_a = aggregate_records(rec_a, args.key_mode)
    raw_b = aggregate_records(rec_b, args.key_mode)
    final_a = build_final_map(raw_a)
    final_b = build_final_map(raw_b)

    ids_a = set(final_a.keys())
    ids_b = set(final_b.keys())

    shared = ids_a & ids_b
    only_a = ids_a - ids_b
    only_b = ids_b - ids_a

    stats_counter = Counter()
    rows: List[Tuple[str, Optional[bool], Optional[bool], str]] = []
    for _id in sorted(shared):
        ca = final_a[_id]
        cb = final_b[_id]
        cat = classify(ca, cb)
        stats_counter[cat] += 1
        rows.append((_id, ca, cb, cat))

    # Aggregate summary
    summary_order = ["both_true", "both_false", "a_true_b_false", "b_true_a_false", "different_null_cases"]
    print("\n=== 統計 (僅針對同時出現 id) ===")
    for key in summary_order:
        print(f"{key}: {stats_counter.get(key,0)}")
    print(f"shared_ids: {len(shared)}")
    print(f"only_in_a: {len(only_a)}")
    print(f"only_in_b: {len(only_b)}")

    # 百分比 (排除 decision 為 None 的配對)
    four_keys = ["both_true", "both_false", "a_true_b_false", "b_true_a_false"]
    denom = sum(stats_counter[k] for k in four_keys)
    print("\n=== 百分比 (排除任一為 None) ===")
    if denom == 0:
        print("無有效配對 (皆為 None)")
    else:
        for k in four_keys:
            cnt = stats_counter.get(k, 0)
            pct = cnt / denom * 100 if denom else 0.0
            print(f"{k}: {cnt} ({pct:.2f}%)")
        agreement = stats_counter.get("both_true",0) + stats_counter.get("both_false",0)
        print(f"overall_agreement: {agreement}/{denom} ({(agreement/denom*100 if denom else 0):.2f}%)")

    # 2x2 矩陣 (A 為列, B 為欄) 只考慮非 None
    if denom > 0:
        a_true_b_true = stats_counter.get("both_true", 0)
        a_true_b_false = stats_counter.get("a_true_b_false", 0)
        a_false_b_true = stats_counter.get("b_true_a_false", 0)
        a_false_b_false = stats_counter.get("both_false", 0)
        row_a_true = a_true_b_true + a_true_b_false
        row_a_false = a_false_b_true + a_false_b_false
        col_b_true = a_true_b_true + a_false_b_true
        col_b_false = a_true_b_false + a_false_b_false

        def pct(v: int) -> str:
            return f"{(v/denom*100):.2f}%" if denom else "-"

        print("\n=== 2x2 矩陣 (A=列, B=欄, 只含非 None) ===")
        # 表頭
        header = ["", "B=True", "B=False", "Row Total"]
        rows = [
            ["A=True", f"{a_true_b_true} ({pct(a_true_b_true)})", f"{a_true_b_false} ({pct(a_true_b_false)})", f"{row_a_true} ({pct(row_a_true)})"],
            ["A=False", f"{a_false_b_true} ({pct(a_false_b_true)})", f"{a_false_b_false} ({pct(a_false_b_false)})", f"{row_a_false} ({pct(row_a_false)})"],
        ]
        col_total = ["Col Total", f"{col_b_true} ({pct(col_b_true)})", f"{col_b_false} ({pct(col_b_false)})", f"{denom} (100.00%)"]

        # 簡單字寬對齊
        col_widths = [max(len(str(r[i])) for r in ([header]+rows+[col_total])) for i in range(len(header))]
        def fmt_row(r):
            return " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(r))

        print(fmt_row(header))
        print("-+-".join('-'*w for w in col_widths))
        for r in rows:
            print(fmt_row(r))
        print("-+-".join('-'*w for w in col_widths))
        print(fmt_row(col_total))

    if args.output:
        out_path = Path(args.output).resolve()
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["key", "decision_a", "decision_b", "category"])
            writer.writerows(rows)
        print(f"[info] 已輸出 CSV: {out_path}")

    # 顯示差異 Top 10 (各類別前幾個)
    diffs = [r for r in rows if r[3] in ("a_true_b_false", "b_true_a_false", "different_null_cases")]
    if diffs:
        print("\n範例差異 (最多 10 筆):")
        for r in diffs[:10]:
            print(f"  {r[0]} -> A:{r[1]} B:{r[2]} ({r[3]})")

    # 需要分組統計時，以 full 粒度對齊
    if any([args.by_model, args.by_category, args.by_model_category]):
        print("\n=== 分組統計 (full 粒度對齊) ===")
        full_a = aggregate_records(rec_a, "full")
        full_b = aggregate_records(rec_b, "full")
        final_full_a = build_final_map(full_a)
        final_full_b = build_final_map(full_b)
        shared_full = set(final_full_a.keys()) & set(final_full_b.keys())

        def parse_full(k: str) -> Tuple[str, str, str]:
            parts = k.split("::", 3)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
            return ("?", "?", k)

        # 準備分組
        model_groups: Dict[str, List[str]] = defaultdict(list)
        cat_groups: Dict[str, List[str]] = defaultdict(list)
        mc_groups: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for k in shared_full:
            m, c, _ = parse_full(k)
            model_groups[m].append(k)
            cat_groups[c].append(k)
            mc_groups[(m, c)].append(k)

        def summarize(keys: List[str]) -> Optional[str]:
            s = Counter()
            for k in keys:
                s[classify(final_full_a[k], final_full_b[k])] += 1
            four = ["both_true", "both_false", "a_true_b_false", "b_true_a_false"]
            denom_g = sum(s[x] for x in four)
            if denom_g == 0:
                return None
            agree = s.get("both_true",0)+s.get("both_false",0)
            return (f"n={denom_g} agree={agree/denom_g*100:.2f}% "
                    f"BT={s.get('both_true',0)} BF={s.get('both_false',0)} "
                    f"A!B={s.get('a_true_b_false',0)} B!A={s.get('b_true_a_false',0)}")

        if args.by_model:
            print("-- by model --")
            for m, ks in sorted(model_groups.items()):
                line = summarize(ks)
                if line:
                    print(f"[{m}] {line}")
        if args.by_category:
            print("-- by category --")
            for c, ks in sorted(cat_groups.items()):
                line = summarize(ks)
                if line:
                    print(f"[{c}] {line}")
        if args.by_model_category:
            print("-- by model+category --")
            for (m,c), ks in sorted(mc_groups.items()):
                line = summarize(ks)
                if line:
                    print(f"[{m}::{c}] {line}")

    # 產出圖表與矩陣 CSV
    if args.matrix_dir:
        out_dir = Path(args.matrix_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[info] 生成矩陣輸出資料夾: {out_dir}")

        # full 粒度必須存在 (若使用 id / model_id 也重新建 full 資料)
        full_a = aggregate_records(rec_a, "full")
        full_b = aggregate_records(rec_b, "full")
        final_full_a = build_final_map(full_a)
        final_full_b = build_final_map(full_b)
        shared_full = set(final_full_a.keys()) & set(final_full_b.keys())

        def parse_full(k: str) -> Tuple[str, str, str]:
            parts = k.split("::", 3)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
            return ("?", "?", k)

        # 建立 per-key 詳細資料結構
        detailed_rows: List[Dict[str, str]] = []
        per_model_keys: Dict[str, List[str]] = defaultdict(list)
        for k in shared_full:
            m, c, i = parse_full(k)
            a_dec = final_full_a[k]
            b_dec = final_full_b[k]
            cls = classify(a_dec, b_dec)
            detailed_rows.append({
                "model_name": m,
                "test_category": c,
                "id": i,
                "decision_a": str(a_dec),
                "decision_b": str(b_dec),
                "class": cls,
            })
            per_model_keys[m].append(k)

        # 寫出全部 key 詳細 CSV
        with (out_dir / "all_keys_detailed.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["model_name","test_category","id","decision_a","decision_b","class"])
            w.writeheader()
            w.writerows(detailed_rows)

        def confusion_counts(keys: List[str]) -> Dict[str, int]:
            s = Counter()
            for k in keys:
                s[classify(final_full_a[k], final_full_b[k])] += 1
            return s

        def sanitize(name: str) -> str:
            return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]

        def save_matrix(name: str, counts: Dict[str,int]):
            four = ["both_true","a_true_b_false","b_true_a_false","both_false"]
            denom_local = sum(counts.get(k,0) for k in ["both_true","both_false","a_true_b_false","b_true_a_false"])
            if denom_local == 0:
                print(f"[warn] {name} 無有效 (non-None) 配對，跳過圖表。")
                return
            TT = counts.get("both_true",0)
            TF = counts.get("a_true_b_false",0)
            FT = counts.get("b_true_a_false",0)
            FF = counts.get("both_false",0)
            # 寫 CSV
            csv_path = out_dir / f"matrix_{sanitize(name)}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["A\\B","True","False","Row Total"])
                w.writerow(["True", TT, TF, TT+TF])
                w.writerow(["False", FT, FF, FT+FF])
                w.writerow(["Col Total", TT+FT, TF+FF, denom_local])
            if not _HAS_MPL:
                print(f"[warn] 缺少 matplotlib/numpy，僅輸出 CSV: {csv_path}")
                return
            import numpy as _np  # 保險重匯入
            data = _np.array([[TT, TF],[FT, FF]])
            fig, ax = plt.subplots(figsize=(3.8,3.8))
            im = ax.imshow(data, cmap="Blues", vmin=0, vmax=data.max() if data.max()>0 else 1)
            ax.set_xticks([0,1]); ax.set_yticks([0,1])
            ax.set_xticklabels(["B=True","B=False"], fontsize=10)
            ax.set_yticklabels(["A=True","A=False"], fontsize=10)
            ax.set_title(f"{name}\n2x2 矩陣 (n={denom_local})", fontsize=11)
            for (r,c), val in _np.ndenumerate(data):
                pct = val/denom_local*100 if denom_local else 0
                ax.text(c, r, f"{val}\n{pct:.1f}%", ha="center", va="center", fontsize=9, color="black")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            fig.tight_layout()
            fig_path = out_dir / f"matrix_{sanitize(name)}.png"
            fig.savefig(fig_path, dpi=160)
            plt.close(fig)
            print(f"[info] 輸出矩陣圖: {fig_path}")

        # per-model
        for model_name, keys in sorted(per_model_keys.items()):
            save_matrix(model_name, confusion_counts(keys))
        # overall
        save_matrix("overall", confusion_counts(list(shared_full)))


if __name__ == "__main__":
    main()
'''
python berkeley-function-call-leaderboard/LLM-counsel/compare_counsel.py `
  --dir-a score-gpt-4.1-mini `
  --dir-b score-Qwen3-8B `
  --root berkeley-function-call-leaderboard/LLM-counsel
'''