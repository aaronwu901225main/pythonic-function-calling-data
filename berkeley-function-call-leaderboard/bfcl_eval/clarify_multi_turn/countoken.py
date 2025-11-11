#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# python pipeline/countoken/countoken.py --input pipeline/data/087190226fd447b5b4595971dc8a8728/multi_turn_eng.jsonl --bin_size 50
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
    # 舊參數（僅用於文字輸出之區間統計），保留相容性
    ap.add_argument("--bin_size", type=int, default=50, help="區間大小 (僅影響文字區間統計，作圖將改用 --bins；預設 50)")
    # 新參數：與 stats_last_column_last_value.py 對齊的作圖邏輯
    ap.add_argument("--bins", type=int, default=30, help="直方圖桶數（預設 30）")
    ap.add_argument(
        "--model",
        type=str,
        default="Salesforce/Llama-xLAM-2-8b-fc-r",
        help="用於渲染與分詞的模型（預設 Salesforce/Llama-xLAM-2-8b-fc-r）",
    )
    ap.add_argument(
        "--render",
        type=str,
        default="chat_template",
        choices=["chat_template", "salesforce_llama"],
        help="渲染策略：chat_template 走 tokenizer.apply_chat_template；salesforce_llama 走與 SalesforceLlamaHandler 相同的手動 prompt 格式化",
    )
    # 舊參數：保留但將不再用於作圖（請改用 --out）
    ap.add_argument(
        "--output",
        type=str,
        default=None,
        help="[已過時] 作圖請改用 --out；此參數將被忽略",
    )
    ap.add_argument(
        "--out",
        type=str,
        default=None,
        help="輸出圖檔路徑（預設 <輸入檔名無副檔名>_hist.png 存於同資料夾）",
    )
    ap.add_argument(
        "--title",
        type=str,
        default=None,
        help="圖表標題（預設以輸入檔名推導）",
    )
    ap.add_argument(
        "--no-plot",
        action="store_true",
        help="僅輸出統計資訊，不產生圖檔",
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

    def format_prompt_salesforce_llama(messages, tools):
        """復刻 berkeley-function-call-leaderboard/bfcl_eval/model_handler/local_inference/salesforce_llama.py::_format_prompt。

        - 以 <|begin_of_text|> 開頭
        - system 區塊包含固定工具使用說明，並把所有工具 schema 以 JSON 列出
        - 對話訊息：
          * role == tool -> ipython 區塊，內容若為 dict/list 轉 JSON
          * 存在 tool_calls -> assistant 區塊，內容為 [{name, arguments}, ...] JSON 陣列，arguments 嘗試 json.loads
          * 其餘 -> 一般 role 區塊，內容 strip
        - 以 assistant header 結尾，作為生成起點
        """
        formatted = "<|begin_of_text|>"

        system_message = "You are a helpful assistant that can use tools. You are developed by Salesforce xLAM team."
        remaining = messages
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            system_message = str(messages[0].get("content", "")).strip()
            remaining = messages[1:]

        # system 區塊 + 工具說明
        formatted += "<|start_header_id|>system<|end_header_id|>\n\n"
        formatted += system_message + "\n"
        formatted += "You have access to a set of tools. When using tools, make calls in a single JSON array: \n\n"
        formatted += '[{"name": "tool_call_name", "arguments": {"arg1": "value1", "arg2": "value2"}}, ... (additional parallel tool calls as needed)]\n\n'
        formatted += (
            "If no tool is suitable, state that explicitly. If the user's input lacks required parameters, ask for clarification. "
        )
        formatted += (
            "Do not interpret or respond until tool results are returned. Once they are available, process them or make additional calls if needed. "
        )
        formatted += (
            "For tasks that don't require tools, such as casual conversation or general advice, respond directly in plain text. The available tools are:\n\n"
        )

        tools = tools or []
        for func in tools:
            try:
                formatted += json.dumps(func, indent=4, ensure_ascii=False) + "\n\n"
            except Exception:
                formatted += _safe_json_dumps(func) + "\n\n"
        formatted += "<|eot_id|>"

        # 對話訊息
        for m in remaining:
            if not isinstance(m, dict):
                # 防禦：轉字串
                formatted += f"<|start_header_id|>user<|end_header_id|>\n\n{str(m).strip()}<|eot_id|>"
                continue

            role = m.get("role")
            if role == "tool":
                formatted += "<|start_header_id|>ipython<|end_header_id|>\n\n"
                c = m.get("content")
                if isinstance(c, (dict, list)):
                    formatted += _safe_json_dumps(c)
                else:
                    formatted += str(c) if c is not None else ""
                formatted += "<|eot_id|>"
            elif "tool_calls" in m and m.get("tool_calls"):
                formatted += "<|start_header_id|>assistant<|end_header_id|>\n\n"
                arr = []
                for tc in (m.get("tool_calls") or []):
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    args = fn.get("arguments")
                    # 將字串 arguments 嘗試轉回 dict
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            pass
                    arr.append({"name": name, "arguments": args})
                formatted += _safe_json_dumps(arr) + "<|eot_id|>"
            else:
                content = str(m.get("content", "")).strip()
                formatted += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"

        formatted += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        return formatted

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
                    tools = obj.get("tools")
                    if args.render == "chat_template":
                        tools_norm = normalize_tools_for_chat_template(tools)
                        # 嘗試正規化後以 chat template 渲染
                        try:
                            norm_msgs = normalize_messages_for_chat_template(messages)
                            token_ids = tokenizer.apply_chat_template(
                                norm_msgs,
                                tools=tools_norm,
                                tokenize=True,
                                add_generation_prompt=False,
                            )
                            counts.append(len(token_ids))
                            parsed_rows += 1
                        except Exception:
                            # 不使用 fallback：渲染失敗直接計入壞掉筆數
                            bad_rows += 1
                    else:
                        # salesforce_llama 手動渲染，盡量與實際推論一致
                        try:
                            formatted = format_prompt_salesforce_llama(messages, tools)
                            token_ids = tokenizer.encode(formatted)
                            counts.append(len(token_ids))
                            parsed_rows += 1
                        except Exception:
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

    # 作圖邏輯改為與 stats_last_column_last_value.py 一致
    if args.no_plot:
        return

    # 在無桌面環境時切換到 Agg 後端，避免 import pyplot 失敗
    try:
        import matplotlib
        if not args.show:
            matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"⚠️ 無法載入繪圖套件 matplotlib，略過作圖：{e}")
        return

    # 字型設定（保留中文相容處理）
    font_path = "/home/at0842/aaronwu901225master.ai13/fonts/Microsoft JhengHei Regular/Microsoft JhengHei Regular.ttf"
    if os.path.exists(font_path):
        from matplotlib import font_manager
        font_manager.fontManager.addfont(font_path)
        font_prop = font_manager.FontProperties(fname=font_path)
        family_name = font_prop.get_name()
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
        plt.rcParams['font.sans-serif'] = [
            'Noto Sans CJK TC',
            'Source Han Sans TC',
            'WenQuanYi Zen Hei',
            'DejaVu Sans',
        ]
    plt.rcParams['axes.unicode_minus'] = False

    # 統計值（與對齊的腳本相同：min/max/mean）
    v_min = min(counts)
    v_max = max(counts)
    v_mean = sum(counts) / len(counts)

    # 輸出圖檔路徑
    if args.out:
        out_path = args.out
    else:
        base = os.path.splitext(os.path.basename(args.input))[0]
        out_dir = os.path.dirname(args.input) or "."
        out_path = os.path.join(out_dir, f"{base}_hist.png")

    # 建立直方圖（bins 為桶數，而非寬度）
    plt.figure(figsize=(8, 5))
    plt.hist(counts, bins=max(1, args.bins), color="#81730DFF", edgecolor="white")
    plt.xlabel("token_count")
    plt.ylabel("Count")
    plt.grid(True, axis="y", alpha=0.25)
    title = args.title or os.path.splitext(os.path.basename(args.input))[0]
    plt.title(title)

    # 註記統計資訊
    text = f"n={len(counts)}\nmin={v_min:.2f}\nmax={v_max:.2f}\nmean={v_mean:.2f}"
    plt.gcf().text(
        0.965,
        0.9,
        text,
        ha="right",
        va="top",
        fontsize=12,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.7),
    )

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"\n🖼️ 已輸出圖檔: {out_path}")

    if args.show:
        try:
            plt.show()
        except Exception:
            pass

if __name__ == "__main__":
    main()
