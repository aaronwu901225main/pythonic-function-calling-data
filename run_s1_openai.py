import asyncio
import csv
import json
import logging
import os
import uuid
import time
from typing import List, Dict
from tqdm import tqdm
from openai_utils import render_template, extract_tags, chat_complete

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
        return " Please generate all content in Traditional Chinese (繁體中文)."
    return ""


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

    # 根據語言設定選擇 prompt
    template_path = get_prompt_path("pipeline/s1_scenario/prompt.md")
    lang = get_language()
    logging.info(f"使用語言: {lang}, prompt 路徑: {template_path}")
    data: List[Dict] = []

    # Use CURRICULUM_CSV environment variable or default to curriculum.csv
    csv_path = os.getenv("CURRICULUM_CSV", "pipeline/data/curriculum.csv")
    logging.info(f"Using curriculum file: {csv_path}")
    rows = read_curriculum(csv_path)
    # Optional: limit number of curriculum rows (to reduce API calls)
    s1_limit_rows = os.getenv("S1_LIMIT_ROWS")
    if s1_limit_rows:
        try:
            rows = rows[: int(s1_limit_rows)]
        except Exception:
            pass
    for row in tqdm(rows):
        prompt = render_template(
            template_path,
            {
                "domain": row["domain"],
                "subdomain": row["subdomain"],
                # default number of scenarios
                "num_scenarios": os.getenv("S1_NUM_SCENARIOS", "1"),
            },
        )
        system = (
            "You are a careful data generator. Follow the format strictly and wrap each scenario inside <scenario> tags."
            + get_system_prompt_suffix()
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
        # Optional: rate limiting sleep between calls
        try:
            rate_sleep = float(os.getenv("OPENAI_RATE_SLEEP", "0"))
            if rate_sleep > 0:
                time.sleep(rate_sleep)
        except Exception:
            pass

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
