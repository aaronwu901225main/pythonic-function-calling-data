import asyncio
import json
import logging
import os
import random
from typing import Any, Dict, List

from openai_utils import render_template, extract_tags, chat_complete

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def generate_simple_queries_openai(run_id: str):
    dataset: List[Dict[str, Any]] = []

    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)

    template_path = "pipeline/s3_queries/simple/prompt.md"
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

    template_path = "pipeline/s3_queries/parallel/prompt.md"
    num_queries = os.getenv("S3_PARALLEL_NUM", "2")

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
                "You are a careful data generator. Output <user_query> and <function_calls> pairs as instructed."
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
                    outer = random.choice(function_inputs[random.choice(r)])
                    try:
                        # pick any function from the outer entry
                        if outer.get("functions"):
                            distractors.append(random.choice(outer["functions"]) ["function"])  # type: ignore
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


async def generate_multi_turn_queries_openai(run_id: str):
    dataset: List[Dict[str, Any]] = []
    with open(f"pipeline/data/{run_id}/functions.json", "r", encoding="utf-8") as f:
        function_inputs: List[Dict[str, Any]] = json.load(f)

    template_path = "pipeline/s3_queries/multiturn/prompt.md"

    for inp in function_inputs:
        function_schemas_obj = inp.get("functions", [])
        prompt = render_template(
            template_path,
            {
                "scenario": inp["scenario"],
                "function_schemas": json.dumps(function_schemas_obj, ensure_ascii=False),
            },
        )
        system = (
            "You are a careful data generator. Produce a <dialogue> containing repeated <query>, <function_call>, and <tool> tags as per instructions."
        )
        content = chat_complete(prompt=prompt, system=system)

        dialogue_blocks = extract_tags(content, "dialogue")
        if not dialogue_blocks:
            continue
        dlg = dialogue_blocks[0]
        queries = extract_tags(dlg, "query")
        calls = extract_tags(dlg, "function_call")
        tools = extract_tags(dlg, "tool")

        traces: List[Dict[str, str]] = []
        for q, c, t in zip(queries, calls, tools):
            traces.append({"query": q})
            traces.append({"function_call": c})
            traces.append({"tool": t})

        dataset.append(
            {
                "trace": traces,
                "function_schemas": [f["function"] for f in function_schemas_obj],
                "domain": inp["domain"],
                "subdomain": inp["subdomain"],
            }
        )

    with open(
        f"pipeline/data/{run_id}/multi_turn_queries.json", "w", encoding="utf-8"
    ) as f:
        f.write(json.dumps(dataset, ensure_ascii=False, indent=2))


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
