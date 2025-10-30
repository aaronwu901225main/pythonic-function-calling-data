import asyncio
from pydantic import BaseModel
from dria import DriaDataset, DatasetGenerator, Model, Dria
from pipeline.s1_scenario import Scenario
import uuid
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


class Curriculum(BaseModel):
    domain: str
    subdomain: str
    entities: str


async def generate_scenarios(run_id):
    """Generate Scenarios"""
    dataset = DriaDataset(
        f"scenarios_{run_id}",
        description="Scenarios dataset",
        schema=Scenario.OutputSchema,
    )
    generator = DatasetGenerator(dataset)

    csv_path = "pipeline/data/curriculum.csv"

    scenario_inputs = DriaDataset.from_csv(
        name=f"curriculum_{run_id}",
        description="",
        csv_path=csv_path,
        schema=Curriculum,
    )

    entries = scenario_inputs.get_entries(data_only=True)

    for entry in entries:
        entry["num_scenarios"] = 10

    await generator.generate(
        instructions=entries,
        singletons=Scenario,
        models=[
            Model.GPT4O,
            Model.LLAMA_3_1_70B_OR,
            Model.LLAMA_3_3_70B_OR,
            Model.GEMINI_20_FLASH,
            Model.GPT4O_MINI,
            Model.LLAMA_3_1_8B_OR,
            Model.QWEN2_5_72B_OR,
            Model.QWEN2_5_7B,
        ],
    )
    dataset.to_json(filepath=f"pipeline/data/{run_id}/scenarios.json")


async def main():
    run_id = uuid.uuid4().hex
    with open("run_id", "w") as f:
        f.write(run_id)
    os.mkdir(f"pipeline/data/{run_id}")
    logging.info(f"Run ID: {run_id}")
    logging.info("Generating Scenarios")
    await generate_scenarios(run_id)
    logging.info("Generated Scenarios")


asyncio.run(main())
