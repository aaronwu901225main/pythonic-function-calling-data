import asyncio
import csv
import json
import logging
import os
import uuid
import time
from typing import List, Dict, Tuple, Any, Optional
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


def process_single_row(idx: int, row_data: Tuple[Dict[str, str], str, str]) -> Optional[List[Dict[str, Any]]]:
    """
    處理單一 curriculum row，生成 scenarios
    
    Args:
        idx: row 索引
        row_data: (row, template_path, system_prompt)
        
    Returns:
        生成的 scenarios 列表，或 None 如果失敗
    """
    row, template_path, system = row_data
    
    try:
        prompt = render_template(
            template_path,
            {
                "domain": row["domain"],
                "subdomain": row["subdomain"],
                "num_scenarios": os.getenv("S1_NUM_SCENARIOS", "1"),
            },
        )
        content = chat_complete(prompt=prompt, system=system)
        scenarios = extract_tags(content, "scenario")
        
        results = []
        for sce in scenarios:
            results.append({
                "domain": row["domain"],
                "subdomain": row["subdomain"],
                "entities": row.get("entities", ""),
                "scenario": sce.strip(),
            })
        
        return results
    except Exception as e:
        logging.error(f"Row {idx} failed: {e}")
        return None


async def generate_scenarios_openai(run_id: str):
    os.makedirs(f"pipeline/data/{run_id}", exist_ok=True)

    # 檢查最終 JSON 是否已存在
    json_path = f"pipeline/data/{run_id}/scenarios.json"
    jsonl_path = ensure_jsonl_path(json_path)
    
    if check_final_json_exists(json_path):
        logging.info(f"scenarios.json already exists, skipping S1")
        return

    # 根據語言設定選擇 prompt
    template_path = get_prompt_path("pipeline/s1_scenario/prompt.md")
    lang = get_language()
    logging.info(f"使用語言: {lang}, prompt 路徑: {template_path}")
    
    system = (
        "You are a careful data generator. Follow the format strictly and wrap each scenario inside <scenario> tags."
        + get_system_prompt_suffix()
    )

    # Use CURRICULUM_CSV environment variable or default to curriculum.csv
    csv_path = os.getenv("CURRICULUM_CSV", "pipeline/data/curriculum.csv")
    logging.info(f"Using curriculum file: {csv_path}")
    rows = read_curriculum(csv_path)
    
    # Optional: limit number of curriculum rows
    s1_limit_rows = os.getenv("S1_LIMIT_ROWS")
    if s1_limit_rows:
        try:
            rows = rows[: int(s1_limit_rows)]
        except Exception:
            pass

    # 載入已完成的 indices
    completed = load_completed_indices(jsonl_path)
    
    # 過濾未完成的項目
    items_to_process = [
        (idx, (row, template_path, system))
        for idx, row in enumerate(rows)
        if idx not in completed
    ]
    
    if not items_to_process:
        logging.info("All rows already processed, finalizing...")
    else:
        logging.info(f"Processing {len(items_to_process)} rows (skipping {len(completed)} completed)")
        
        # 增量寫入器
        with IncrementalWriter(jsonl_path, mode="a") as writer:
            # 定義處理函數 wrapper
            def process_wrapper(idx: int, row_data: Tuple[Dict[str, str], str, str]) -> Optional[Dict[str, Any]]:
                results = process_single_row(idx, row_data)
                if results:
                    # 回傳包含多個 scenario 的記錄
                    return {"_scenarios": results}
                return None
            
            # 平行處理
            max_workers = get_parallel_workers()
            run_parallel_tasks(
                process_wrapper,
                items_to_process,
                max_workers=max_workers,
                desc="Generating Scenarios",
                writer=writer,
            )
    
    # 轉換為最終 JSON 格式
    # 需要展開 _scenarios 列表
    records: List[Dict[str, Any]] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                record = json.loads(line)
                if "_scenarios" in record:
                    records.extend(record["_scenarios"])
    
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(records, ensure_ascii=False, indent=2))
    
    logging.info(f"Finalized {len(records)} scenarios -> {json_path}")


async def main():
    run_id = uuid.uuid4().hex
    with open("run_id", "w", encoding="utf-8") as f:
        f.write(run_id)
    logging.info(f"Run ID: {run_id}")
    await generate_scenarios_openai(run_id)
    logging.info("Generated Scenarios (OpenAI mode)")


if __name__ == "__main__":
    asyncio.run(main())
