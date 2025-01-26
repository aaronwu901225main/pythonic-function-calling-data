import asyncio
import json
import random

from dria import DriaDataset, DatasetGenerator, Model, Dria
from pipeline import SimpleQuery, ParallelQuery, MultiTurnQuery
from pipeline.s3_queries.multiturn.task import Function
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def generate_simple_queries(run_id):
    """Generate Simple Queries"""
    dataset = DriaDataset(
        f"simple_queries_{run_id}",
        description="function dataset",
        schema=SimpleQuery.OutputSchema,
    )
    generator = DatasetGenerator(dataset)

    with open(f"pipeline/data/{run_id}/functions.json", "r") as f:
        function_inputs = json.load(f)

    instructions = []
    for inp in function_inputs:
        for func in inp["functions"]:
            instructions.append(
                {
                    "function_schema": func["function"],
                    "num_queries": 2,
                    "domain": inp["domain"],
                    "subdomain": inp["subdomain"],
                    "scenario": inp["scenario"],
                }
            )

    await generator.generate(
        instructions=instructions,
        singletons=SimpleQuery,
        models=[
            Model.LLAMA_3_1_405B_OR,
            Model.QWEN2_5_CODER_32B_OR,
            Model.GEMINI_15_PRO,
            Model.GEMINI_15_FLASH,
            Model.GEMINI_20_FLASH,
            Model.R1_70b,
            Model.R1_32b,
            Model.Llama3_3_70B,
            Model.ANTHROPIC_SONNET_3_5_OR,
        ],
    )
    dataset.to_json(filepath=f"pipeline/data/{run_id}/simple_queries.json")


async def generate_parallel_queries(run_id):
    """Generate Parallel Functions"""
    dataset = DriaDataset(
        f"__parallel_queries_{run_id}",
        description="function dataset",
        schema=ParallelQuery.OutputSchema,
    )
    generator = DatasetGenerator(dataset)

    with open(f"pipeline/data/{run_id}/functions.json", "r") as f:
        function_inputs = json.load(f)

    instructions = []
    for inp in function_inputs:
        for func in inp["functions"]:
            instructions.append(
                {
                    "function_schema": func["function"],
                    "num_queries": 2,
                    "domain": inp["domain"],
                    "subdomain": inp["subdomain"],
                    "scenario": inp["scenario"],
                }
            )

    await generator.generate(
        instructions=instructions,
        singletons=ParallelQuery,
        models=[
            Model.LARGE,
            Model.QWEN2_5_CODER_32B_OR,
            Model.GEMINI_15_PRO,
            Model.GEMINI_20_FLASH,
        ],
    )
    dataset.to_json(filepath=f"pipeline/data/{run_id}/parallel_queries.json")


async def generate_multiple_queries(run_id):
    """Generate Functions"""

    with open(f"pipeline/data/{run_id}/functions.json", "r") as f:
        function_inputs = json.load(f)

    func_map = {}
    for idx, inp in enumerate(function_inputs):
        for func in inp["functions"]:
            if random.random() > 0.5:
                # add 2 functions
                others = [
                    f["function"]
                    for f in inp["functions"]
                    if f["function"] != func["function"]
                ]
                try:
                    distractors = random.sample(others, 2)
                except:
                    distractors = others
            else:
                # add 3 functions
                others = [
                    f["function"]
                    for f in inp["functions"]
                    if f["function"] != func["function"]
                ]
                if len(others) >= 3:
                    distractors = random.sample(others, 3)
                elif len(others) == 2:
                    distractors = random.sample(others, 2)
                else:
                    distractors = others

            if random.random() > 0.5:
                # add outer elements
                r = list(range(len(function_inputs)))
                r.remove(idx)
                distractors.append(
                    random.choice(function_inputs[random.choice(r)]["functions"])[
                        "function"
                    ]
                )

            func_map[func["function"]] = distractors

    with open(f"pipeline/data/{run_id}/simple_queries.json", "r") as f:
        simple_queries = json.load(f)

    samples = random.sample(simple_queries, 10000)
    for sample in samples:
        distractors = func_map[sample["function_schema"]]
        sample["function_schemas"] = [sample["function_schema"]] + distractors
        del sample["function_schema"]

    with open(f"pipeline/data/{run_id}/multiple_queries.json", "w") as f:
        f.write(json.dumps(samples))


async def generate_multi_turn_queries(run_id):
    """Generate Functions"""
    dataset = DriaDataset(
        f"multi_turn_queries_{run_id}",
        description="function dataset",
        schema=MultiTurnQuery.OutputSchema,
    )
    generator = DatasetGenerator(dataset)

    with open(f"pipeline/data/{run_id}/functions.json", "r") as f:
        function_inputs = json.load(f)

    instructions = []
    for inp in function_inputs:
        function_schemas = []

        for func in inp["functions"]:
            try:
                Function(**func)
                function_schemas.append(func)
            except:
                pass
        instructions.append(
            {
                "function_schemas": function_schemas,
                "domain": inp["domain"],
                "subdomain": inp["subdomain"],
                "scenario": inp["scenario"],
            }
        )

    await generator.generate(
        instructions=instructions,
        singletons=MultiTurnQuery,
        models=[
            Model.LLAMA3_3_70B,
            Model.QWEN_QWQ,
            Model.DEEPSEEK_R1_32B,
            Model.DEEPSEEK_R1_70B,
            Model.ANTHROPIC_SONNET_3_5_OR,
        ],
    )
    dataset.to_json(filepath=f"pipeline/data/{run_id}/multi_turn_queries.json")


async def main():
    with open("run_id", "r") as run_id:
        run_id = run_id.read()
    logging.info(f"Run ID: {run_id}")
    await generate_simple_queries(run_id)
    await generate_parallel_queries(run_id)
    await generate_multiple_queries(run_id)
    await generate_multi_turn_queries(run_id)
    logging.info("Generated Queries")


asyncio.run(main())
