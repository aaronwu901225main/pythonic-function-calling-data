import argparse
import json
import os
import ast
from typing import Any, Dict, List, Tuple

from bfcl_eval.constants.executable_backend_config import (
    MULTI_TURN_FUNC_DOC_FILE_MAPPING,
)
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import (
    execute_multi_turn_func_call,
)
from bfcl_eval.constants.default_prompts import (
    DEFAULT_SYSTEM_PROMPT_FORMAT,
    DEFAULT_USER_PROMPT_FOR_ADDITIONAL_FUNCTION_PROMPTING,
    OUTPUT_FORMAT_MAPPING,
    PARAM_TYPE_MAPPING,
    PROMPT_STYLE_TEMPLATES,
    PROMPT_TEMPLATE_MAPPING,
)


DATA_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data"
)
FUNC_DOC_DIR = os.path.join(DATA_ROOT, "multi_turn_func_doc")
POSSIBLE_ANSWER_DIR = os.path.join(DATA_ROOT, "possible_answer")


def _load_json_or_ndjson(path: str) -> List[Dict[str, Any]]:
    """
    Load either a JSON array file or a NDJSON (one-json-object-per-line) file and return a list of records.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        # Try JSON array first
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            # If it's a single object, wrap it for consistency
            return [data]
        except Exception:
            pass
    # Fallback to NDJSON
    recs: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return recs


def _iter_ndjson(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_func_docs_for_classes(involved_classes: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Returns a mapping: tool_name -> tool_spec (description, parameters) aggregated across involved classes.
    Only converts parameter types from dict->object.
    """
    tools: Dict[str, Dict[str, Any]] = {}
    for cls in involved_classes:
        fn = MULTI_TURN_FUNC_DOC_FILE_MAPPING.get(cls)
        if not fn:
            continue
        path = os.path.join(FUNC_DOC_DIR, fn)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                name = rec.get("name")
                if not name:
                    continue
                desc = rec.get("description", "")
                params = rec.get("parameters", {})
                # normalize parameters JSON Schema type
                if isinstance(params, dict) and params.get("type") == "dict":
                    params = params.copy()
                    params["type"] = "object"
                tools.setdefault(name, {
                    "name": name,
                    "description": desc,
                    "parameters": params or {"type": "object", "properties": {}, "required": []},
                })
    return tools


def select_tools_for_path(all_tools: Dict[str, Dict[str, Any]], path_funcs: List[str]) -> List[Dict[str, Any]]:
    """
    path_funcs: list like ["GorillaFileSystem.ls", "GorillaFileSystem.cd", ...]
    We select unique function names in order of appearance when available in docs.
    """
    ordered_names: List[str] = []
    for qual in path_funcs:
        # path entries could be like "Class.func" or just "func"
        func = qual.split(".")[-1]
        if func not in ordered_names:
            ordered_names.append(func)
    selected: List[Dict[str, Any]] = []
    seen = set()
    for name in ordered_names:
        spec = all_tools.get(name)
        if not spec or name in seen:
            continue
        selected.append(spec)
        seen.add(name)
    return selected


def _extract_used_tool_names(ground_truth: List[List[str]]) -> List[str]:
    """
    From the ground_truth calls (list per turn), extract function names in first-seen order.
    Each call is a python-like string; we take the identifier before '(' and strip any qualifier like Class.
    """
    seen = set()
    ordered: List[str] = []
    for turn_calls in ground_truth or []:
        for raw in turn_calls or []:
            name = str(raw).split("(")[0].split(".")[-1].strip()
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


def _ast_to_py(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_ast_to_py(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return [_ast_to_py(elt) for elt in node.elts]
    if isinstance(node, ast.Dict):
        return { _ast_to_py(k): _ast_to_py(v) for k, v in zip(node.keys, node.values) }
    if isinstance(node, ast.Name):
        # allow literals like True/False/None and simple names (fallback to string)
        if node.id in ("True", "False", "None"):
            return eval(node.id)
        return node.id
    # Strings wrapped as JoinedStr or BinOp concatenations are rare; fallback to string repr
    try:
        return ast.literal_eval(node)
    except Exception:
        return str(ast.unparse(node)) if hasattr(ast, "unparse") else str(node)


def parse_call(call_str: str, param_order: List[str] | None = None) -> Tuple[str, Dict[str, Any]]:
    """
    Parse a python-like function call string (e.g., "cd(folder='docs')" or "cd('docs')")
    into (func_name, arguments dict). When positional args appear, map them to param_order.
    """
    expr = ast.parse(call_str, mode="eval")
    if not isinstance(expr.body, ast.Call):
        raise ValueError(f"Not a call: {call_str}")
    func_node = expr.body.func
    if isinstance(func_node, ast.Attribute):
        func_name = func_node.attr
    elif isinstance(func_node, ast.Name):
        func_name = func_node.id
    else:
        func_name = str(call_str.split("(")[0])

    args: Dict[str, Any] = {}
    # keyword args first
    for kw in expr.body.keywords:
        if kw.arg is None:  # **kwargs (not expected)
            continue
        args[kw.arg] = _ast_to_py(kw.value)

    # positional args mapping
    if expr.body.args:
        if not param_order:
            # If unknown, assign generic keys p1, p2... to preserve values
            for i, a in enumerate(expr.body.args):
                args[f"arg{i+1}"] = _ast_to_py(a)
        else:
            for i, a in enumerate(expr.body.args):
                if i < len(param_order):
                    args[param_order[i]] = _ast_to_py(a)
                else:
                    args[f"arg{i+1}"] = _ast_to_py(a)
    return func_name, args


def get_param_order_for_tool(tool_spec: Dict[str, Any]) -> List[str]:
    params = tool_spec.get("parameters") or {}
    props = params.get("properties", {})
    # maintain insertion order of properties
    order = list(props.keys())
    if not order:
        return []
    return order


def build_messages_for_entry(entry: Dict[str, Any], ground_truth: List[List[str]], tools_index: Dict[str, Dict[str, Any]], system_prompt: str | None = None) -> List[Dict[str, Any]]:
    """
    Build clarify-style messages:
    - For each user turn: add user message
    - Add assistant with tool_calls (one message per turn including all calls in that turn)
    - Execute calls to produce tool messages (one tool message per call)
    - Add a brief assistant natural-language acknowledgement per turn
    """
    messages: List[Dict[str, Any]] = []
    question_turns = entry.get("question", [])
    initial_config = entry.get("initial_config", {})
    involved_classes = entry.get("involved_classes", [])
    test_entry_id = entry.get("id")
    # Insert BFCL-style system prompt at the very beginning if provided
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Execute per turn to generate outputs using provided evaluator
    model_name = "clarify_converter"
    # Align with BFCL: decide long_context from id/category keywords
    long_context = (
        (test_entry_id or "") and (
            ("long_context" in test_entry_id) or ("composite" in test_entry_id)
        )
    )

    missed_map: Dict[str, List[str]] = entry.get("missed_function", {}) or {}

    for t_idx, turn in enumerate(question_turns):
        # user content: expect list of message dicts; take the first user content
        user_msg = None
        for m in turn:
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        if user_msg is None:
            # fallback: concatenate all contents
            user_msg = "\n".join([m.get("content", "") for m in turn])

        # Missed-Function（Prompting 規則）：在指定回合把「新增函式文件清單」以純文字貼到該輪 user 訊息
        miss_funcs = missed_map.get(str(t_idx))
        if miss_funcs:
            missed_specs: List[Dict[str, Any]] = []
            for nm in miss_funcs:
                spec = tools_index.get(nm) or tools_index.get(nm.split(".")[-1])
                if spec:
                    missed_specs.append(spec)
            if missed_specs:
                functions_text = json.dumps(missed_specs, ensure_ascii=False, indent=2)
                user_msg = DEFAULT_USER_PROMPT_FOR_ADDITIONAL_FUNCTION_PROMPTING.format(
                    functions=functions_text
                )
        messages.append({"role": "user", "content": user_msg})

        # prepare calls for this turn
        calls_this_turn = ground_truth[t_idx] if t_idx < len(ground_truth) else []
        tool_calls_payload = []
        parsed_calls: List[Tuple[str, Dict[str, Any], str]] = []  # (name, args, raw)
        for raw in calls_this_turn:
            try:
                raw_str = raw.strip()
                # find parameter order from tool spec if present
                # We must look up by function name only
                tmp_name = raw_str.split("(")[0].split(".")[-1]
                param_order = get_param_order_for_tool(tools_index.get(tmp_name, {}))
                fname, fargs = parse_call(raw_str, param_order)
            except Exception:
                # if parsing fails, fallback to raw as a single string argument
                fname = raw.split("(")[0].split(".")[-1]
                fargs = {"__raw": raw}
            parsed_calls.append((fname, fargs, raw))
            tool_calls_payload.append({
                "type": "function",
                "function": {
                    "name": fname,
                    "arguments": fargs,
                },
            })

        if tool_calls_payload:
            messages.append({"role": "assistant", "tool_calls": tool_calls_payload})

        # Execute raw calls to produce tool outputs
        if calls_this_turn:
            exec_outputs, _ = execute_multi_turn_func_call(
                func_call_list=calls_this_turn,
                initial_config=initial_config,
                involved_classes=involved_classes,
                model_name=model_name,
                test_entry_id=test_entry_id,
                long_context=long_context,
                is_evaL_run=False,
            )
            for out in exec_outputs:
                # Ensure tool content is a JSON string
                tool_content: str
                try:
                    # If out is already JSON, keep as-is string
                    json.loads(out)
                    tool_content = out
                except Exception:
                    tool_content = json.dumps({"result": out})
                messages.append({"role": "tool", "content": tool_content})

        # Add a short assistant acknowledgement for the turn
        if tool_calls_payload:
            executed_names = ", ".join([c[0] for c in parsed_calls])
            messages.append({
                "role": "assistant",
                "content": f"已執行工具：{executed_names}。",
            })

    return messages


def convert_file(input_dataset: str, input_possible_answer: str, output_jsonl: str):
    data = _load_json_or_ndjson(input_dataset)
    gt_map = {e.get("id"): e.get("ground_truth", []) for e in _load_json_or_ndjson(input_possible_answer)}

    with open(output_jsonl, "w", encoding="utf-8") as out_f:
        for entry in data:
            entry_id = entry.get("id")
            involved_classes = entry.get("involved_classes", [])
            path_funcs = entry.get("path", [])

            # tools index across involved classes
            all_tools_index = load_func_docs_for_classes(involved_classes)
            # Prefer tools actually used in ground_truth calls to ensure completeness (e.g., cd/ls/mkdir)
            ground_truth = gt_map.get(entry_id, [])
            used_names = _extract_used_tool_names(ground_truth)
            # Fallback/extend with names from path when available
            for qual in path_funcs:
                nm = qual.split(".")[-1]
                if nm not in used_names:
                    used_names.append(nm)
            # Build ordered tools list based on used_names; include only those we have specs for
            tools: List[Dict[str, Any]] = []
            seen_tools = set()
            for nm in used_names:
                spec = all_tools_index.get(nm)
                if spec and nm not in seen_tools:
                    tools.append(spec)
                    seen_tools.add(nm)
            # If still empty (edge case), include all available tools for involved classes
            if not tools and all_tools_index:
                tools = list(all_tools_index.values())

            # Compose BFCL-style system prompt using all available tool docs (lightweight, local)
            def _parse_prompt_variation_params_local(cfg: str) -> tuple[str, bool, str, str, str]:
                parts = dict(item.split("=", 1) for item in cfg.split("&"))
                return (
                    parts.get("ret_fmt", "python"),
                    parts.get("tool_call_tag", "False") == "True",
                    parts.get("func_doc_fmt", "json"),
                    parts.get("prompt_fmt", "plaintext"),
                    parts.get("style", "classic"),
                )

            def _format_function_doc_local(funcs: List[Dict[str, Any]], fmt: str) -> str:
                # For our datasets, default is json；其餘格式在此輕量支援為 JSON。
                return json.dumps(funcs, ensure_ascii=False, indent=4)

            def _compose_system_prompt_local(cfg: str, funcs: List[Dict[str, Any]]) -> str:
                ret_fmt, has_tag, func_doc_fmt, prompt_fmt, style_key = _parse_prompt_variation_params_local(cfg)
                formatted_funcs = _format_function_doc_local(funcs, func_doc_fmt)
                prompt_template = PROMPT_TEMPLATE_MAPPING.get(prompt_fmt, PROMPT_TEMPLATE_MAPPING["plaintext"])
                style_template = PROMPT_STYLE_TEMPLATES.get(style_key, PROMPT_STYLE_TEMPLATES["classic"])

                persona = style_template["persona"]
                task = style_template["task"]
                if has_tag:
                    tool_call_format = style_template["tool_call_with_tag"].format(
                        output_format=OUTPUT_FORMAT_MAPPING[ret_fmt],
                        param_types=PARAM_TYPE_MAPPING[ret_fmt],
                    )
                else:
                    tool_call_format = style_template["tool_call_no_tag"].format(
                        output_format=OUTPUT_FORMAT_MAPPING[ret_fmt],
                        param_types=PARAM_TYPE_MAPPING[ret_fmt],
                    )
                multiturn_behavior = style_template["multiturn_behavior"]
                available_tools = style_template["available_tools"].format(
                    format=func_doc_fmt,
                    functions=formatted_funcs,
                )

                system_prompt_local = prompt_template.format(
                    persona=persona,
                    task=task,
                    tool_call_format=tool_call_format,
                    multiturn_behavior=multiturn_behavior,
                    available_tools=available_tools,
                )
                return system_prompt_local

            all_function_docs = list(all_tools_index.values()) if all_tools_index else []
            system_prompt = _compose_system_prompt_local(DEFAULT_SYSTEM_PROMPT_FORMAT, all_function_docs)

            # messages
            messages = build_messages_for_entry(entry, ground_truth, all_tools_index, system_prompt)

            obj = {
                "id": entry_id,
                "tools": tools,
                "messages": messages,
                "label_kind": "full",
            }
            out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Convert BFCL multi-turn dataset to clarify_eng.jsonl schema")
    parser.add_argument("--dataset", required=False, default=os.path.join(DATA_ROOT, "BFCL_v4_multi_turn_base.json"), help="Input dataset JSON path")
    parser.add_argument("--possible_answer", required=False, default=os.path.join(POSSIBLE_ANSWER_DIR, "BFCL_v4_multi_turn_base.json"), help="Possible answer JSON path containing ground_truth")
    parser.add_argument("--output", required=False, default=os.path.join(os.path.dirname(DATA_ROOT), "multi-turn-example", "bfcl_multi_turn_clarify.jsonl"), help="Output JSONL path")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    convert_file(args.dataset, args.possible_answer, args.output)
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
