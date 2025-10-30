import json
import os
import re
import ast
import uuid
from typing import Any, Dict, List, Tuple

from pipeline.s2_functions.parser import parse_signature


def _python_type_to_jsonschema(t: str) -> Dict[str, Any]:
    t = t.strip()
    # Basic mapping
    if t.lower() in {"str", "string"}:
        return {"type": "string"}
    if t.lower() in {"int", "integer"}:
        return {"type": "integer"}
    if t.lower() in {"float", "double", "number"}:
        return {"type": "number"}
    if t.lower() in {"bool", "boolean"}:
        return {"type": "boolean"}
    if t.lower().startswith("list[") or t.lower() == "list":
        # extract inner type if any
        inner = "string"
        m = re.match(r"list\[([^\]]+)\]", t, flags=re.IGNORECASE)
        if m:
            inner = m.group(1)
        return {"type": "array", "items": _python_type_to_jsonschema(inner)}
    if t.lower().startswith("dict[") or t.lower() == "dict":
        # Generic object
        return {"type": "object"}
    # Fallback
    return {"type": "string"}


def build_tool_from_signature(signature: str) -> Dict[str, Any]:
    parsed = parse_signature(signature)
    name = parsed.get("function_name", "unknown")
    params = parsed.get("parameters", [])

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for p_name, p_type, p_default in params:
        properties[p_name] = _python_type_to_jsonschema(p_type)
        if p_default is None:
            required.append(p_name)

    schema = {
        "name": name,
        "description": f"Auto-generated tool for function {name}",
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
    return schema


CALL_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\((.*)\)\s*$", re.DOTALL)


def _split_args(arg_str: str) -> List[str]:
    parts: List[str] = []
    buf = []
    depth = 0
    in_str: str | None = None
    i = 0
    while i < len(arg_str):
        ch = arg_str[i]
        if in_str:
            buf.append(ch)
            if ch == in_str and arg_str[i - 1] != "\\":
                in_str = None
        else:
            if ch in ("'", '"'):
                in_str = ch
                buf.append(ch)
            elif ch in "([{":
                depth += 1
                buf.append(ch)
            elif ch in ")]}":
                depth -= 1
                buf.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def parse_function_call(call: str, param_names: List[str]) -> Tuple[str, Dict[str, Any]]:
    m = CALL_RE.match(call)
    if not m:
        # Fallback: no parse
        return call.strip(), {}
    name, args_str = m.group(1), m.group(2)

    # Try AST for robust parsing
    try:
        node = ast.parse(f"f({args_str})", mode="eval")
        if not isinstance(node.body, ast.Call):
            raise ValueError("not a call")
        call_node: ast.Call = node.body  # type: ignore
        args_out: Dict[str, Any] = {}
        # positional
        for i, arg in enumerate(call_node.args):
            if i < len(param_names):
                try:
                    args_out[param_names[i]] = ast.literal_eval(arg)
                except Exception:
                    args_out[param_names[i]] = ast.unparse(arg) if hasattr(ast, "unparse") else str(arg)
        # keywords
        for kw in call_node.keywords:
            key = kw.arg if kw.arg is not None else None
            if key is None:
                continue
            try:
                args_out[key] = ast.literal_eval(kw.value)
            except Exception:
                args_out[key] = ast.unparse(kw.value) if hasattr(ast, "unparse") else str(kw.value)
        return name, args_out
    except Exception:
        # Fallback manual split
        args_out: Dict[str, Any] = {}
        parts = _split_args(args_str)
        pos_idx = 0
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                args_out[k.strip()] = v.strip().strip("'\"")
            else:
                if pos_idx < len(param_names):
                    args_out[param_names[pos_idx]] = part.strip().strip("'\"")
                    pos_idx += 1
        return name, args_out


def convert(run_id: str, out_path: str | None = None) -> str:
    base_dir = os.path.join("pipeline", "data", run_id)
    functions_fp = os.path.join(base_dir, "functions.json")
    multi_turn_fp = os.path.join(base_dir, "multi_turn_queries.json")

    if not os.path.exists(functions_fp) or not os.path.exists(multi_turn_fp):
        raise FileNotFoundError("Required files not found. Make sure functions.json and multi_turn_queries.json exist.")

    with open(functions_fp, "r", encoding="utf-8") as f:
        functions_data = json.load(f)

    # Build function signature map: name -> signature
    name_to_sig: Dict[str, str] = {}
    name_to_param_names: Dict[str, List[str]] = {}

    for entry in functions_data:
        for func in entry.get("functions", []):
            sig = func["function"]
            parsed = parse_signature(sig)
            name = parsed.get("function_name")
            if not name:
                continue
            name_to_sig[name] = sig
            name_to_param_names[name] = [p[0] for p in parsed.get("parameters", [])]

    with open(multi_turn_fp, "r", encoding="utf-8") as f:
        multi_turn_data = json.load(f)

    if out_path is None:
        out_path = os.path.join(base_dir, "multi_turn_eng.jsonl")

    written = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for idx, sample in enumerate(multi_turn_data):
            trace: List[Dict[str, str]] = sample.get("trace", [])
            function_schemas: List[str] = sample.get("function_schemas", [])

            # tools from function_schemas
            tools: List[Dict[str, Any]] = []
            tool_names_seen = set()
            for sig in function_schemas:
                parsed = parse_signature(sig)
                name = parsed.get("function_name")
                if not name or name in tool_names_seen:
                    continue
                tools.append(build_tool_from_signature(sig))
                tool_names_seen.add(name)

            # build messages from trace triples
            messages: List[Dict[str, Any]] = []
            # iterate in steps of 3: query, function_call, tool
            i = 0
            while i < len(trace):
                t = trace[i:i+3]
                if len(t) < 2:
                    break
                q = t[0].get("query") if "query" in t[0] else None
                fc = None
                tool_resp = None
                if len(t) >= 2:
                    fc = t[1].get("function_call") if "function_call" in t[1] else None
                if len(t) >= 3:
                    tool_resp = t[2].get("tool") if "tool" in t[2] else None

                if q:
                    messages.append({"role": "user", "content": q})
                if fc:
                    m = CALL_RE.match(fc)
                    func_name = None
                    args_obj: Dict[str, Any] = {}
                    if m:
                        func_name, args_obj = parse_function_call(fc, name_to_param_names.get(m.group(1), []))
                        # parse_function_call returns name, args
                    # Build assistant with tool_calls
                    if func_name:
                        messages.append({
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": func_name,
                                        "arguments": args_obj,
                                    }
                                }
                            ]
                        })
                if tool_resp is not None:
                    # Tool responses are strings or JSON-like
                    # Keep as string
                    messages.append({"role": "tool", "content": str(tool_resp)})
                i += 3

            item = {
                "id": f"ex_{run_id}_{idx:06d}_{uuid.uuid4().hex[:8]}",
                "tools": tools,
                "messages": messages,
                "label_kind": "full",
            }
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
            written += 1
    return out_path


if __name__ == "__main__":
    # Auto-detect run_id file
    run_id_fp = os.path.join(os.getcwd(), "run_id")
    if not os.path.exists(run_id_fp):
        raise SystemExit("run_id file not found. Please create one or pass run_id explicitly by editing the script.")
    with open(run_id_fp, "r", encoding="utf-8") as f:
        run_id = f.read().strip()
    out = convert(run_id)
    print(f"Wrote: {out}")
