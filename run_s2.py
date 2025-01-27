import asyncio
from dria import DriaDataset, DatasetGenerator, Model, Dria
from pipeline import Scenario, Functions
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def generate_functions(run_id):
    """Generate Functions"""
    dataset = DriaDataset(
        f"functions_{run_id}",
        description="function dataset",
        schema=Functions.OutputSchema,
    )
    generator = DatasetGenerator(dataset)

    scenario_inputs = DriaDataset.from_json(
        name=f"scenario_{run_id}",
        description="",
        json_path=f"pipeline/data/{run_id}/scenarios.json",
        schema=Scenario.OutputSchema,
    )

    await generator.generate(
        instructions=scenario_inputs,
        singletons=Functions,
        models=[
            Model.QWEN_QWQ_OR,
            Model.LLAMA_3_1_405B_OR,
            Model.ANTHROPIC_SONNET_3_5_OR,
            Model.ANTHROPIC_HAIKU_3_5_OR,
            Model.DEEPSEEK_R1_14B,
            Model.DEEPSEEK_R1_32B,
            Model.DEEPSEEK_R1_70B,
            Model.LLAMA_3_3_70B_OR,
            Model.GEMINI_20_FLASH,
            Model.GPT4O,
            Model.GPT4O_MINI,
            Model.LLAMA_3_1_8B_OR,
            Model.QWEN2_5_CODER_32B_OR,
        ],
    )
    dataset.to_json(filepath=f"pipeline/data/{run_id}/functions.json")


async def main():
    with open("run_id", "r") as run_id:
        run_id = run_id.read()
    logging.info(f"Run ID: {run_id}")
    await generate_functions(run_id)
    logging.info("Generated User Queries")


asyncio.run(main())
# 5550
