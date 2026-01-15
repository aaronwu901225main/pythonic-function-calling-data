"""
S1 多行組合生成版本
支援從 curriculum 隨機抽取多行來生成場景，避免產生類似的題目

環境變數設定：
- S1_MULTIROW_CONFIG: 設定格式如 "2*500,3*250,4*250"
  - 表示: 抽2行生成500題, 抽3行生成250題, 抽4行生成250題
- 如果未設定此變數，則回退到原本的單行生成模式

範例:
export S1_MULTIROW_CONFIG="2*500,3*250,4*250"
python run_s1_openai_multirow.py
"""

import asyncio
import csv
import json
import logging
import os
import uuid
import time
import random
from typing import List, Dict, Tuple, Set
from tqdm import tqdm
from openai_utils import render_template, extract_tags, chat_complete
from itertools import combinations

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 語言設定：支援 "en" (英文) 或 "zh_tw" (繁體中文)
def get_language() -> str:
    """獲取當前語言設定"""
    return os.getenv("LANG_CODE", "en").lower()

def get_prompt_path(base_path: str) -> str:
    """根據語言設定獲取對應的 prompt 路徑
    
    Args:
        base_path: 基礎 prompt 路徑，如 'pipeline/s1_scenario/prompt.md'
    
    Returns:
        對應語言的 prompt 路徑
    """
    lang = get_language()
    if lang == "zh_tw":
        # 將 prompt.md 轉換為 prompt_zh_tw.md
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
    """讀取 curriculum CSV 檔案"""
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


def parse_multirow_config(config_str: str) -> List[Tuple[int, int]]:
    """
    解析多行配置字串
    
    Args:
        config_str: 格式如 "2*500,3*250,4*250"
    
    Returns:
        [(rows_count, sample_count), ...] 如 [(2, 500), (3, 250), (4, 250)]
    """
    if not config_str:
        return []
    
    configs = []
    parts = config_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            rows_count, sample_count = part.split('*')
            configs.append((int(rows_count), int(sample_count)))
        except (ValueError, IndexError) as e:
            logging.warning(f"無法解析配置 '{part}': {e}")
            continue
    
    return configs


def generate_row_combinations(
    all_rows: List[Dict[str, str]], 
    rows_per_sample: int, 
    num_samples: int
) -> List[List[Dict[str, str]]]:
    """
    生成不重複的行組合
    
    Args:
        all_rows: 所有可用的 curriculum 行
        rows_per_sample: 每個樣本要抽取的行數
        num_samples: 要生成的樣本數
    
    Returns:
        組合列表，每個組合是 rows_per_sample 個 row 的列表
    """
    total_rows = len(all_rows)
    
    if rows_per_sample > total_rows:
        raise ValueError(
            f"要求每個樣本抽取 {rows_per_sample} 行，但總共只有 {total_rows} 行"
        )
    
    # 計算理論上可能的組合數
    from math import comb
    max_combinations = comb(total_rows, rows_per_sample)
    
    if num_samples > max_combinations:
        logging.warning(
            f"要求 {num_samples} 個樣本，但只有 {max_combinations} 種不重複組合。"
            f"將生成所有可能的組合。"
        )
        num_samples = max_combinations
    
    # 生成所有可能的組合索引
    all_indices_combinations = list(combinations(range(total_rows), rows_per_sample))
    
    # 隨機抽取所需數量的組合
    if num_samples >= len(all_indices_combinations):
        selected_indices_combinations = all_indices_combinations
    else:
        selected_indices_combinations = random.sample(all_indices_combinations, num_samples)
    
    # 將索引組合轉換為實際的行組合
    result = []
    for indices in selected_indices_combinations:
        combination = [all_rows[i] for i in indices]
        result.append(combination)
    
    return result


def merge_rows(rows: List[Dict[str, str]]) -> Dict[str, str]:
    """
    合併多個 curriculum 行
    
    將多個行的 domain, subdomain, entities 合併成一個綜合的描述
    """
    domains = list(set(row["domain"] for row in rows))
    subdomains = [f"{row['domain']}/{row['subdomain']}" for row in rows]
    
    # 合併 entities (如果有的話)
    all_entities = []
    for row in rows:
        entities_str = row.get("entities", "")
        if entities_str:
            try:
                entities = eval(entities_str)  # 從字符串轉為列表
                if isinstance(entities, list):
                    all_entities.extend(entities)
            except:
                pass
    
    # 去重
    all_entities = list(set(all_entities))
    
    return {
        "domain": ", ".join(domains),
        "subdomain": " + ".join(subdomains),
        "entities": str(all_entities) if all_entities else "",
        "original_rows": rows,  # 保留原始行以供參考
    }


def _generate_curriculum_usage_csv(all_data: List[Dict], csv_path: str):
    """
    生成 curriculum 使用記錄的 CSV 檔案
    
    格式：
    - 2*500: 7列 (題號, domain1, subdomain1, entity1, domain2, subdomain2, entity2)
    - 3*500: 10列 (題號, domain1, subdomain1, entity1, domain2, subdomain2, entity2, domain3, subdomain3, entity3)
    """
    if not all_data:
        return
    
    # 找出最大的 rows_per_sample
    max_rows = 0
    for d in all_data:
        if "meta" in d and "rows_per_sample" in d["meta"]:
            max_rows = max(max_rows, d["meta"]["rows_per_sample"])
    
    if max_rows == 0:
        logging.warning("無法生成 CSV：找不到 rows_per_sample 資訊")
        return
    
    # 建立標題
    headers = ["題號"]
    for i in range(1, max_rows + 1):
        headers.extend([f"domain{i}", f"subdomain{i}", f"entities{i}"])
    
    # 準備數據
    rows = []
    for idx, data in enumerate(all_data, 1):
        if "meta" not in data:
            continue
        
        row = [str(idx)]
        original_rows = data["meta"].get("original_rows", [])
        
        # 添加每個原始行的資訊
        for orig_row in original_rows:
            row.append(orig_row.get("domain", ""))
            row.append(orig_row.get("subdomain", ""))
            row.append(orig_row.get("entities", ""))
        
        # 補齊空白欄位（如果此題的行數少於最大行數）
        while len(row) < len(headers):
            row.append("")
        
        rows.append(row)
    
    # 寫入 CSV
    import csv
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    
    logging.info(f"CSV 記錄檔案: {len(rows)} 題, {len(headers)} 欄")


async def generate_scenarios_multirow(run_id: str, multirow_configs: List[Tuple[int, int]]):
    """
    使用多行組合模式生成場景
    
    Args:
        run_id: 運行 ID
        multirow_configs: [(rows_count, sample_count), ...] 配置列表
    """
    os.makedirs(f"pipeline/data/{run_id}", exist_ok=True)
    
    # 根據語言設定選擇 prompt
    template_path = get_prompt_path("pipeline/s1_scenario/prompt.md")
    lang = get_language()
    logging.info(f"使用語言: {lang}, prompt 路徑: {template_path}")
    all_data: List[Dict] = []
    
    # 讀取 curriculum
    csv_path = os.getenv("CURRICULUM_CSV", "pipeline/data/curriculum.csv")
    logging.info(f"使用 curriculum 檔案: {csv_path}")
    all_rows = read_curriculum(csv_path)
    logging.info(f"共讀取 {len(all_rows)} 行 curriculum 資料")
    
    # 對每個配置生成樣本
    for config_idx, (rows_per_sample, num_samples) in enumerate(multirow_configs):
        logging.info(f"\n配置 {config_idx + 1}: 每題抽取 {rows_per_sample} 行，生成 {num_samples} 題")
        
        # 生成不重複的行組合
        combinations_list = generate_row_combinations(all_rows, rows_per_sample, num_samples)
        logging.info(f"成功生成 {len(combinations_list)} 個不重複的行組合")
        
        # 對每個組合生成場景
        for combo_idx, row_combination in enumerate(tqdm(combinations_list, desc=f"配置{config_idx+1}")):
            # 合併多行
            merged_row = merge_rows(row_combination)
            
            # 生成 prompt
            prompt = render_template(
                template_path,
                {
                    "domain": merged_row["domain"],
                    "subdomain": merged_row["subdomain"],
                    "num_scenarios": os.getenv("S1_NUM_SCENARIOS", "1"),
                },
            )
            
            system = (
                "You are a careful data generator. Follow the format strictly and wrap each scenario inside <scenario> tags. "
                f"Generate scenarios that integrate concepts from multiple domains: {merged_row['subdomain']}"
                + get_system_prompt_suffix()
            )
            
            content = chat_complete(prompt=prompt, system=system)
            scenarios = extract_tags(content, "scenario")
            
            for sce in scenarios:
                data_entry = {
                    "domain": merged_row["domain"],
                    "subdomain": merged_row["subdomain"],
                    "entities": merged_row["entities"],
                    "scenario": sce.strip(),
                    # 額外的元資料
                    "meta": {
                        "config_index": config_idx,
                        "rows_per_sample": rows_per_sample,
                        "combination_index": combo_idx,
                        "original_rows_count": len(row_combination),
                        "original_domains": [r["domain"] for r in row_combination],
                        "original_subdomains": [r["subdomain"] for r in row_combination],
                        "original_rows": row_combination,  # 完整的原始行資訊
                    }
                }
                all_data.append(data_entry)
            
            # Rate limiting
            try:
                rate_sleep = float(os.getenv("OPENAI_RATE_SLEEP", "0"))
                if rate_sleep > 0:
                    time.sleep(rate_sleep)
            except Exception:
                pass
    
    # 保存結果
    output_path = f"pipeline/data/{run_id}/scenarios.json"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(all_data, ensure_ascii=False, indent=2))
    
    logging.info(f"\n總共生成 {len(all_data)} 個場景")
    logging.info(f"保存至: {output_path}")
    
    # 生成 CSV 記錄檔案
    csv_path = f"pipeline/data/{run_id}/curriculum_usage.csv"
    _generate_curriculum_usage_csv(all_data, csv_path)
    logging.info(f"Curriculum 使用記錄保存至: {csv_path}")
    
    # 生成統計報告
    stats = {
        "total_scenarios": len(all_data),
        "configurations": []
    }
    
    for config_idx, (rows_per_sample, num_samples) in enumerate(multirow_configs):
        config_scenarios = [d for d in all_data if d["meta"]["config_index"] == config_idx]
        stats["configurations"].append({
            "rows_per_sample": rows_per_sample,
            "requested_samples": num_samples,
            "generated_scenarios": len(config_scenarios),
            "unique_combinations": len(set(d["meta"]["combination_index"] for d in config_scenarios)),
        })
    
    stats_path = f"pipeline/data/{run_id}/scenarios_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(stats, ensure_ascii=False, indent=2))
    
    logging.info(f"\n統計報告:")
    for i, config_stat in enumerate(stats["configurations"]):
        logging.info(f"  配置 {i+1} ({config_stat['rows_per_sample']}行*{config_stat['requested_samples']}題):")
        logging.info(f"    - 生成場景數: {config_stat['generated_scenarios']}")
        logging.info(f"    - 唯一組合數: {config_stat['unique_combinations']}")


async def generate_scenarios_single_row(run_id: str):
    """
    原始的單行生成模式 (回退模式)
    """
    os.makedirs(f"pipeline/data/{run_id}", exist_ok=True)

    # 根據語言設定選擇 prompt
    template_path = get_prompt_path("pipeline/s1_scenario/prompt.md")
    lang = get_language()
    logging.info(f"使用語言: {lang}, prompt 路徑: {template_path}")
    data: List[Dict] = []

    csv_path = os.getenv("CURRICULUM_CSV", "pipeline/data/curriculum.csv")
    logging.info(f"使用 curriculum 檔案: {csv_path}")
    rows = read_curriculum(csv_path)
    
    # Optional: limit number of curriculum rows
    s1_limit_rows = os.getenv("S1_LIMIT_ROWS")
    if s1_limit_rows:
        try:
            rows = rows[: int(s1_limit_rows)]
        except Exception:
            pass
    
    logging.info(f"單行模式: 處理 {len(rows)} 行 curriculum")
    
    for row in tqdm(rows):
        prompt = render_template(
            template_path,
            {
                "domain": row["domain"],
                "subdomain": row["subdomain"],
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
    
    logging.info(f"單行模式: 共生成 {len(data)} 個場景")


async def main():
    # 檢查是否設定多行配置
    multirow_config_str = os.getenv("S1_MULTIROW_CONFIG")
    
    run_id = uuid.uuid4().hex
    with open("run_id", "w", encoding="utf-8") as f:
        f.write(run_id)
    logging.info(f"Run ID: {run_id}")
    
    if multirow_config_str:
        # 多行模式
        logging.info(f"檢測到多行配置: {multirow_config_str}")
        multirow_configs = parse_multirow_config(multirow_config_str)
        
        if not multirow_configs:
            logging.error("多行配置解析失敗，請檢查格式 (應為 '2*500,3*250,4*250')")
            return
        
        logging.info(f"解析到 {len(multirow_configs)} 個配置:")
        for rows, samples in multirow_configs:
            logging.info(f"  - {rows} 行 * {samples} 題")
        
        await generate_scenarios_multirow(run_id, multirow_configs)
        logging.info("多行模式生成完成")
    else:
        # 單行模式 (原始模式)
        logging.info("未設定 S1_MULTIROW_CONFIG，使用單行模式")
        await generate_scenarios_single_row(run_id)
        logging.info("單行模式生成完成")


if __name__ == "__main__":
    asyncio.run(main())
