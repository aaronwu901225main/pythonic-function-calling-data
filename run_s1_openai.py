import asyncio
import csv
import json
import logging
import os
import uuid
from typing import List, Dict

from openai_utils import render_template, extract_tags, chat_complete

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def read_curriculum(csv_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "domain": r["domain"],
                "subdomain": r["subdomain"],
                "entities": r.get("entities", ""),
            })
    return rows


async def generate_scenarios_openai(run_id: str):
    os.makedirs(f"pipeline/data/{run_id}", exist_ok=True)

    template_path = "pipeline/s1_scenario/prompt.md"
    data: List[Dict] = []

    rows = read_curriculum("pipeline/data/curriculum.csv")
    for row in rows:
        prompt = render_template(
            template_path,
            {
                "domain": row["domain"],
                "subdomain": row["subdomain"],
                # default number of scenarios
                "num_scenarios": os.getenv("S1_NUM_SCENARIOS", "10"),
            },
        )
        system = (
            "You are a careful data generator. Follow the format strictly and wrap each scenario inside <scenario> tags."
        )
        content = chat_complete(prompt=prompt, system=system)
        scenarios = extract_tags(content, "scenario")
        for sce in scenarios:
            data.append(
                {
                    "domain": row["domain"],
                    "subdomain": row["subdomain"],
                    "entities": row.get("entities", ""),
                    "scenario": sce.strip(),
                }
            )

    with open(f"pipeline/data/{run_id}/scenarios.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))


async def main():
    run_id = uuid.uuid4().hex
    with open("run_id", "w", encoding="utf-8") as f:
        f.write(run_id)
    logging.info(f"Run ID: {run_id}")
    await generate_scenarios_openai(run_id)
    logging.info("Generated Scenarios (OpenAI mode)")


if __name__ == "__main__":
    asyncio.run(main())
