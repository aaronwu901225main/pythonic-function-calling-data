import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Tuple, Optional
from tqdm import tqdm
from openai_utils import render_template, extract_tags, extract_code_fence, chat_complete
from pipeline.s2_functions.parser import parse_signature
from incremental_utils import (
    IncrementalWriter,
    load_completed_indices,
    run_parallel_tasks,
    get_parallel_workers,
    ensure_jsonl_path,
    check_final_json_exists,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 語言設定：支援 "en" (英文) 或 "zh_tw" (繁體中文)
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
        return " Please write all docstrings and descriptions in Traditional Chinese (繁體中文). Keep function names in English."
    return ""


def _write_debug(debug_enabled: bool, debug_out_path: str, record: Dict[str, Any]):
    if not debug_enabled:
        return
    try:
        os.makedirs(os.path.dirname(debug_out_path), exist_ok=True)
        with open(debug_out_path, "a", encoding="utf-8") as df:
            df.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _coerce_expected(expected_text: str, return_type: str) -> Any:
    text = (expected_text or "").strip()
    rt = (return_type or "").lower()
    # list/dict: try json
    if "list" in rt or "dict" in rt:
        try:
            return json.loads(text)
        except Exception:
            pass
    # simple scalars
    if rt == "int":
        try:
            return int(text)
        except Exception:
            return text
    if rt == "float":
        try:
            return float(text)
        except Exception:
            return text
    if rt == "bool":
        low = text.lower()
        if low in ("true", "false"):
            return low == "true"
        return text
    if rt == "none":
        return None
    # default string
    return text


def process_single_scenario(
    idx: int,
    task_data: Tuple[Dict[str, Any], str, str, int, bool, str]
) -> Optional[Dict[str, Any]]:
    """
    處理單一 scenario，生成 functions
    
    Args:
        idx: scenario 索引
        task_data: (inp, template_path, system, max_retries, debug_enabled, debug_path)
        
    Returns:
        包含 functions 的結果字典，或 None
    """
    inp, template_path, system, max_retries, debug_enabled, debug_path = task_data
    
    if debug_enabled:
        _write_debug(debug_enabled, debug_path, {
            "sample_index": idx,
            "scenario": inp["scenario"][:100] + "..." if len(inp["scenario"]) > 100 else inp["scenario"],
            "phase": "start",
            "event": "processing_scenario"
        })
    
    prompt = render_template(template_path, {"scenario": inp["scenario"]})
    
    functions: List[Dict[str, Any]] = []
    for attempt in range(max_retries + 1):
        try:
            content = chat_complete(prompt=prompt, system=system)
        except Exception as e:
            logging.error(f"Sample {idx} attempt {attempt}: API error: {e}")
            continue
        
        if debug_enabled:
            _write_debug(debug_enabled, debug_path, {
                "sample_index": idx,
                "attempt": attempt,
                "phase": "chat_complete",
                "event": "response_received",
                "content_length": len(content)
            })
        
        func_blocks = extract_tags(content, "function")
        
        if debug_enabled:
            _write_debug(debug_enabled, debug_path, {
                "sample_index": idx,
                "attempt": attempt,
                "phase": "extract",
                "event": "function_blocks_extracted",
                "count": len(func_blocks)
            })
        
        temp_functions: List[Dict[str, Any]] = []
        for fb_idx, fb in enumerate(func_blocks):
            sig_blocks = extract_tags(fb, "signature")
            if not sig_blocks:
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempt,
                        "phase": "parse",
                        "event": "no_signature_blocks",
                        "function_block_index": fb_idx
                    })
                continue
                
            code_blocks = extract_code_fence(sig_blocks[0], lang="python")
            if not code_blocks:
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempt,
                        "phase": "parse",
                        "event": "no_code_blocks",
                        "function_block_index": fb_idx
                    })
                continue
                
            schema = code_blocks[0]
            parsed = parse_signature(schema)
            if not parsed.get("function_name"):
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempt,
                        "phase": "parse",
                        "event": "parse_signature_failed",
                        "function_block_index": fb_idx,
                        "schema": schema[:200] + "..." if len(schema) > 200 else schema
                    })
                continue
                
            return_type = parsed.get("return_type", "")
            exp_blocks = extract_tags(fb, "expected")
            expected_raw = exp_blocks[0] if exp_blocks else ""
            expected = _coerce_expected(expected_raw, return_type)
            
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "parse",
                    "event": "function_parsed_success",
                    "function_block_index": fb_idx,
                    "function_name": parsed.get("function_name"),
                    "return_type": return_type
                })

            temp_functions.append({"function": schema, "expected": expected})
        
        if temp_functions:
            functions = temp_functions
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "success",
                    "event": "functions_accepted",
                    "count": len(functions)
                })
            break
        elif attempt < max_retries:
            logging.warning(f"S2 sample {idx} attempt {attempt + 1} failed, retrying...")
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "retry",
                    "event": "functions_parsing_failed_retrying"
                })
        else:
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "failure",
                    "event": "all_attempts_failed",
                    "max_retries": max_retries
                })

    return {
        "scenario": inp["scenario"],
        "domain": inp["domain"],
        "subdomain": inp["subdomain"],
        "functions": functions,
    }


async def generate_functions_openai(run_id: str):
    # 檢查最終 JSON 是否已存在
    json_path = f"pipeline/data/{run_id}/functions.json"
    jsonl_path = ensure_jsonl_path(json_path)
    
    if check_final_json_exists(json_path):
        logging.info(f"functions.json already exists, skipping S2")
        return

    # read scenarios
    with open(f"pipeline/data/{run_id}/scenarios.json", "r", encoding="utf-8") as f:
        scenario_inputs: List[Dict[str, Any]] = json.load(f)

    # Optional: limit number of scenarios
    s2_limit = os.getenv("S2_LIMIT_SCENARIOS")
    if s2_limit:
        try:
            scenario_inputs = scenario_inputs[: int(s2_limit)]
        except Exception:
            pass

    # 根據語言設定選擇 prompt
    template_path = get_prompt_path("pipeline/s2_functions/prompt.md")
    lang = get_language()
    logging.info(f"使用語言: {lang}, prompt 路徑: {template_path}")
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    debug_enabled = os.getenv("S2_DEBUG", "0") == "1"
    debug_path = f"pipeline/data/{run_id}/s2_functions_debug.jsonl"
    
    system = (
        "You are a careful data generator. Follow the format strictly, include multiple <function> blocks each with a <signature> code fence and an <expected> value."
        + get_system_prompt_suffix()
    )

    # 載入已完成的 indices
    completed = load_completed_indices(jsonl_path)
    
    # 過濾未完成的項目
    items_to_process = [
        (idx, (inp, template_path, system, max_retries, debug_enabled, debug_path))
        for idx, inp in enumerate(scenario_inputs)
        if idx not in completed
    ]
    
    if not items_to_process:
        logging.info("All scenarios already processed, finalizing...")
    else:
        logging.info(f"Processing {len(items_to_process)} scenarios (skipping {len(completed)} completed)")
        
        # 增量寫入器
        with IncrementalWriter(jsonl_path, mode="a") as writer:
            # 平行處理
            max_workers = get_parallel_workers()
            run_parallel_tasks(
                process_single_scenario,
                items_to_process,
                max_workers=max_workers,
                desc="Generating Functions",
                writer=writer,
            )
    
    # 轉換為最終 JSON 格式
    records: List[Dict[str, Any]] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                record = json.loads(line)
                record.pop("_sample_index", None)
                records.append(record)
    
    # 按原始順序排序
    records.sort(key=lambda r: scenario_inputs.index(
        next((s for s in scenario_inputs if s["scenario"] == r["scenario"]), scenario_inputs[0])
    ) if r.get("scenario") else float('inf'))
    
    os.makedirs(f"pipeline/data/{run_id}", exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(records, ensure_ascii=False, indent=2))
    
    logging.info(f"Finalized {len(records)} functions -> {json_path}")


async def main():
    with open("run_id", "r", encoding="utf-8") as fp:
        run_id = fp.read().strip()
    logging.info(f"Run ID: {run_id}")
    await generate_functions_openai(run_id)
    logging.info("Generated Functions (OpenAI mode)")


if __name__ == "__main__":
    asyncio.run(main())
