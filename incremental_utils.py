"""
共用增量寫入與平行處理工具模組

提供功能：
1. 增量寫入 (Incremental Writing): 一邊產生一邊寫入 JSONL，避免中斷後資料遺失
2. 斷點續傳 (Resume from Checkpoint): 讀取已完成的 index，從中間繼續
3. 平行處理 (Parallel Processing): 使用 ThreadPoolExecutor 加速 API 呼叫
4. 最終合併 (Final Merge): 將 JSONL 轉換為最終 JSON 格式

使用範例:
    from incremental_utils import IncrementalWriter, load_completed_indices, run_parallel_tasks
    
    # 建立增量寫入器
    writer = IncrementalWriter("pipeline/data/{run_id}/functions.jsonl")
    completed = load_completed_indices(writer.jsonl_path)
    
    # 過濾已完成的項目
    tasks = [(idx, item) for idx, item in enumerate(items) if idx not in completed]
    
    # 平行處理
    results = run_parallel_tasks(process_fn, tasks, max_workers=5)
    
    # 寫入結果
    for idx, result in results:
        writer.write(result, idx)
    
    # 轉換為最終 JSON
    writer.finalize_to_json("pipeline/data/{run_id}/functions.json")
"""
import json
import os
import threading
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

T = TypeVar('T')


class IncrementalWriter:
    """
    增量寫入器：邊產生邊寫入 JSONL 檔案
    
    特性:
    - 線程安全 (Thread-safe)
    - 每次寫入自動 flush
    - 支援 sample_index 追蹤
    """
    
    def __init__(self, jsonl_path: str, mode: str = "a"):
        """
        Args:
            jsonl_path: JSONL 輸出檔案路徑
            mode: 寫入模式 ("a" 附加, "w" 覆寫)
        """
        self.jsonl_path = jsonl_path
        self.mode = mode
        self._lock = threading.Lock()
        self._written_count = 0
        
        # 確保目錄存在
        os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
        
        # 開啟檔案
        self._file = open(jsonl_path, mode, encoding="utf-8")
        
    def write(self, record: Dict[str, Any], sample_index: Optional[int] = None) -> None:
        """
        寫入一筆記錄到 JSONL
        
        Args:
            record: 要寫入的記錄
            sample_index: 樣本索引 (會自動加入 _sample_index 欄位)
        """
        if sample_index is not None:
            record = {**record, "_sample_index": sample_index}
        
        with self._lock:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
            self._written_count += 1
    
    def close(self) -> None:
        """關閉檔案"""
        with self._lock:
            if self._file and not self._file.closed:
                self._file.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    @property
    def written_count(self) -> int:
        """已寫入的記錄數"""
        return self._written_count
    
    def finalize_to_json(self, json_path: str, sort_by_index: bool = True) -> int:
        """
        將 JSONL 轉換為最終的 JSON 陣列格式
        
        Args:
            json_path: 輸出 JSON 檔案路徑
            sort_by_index: 是否按 sample_index 排序
            
        Returns:
            記錄總數
        """
        self.close()
        
        records: List[Dict[str, Any]] = []
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        
        if sort_by_index:
            # 按 _sample_index 排序
            records.sort(key=lambda r: r.get("_sample_index", float('inf')))
        
        # 移除 _sample_index 欄位
        for r in records:
            r.pop("_sample_index", None)
        
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(records, ensure_ascii=False, indent=2))
        
        logging.info(f"Finalized {len(records)} records -> {json_path}")
        return len(records)


def load_completed_indices(jsonl_path: str) -> Set[int]:
    """
    從現有 JSONL 檔案載入已完成的 sample_index
    
    Args:
        jsonl_path: JSONL 檔案路徑
        
    Returns:
        已完成的 sample_index 集合
    """
    completed: Set[int] = set()
    
    if not os.path.exists(jsonl_path):
        return completed
    
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if "_sample_index" in record:
                            completed.add(record["_sample_index"])
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logging.warning(f"Error loading completed indices from {jsonl_path}: {e}")
    
    if completed:
        logging.info(f"Resuming: found {len(completed)} completed samples in {jsonl_path}")
    
    return completed


def run_parallel_tasks(
    task_fn: Callable[[int, T], Optional[Dict[str, Any]]],
    items: List[Tuple[int, T]],
    max_workers: int = 5,
    desc: str = "Processing",
    writer: Optional[IncrementalWriter] = None,
) -> List[Tuple[int, Optional[Dict[str, Any]]]]:
    """
    平行執行任務並收集結果
    
    Args:
        task_fn: 處理函數 (idx, item) -> result
        items: [(index, item), ...] 要處理的項目列表
        max_workers: 最大工作線程數
        desc: 進度條描述
        writer: 可選的增量寫入器，若提供則立即寫入結果
        
    Returns:
        [(index, result), ...] 結果列表
    """
    if not items:
        return []
    
    results: List[Tuple[int, Optional[Dict[str, Any]]]] = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任務
        future_to_idx = {
            executor.submit(task_fn, idx, item): idx 
            for idx, item in items
        }
        
        # 收集結果並顯示進度
        with tqdm(total=len(items), desc=desc) as pbar:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    results.append((idx, result))
                    
                    # 立即寫入結果
                    if writer and result is not None:
                        writer.write(result, idx)
                        
                except Exception as e:
                    logging.error(f"Task {idx} failed: {e}")
                    results.append((idx, None))
                
                pbar.update(1)
    
    return results


def get_parallel_workers() -> int:
    """
    獲取平行處理的工作線程數
    
    可透過 PARALLEL_WORKERS 環境變數設定，預設為 5
    """
    try:
        return int(os.getenv("PARALLEL_WORKERS", "5"))
    except ValueError:
        return 5


def ensure_jsonl_path(base_path: str) -> str:
    """
    確保增量 JSONL 路徑 (在同目錄，加上 .incr.jsonl 後綴)
    
    Args:
        base_path: 原始 JSON 路徑，如 "pipeline/data/{run_id}/functions.json"
        
    Returns:
        增量 JSONL 路徑，如 "pipeline/data/{run_id}/functions.incr.jsonl"
    """
    if base_path.endswith(".json"):
        return base_path.replace(".json", ".incr.jsonl")
    return base_path + ".incr.jsonl"


def check_final_json_exists(json_path: str) -> bool:
    """檢查最終 JSON 檔案是否存在且有效"""
    if not os.path.exists(json_path):
        return False
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


def count_jsonl_records(jsonl_path: str) -> int:
    """計算 JSONL 檔案中的記錄數"""
    if not os.path.exists(jsonl_path):
        return 0
    
    count = 0
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except Exception:
        pass
    return count
