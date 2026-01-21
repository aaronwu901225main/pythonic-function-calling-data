import asyncio
import json
import logging
import os
import random
from typing import Any, Dict, List, Tuple, Optional
from tqdm import tqdm
from openai_utils import render_template, extract_tags, chat_complete
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
        return " Please write all user queries in Traditional Chinese (繁體中文). Use Chinese names for people and places."
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


async def generate_simple_queries_openai(run_id: str):
    dataset: List[Dict[str, Any]] = []

    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)

    template_path = get_prompt_path("pipeline/s3_queries/simple/prompt.md")
    lang = get_language()
    logging.info(f"Simple queries - 使用語言: {lang}")
    num_queries = os.getenv("S3_SIMPLE_NUM", "2")

    for inp in function_inputs:
        for func in inp.get("functions", []):
            prompt = render_template(
                template_path,
                {
                    "function_schema": func["function"],
                    "num_queries": num_queries,
                },
            )
            system = (
                "You are a careful data generator. Output multiple <user_query> and <function_call> tag pairs as instructed."
                + get_system_prompt_suffix()
            )
            content = chat_complete(prompt=prompt, system=system)
            queries = extract_tags(content, "user_query")
            calls = extract_tags(content, "function_call")
            for q, c in zip(queries, calls):
                dataset.append(
                    {
                        "user_query": q,
                        "function_call": c,
                        "function_schema": func["function"],
                        "domain": inp["domain"],
                        "subdomain": inp["subdomain"],
                    }
                )

    with open(
        f"pipeline/data/{run_id}/simple_queries.json", "w", encoding="utf-8"
    ) as f:
        f.write(json.dumps(dataset, ensure_ascii=False, indent=2))


async def generate_parallel_queries_openai(run_id: str):
    dataset: List[Dict[str, Any]] = []

    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)

    template_path = get_prompt_path("pipeline/s3_queries/parallel/prompt.md")
    lang = get_language()
    logging.info(f"Parallel queries - 使用語言: {lang}")
    num_queries = os.getenv("S3_PARALLEL_NUM", "2")

    for inp in tqdm(function_inputs):
        for func in inp.get("functions", []):
            prompt = render_template(
                template_path,
                {
                    "function_schema": func["function"],
                    "num_queries": num_queries,
                },
            )
            system = (
                "You are a careful data generator. Output <user_query> and <function_calls> pairs as instructed."
                + get_system_prompt_suffix()
            )
            content = chat_complete(prompt=prompt, system=system)
            queries = extract_tags(content, "user_query")
            calls_blocks = extract_tags(content, "function_calls")
            for q, c in zip(queries, calls_blocks):
                dataset.append(
                    {
                        "user_query": q,
                        "function_call": c,  # store multiple calls as a single string (multi-line)
                        "function_schema": func["function"],
                        "domain": inp["domain"],
                        "subdomain": inp["subdomain"],
                    }
                )

    with open(
        f"pipeline/data/{run_id}/parallel_queries.json", "w", encoding="utf-8"
    ) as f:
        f.write(json.dumps(dataset, ensure_ascii=False, indent=2))


async def generate_multiple_queries_openai(run_id: str):
    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)

    # Build distractors map similar to original implementation
    func_map: Dict[str, List[str]] = {}
    for idx, inp in enumerate(function_inputs):
        for func in inp.get("functions", []):
            # choose distractors from same scenario first
            others = [
                f["function"] for f in inp.get("functions", []) if f["function"] != func["function"]
            ]
            distractors: List[str] = []
            if random.random() > 0.5:
                try:
                    distractors = random.sample(others, 2)
                except Exception:
                    distractors = others
            else:
                if len(others) >= 3:
                    distractors = random.sample(others, 3)
                elif len(others) == 2:
                    distractors = random.sample(others, 2)
                else:
                    distractors = others

            # occasionally add an outer element
            if random.random() > 0.5 and len(function_inputs) > 1:
                r = list(range(len(function_inputs)))
                try:
                    r.remove(idx)
                except ValueError:
                    pass
                if r:
                    outer = function_inputs[random.choice(r)]
                    try:
                        # pick any function from the outer entry
                        if outer.get("functions"):
                            distractors.append(random.choice(outer["functions"])["function"])  # type: ignore
                    except Exception:
                        pass

            func_map[func["function"]] = distractors

    with open(f"pipeline/data/{run_id}/simple_queries.json", "r", encoding="utf-8") as f:
        simple_queries: List[Dict[str, Any]] = json.load(f)

    k = min(len(simple_queries), 10000)
    samples = random.sample(simple_queries, k) if k > 0 else []
    for sample in samples:
        distractors = func_map.get(sample["function_schema"], [])
        sample["function_schemas"] = [sample["function_schema"]] + distractors
        del sample["function_schema"]

    with open(
        f"pipeline/data/{run_id}/multiple_queries.json", "w", encoding="utf-8"
    ) as f:
        f.write(json.dumps(samples, ensure_ascii=False, indent=2))


def process_single_multi_turn(
    idx: int,
    task_data: Tuple[Dict[str, Any], str, str, int, bool, str]
) -> Optional[Dict[str, Any]]:
    """
    處理單一 sample，生成 multi-turn dialogue
    
    Args:
        idx: sample 索引
        task_data: (inp, template_path, system, max_retries, debug_enabled, debug_path)
        
    Returns:
        包含 trace 的結果字典，或 None
    """
    inp, template_path, system, max_retries, debug_enabled, debug_path = task_data
    
    function_schemas_obj = inp.get("functions", [])
    
    if debug_enabled:
        _write_debug(debug_enabled, debug_path, {
            "sample_index": idx,
            "scenario": inp["scenario"][:100] + "..." if len(inp["scenario"]) > 100 else inp["scenario"],
            "function_count": len(function_schemas_obj),
            "phase": "start",
            "event": "processing_sample"
        })
    
    prompt = render_template(
        template_path,
        {
            "scenario": inp["scenario"],
            "function_schemas": json.dumps(function_schemas_obj, ensure_ascii=False),
        },
    )
    
    traces: List[Dict[str, str]] = []
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
        
        dialogue_blocks = extract_tags(content, "dialogue")
        if not dialogue_blocks:
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "extract",
                    "event": "no_dialogue_blocks"
                })
            if attempt < max_retries:
                logging.warning(f"S3 sample {idx} attempt {attempt + 1} failed to extract dialogue, retrying...")
                continue
            else:
                break
        
        dlg = dialogue_blocks[0]
        
        if debug_enabled:
            _write_debug(debug_enabled, debug_path, {
                "sample_index": idx,
                "attempt": attempt,
                "phase": "extract",
                "event": "dialogue_extracted",
                "dialogue_length": len(dlg)
            })
        
        # Prefer new <turn> format
        turn_blocks = extract_tags(dlg, "turn")
        temp_traces: List[Dict[str, str]] = []
        
        if turn_blocks:
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "parse",
                    "event": "using_turn_format",
                    "turn_count": len(turn_blocks)
                })
                
            for turn_idx, tb in enumerate(turn_blocks):
                q_blocks = extract_tags(tb, "query")
                if not q_blocks:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempt,
                            "phase": "parse",
                            "event": "no_query_in_turn",
                            "turn_index": turn_idx
                        })
                    continue
                q = q_blocks[0]
                temp_traces.append({"query": q})
                
                fcs = extract_tags(tb, "function_call")
                tls = extract_tags(tb, "tool")
                responses = extract_tags(tb, "response")
                
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempt,
                        "phase": "parse",
                        "event": "turn_parsed",
                        "turn_index": turn_idx,
                        "function_calls": len(fcs),
                        "tool_responses": len(tls),
                        "assistant_responses": len(responses)
                    })
                
                for c, t in zip(fcs, tls):
                    temp_traces.append({"function_call": c})
                    temp_traces.append({"tool": t})
                
                if responses:
                    temp_traces.append({"response": responses[0]})
        else:
            # Backward compatibility: flat sequence
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "parse",
                    "event": "using_flat_format"
                })
                
            queries = extract_tags(dlg, "query")
            calls = extract_tags(dlg, "function_call")
            tools = extract_tags(dlg, "tool")
            
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "parse",
                    "event": "flat_format_extracted",
                    "queries": len(queries),
                    "function_calls": len(calls),
                    "tool_responses": len(tools)
                })
            
            for q, c, t in zip(queries, calls, tools):
                temp_traces.append({"query": q})
                temp_traces.append({"function_call": c})
                temp_traces.append({"tool": t})
        
        if temp_traces:
            traces = temp_traces
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "success",
                    "event": "dialogue_parsed_success",
                    "trace_count": len(traces)
                })
            break
        elif attempt < max_retries:
            logging.warning(f"S3 sample {idx} attempt {attempt + 1} failed to parse dialogue, retrying...")
            if debug_enabled:
                _write_debug(debug_enabled, debug_path, {
                    "sample_index": idx,
                    "attempt": attempt,
                    "phase": "retry",
                    "event": "dialogue_parsing_failed_retrying"
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
        "trace": traces,
        "function_schemas": [f["function"] for f in function_schemas_obj],
        "domain": inp["domain"],
        "subdomain": inp["subdomain"],
    }


async def generate_multi_turn_queries_openai(run_id: str):
    # 檢查最終 JSON 是否已存在
    json_path = f"pipeline/data/{run_id}/multi_turn_queries.json"
    jsonl_path = ensure_jsonl_path(json_path)
    
    if check_final_json_exists(json_path):
        logging.info(f"multi_turn_queries.json already exists, skipping S3 multi-turn")
        return

    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)

    template_path = get_prompt_path("pipeline/s3_queries/multiturn/prompt.md")
    lang = get_language()
    logging.info(f"Multi-turn queries - 使用語言: {lang}")
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    debug_enabled = os.getenv("S3_DEBUG", "0") == "1"
    debug_path = f"pipeline/data/{run_id}/s3_queries_debug.jsonl"

    system = (
        "You are a careful data generator. Produce a <dialogue> containing repeated <query>, <function_call>, and <tool> tags as per instructions."
        + get_system_prompt_suffix()
    )

    # 載入已完成的 indices
    completed = load_completed_indices(jsonl_path)
    
    # 過濾未完成的項目
    items_to_process = [
        (idx, (inp, template_path, system, max_retries, debug_enabled, debug_path))
        for idx, inp in enumerate(function_inputs)
        if idx not in completed
    ]
    
    if not items_to_process:
        logging.info("All samples already processed, finalizing...")
    else:
        logging.info(f"Processing {len(items_to_process)} samples (skipping {len(completed)} completed)")
        
        # 增量寫入器
        with IncrementalWriter(jsonl_path, mode="a") as writer:
            # 平行處理
            max_workers = get_parallel_workers()
            run_parallel_tasks(
                process_single_multi_turn,
                items_to_process,
                max_workers=max_workers,
                desc="Generating Multi-Turn Dialogues",
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
    
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(records, ensure_ascii=False, indent=2))
    
    logging.info(f"Finalized {len(records)} multi-turn dialogues -> {json_path}")


async def main():
    with open("run_id", "r", encoding="utf-8") as run_id_fp:
        run_id = run_id_fp.read().strip()
    logging.info(f"Run ID: {run_id}")
    # Feature toggles via env vars
    only_multi = os.getenv("ONLY_MULTI_TURN", "0") == "1"
    enable_simple = os.getenv("ENABLE_SIMPLE", "1") == "1"
    enable_parallel = os.getenv("ENABLE_PARALLEL", "1") == "1"
    enable_multiple = os.getenv("ENABLE_MULTIPLE", "1") == "1"
    enable_multi = os.getenv("ENABLE_MULTI_TURN", "1") == "1"

    if only_multi:
        enable_simple = False
        enable_parallel = False
        enable_multiple = False
        enable_multi = True

    if enable_simple:
        await generate_simple_queries_openai(run_id)
    if enable_parallel:
        await generate_parallel_queries_openai(run_id)
    if enable_multiple:
        await generate_multiple_queries_openai(run_id)
    if enable_multi:
        await generate_multi_turn_queries_openai(run_id)
    logging.info("Generated Queries (OpenAI mode)")


if __name__ == "__main__":
    asyncio.run(main())
