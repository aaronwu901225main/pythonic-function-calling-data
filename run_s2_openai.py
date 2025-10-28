import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List

from openai_utils import render_template, extract_tags, extract_code_fence, chat_complete
from pipeline.s2_functions.parser import parse_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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
    out: List[Dict[str, Any]] = []

    for inp in scenario_inputs:
        prompt = render_template(template_path, {"scenario": inp["scenario"]})
        system = (
            "You are a careful data generator. Follow the format strictly, include multiple <function> blocks each with a <signature> code fence and an <expected> value."
        )
        content = chat_complete(prompt=prompt, system=system)
        func_blocks = extract_tags(content, "function")

        functions: List[Dict[str, Any]] = []
        for fb in func_blocks:
            sig_blocks = extract_tags(fb, "signature")
            if not sig_blocks:
                continue
            # extract code fence labelled python from signature tag content
            code_blocks = extract_code_fence(sig_blocks[0], lang="python")
            if not code_blocks:
                continue
            schema = code_blocks[0]
            parsed = parse_signature(schema)
            return_type = parsed.get("return_type", "")

            exp_blocks = extract_tags(fb, "expected")
            expected_raw = exp_blocks[0] if exp_blocks else ""
            expected = _coerce_expected(expected_raw, return_type)

            functions.append({"function": schema, "expected": expected})

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
