import json
import os
import re
import ast
import uuid
from typing import Any, Dict, List, Tuple

from pipeline.s2_functions.parser import parse_signature


def _python_type_to_jsonschema(t: str, use_dict_type: bool = True) -> Dict[str, Any]:
    """Convert Python type annotation to JSON Schema.
    
    Args:
        t: Python type string (e.g., 'str', 'List[int]', 'Dict[str, Any]')
        use_dict_type: If True, use "dict" instead of "object" for dict types (trading_bot.json format)
    """
    t = t.strip()
    
    # Handle List[type] patterns
    list_match = re.match(r"List\[(.+)\]", t, re.IGNORECASE)
    if list_match:
        inner_type = list_match.group(1)
        return {"type": "array", "items": _python_type_to_jsonschema(inner_type, use_dict_type)}
    
    # Handle Dict[key, value] patterns
    dict_match = re.match(r"Dict\[(.+?),\s*(.+)\]", t, re.IGNORECASE)
    if dict_match:
        # For Dict types, we return dict type with empty properties
        # Actual properties should be defined in :return_fields:
        return {"type": "dict" if use_dict_type else "object", "properties": {}}
    
    # Basic type mapping
    type_map = {
        "str": "string",
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "double": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "list": "array",
        "dict": "dict" if use_dict_type else "object",
        "object": "dict" if use_dict_type else "object",
        "any": "string",  # fallback
    }
    
    normalized = t.lower()
    if normalized in type_map:
        result_type = type_map[normalized]
        if result_type == "array":
            return {"type": "array", "items": {"type": "string"}}  # default item type
        elif result_type in ("dict", "object"):
            return {"type": result_type}
        else:
            return {"type": result_type}
    
    # Fallback
    return {"type": "string"}


def build_tool_from_signature(signature: str) -> Dict[str, Any]:
    """Build a tool (function calling schema) from a full function snippet including docstring.

    Enhancements:
    - Extract full docstring (summary + details) as tool description.
    - Extract per-parameter descriptions from :param lines and attach to JSON Schema properties.
    - Preserve return / raises info appended to description if present.
    - Generate response schema from return type annotation.
    - Use "dict" instead of "object" for compatibility with trading_bot.json format.
    """
    parsed = parse_signature(signature)
    name = parsed.get("function_name", "unknown")
    params = parsed.get("parameters", [])
    return_type = parsed.get("return_type", "")

    # --- Docstring extraction ---
    docstring_summary_lines: List[str] = []
    param_descriptions: Dict[str, str] = {}
    return_description: str | None = None
    return_fields: Dict[str, tuple[str, str]] = {}  # field_name -> (type, description)
    raises_descriptions: List[str] = []

    # Match triple quotes (""" ... """ or ''' ... ''')
    doc_match = re.search(r'(["\"])\1\1(.*?)\1\1\1', signature, re.DOTALL)  # not reliable, fallback below
    if not doc_match:
        # Simpler explicit patterns
        doc_match = re.search(r'"""(.*?)"""', signature, re.DOTALL) or re.search(r"'''(.*?)'''", signature, re.DOTALL)

    if doc_match:
        raw_doc = doc_match.group(1) if doc_match.lastindex == 1 else doc_match.group(doc_match.lastindex) if doc_match.lastindex else doc_match.group(0)
        # If using explicit pattern raw_doc may be entire group; ensure we take inner content for explicit pattern
        if '"""' in raw_doc or "'''" in raw_doc:
            # Already full; attempt capture again
            inner = re.search(r'"""(.*?)"""', raw_doc, re.DOTALL) or re.search(r"'''(.*?)'''", raw_doc, re.DOTALL)
            if inner:
                raw_doc = inner.group(1)
        lines = [l.rstrip() for l in raw_doc.splitlines()]
        
        in_return_fields = False
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                continue
            
            # Check for :return_fields: section
            if stripped.startswith(':return_fields:'):
                in_return_fields = True
                continue
            
            # Parse return field lines (format: "- field_name (type): description")
            if in_return_fields:
                # Stop if we hit another section
                if stripped.startswith(':'):
                    in_return_fields = False
                else:
                    # Match pattern: - field_name (type): description
                    field_match = re.match(r'-\s+(\w+)\s*\(([^)]+)\)\s*:\s*(.+)', stripped)
                    if field_match:
                        field_name = field_match.group(1)
                        field_type = field_match.group(2).strip()
                        field_desc = field_match.group(3).strip()
                        return_fields[field_name] = (field_type, field_desc)
                        continue
            
            param_m = re.match(r':param\s+(\w+)\s*:\s*(.+)', stripped)
            if param_m:
                p_name = param_m.group(1)
                p_desc = param_m.group(2).strip()
                param_descriptions[p_name] = p_desc
                continue
            return_m = re.match(r':return:\s*(.+)', stripped)
            if return_m:
                return_description = return_m.group(1).strip()
                continue
            raises_m = re.match(r':raises\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.+)', stripped)
            if raises_m:
                raises_descriptions.append(f"{raises_m.group(1)}: {raises_m.group(2).strip()}")
                continue
            # Normal descriptive line (only if not in return_fields section)
            if not in_return_fields:
                docstring_summary_lines.append(stripped)

    # Build combined description
    description_parts: List[str] = []
    if docstring_summary_lines:
        description_parts.append(" ".join(docstring_summary_lines).strip())
    if return_description:
        description_parts.append(f"Return: {return_description}")
    if raises_descriptions:
        description_parts.append("Raises: " + "; ".join(raises_descriptions))
    full_description = " \n".join(description_parts) if description_parts else f"Function {name}."

    # --- Build properties ---
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for p_name, p_type, p_default in params:
        prop_schema = _python_type_to_jsonschema(p_type, use_dict_type=True)
        p_desc = param_descriptions.get(p_name)
        if p_desc:
            prop_schema["description"] = p_desc
        properties[p_name] = prop_schema
        if p_default is None:
            required.append(p_name)

    # --- Build response schema from return type and return_fields ---
    response_schema: Dict[str, Any] = {"type": "dict", "properties": {}}
    
    if return_type and return_type.lower() not in {"none", ""}:
        # If we have detailed return_fields documentation, use it
        if return_fields:
            response_properties: Dict[str, Any] = {}
            for field_name, (field_type_str, field_desc) in return_fields.items():
                # Convert Python type string to JSON Schema
                field_schema = _python_type_to_jsonschema(field_type_str, use_dict_type=True)
                field_schema["description"] = field_desc
                response_properties[field_name] = field_schema
            
            response_schema = {
                "type": "dict",
                "properties": response_properties
            }
        else:
            # Fallback to old behavior if no return_fields documented
            return_type_schema = _python_type_to_jsonschema(return_type, use_dict_type=True)
            # If return type is dict, ensure it has properties structure
            if return_type_schema.get("type") == "dict":
                # Ensure properties field exists for dict type
                if "properties" not in return_type_schema:
                    return_type_schema["properties"] = {}
                response_schema = return_type_schema
            else:
                # Wrap non-dict return types in a result property
                response_schema = {
                    "type": "dict",
                    "properties": {
                        "result": return_type_schema
                    }
                }
            # Add return description if available (and no detailed fields)
            if return_description:
                if "properties" in response_schema and "result" in response_schema["properties"]:
                    response_schema["properties"]["result"]["description"] = return_description
                elif "description" not in response_schema:
                    response_schema["description"] = return_description

    schema = {
        "name": name,
        "description": full_description,
        "parameters": {
            "type": "dict",
            "properties": properties,
            "required": required,
        },
        "response": response_schema,
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


def json_sanitize(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable forms.

    - Ellipsis -> "..."
    - set -> list
    - tuple -> list
    - bytes -> utf-8 decoded (errors ignored)
    - Any non-serializable fallback -> str(obj)
    """
    if obj is Ellipsis:
        return "..."
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="ignore")
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [json_sanitize(v) for v in list(obj)]
    # Try JSON dump; if fails, fallback to str
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def convert(run_id: str, out_path: str | None = None) -> str:
    base_dir = os.path.join("pipeline", "data", run_id)
    functions_fp = os.path.join(base_dir, "functions.json")
    multi_turn_fp = os.path.join(base_dir, "multi_turn_queries.json")
    pseudo_fp = os.path.join(base_dir, "pseudo_functions.json")

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

    # Optional: include pseudo tools
    include_pseudo = os.getenv("INCLUDE_PSEUDO_TOOLS", "1") == "1"
    pseudo_by_index: Dict[int, List[str]] = {}
    pseudo_style_by_index: Dict[int, str] = {}
    if include_pseudo and os.path.exists(pseudo_fp):
        try:
            with open(pseudo_fp, "r", encoding="utf-8") as f:
                pseudo_data = json.load(f)
            for item in pseudo_data:
                idx = int(item.get("sample_index"))
                pseudo_by_index[idx] = item.get("pseudo_functions", [])
                pseudo_style_by_index[idx] = item.get("style", "distractor")
        except Exception:
            pseudo_by_index = {}

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

            # Optionally append pseudo tools (signatures)
            if include_pseudo and idx in pseudo_by_index:
                for psig in pseudo_by_index[idx]:
                    try:
                        parsed = parse_signature(psig)
                        name = parsed.get("function_name")
                        if not name or name in tool_names_seen:
                            continue
                        pseudo_tool = build_tool_from_signature(psig)
                        # 標記為 pseudo，方便下游區分/過濾
                        pseudo_tool["x_pseudo"] = True
                        pseudo_tool["x_pseudo_kind"] = pseudo_style_by_index.get(idx, "distractor")
                        tools.append(pseudo_tool)
                        tool_names_seen.add(name)
                    except Exception:
                        continue

            # build messages from trace allowing multiple function calls per user turn
            messages: List[Dict[str, Any]] = []
            i = 0
            n = len(trace)
            while i < n:
                item = trace[i]
                if "query" in item:
                    # Start a new user turn
                    messages.append({"role": "user", "content": item["query"]})
                    i += 1
                    # Collect one or more (function_call, tool) pairs that follow
                    tool_calls: List[Dict[str, Any]] = []
                    tool_messages: List[Dict[str, Any]] = []
                    while i < n and "function_call" in trace[i]:
                        fc_text = trace[i]["function_call"]
                        tool_text = None
                        if i + 1 < n and "tool" in trace[i + 1]:
                            tool_text = trace[i + 1]["tool"]
                        # Parse function call
                        m = CALL_RE.match(fc_text)
                        func_name = None
                        args_obj: Dict[str, Any] = {}
                        if m:
                            func_name, args_obj = parse_function_call(fc_text, name_to_param_names.get(m.group(1), []))
                        if func_name:
                            tool_calls.append({
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "arguments": args_obj,
                                }
                            })
                        if tool_text is not None:
                            tool_messages.append({"role": "tool", "content": str(tool_text)})
                        # advance past function_call and optional tool
                        i += 2 if (i + 1 < n and "tool" in trace[i + 1]) else 1
                    if tool_calls:
                        messages.append({"role": "assistant", "tool_calls": tool_calls})
                        messages.extend(tool_messages)
                else:
                    # If the structure is unexpected, advance safely
                    i += 1

            item = {
                "id": f"ex_{run_id}_{idx:06d}_{uuid.uuid4().hex[:8]}",
                "tools": tools,
                "messages": messages,
            }
            safe_item = json_sanitize(item)
            out.write(json.dumps(safe_item, ensure_ascii=False) + "\n")
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
