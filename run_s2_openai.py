import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List
from tqdm import tqdm
from openai_utils import render_template, extract_tags, extract_code_fence, chat_complete
from pipeline.s2_functions.parser import parse_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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


async def generate_functions_openai(run_id: str):
    # read scenarios
    with open(f"pipeline/data/{run_id}/scenarios.json", "r", encoding="utf-8") as f:
        scenario_inputs: List[Dict[str, Any]] = json.load(f)

    # Optional: limit number of scenarios to process (to reduce API calls)
    s2_limit = os.getenv("S2_LIMIT_SCENARIOS")
    if s2_limit:
        try:
            scenario_inputs = scenario_inputs[: int(s2_limit)]
        except Exception:
            pass

    template_path = "pipeline/s2_functions/prompt.md"
    max_retries = int(os.getenv("MAX_RETRIES", "2"))    
    debug_enabled = os.getenv("S2_DEBUG", "0") == "1"
    debug_path = f"pipeline/data/{run_id}/s2_functions_debug.jsonl"
    out: List[Dict[str, Any]] = []

    for idx, inp in enumerate(tqdm(scenario_inputs)):
        if debug_enabled:
            _write_debug(debug_enabled, debug_path, {
                "sample_index": idx,
                "scenario": inp["scenario"][:100] + "..." if len(inp["scenario"]) > 100 else inp["scenario"],
                "phase": "start",
                "event": "processing_scenario"
            })
            
        prompt = render_template(template_path, {"scenario": inp["scenario"]})
        system = (
            "You are a careful data generator. Follow the format strictly, include multiple <function> blocks each with a <signature> code fence and an <expected> value."
        )
        
        functions: List[Dict[str, Any]] = []
        for attempt in range(max_retries + 1):
            content = chat_complete(prompt=prompt, system=system)
            
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
                    
                # extract code fence labelled python from signature tag content
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
                if not parsed.get("function_name"):  # 解析失敗
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
            
            if temp_functions:  # 成功解析到函數
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
                print(f"Warning: S2 attempt {attempt + 1} failed to parse functions for scenario, retrying...")
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

        out.append(
            {
                "scenario": inp["scenario"],
                "domain": inp["domain"],
                "subdomain": inp["subdomain"],
                "functions": functions,
            }
        )

        # Optional: rate limiting sleep between calls
        try:
            rate_sleep = float(os.getenv("OPENAI_RATE_SLEEP", "0"))
            if rate_sleep > 0:
                time.sleep(rate_sleep)
        except Exception:
            pass

    os.makedirs(f"pipeline/data/{run_id}", exist_ok=True)
    with open(f"pipeline/data/{run_id}/functions.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2))


async def main():
    with open("run_id", "r", encoding="utf-8") as fp:
        run_id = fp.read().strip()
    logging.info(f"Run ID: {run_id}")
    await generate_functions_openai(run_id)
    logging.info("Generated Functions (OpenAI mode)")


if __name__ == "__main__":
    asyncio.run(main())
