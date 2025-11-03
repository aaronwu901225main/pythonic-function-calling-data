# -*- coding: utf-8 -*-
"""
依據下列 CSV（需與本檔在同資料夾）自動繪製折線圖：
- data_chinese.csv
- data_live.csv
- data_multi_turn.csv
- data_non_live.csv
- data_overall.csv
- data_chinese_multi_turn.csv
- data_chinese_overall.csv

規則：
1) 只繪製「Model」欄位內含 ckpt 的列（LoRA 版本）。
2) 以「ckptXXXX- 後面的超參數字串完全相同」為同一條折線（只允許 ckpt 不同）。
3) y 軸為各檔案對應的總準確度欄位（自動偵測，含 '%' 會自動轉數字）。
4) 若有找到 baseline：`xLAM-2-8b-fc-r (FC)(原版)`（或不含 LoRA/ckpt 的 xLAM-2-8b-fc-r），
   會加一條水平虛線當基準。
5) 一個 CSV 產出一張圖，檔名為 `{原檔名}_ckpt_lora_lines.png`。

需求套件：pandas, matplotlib
"""

import os
import re
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import transforms

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

# 需要讀的檔名（固定）
TARGET_FILES = [
    "data_overall.csv",
    "data_chinese.csv",
    "data_live.csv",
    "data_non_live.csv",
    "data_multi_turn.csv",
    "data_chinese_multi_turn.csv",
    "data_chinese_overall.csv"
]

# 可能的整體準確度欄位名稱候選（會依序嘗試）
ACC_COL_CANDIDATES = [
    "Overall Acc",
    "Overall (ZH) Acc",
    "Live Overall Acc",
    "Non-Live Overall Acc",
    "Multi Turn Overall Acc",
    "AST (ZH) Summary",
    "AST Summary",
    "Multi Turn (ZH) Overall Acc",
]

# 解析 ckpt 的正則：抓出 ckpt 數字與後綴超參數字串
CKPT_RE = re.compile(r"^(?P<prefix>.*?\bLoRA\s+)?ckpt(?P<ckpt>\d+)-(?P<rest>.+)$", re.IGNORECASE)

def pick_acc_col(df: pd.DataFrame) -> str:
    """挑選各 CSV 的整體準確度欄位。"""
    for c in ACC_COL_CANDIDATES:
        if c in df.columns:
            return c
    # fallback: 嘗試找名稱含 acc
    for col in df.columns:
        if "acc" in str(col).lower():
            return col
    raise ValueError("找不到準確度欄位，請檢查 CSV 欄位名稱。")

def parse_percent(x):
    """把 '67.5%' 或 '67.5' 轉 float。無法解析回傳 None。"""
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        return None

def extract_ckpt_info(model_name: str):
    """
    從 Model 名稱抽出 (prefix, ckpt_int, rest)；失敗回 None。
    rest = '1batch-2560seq-1epoch-apigen' 等，用來當分組鍵（同一條線）。
    """
    if not isinstance(model_name, str):
        return None
    m = CKPT_RE.search(model_name.strip())
    if not m:
        return None
    try:
        ckpt = int(m.group("ckpt"))
    except Exception:
        return None
    prefix = (m.group("prefix") or "").strip()
    rest = m.group("rest").strip()
    return prefix, ckpt, rest

def find_baseline(df: pd.DataFrame, acc_col: str):
    """
    嘗試找 `xLAM-2-8b-fc-r (FC)(原版)` 的 baseline；找不到就找
    不含 'LoRA'/'ckpt' 的 xLAM-2-8b-fc-r。
    回傳 (model_name, baseline_acc) 或 (None, None)
    """
    mcol = "Model"
    if mcol not in df.columns:
        return None, None

    s = df[mcol].astype(str)

    # 優先 (FC)(原版)
    base_rows = df[s.str.contains(r"xLAM-2-8b-fc-r\s*\(FC\).*原版", case=False, regex=True)]
    if base_rows.empty:
        # 次選：不含 LoRA 或 ckpt 的 xLAM-2-8b-fc-r
        base_rows = df[s.str.contains(r"xLAM-2-8b-fc-r", case=False, regex=True) &
                       ~s.str.contains(r"LoRA|ckpt", case=False, regex=True)]

    if base_rows.empty:
        return None, None

    row = base_rows.iloc[0]
    return row["Model"], parse_percent(row[acc_col])

def plot_one_csv(csv_path: str, out_dir: str = "."):
    """讀取單一 CSV 並輸出折線圖 PNG。"""
    if not os.path.exists(csv_path):
        print(f"[略過] 找不到檔案：{csv_path}")
        return None

    df = pd.read_csv(csv_path)
    if "Model" not in df.columns:
        print(f"[略過] 檔案缺少 'Model' 欄位：{csv_path}")
        return None

    # 自動挑整體準確度欄位
    acc_col = pick_acc_col(df)

    # baseline
    baseline_name, baseline_acc = find_baseline(df, acc_col)

    # 僅保留包含 ckpt 的 LoRA 模型
    df = df[~df["Model"].isna()].copy()
    df["ckpt_info"] = df["Model"].apply(extract_ckpt_info)
    ckpt_df = df[df["ckpt_info"].notna()].copy()
    if ckpt_df.empty:
        print(f"[略過] 沒有包含 checkpoint 的模型：{csv_path}")
        return None

    # 展開欄位
    ckpt_df[["prefix", "ckpt", "lora_rest"]] = ckpt_df["ckpt_info"].apply(pd.Series)
    ckpt_df["acc_pct"] = ckpt_df[acc_col].apply(parse_percent)
    ckpt_df = ckpt_df[ckpt_df["acc_pct"].notna()]
    if ckpt_df.empty:
        print(f"[略過] 沒有可用的準確度資料：{csv_path}")
        return None

    # 群組鍵：僅用 rest（ckpt 後面的超參數字串）→ 確保同一 LoRA、僅 ckpt 不同
    ckpt_df["group_key"] = ckpt_df["lora_rest"]

    # 固定圖高度，移除先前的動態高度調整
    plt.figure(figsize=(10, 6))
    ax = plt.gca()

    for gkey, g in ckpt_df.groupby("group_key"):
        gg = g.sort_values("ckpt")
        ax.plot(gg["ckpt"].values, gg["acc_pct"].values, marker="o", label=gkey)

    # ---- 新增：為所有非 checkpoint 模型加水平線 ----
    non_ckpt_df = df[df["ckpt_info"].isna()].copy()
    if not non_ckpt_df.empty:
        non_ckpt_df["acc_pct"] = non_ckpt_df[acc_col].apply(parse_percent)
        non_ckpt_df = non_ckpt_df[non_ckpt_df["acc_pct"].notna()]
        # 排除 baseline
        if baseline_name is not None:
            non_ckpt_df = non_ckpt_df[non_ckpt_df["Model"] != baseline_name]
        if not non_ckpt_df.empty:
            # 只保留最佳（最高 acc）一筆；若有多筆同分取第一筆
            best_idx = non_ckpt_df["acc_pct"].idxmax()
            best_row = non_ckpt_df.loc[best_idx]
            best_name = str(best_row["Model"])[:120]
            best_acc = float(best_row["acc_pct"])
            color = plt.get_cmap('tab20')(0)
            # 畫水平線
            ax.axhline(best_acc, linestyle=":", linewidth=1.5, alpha=0.95, color=color)
            # 放標籤（單一不需碰撞處理）
            x_label_axes = 1.005
            trans = transforms.blended_transform_factory(ax.transAxes, ax.transData)
            x_min = ckpt_df["ckpt"].min(); x_max = ckpt_df["ckpt"].max(); span = max(1, x_max - x_min)
            ax.set_xlim(x_min - span * 0.02, x_max + span * 0.02)
            ax.text(
                x_label_axes,
                best_acc,
                f"最佳非ckpt且非baseline:\n{best_name} ({best_acc:.2f}%)",
                va='center', ha='left', fontsize=8, color=color,
                transform=trans, clip_on=False,
                bbox=dict(facecolor='white', alpha=0.65, edgecolor='none', pad=1),
            )

    # 畫 baseline
    if baseline_acc is not None:
        ax.axhline(baseline_acc, linestyle="--", linewidth=1.5,
                   label=f"Baseline: {baseline_name}")

    ax.set_xlabel("Checkpoint 編號")
    ax.set_ylabel("準確度(%)")
    title = os.path.basename(csv_path) + "：LORA 不同 ckpt 模型的準確度折線圖"
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, which="both", axis="both", linewidth=0.5)

    os.makedirs(out_dir, exist_ok=True)
    stem, _ = os.path.splitext(os.path.basename(csv_path))
    out_png = os.path.join(out_dir, f"{stem}_ckpt_lora_lines.png")

    plt.tight_layout()
    plt.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close()

    print(f"[完成] 已輸出：{out_png}")
    return out_png

def main():
    here = os.path.abspath(os.path.dirname(__file__))
    outputs = []
    for fname in TARGET_FILES:
        csv_path = os.path.join(here+"/score", fname)
        out_png = plot_one_csv(csv_path, out_dir=here+"/score/figures")
        if out_png:
            outputs.append(out_png)

    if not outputs:
        print("沒有產生任何圖。請確認 CSV 檔名與放置路徑是否正確。")

if __name__ == "__main__":
    main()
