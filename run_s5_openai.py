"""
Stage 5: Generate miss_function and miss_parameter multi-turn dialogues

This module generates multi-turn dialogues with "missing" scenarios:
- miss_function: A function is initially missing from the tool list, and the user provides it later
- miss_parameter: The user omits required parameters, and the assistant asks for clarification

Environment Variables:
    LANG_CODE: Language setting ("en" or "zh_tw")
    MISS_MODE: Mode to run ("miss_function", "miss_param", or "both")
    MISS_TURNS: Number of turns that should be "miss" turns (e.g., "1" or "1-2" for range)
    S5_DEBUG: Enable debug output ("1" to enable)
    MAX_RETRIES: Maximum retries for API calls
"""
import asyncio
import json
import logging
import os
import random
import re
from typing import Any, Dict, List, Tuple, Optional
from tqdm import tqdm
from openai_utils import render_template, extract_tags, chat_complete
from pipeline.s2_functions.parser import parse_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ============================================================================
# Language utilities
# ============================================================================
def get_language() -> str:
    """獲取當前語言設定"""
    return os.getenv("LANG_CODE", "en").lower()

def get_prompt_path(base_path: str) -> str:
    """根據語言設定獲取對應的 prompt 路徑"""
    lang = get_language()
    if lang == "zh_tw":
        path_without_ext = base_path.rsplit('.', 1)[0]
        return f"{path_without_ext}_zh_tw.md"
    return base_path

def get_system_prompt_suffix() -> str:
    """根據語言設定獲取 system prompt 的語言後綴"""
    lang = get_language()
    if lang == "zh_tw":
        return " Please write all user queries in Traditional Chinese (繁體中文). Use Chinese names for people and places."
    return ""


# ============================================================================
# Debug utilities
# ============================================================================
def _write_debug(debug_enabled: bool, debug_out_path: str, record: Dict[str, Any]):
    if not debug_enabled:
        return
    try:
        os.makedirs(os.path.dirname(debug_out_path), exist_ok=True)
        with open(debug_out_path, "a", encoding="utf-8") as df:
            df.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ============================================================================
# Miss turns configuration
# ============================================================================
def parse_miss_turns(miss_turns_str: str) -> Tuple[int, int]:
    """
    Parse MISS_TURNS environment variable.
    
    Formats:
        "1" -> (1, 1)
        "1-2" -> (1, 2)
        
    Returns:
        Tuple of (min_turns, max_turns)
    """
    miss_turns_str = miss_turns_str.strip()
    if "-" in miss_turns_str:
        parts = miss_turns_str.split("-")
        return int(parts[0]), int(parts[1])
    else:
        n = int(miss_turns_str)
        return n, n


def get_miss_turns_count() -> int:
    """Get a random number of miss turns based on configuration."""
    miss_turns_str = os.getenv("MISS_TURNS", "1")
    min_turns, max_turns = parse_miss_turns(miss_turns_str)
    return random.randint(min_turns, max_turns)


# ============================================================================
# Function selection for miss scenarios
# ============================================================================
def select_missing_function(functions: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Select one function to be the "missing" function.
    
    Returns:
        Tuple of (missing_function, remaining_functions)
    """
    if len(functions) < 2:
        raise ValueError("Need at least 2 functions to create a miss_function scenario")
    
    # Prefer functions with more parameters (more useful/complex)
    candidates = sorted(functions, key=lambda f: len(parse_signature(f["function"]).get("parameters", [])), reverse=True)
    
    # Select one from top half to ensure it's useful
    top_half = candidates[:max(1, len(candidates) // 2)]
    missing = random.choice(top_half)
    
    remaining = [f for f in functions if f != missing]
    return missing, remaining


def select_function_for_miss_param(functions: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Select a function and parameters to be "missing" for miss_param scenario.
    
    Returns:
        Tuple of (target_function, missing_param_names)
    """
    # Find functions with required parameters
    candidates = []
    for func in functions:
        parsed = parse_signature(func["function"])
        params = parsed.get("parameters", [])
        required_params = [p[0] for p in params if p[2] is None]  # p[2] is default value
        if required_params:
            candidates.append((func, required_params))
    
    if not candidates:
        # Fallback: use any function with parameters
        for func in functions:
            parsed = parse_signature(func["function"])
            params = parsed.get("parameters", [])
            if params:
                candidates.append((func, [p[0] for p in params]))
    
    if not candidates:
        raise ValueError("No suitable function found for miss_param scenario")
    
    func, param_names = random.choice(candidates)
    
    # Select 1-2 parameters to be missing (but not all)
    num_missing = min(random.randint(1, 2), max(1, len(param_names) - 1))
    missing_params = random.sample(param_names, num_missing)
    
    return func, missing_params


# ============================================================================
# Dialogue parsing
# ============================================================================
def parse_dialogue(content: str) -> List[Dict[str, Any]]:
    """Parse dialogue from LLM response into structured turns."""
    traces: List[Dict[str, Any]] = []
    
    dialogue_blocks = extract_tags(content, "dialogue")
    if not dialogue_blocks:
        return traces
    
    dlg = dialogue_blocks[0]
    turn_blocks = extract_tags(dlg, "turn")
    
    for tb in turn_blocks:
        turn_trace: List[Dict[str, str]] = []
        
        q_blocks = extract_tags(tb, "query")
        if not q_blocks:
            continue
        
        turn_trace.append({"query": q_blocks[0]})
        
        # Extract function calls and tool responses
        fcs = extract_tags(tb, "function_call")
        tls = extract_tags(tb, "tool")
        responses = extract_tags(tb, "response")
        
        for c, t in zip(fcs, tls):
            turn_trace.append({"function_call": c})
            turn_trace.append({"tool": t})
        
        # Handle case where no function calls but has response (miss scenario)
        if not fcs and responses:
            turn_trace.append({"response": responses[0]})
        elif responses:
            turn_trace.append({"response": responses[0]})
        
        traces.extend(turn_trace)
    
    return traces


# ============================================================================
# Miss Function Generation
# ============================================================================
async def generate_miss_function_queries(run_id: str):
    """Generate multi-turn dialogues with missing function scenarios."""
    dataset: List[Dict[str, Any]] = []
    
    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)
    
    template_path = get_prompt_path("pipeline/s5_miss_scenarios/prompt_miss_func.md")
    lang = get_language()
    logging.info(f"Miss Function queries - 使用語言: {lang}")
    
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    debug_enabled = os.getenv("S5_DEBUG", "0") == "1"
    debug_path = f"pipeline/data/{run_id}/s5_miss_func_debug.jsonl"
    
    for idx, inp in enumerate(tqdm(function_inputs, desc="Generating miss_function dialogues")):
        functions = inp.get("functions", [])
        
        if len(functions) < 2:
            logging.warning(f"Sample {idx}: Not enough functions for miss_function scenario, skipping")
            continue
        
        try:
            missing_func, remaining_funcs = select_missing_function(functions)
        except ValueError as e:
            logging.warning(f"Sample {idx}: {e}, skipping")
            continue
        
        miss_turns = get_miss_turns_count()
        total_turns = random.randint(5, 7)
        
        if debug_enabled:
            _write_debug(debug_enabled, debug_path, {
                "sample_index": idx,
                "scenario": inp["scenario"][:100] + "...",
                "missing_function": parse_signature(missing_func["function"]).get("function_name"),
                "remaining_count": len(remaining_funcs),
                "miss_turns": miss_turns,
                "total_turns": total_turns,
                "phase": "start"
            })
        
        prompt = render_template(
            template_path,
            {
                "scenario": inp["scenario"],
                "function_schemas": json.dumps([f["function"] for f in remaining_funcs], ensure_ascii=False),
                "missing_function": missing_func["function"],
                "total_turns": str(total_turns),
                "miss_turns": str(miss_turns),
            },
        )
        
        system = (
            "You are a careful data generator. Produce a <dialogue> containing turns with missing function scenarios as instructed."
            + get_system_prompt_suffix()
        )
        
        traces: List[Dict[str, str]] = []
        for attempt in range(max_retries + 1):
            content = chat_complete(prompt=prompt, system=system)
            
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "chat_complete",
                    "content_length": len(content)
                })
            
            traces = parse_dialogue(content)
            
            if traces:
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempt,
                        "phase": "success",
                        "trace_count": len(traces)
                    })
                break
            elif attempt < max_retries:
                logging.warning(f"Sample {idx}: Attempt {attempt + 1} failed, retrying...")
        
        # Store with metadata about the missing function
        dataset.append({
            "trace": traces,
            "function_schemas": [f["function"] for f in remaining_funcs],
            "missing_function": missing_func["function"],
            "missing_function_expected": missing_func.get("expected"),
            "all_function_schemas": [f["function"] for f in functions],  # Full list for reference
            "domain": inp["domain"],
            "subdomain": inp["subdomain"],
            "scenario_type": "miss_function",
            "miss_turns": miss_turns,
        })
    
    output_path = f"pipeline/data/{run_id}/miss_function_queries.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(dataset, ensure_ascii=False, indent=2))
    
    logging.info(f"Generated {len(dataset)} miss_function dialogues -> {output_path}")
    return dataset


# ============================================================================
# Miss Parameter Generation
# ============================================================================
async def generate_miss_param_queries(run_id: str):
    """Generate multi-turn dialogues with missing parameter scenarios."""
    dataset: List[Dict[str, Any]] = []
    
    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)
    
    template_path = get_prompt_path("pipeline/s5_miss_scenarios/prompt_miss_param.md")
    lang = get_language()
    logging.info(f"Miss Parameter queries - 使用語言: {lang}")
    
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    debug_enabled = os.getenv("S5_DEBUG", "0") == "1"
    debug_path = f"pipeline/data/{run_id}/s5_miss_param_debug.jsonl"
    
    for idx, inp in enumerate(tqdm(function_inputs, desc="Generating miss_param dialogues")):
        functions = inp.get("functions", [])
        
        if not functions:
            logging.warning(f"Sample {idx}: No functions, skipping")
            continue
        
        try:
            target_func, missing_params = select_function_for_miss_param(functions)
        except ValueError as e:
            logging.warning(f"Sample {idx}: {e}, skipping")
            continue
        
        miss_turns = get_miss_turns_count()
        total_turns = random.randint(5, 7)
        
        if debug_enabled:
            _write_debug(debug_enabled, debug_path, {
                "sample_index": idx,
                "scenario": inp["scenario"][:100] + "...",
                "target_function": parse_signature(target_func["function"]).get("function_name"),
                "missing_params": missing_params,
                "miss_turns": miss_turns,
                "total_turns": total_turns,
                "phase": "start"
            })
        
        prompt = render_template(
            template_path,
            {
                "scenario": inp["scenario"],
                "function_schemas": json.dumps([f["function"] for f in functions], ensure_ascii=False),
                "target_function": target_func["function"],
                "missing_params": ", ".join(missing_params),
                "total_turns": str(total_turns),
                "miss_turns": str(miss_turns),
            },
        )
        
        system = (
            "You are a careful data generator. Produce a <dialogue> containing turns with missing parameter scenarios as instructed."
            + get_system_prompt_suffix()
        )
        
        traces: List[Dict[str, str]] = []
        for attempt in range(max_retries + 1):
            content = chat_complete(prompt=prompt, system=system)
            
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "chat_complete",
                    "content_length": len(content)
                })
            
            traces = parse_dialogue(content)
            
            if traces:
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempt,
                        "phase": "success",
                        "trace_count": len(traces)
                    })
                break
            elif attempt < max_retries:
                logging.warning(f"Sample {idx}: Attempt {attempt + 1} failed, retrying...")
        
        # Store with metadata about missing parameters
        dataset.append({
            "trace": traces,
            "function_schemas": [f["function"] for f in functions],
            "target_function": target_func["function"],
            "missing_params": missing_params,
            "domain": inp["domain"],
            "subdomain": inp["subdomain"],
            "scenario_type": "miss_param",
            "miss_turns": miss_turns,
        })
    
    output_path = f"pipeline/data/{run_id}/miss_param_queries.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(dataset, ensure_ascii=False, indent=2))
    
    logging.info(f"Generated {len(dataset)} miss_param dialogues -> {output_path}")
    return dataset


# ============================================================================
# Main entry point
# ============================================================================
async def main():
    with open("run_id", "r", encoding="utf-8") as f:
        run_id = f.read().strip()
    
    logging.info(f"Run ID: {run_id}")
    
    # Mode selection via environment variable
    miss_mode = os.getenv("MISS_MODE", "both").lower()
    logging.info(f"MISS_MODE: {miss_mode}")
    logging.info(f"MISS_TURNS: {os.getenv('MISS_TURNS', '1')}")
    
    if miss_mode in ("miss_function", "miss_func", "both"):
        await generate_miss_function_queries(run_id)
    
    if miss_mode in ("miss_param", "miss_parameter", "both"):
        await generate_miss_param_queries(run_id)
    
    logging.info("Stage 5 completed.")


if __name__ == "__main__":
    asyncio.run(main())
