#!/usr/bin/env python3
import json
import argparse
import random
from typing import Dict, Any, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Per-sample tool merge: 保留原本每題的 tools，"
            "再從其他題目隨機補工具直到接近 token 上限。"
        )
    )
    p.add_argument("--input", required=True, help="來源 multi_turn_eng.jsonl")
    p.add_argument("--output", required=True, help="輸出 merged jsonl")
    p.add_argument("--include-pseudo", action="store_true", help="是否包含 x_pseudo 工具")
    p.add_argument("--seed", type=int, default=None, help="亂數種子（可重現）")
    p.add_argument(
        "--token-budget",
        type=int,
        default=0,
        help="tools 區段預算 token 上限，0 代表不限制（仍會隨機補滿所有候選）",
    )
    return p.parse_args()


def _estimate_tokens_for_sample(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> int:
    """粗略估算「題目(messages) + tools」會吃掉多少 token。

    做法：把 {"messages": messages, "tools": tools} 轉成 JSON 字串，
    取長度除以 4 當近似值。這不是精確值，但足夠用來避免明顯超標。
    """

    payload = {"messages": messages, "tools": tools}
    s = json.dumps(payload, ensure_ascii=False)
    # 約略估計：平均 4 個字元 ≈ 1 token
    return max(1, len(s) // 4)


def load_all_lines(path: str) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            lines.append(obj)
    return lines


def build_global_tool_pool(lines: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """建立全域工具池（name -> schema），保留第一個定義。"""

    global_tools: Dict[str, Dict[str, Any]] = {}
    for obj in lines:
        for t in obj.get("tools", []):
            name = t.get("name")
            if not isinstance(name, str):
                continue
            if name in global_tools:
                continue
            if "parameters" not in t:
                t["parameters"] = {"type": "object", "properties": {}, "required": []}
            global_tools[name] = t
    return global_tools


def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    lines = load_all_lines(args.input)
    global_tools = build_global_tool_pool(lines)

    print(f"[INFO] total samples={len(lines)} global unique tools={len(global_tools)}")

    written = 0
    with open(args.output, "w", encoding="utf-8") as out_f:
        for idx, obj in enumerate(lines):
            original_tools: List[Dict[str, Any]] = obj.get("tools") or []

            # 1. 保留原本這一題的 tools（去重 by name）
            base_tools_by_name: Dict[str, Dict[str, Any]] = {}
            for t in original_tools:
                name = t.get("name")
                if not isinstance(name, str):
                    continue
                if name in base_tools_by_name:
                    continue
                if "parameters" not in t:
                    t["parameters"] = {"type": "object", "properties": {}, "required": []}
                # 移除 pseudo 標記，避免影響下游
                cleaned = dict(t)
                cleaned.pop("x_pseudo", None)
                cleaned.pop("x_pseudo_kind", None)
                base_tools_by_name[name] = cleaned

            base_tools: List[Dict[str, Any]] = list(base_tools_by_name.values())

            # 2. 準備候選池：其他題目的工具
            candidate_tools: List[Dict[str, Any]] = []
            for name, schema in global_tools.items():
                if name in base_tools_by_name:
                    continue  # 已經在本題
                is_pseudo = bool(schema.get("x_pseudo"))
                if is_pseudo and not args.include_pseudo:
                    continue
                # 移除 pseudo 標記，僅作為一般工具加入候選
                cleaned = dict(schema)
                cleaned.pop("x_pseudo", None)
                cleaned.pop("x_pseudo_kind", None)
                candidate_tools.append(cleaned)

            random.shuffle(candidate_tools)

            # 3. 若沒有 token 預算，直接 base + 所有候選
            if args.token_budget and args.token_budget > 0:
                merged_tools: List[Dict[str, Any]] = list(base_tools)
                current_tokens = _estimate_tokens_for_sample(
                    obj.get("messages") or [], merged_tools
                )

                if current_tokens > args.token_budget:
                    # 連原本 tools 加起來都超過預算，只保留原本 tools
                    print(
                        f"[WARN] sample {idx} base_tools tokens={current_tokens} "
                        f"> budget={args.token_budget}, no extra tools added."
                    )
                else:
                    for t in candidate_tools:
                        merged_tools.append(t)
                        new_tokens = _estimate_tokens_for_sample(
                            obj.get("messages") or [], merged_tools
                        )
                        if new_tokens > args.token_budget:
                            # 超出預算，撤回這個並停止
                            merged_tools.pop()
                            break
                        current_tokens = new_tokens
            else:
                # 不限制 token，就 base + 全部候選
                merged_tools = list(base_tools) + candidate_tools

            # 最終打亂整體順序，避免固定把本題工具排在前面
            random.shuffle(merged_tools)
            obj["tools"] = merged_tools
            out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1

    print(
        f"[DONE] Wrote {written} lines -> {args.output} "
        f"(token_budget={args.token_budget}, include_pseudo={args.include_pseudo})"
    )


if __name__ == "__main__":
    main()