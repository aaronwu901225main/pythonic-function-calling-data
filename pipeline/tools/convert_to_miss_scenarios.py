"""
Convert miss_function and miss_param queries to the final multi-turn format.

This module handles the special structure of miss scenarios:
- miss_function: The missing function is not in the initial tool list, 
                 but the user provides it during the conversation
- miss_param: The assistant asks for missing parameters

Output format matches multi_turn_eng.jsonl but with additional metadata.
"""
import json
import os
import re
import ast
from typing import Any, Dict, List, Tuple, Optional

from pipeline.s2_functions.parser import parse_signature
from pipeline.tools.convert_to_multi_turn_eng import (
    build_tool_from_signature,
    parse_function_call,
    json_sanitize,
    CALL_RE,
    get_language,
)


# Regex pattern to remove role prefixes like "劉婷婷：", "智能助手：", "User:", "Assistant:"
ROLE_PREFIX_PATTERN = re.compile(
    r'^(?:'
    r'[\u4e00-\u9fff]{2,4}：|'  # Chinese name + colon (e.g., 劉婷婷：, 智能助手：)
    r'[A-Za-z]+\s*:\s*'         # English role + colon (e.g., User:, Assistant:)
    r')',
    re.MULTILINE
)


def strip_role_prefix(text: str) -> str:
    """Remove role prefixes like '劉婷婷：' or '智能助手：' from text."""
    if not text:
        return text
    return ROLE_PREFIX_PATTERN.sub('', text).strip()


def get_output_dir(mode: str) -> str:
    """根據模式獲取輸出子目錄名稱"""
    if mode == "miss_func":
        return "miss_func"
    elif mode == "miss_param":
        return "miss_param"
    else:
        return "base"


def get_output_filename(mode: str) -> str:
    """根據語言和模式設定獲取輸出檔名"""
    lang = get_language()
    lang_suffix = "zh_tw" if lang == "zh_tw" else "eng"
    return f"multi_turn_{mode}_{lang_suffix}.jsonl"


def convert_miss_function(run_id: str, out_path: Optional[str] = None) -> str:
    """
    Convert miss_function_queries.json to final format.
    
    Special handling:
    - Initial tools list does NOT include the missing function
    - The missing function is provided by user during conversation
    - We track which turn(s) are "miss" turns
    """
    base_dir = os.path.join("pipeline", "data", run_id)
    queries_fp = os.path.join(base_dir, "miss_function_queries.json")
    
    if not os.path.exists(queries_fp):
        raise FileNotFoundError(f"miss_function_queries.json not found at {queries_fp}")
    
    with open(queries_fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if out_path is None:
        # 輸出到 miss_func 子目錄
        output_dir = os.path.join(base_dir, get_output_dir("miss_func"))
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, get_output_filename("miss_func"))
    
    # Build param names map for parsing
    name_to_param_names: Dict[str, List[str]] = {}
    for sample in data:
        for sig in sample.get("all_function_schemas", []):
            parsed = parse_signature(sig)
            name = parsed.get("function_name")
            if name:
                name_to_param_names[name] = [p[0] for p in parsed.get("parameters", [])]
    
    written = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for idx, sample in enumerate(data):
            trace = sample.get("trace", [])
            function_schemas = sample.get("function_schemas", [])  # Initial (without missing)
            missing_function = sample.get("missing_function", "")
            all_schemas = sample.get("all_function_schemas", [])
            
            # Build initial tools (without missing function)
            tools: List[Dict[str, Any]] = []
            tool_names_seen = set()
            for sig in function_schemas:
                parsed = parse_signature(sig)
                name = parsed.get("function_name")
                if not name or name in tool_names_seen:
                    continue
                tools.append(build_tool_from_signature(sig))
                tool_names_seen.add(name)
            
            # Get missing function info
            missing_parsed = parse_signature(missing_function) if missing_function else {}
            missing_name = missing_parsed.get("function_name", "")
            missing_tool = build_tool_from_signature(missing_function) if missing_function else None
            
            # Parse trace into turns and messages
            all_messages: List[Dict[str, Any]] = []
            turns_count = 0
            miss_turn_indices: List[int] = []
            user_provided_function_turn: Optional[int] = None  # Turn where user provides the function
            
            # Keywords that indicate a "cannot fulfill" response (miss turn)
            miss_keywords_en = ["don't have", "cannot", "don't have access", "no function", "not available", 
                               "unable to", "can't", "provide the function", "provide me"]
            miss_keywords_zh = ["沒有", "無法", "不可用", "缺少", "不存在", "無法執行", "做不到", 
                               "提供函數", "提供這個函數", "提供功能", "沒有這個功能", "沒有可以"]
            
            def is_miss_response(response_text: str) -> bool:
                """Check if response indicates assistant cannot fulfill due to missing function."""
                response_lower = response_text.lower()
                for kw in miss_keywords_en + miss_keywords_zh:
                    if kw.lower() in response_lower:
                        return True
                return False
            
            def is_function_definition(query_text: str) -> bool:
                """Check if user query contains a function definition."""
                # Check for Python function signature patterns
                if "def " in query_text and "(" in query_text:
                    return True
                # Check for docstring patterns
                if '"""' in query_text or "'''" in query_text:
                    return True
                return False
            
            i = 0
            n = len(trace)
            
            while i < n:
                item = trace[i]
                if "query" in item:
                    query = strip_role_prefix(item["query"])
                    all_messages.append({"role": "user", "content": query})
                    current_turn_index = turns_count
                    turns_count += 1
                    
                    i += 1
                    turn_has_function_call = False
                    turn_response_text = ""
                    called_missing_function = False
                    
                    # Collect subsequent items for this turn
                    while i < n and ("function_call" in trace[i] or "tool" in trace[i] or "response" in trace[i]):
                        if "function_call" in trace[i]:
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
                                # Check if this is the missing function being called
                                if func_name == missing_name:
                                    called_missing_function = True
                                
                                all_messages.append({
                                    "role": "assistant",
                                    "tool_calls": [{
                                        "type": "function",
                                        "function": {
                                            "name": func_name,
                                            "arguments": args_obj,
                                        }
                                    }],
                                    "content": ""
                                })
                                turn_has_function_call = True
                            
                            if tool_text is not None:
                                all_messages.append({
                                    "role": "tool",
                                    "name": func_name if func_name else "unknown",
                                    "content": str(tool_text)
                                })
                            
                            i += 2 if (i + 1 < n and "tool" in trace[i + 1]) else 1
                        
                        elif "response" in trace[i]:
                            turn_response_text = strip_role_prefix(trace[i]["response"])
                            
                            all_messages.append({
                                "role": "assistant",
                                "content": turn_response_text
                            })
                            i += 1
                        else:
                            i += 1
                    
                    # Determine if this is a true "miss" turn
                    # Miss turn criteria:
                    # 1. No function call in this turn
                    # 2. Response indicates cannot fulfill (contains miss keywords)
                    if not turn_has_function_call and is_miss_response(turn_response_text):
                        miss_turn_indices.append(current_turn_index)
                    
                    # Check if this turn is where user provides the function definition
                    if is_function_definition(query) and called_missing_function:
                        user_provided_function_turn = current_turn_index
                else:
                    i += 1
            
            # Create output record
            record = {
                "id": f"{run_id}_miss_func_{idx:06d}",
                "sample_index": idx,
                "tools": tools,  # Initial tools (missing function NOT included)
                "missing_function_tool": missing_tool,  # The function that was missing (for merge_global_tools exclusion)
                "messages": all_messages,
                "dataset": "miss_function",
                "total_turns": turns_count,
                "miss_turn_indices": list(set(miss_turn_indices)),  # Turns where assistant couldn't fulfill
                "user_provided_function_turn": user_provided_function_turn,  # Turn where user provided the function
                "scenario_type": "miss_function",
            }
            
            safe_record = json_sanitize(record)
            out.write(json.dumps(safe_record, ensure_ascii=False) + "\n")
            written += 1
    
    print(f"Converted {written} miss_function samples -> {out_path}")
    return out_path


def convert_miss_param(run_id: str, out_path: Optional[str] = None) -> str:
    """
    Convert miss_param_queries.json to final format.
    
    Special handling:
    - Track which turn(s) have missing parameters
    - Store which parameters were missing
    """
    base_dir = os.path.join("pipeline", "data", run_id)
    queries_fp = os.path.join(base_dir, "miss_param_queries.json")
    
    if not os.path.exists(queries_fp):
        raise FileNotFoundError(f"miss_param_queries.json not found at {queries_fp}")
    
    with open(queries_fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if out_path is None:
        # 輸出到 miss_param 子目錄
        output_dir = os.path.join(base_dir, get_output_dir("miss_param"))
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, get_output_filename("miss_param"))
    
    # Build param names map
    name_to_param_names: Dict[str, List[str]] = {}
    for sample in data:
        for sig in sample.get("function_schemas", []):
            parsed = parse_signature(sig)
            name = parsed.get("function_name")
            if name:
                name_to_param_names[name] = [p[0] for p in parsed.get("parameters", [])]
    
    written = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for idx, sample in enumerate(data):
            trace = sample.get("trace", [])
            function_schemas = sample.get("function_schemas", [])
            missing_params = sample.get("missing_params", [])
            target_function = sample.get("target_function", "")
            
            # Build tools
            tools: List[Dict[str, Any]] = []
            tool_names_seen = set()
            for sig in function_schemas:
                parsed = parse_signature(sig)
                name = parsed.get("function_name")
                if not name or name in tool_names_seen:
                    continue
                tools.append(build_tool_from_signature(sig))
                tool_names_seen.add(name)
            
            # Get target function info
            target_parsed = parse_signature(target_function) if target_function else {}
            target_name = target_parsed.get("function_name", "")
            
            # Keywords that indicate assistant is asking for missing parameters
            param_ask_keywords_en = ["what", "which", "please provide", "could you", "specify", 
                                     "need to know", "tell me", "clarify", "missing"]
            param_ask_keywords_zh = ["什麼", "哪個", "請提供", "請問", "請告訴", "需要知道", 
                                     "能否提供", "能告訴", "缺少", "需要", "是什麼"]
            
            def is_asking_for_params(response_text: str) -> bool:
                """Check if response is asking for missing parameters."""
                response_lower = response_text.lower()
                # Check for question patterns
                has_question = "?" in response_text or "？" in response_text
                has_keywords = any(kw.lower() in response_lower for kw in param_ask_keywords_en + param_ask_keywords_zh)
                return has_question and has_keywords
            
            # Parse trace into messages
            all_messages: List[Dict[str, Any]] = []
            turns_count = 0
            miss_turn_indices: List[int] = []
            
            i = 0
            n = len(trace)
            
            while i < n:
                item = trace[i]
                if "query" in item:
                    query = strip_role_prefix(item["query"])
                    all_messages.append({"role": "user", "content": query})
                    current_turn_index = turns_count
                    turns_count += 1
                    
                    i += 1
                    turn_has_function_call = False
                    turn_response_text = ""
                    
                    while i < n and ("function_call" in trace[i] or "tool" in trace[i] or "response" in trace[i]):
                        if "function_call" in trace[i]:
                            fc_text = trace[i]["function_call"]
                            tool_text = None
                            if i + 1 < n and "tool" in trace[i + 1]:
                                tool_text = trace[i + 1]["tool"]
                            
                            m = CALL_RE.match(fc_text)
                            func_name = None
                            args_obj: Dict[str, Any] = {}
                            if m:
                                func_name, args_obj = parse_function_call(fc_text, name_to_param_names.get(m.group(1), []))
                            
                            if func_name:
                                all_messages.append({
                                    "role": "assistant",
                                    "tool_calls": [{
                                        "type": "function",
                                        "function": {
                                            "name": func_name,
                                            "arguments": args_obj,
                                        }
                                    }],
                                    "content": ""
                                })
                                turn_has_function_call = True
                            
                            if tool_text is not None:
                                all_messages.append({
                                    "role": "tool",
                                    "name": func_name if func_name else "unknown",
                                    "content": str(tool_text)
                                })
                            
                            i += 2 if (i + 1 < n and "tool" in trace[i + 1]) else 1
                        
                        elif "response" in trace[i]:
                            turn_response_text = strip_role_prefix(trace[i]["response"])
                            
                            all_messages.append({
                                "role": "assistant",
                                "content": turn_response_text
                            })
                            i += 1
                        else:
                            i += 1
                    
                    # Determine if this is a true "miss" turn (asking for missing params)
                    if not turn_has_function_call and is_asking_for_params(turn_response_text):
                        miss_turn_indices.append(current_turn_index)
                else:
                    i += 1
            
            # Create output record
            record = {
                "id": f"{run_id}_miss_param_{idx:06d}",
                "sample_index": idx,
                "tools": tools,
                "messages": all_messages,
                "dataset": "miss_param",
                "total_turns": turns_count,
                "miss_turn_indices": list(set(miss_turn_indices)),
                "missing_params": missing_params,
                "target_function_name": target_name,
                "scenario_type": "miss_param",
            }
            
            safe_record = json_sanitize(record)
            out.write(json.dumps(safe_record, ensure_ascii=False) + "\n")
            written += 1
    
    print(f"Converted {written} miss_param samples -> {out_path}")
    return out_path


def main():
    """Convert both miss_function and miss_param if their source files exist."""
    run_id_fp = os.path.join(os.getcwd(), "run_id")
    if not os.path.exists(run_id_fp):
        raise SystemExit("run_id file not found")
    
    with open(run_id_fp, "r", encoding="utf-8") as f:
        run_id = f.read().strip()
    
    base_dir = os.path.join("pipeline", "data", run_id)
    
    # Convert miss_function if exists
    miss_func_fp = os.path.join(base_dir, "miss_function_queries.json")
    if os.path.exists(miss_func_fp):
        try:
            convert_miss_function(run_id)
        except Exception as e:
            print(f"Error converting miss_function: {e}")
    
    # Convert miss_param if exists
    miss_param_fp = os.path.join(base_dir, "miss_param_queries.json")
    if os.path.exists(miss_param_fp):
        try:
            convert_miss_param(run_id)
        except Exception as e:
            print(f"Error converting miss_param: {e}")


if __name__ == "__main__":
    main()
