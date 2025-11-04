#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# python pipeline/countoken/countoken.py --input pipeline/data/087190226fd447b5b4595971dc8a8728/multi_turn_eng.jsonl --bin_size 50

import argparse
import json
import os
from collections import Counter
from statistics import median
from transformers import AutoTokenizer
import math

def bucketize(n, bin_size=50):
    """把 token 數量分到區間"""
    low = (n // bin_size) * bin_size
    high = low + bin_size - 1
    return f"{low}-{high}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=str, required=True, help="輸入 JSONL 檔 (每行有 text 欄位)")
    ap.add_argument("--bin_size", type=int, default=50, help="區間大小 (預設 50)")
    ap.add_argument(
        "--output",
        type=str,
        default=None,
        help="輸出圖檔路徑 (預設儲存到與輸入檔同資料夾，檔名 *_tokens_hist_<bin>.png)",
    )
    ap.add_argument(
        "--show",
        action="store_true",
        help="顯示互動式視窗 (伺服器/無桌面環境不建議)",
    )
    args = ap.parse_args()

    model_name = "Salesforce/Llama-xLAM-2-8b-fc-r"
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)

    counts = []
    bad_rows = 0

    with open(args.input, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                text = obj.get("text", "")
                tokens = tokenizer.encode(text)
                counts.append(len(tokens))
            except Exception:
                bad_rows += 1

    if not counts:
        print("❌ 沒有成功解析的資料")
        return

    # 做區間分布
    hist = Counter(bucketize(n, args.bin_size) for n in counts)

    print("—— 區間統計 ——")
    for rng, cnt in sorted(hist.items(), key=lambda x: int(x[0].split("-")[0])):
        print(f"{rng}: {cnt} 筆")

    print("\n—— 總結 ——")
    print(f"總筆數: {len(counts)} (壞掉 {bad_rows} 筆)")
    print(f"總 token 數: {sum(counts)}")
    print(f"平均 tokens/筆: {sum(counts)/len(counts):.2f}")
    print(f"最大 tokens/筆: {max(counts)}")
    print(f"最小 tokens/筆: {min(counts)}")

    # ——— 作圖：Token 分布直方圖（依 bin_size） ———
    # 在無桌面環境時切換到 Agg 後端，避免 import pyplot 失敗
    try:
        import matplotlib
        if not args.show:
            matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"⚠️ 無法載入繪圖套件 matplotlib，略過作圖：{e}")
        return
    
    # 設定中文字型（避免亂碼）
    font_path = "/home/at0842/aaronwu901225master.ai13/fonts/Microsoft JhengHei Regular/Microsoft JhengHei Regular.ttf"
    if os.path.exists(font_path):
        from matplotlib import font_manager
        # 將字型檔加入 Matplotlib 字型管理器，避免 findfont 找不到
        font_manager.fontManager.addfont(font_path)
        font_prop = font_manager.FontProperties(fname=font_path)
        family_name = font_prop.get_name()  # 通常是 'Microsoft JhengHei'
        # 以新增的家族名稱為優先，確保中文可正常顯示
        plt.rcParams['font.family'] = [family_name]
        plt.rcParams['font.sans-serif'] = [
            family_name,
            'Noto Sans CJK TC',
            'Source Han Sans TC',
            'WenQuanYi Zen Hei',
            'DejaVu Sans',
        ]
        print(f"使用字型：{family_name} (from {font_path})")
    else:
        # 中文字型設定（視系統而定，避免亂碼）— Linux 常見可用的 CJK 字型做為備援
        plt.rcParams['font.sans-serif'] = [
            'Noto Sans CJK TC',
            'Source Han Sans TC',
            'WenQuanYi Zen Hei',
            'DejaVu Sans',
        ]
    plt.rcParams['axes.unicode_minus'] = False  # 負號正常顯示

    max_cnt = max(counts)
    # 依 bin_size 建立桶邊界，例如 0, 50, 100, ...
    # 多加一個邊界以覆蓋到最大值
    upper = ((max_cnt // args.bin_size) + 1) * args.bin_size
    bins = list(range(0, upper + args.bin_size, args.bin_size))

    mean_val = sum(counts) / len(counts)
    median_val = median(counts)

    plt.figure(figsize=(10, 6))
    plt.hist(counts, bins=bins, color="#4C78A8", edgecolor="white")
    plt.title("Token 數量分布 (依區間)")
    plt.xlabel("每筆的 Token 數")
    plt.ylabel("筆數")
    plt.grid(axis="y", linestyle=":", alpha=0.5)

    # 標出平均與中位數線
    ylim = plt.ylim()
    plt.vlines([mean_val, median_val], ymin=0, ymax=ylim[1], colors=["#E45756", "#72B7B2"],
               linestyles=["--", "-."] , label=["平均", "中位數"])
    # 補上圖例（手動建立兩條線的圖例）
    from matplotlib.lines import Line2D
    legend_elems = [
        Line2D([0], [0], color="#E45756", linestyle="--", label=f"平均 {mean_val:.1f}"),
        Line2D([0], [0], color="#72B7B2", linestyle="-.", label=f"中位數 {median_val:.1f}"),
    ]
    plt.legend(handles=legend_elems)

    # 決定輸出路徑
    if args.output:
        out_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.input))[0]
        out_dir = os.path.dirname(args.input) or "."
        out_path = os.path.join(out_dir, f"{base}_tokens_hist_{args.bin_size}.png")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"\n🖼️ 已輸出圖檔: {out_path}")

    if args.show:
        try:
            plt.show()
        except Exception:
            # 在無桌面環境時 show 會失敗，忽略即可
            pass

if __name__ == "__main__":
    main()
