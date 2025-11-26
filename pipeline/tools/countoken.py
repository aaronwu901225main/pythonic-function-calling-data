#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# python pipeline/countoken/countoken.py --input pipeline/data/087190226fd447b5b4595971dc8a8728/multi_turn_eng.jsonl --bin_size 50
# python pipeline/countoken/countoken.py --input /home/at0842/aaronwu901225master.ai13/gorilla/berkeley-function-call-leaderboard/bfcl_eval/clarify_multi_turn/bfcl_multi_turn_long_context_en.jsonl --bin_size 50
# 說明：
# 1) 若輸入 JSONL 每列含有 text 欄位，直接以 text 計數。
# 2) 若輸入 JSONL 每列含有 messages（與可選 tools），會在記憶體中用 chat template 渲染後直接計數，無需輸出中間檔。
#    若發現 assistant.tool_calls 的 arguments 為 dict，程式會自動轉為 JSON 字串以提升相容性。

import argparse
import json
import os
from collections import Counter
from statistics import median
from transformers import AutoTokenizer
import math
import copy

def _safe_json_dumps(obj):
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        # 退而求其次的轉字串
        return str(obj)

def normalize_messages_for_chat_template(messages):
    """將 messages 正規化，以符合常見 chat template 的預期格式。

    - 將 tool_calls 中 function.arguments 若為 dict 轉為 JSON 字串
    - 自動補齊缺少的必要欄位（若 chat template 需要時較不容易出錯）
    - 不修改原輸入，傳回深拷貝
    """
    msgs = copy.deepcopy(messages)
    call_seq = 0
    pending_tool_call_ids = []  # 用於將後續 tool 回應綁定到對應的 tool_call
    for m in msgs:
        # OpenAI 風格：assistant 可能包含 tool_calls
        if isinstance(m, dict) and m.get("role") == "assistant" and "tool_calls" in m:
            tc_list = m.get("tool_calls") or []
            for tc in tc_list:
                if isinstance(tc, dict) and tc.get("type") == "function":
                    fn = tc.get("function") or {}
                    # 將 dict 轉成字串，避免 tokenizer.apply_chat_template 拒收
                    if isinstance(fn.get("arguments"), (dict, list)):
                        fn["arguments"] = _safe_json_dumps(fn["arguments"])
                    # 有些模板要求 id
                    if not tc.get("id"):
                        tc["id"] = f"call_{call_seq}"
                        call_seq += 1
                    # 收集以便下一個/幾個 tool 訊息能綁定對應 id
                    if tc.get("id"):
                        pending_tool_call_ids.append(tc["id"])
        # tool 角色：通常 content 為字串即可
        if isinstance(m, dict) and m.get("role") == "tool":
            if not isinstance(m.get("content"), str):
                m["content"] = _safe_json_dumps(m.get("content"))
            # 若缺少 tool_call_id，嘗試按順序配對到先前的 assistant.tool_calls
            if not m.get("tool_call_id") and pending_tool_call_ids:
                m["tool_call_id"] = pending_tool_call_ids.pop(0)
    return msgs

def normalize_tools_for_chat_template(tools):
    """將 tools 轉為常見 chat template 期望的 {"type":"function","function":{...}} 結構。

    - 若已是期望結構則原樣返回
    - 若為 {name, description, parameters} 形式，則包一層
    - 非法/未知類型則盡力保留資訊
    """
    if not tools:
        return tools
    norm = []
    for t in tools:
        if not isinstance(t, dict):
            # 盡力轉字串保留
            norm.append({"type": "function", "function": {"name": str(t), "description": "", "parameters": {}}})
            continue
        if t.get("type") == "function" and isinstance(t.get("function"), dict):
            norm.append(t)
        else:
            name = t.get("name") or "unknown"
            desc = t.get("description", "")
            params = t.get("parameters", {})
            norm.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params if isinstance(params, dict) else {}
                }
            })
    return norm

## 已移除 fallback_render_text：若 chat template 渲染失敗將直接計為壞掉筆數

def bucketize(n, bin_size=50):
    """把 token 數量分到區間"""
    low = (n // bin_size) * bin_size
    high = low + bin_size - 1
    return f"{low}-{high}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        type=str,
        required=True,
        help="輸入 JSONL 檔（每行含 text，或含 messages 與可選 tools 皆可）",
    )
    ap.add_argument("--bin_size", type=int, default=50, help="區間大小 (預設 50)")
    ap.add_argument(
        "--model",
        type=str,
        default="Salesforce/Llama-xLAM-2-8b-fc-r",
        help="用於渲染與分詞的模型（預設 Salesforce/Llama-xLAM-2-8b-fc-r）",
    )
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

    # 為了支援自定義 chat template，需 trust_remote_code=True
    tokenizer = AutoTokenizer.from_pretrained(
        args.model, use_fast=True, trust_remote_code=True
    )

    counts = []
    bad_rows = 0
    parsed_rows = 0
    # 不使用 fallback，渲染失敗直接計入壞掉筆數

    with open(args.input, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if "text" in obj and isinstance(obj.get("text"), str):
                    # 直接使用 text 欄位計數
                    text = obj.get("text", "")
                    token_ids = tokenizer.encode(text)
                    counts.append(len(token_ids))
                elif "messages" in obj and isinstance(obj.get("messages"), (list, tuple)):
                    messages = obj.get("messages")
                    tools = normalize_tools_for_chat_template(obj.get("tools"))
                    # 嘗試正規化後以 chat template 渲染
                    try:
                        norm_msgs = normalize_messages_for_chat_template(messages)
                        token_ids = tokenizer.apply_chat_template(
                            norm_msgs,
                            tools=tools,
                            tokenize=True,
                            add_generation_prompt=False,
                        )
                        counts.append(len(token_ids))
                        parsed_rows += 1
                    except Exception:
                        # 不使用 fallback：渲染失敗直接計入壞掉筆數
                        bad_rows += 1
                else:
                    # 資料行格式不符，計入壞掉筆數
                    bad_rows += 1
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
    print(f"總筆數: {len(counts)} (chat 成功 {parsed_rows} 筆, 壞掉 {bad_rows} 筆)")
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
    min_cnt = min(counts)
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

    # 將 x 軸下界設為所有資料的最小值，集中顯示有資料的區間
    try:
        plt.xlim(left=min_cnt-1000)
    except Exception:
        # 若設定失敗則忽略，保持預設視窗
        pass

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
