#!/usr/bin/env python3
"""
BFCL Multi-Turn 測試錯誤類型統計分析程式

此程式會分析 score/{model_name}/multi_turn/ 資料夾中的 JSON 檔案，
統計各種錯誤類型的數量和百分比。

錯誤類型包括：
1. multi_turn:inference_error - 模型輸出格式錯誤
2. multi_turn:force_terminated - 回合數不匹配
3. multi_turn:empty_turn_model_response - 需要函數呼叫時模型輸出為空
4. multi_turn:instance_state_mismatch - 物件狀態不匹配
5. multi_turn:execution_response_mismatch - 函數回傳值不匹配
6. multi_turn:irrelevance_error:decoder_success - 不需要函數呼叫時卻發出了有效的函數呼叫

額外統計：
- function_call_over - 模型呼叫的函數數量超過預期
- function_call_under - 模型呼叫的函數數量少於預期

用法:
    python analyze_multi_turn_errors.py <model_name> [--all]
    
範例:
    python analyze_multi_turn_errors.py Salesforce_Llama-xLAM-2-8b-fc-r
    python analyze_multi_turn_errors.py --all
"""

import json
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import csv


# 定義所有可能的錯誤類型
ERROR_TYPES = [
    "multi_turn:inference_error",
    "multi_turn:force_terminated", 
    "multi_turn:empty_turn_model_response",
    "multi_turn:instance_state_mismatch",
    "multi_turn:execution_response_mismatch",
    "multi_turn:irrelevance_error:decoder_success",
]

# 額外的 function call 數量統計類型
FC_COUNT_TYPES = [
    "function_call_over",   # 多 call
    "function_call_under",  # 少 call
]

# 測試類別
TEST_CATEGORIES = [
    "multi_turn_base",
    "multi_turn_miss_func",
    "multi_turn_miss_param",
    "multi_turn_long_context",
    "zh_multi_turn_base",
    "zh_multi_turn_miss_func",
    "zh_multi_turn_miss_param",
    "zh_multi_turn_long_context",
]


def count_function_calls_per_turn(turn_data) -> int:
    """
    計算單一輪次的 function call 數量。
    turn_data 可能是 list of strings 或單一 string。
    """
    if not turn_data:
        return 0
    
    if isinstance(turn_data, list):
        count = 0
        for item in turn_data:
            if isinstance(item, list):
                count += len(item)
            elif isinstance(item, str):
                count += 1
        return count
    elif isinstance(turn_data, str):
        return 1
    return 0


def extract_function_names_per_turn(turn_data) -> List[str]:
    """
    從單一輪次的 function call 資料中提取函數名稱列表。
    例如: "cd(folder='workspace')" -> "cd"
    """
    import re
    
    if not turn_data:
        return []
    
    func_names = []
    if isinstance(turn_data, list):
        for item in turn_data:
            if isinstance(item, list):
                for call in item:
                    if isinstance(call, str):
                        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)', call)
                        if match:
                            func_names.append(match.group(1))
            elif isinstance(item, str):
                match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)', item)
                if match:
                    func_names.append(match.group(1))
    elif isinstance(turn_data, str):
        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)', turn_data)
        if match:
            func_names.append(match.group(1))
    
    return func_names


def analyze_function_call_count(entry: dict) -> Dict[str, bool]:
    """
    逐題分析 function call 數量差異和函數名稱正確性。
    遍歷所有輪次，如果任一輪發生某種情況則標記為 True。
    
    Returns:
        Dict[str, bool]: 包含各類型是否發生的字典
            - "over": 是否有任一輪模型比預期多 call
            - "under": 是否有任一輪模型比預期少 call
            - "equal_wrong": 是否有任一輪數量相等但函數名稱錯誤
            - "equal_correct": 只有當以上三個都沒發生，且有任一輪數量相等但內容不同時為 True
    """
    model_result = entry.get("model_result_decoded", [])
    possible_answer = entry.get("possible_answer", [])
    
    result = {
        "over": False,
        "under": False,
        "equal_correct": False,
        "equal_wrong": False,
    }
    
    # 用於追蹤是否有 equal_correct 的候選輪次
    has_equal_correct_candidate = False
    
    # 確保兩者都是列表
    if not isinstance(model_result, list):
        model_result = []
    if not isinstance(possible_answer, list):
        possible_answer = []
    
    # 取最大輪次數來遍歷
    max_turns = max(len(model_result), len(possible_answer))
    
    for i in range(max_turns):
        # 取得該輪的資料，若超出範圍則為空
        model_turn = model_result[i] if i < len(model_result) else []
        expected_turn = possible_answer[i] if i < len(possible_answer) else []
        
        # 如果該輪與 GT 完全相同，跳過不計入統計
        if model_turn == expected_turn:
            continue
        
        model_count = count_function_calls_per_turn(model_turn)
        expected_count = count_function_calls_per_turn(expected_turn)
        
        if model_count > expected_count:
            result["over"] = True
        elif model_count < expected_count:
            result["under"] = True
        else:
            # 數量相等，檢查函數名稱
            model_funcs = extract_function_names_per_turn(model_turn)
            expected_funcs = extract_function_names_per_turn(expected_turn)
            if sorted(model_funcs) == sorted(expected_funcs):
                has_equal_correct_candidate = True
            else:
                result["equal_wrong"] = True
    
    # equal_correct 只有在其他三個都沒發生時才計入
    if has_equal_correct_candidate and not result["over"] and not result["under"] and not result["equal_wrong"]:
        result["equal_correct"] = True
    
    return result


def analyze_score_file(file_path: str) -> Dict:
    """
    分析單一 score JSON 檔案，統計錯誤類型。
    
    Returns:
        Dict: 包含 total, correct, 和各種錯誤類型計數的字典
    """
    stats = {
        "total": 0,
        "correct": 0,
        "errors": defaultdict(int),
        "error_questions": defaultdict(list),  # 記錄每種錯誤的題號
        "other_errors": 0,
        "fc_over": 0,           # function call 多 call
        "fc_under": 0,          # function call 少 call
        "fc_equal_correct": 0,  # function call 數量相等且函數名稱正確
        "fc_equal_wrong": 0,    # function call 數量相等但函數名稱錯誤
        "fc_over_questions": [],
        "fc_under_questions": [],
        "fc_equal_correct_questions": [],
        "fc_equal_wrong_questions": [],
    }
    
    if not os.path.exists(file_path):
        return stats
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
                
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"警告: 第 {line_num} 行 JSON 解析錯誤: {e}")
                continue
            
            # 第一行是總結統計（包含 accuracy, correct_count, total_count）
            if "accuracy" in entry and "total_count" in entry:
                stats["total"] = entry.get("total_count", 0)
                stats["correct"] = entry.get("correct_count", 0)
                continue
            
            # 個別測試結果
            if "valid" not in entry:
                continue
            
            # 逐題統計 function call 數量差異（有發生就加一）
            fc_counts = analyze_function_call_count(entry)
            
            # 獲取題號（使用 id 欄位，若無則使用行號）
            question_id = entry.get("id", f"line_{line_num}")
            
            if fc_counts["over"]:
                stats["fc_over"] += 1
                stats["fc_over_questions"].append(question_id)
            if fc_counts["under"]:
                stats["fc_under"] += 1
                stats["fc_under_questions"].append(question_id)
            if fc_counts["equal_correct"]:
                stats["fc_equal_correct"] += 1
                stats["fc_equal_correct_questions"].append(question_id)
            if fc_counts["equal_wrong"]:
                stats["fc_equal_wrong"] += 1
                stats["fc_equal_wrong_questions"].append(question_id)
                
            if entry["valid"]:
                continue  # 正確的測試不需要記錄錯誤
            
            # 錯誤的測試
            error_info = entry.get("error", {})
            error_type = error_info.get("error_type", "unknown")
            
            # 獲取題號（使用 id 欄位，若無則使用行號）
            question_id = entry.get("id", f"line_{line_num}")
            
            if error_type in ERROR_TYPES:
                stats["errors"][error_type] += 1
                stats["error_questions"][error_type].append(question_id)
            else:
                stats["errors"][error_type] += 1
                stats["error_questions"][error_type].append(question_id)
                if error_type != "unknown":
                    stats["other_errors"] += 1
    
    return stats


def analyze_model(model_name: str, score_dir: str) -> Dict:
    """
    分析特定模型的所有 multi-turn 測試結果。
    
    Returns:
        Dict: 以測試類別為 key 的統計結果字典
    """
    model_multi_turn_dir = os.path.join(score_dir, model_name, "multi_turn")
    
    if not os.path.exists(model_multi_turn_dir):
        print(f"警告: 找不到目錄 {model_multi_turn_dir}")
        return {}
    
    results = {}
    
    for category in TEST_CATEGORIES:
        score_file = os.path.join(model_multi_turn_dir, f"BFCL_v4_{category}_score.json")
        if os.path.exists(score_file):
            category_stats = analyze_score_file(score_file)
            # 在題號前加上類別名稱作為前綴
            if "error_questions" in category_stats:
                prefixed_questions = defaultdict(list)
                for error_type, question_ids in category_stats["error_questions"].items():
                    prefixed_questions[error_type] = [f"{category}:{qid}" for qid in question_ids]
                category_stats["error_questions"] = prefixed_questions
            
            # 處理 fc 相關題號
            for fc_type in ["fc_over_questions", "fc_under_questions", "fc_equal_correct_questions", "fc_equal_wrong_questions"]:
                if fc_type in category_stats:
                    category_stats[fc_type] = [f"{category}:{qid}" for qid in category_stats[fc_type]]
            
            results[category] = category_stats
    
    return results


def get_all_models(score_dir: str) -> List[str]:
    """獲取 score 目錄下所有模型名稱"""
    models = []
    if not os.path.exists(score_dir):
        return models
    
    for item in os.listdir(score_dir):
        item_path = os.path.join(score_dir, item)
        if os.path.isdir(item_path):
            multi_turn_path = os.path.join(item_path, "multi_turn")
            if os.path.exists(multi_turn_path):
                models.append(item)
    
    return sorted(models)


def print_model_report(model_name: str, results: Dict):
    """
    印出單一模型的詳細報告。
    """
    print("\n" + "=" * 80)
    print(f"模型: {model_name}")
    print("=" * 80)
    
    # 彙總所有類別
    total_all = 0
    correct_all = 0
    error_counts_all = defaultdict(int)
    error_questions_all = defaultdict(list)
    fc_over_all = 0
    fc_under_all = 0
    fc_equal_correct_all = 0
    fc_equal_wrong_all = 0
    
    for category in TEST_CATEGORIES:
        if category not in results:
            continue
            
        stats = results[category]
        total_all += stats["total"]
        correct_all += stats["correct"]
        fc_over_all += stats.get("fc_over", 0)
        fc_under_all += stats.get("fc_under", 0)
        fc_equal_correct_all += stats.get("fc_equal_correct", 0)
        fc_equal_wrong_all += stats.get("fc_equal_wrong", 0)
        
        for error_type, count in stats["errors"].items():
            error_counts_all[error_type] += count
        
        # 收集錯誤題號
        if "error_questions" in stats:
            for error_type, question_ids in stats["error_questions"].items():
                error_questions_all[error_type].extend(question_ids)
    
    # 印出各類別詳細資訊
    print("\n📊 各測試類別統計:")
    print("-" * 80)
    print(f"{'測試類別':<40} {'總數':>8} {'正確':>8} {'準確率':>10}")
    print("-" * 80)
    
    for category in TEST_CATEGORIES:
        if category not in results:
            continue
        stats = results[category]
        accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"{category:<40} {stats['total']:>8} {stats['correct']:>8} {accuracy:>9.1f}%")
    
    print("-" * 80)
    total_accuracy = (correct_all / total_all * 100) if total_all > 0 else 0
    print(f"{'總計':<40} {total_all:>8} {correct_all:>8} {total_accuracy:>9.1f}%")
    
    # 印出錯誤類型統計
    print("\n📋 錯誤類型統計:")
    print("-" * 80)
    print(f"{'錯誤類型':<55} {'數量':>8} {'百分比':>10}")
    print("-" * 80)
    
    error_total = sum(error_counts_all.values())
    
    for error_type in ERROR_TYPES:
        count = error_counts_all.get(error_type, 0)
        percentage = (count / error_total * 100) if error_total > 0 else 0
        # 縮短錯誤類型名稱以便顯示
        short_type = error_type.replace("multi_turn:", "")
        print(f"{short_type:<55} {count:>8} {percentage:>9.1f}%")
    
    # 其他未知錯誤
    other_count = 0
    for error_type, count in error_counts_all.items():
        if error_type not in ERROR_TYPES:
            other_count += count
    
    if other_count > 0:
        percentage = (other_count / error_total * 100) if error_total > 0 else 0
        print(f"{'其他錯誤':<55} {other_count:>8} {percentage:>9.1f}%")
    
    print("-" * 80)
    print(f"{'錯誤總數':<55} {error_total:>8}")
    
    # 印出錯誤題號（僅顯示前 10 個，避免輸出過長）
    print("\n📝 錯誤題號列表 (僅顯示前 10 個):")
    print("-" * 80)
    for error_type in ERROR_TYPES:
        if error_type in error_questions_all and error_questions_all[error_type]:
            short_type = error_type.replace("multi_turn:", "")
            questions = error_questions_all[error_type][:10]
            questions_str = ", ".join(questions)
            more = f" ... 及其他 {len(error_questions_all[error_type]) - 10} 個" if len(error_questions_all[error_type]) > 10 else ""
            print(f"{short_type}: {questions_str}{more}")
    print("-" * 80)
    
    # 印出 Function Call 數量統計
    print("\n🔧 Function Call 數量統計:")
    print("-" * 80)
    fc_total = fc_over_all + fc_under_all + fc_equal_correct_all + fc_equal_wrong_all
    if fc_total > 0:
        print(f"{'FC 數量過多 (over)':<55} {fc_over_all:>8} {(fc_over_all/fc_total*100):>9.1f}%")
        print(f"{'FC 數量過少 (under)':<55} {fc_under_all:>8} {(fc_under_all/fc_total*100):>9.1f}%")
        print(f"{'FC 數量相等 且函數正確 (equal_correct)':<55} {fc_equal_correct_all:>8} {(fc_equal_correct_all/fc_total*100):>9.1f}%")
        print(f"{'FC 數量相等 但函數錯誤 (equal_wrong)':<55} {fc_equal_wrong_all:>8} {(fc_equal_wrong_all/fc_total*100):>9.1f}%")
    print("-" * 80)
    
    # 印出各類別的錯誤分佈
    print("\n📈 各類別錯誤分佈:")
    print("-" * 80)
    header = f"{'類別':<25}"
    for error_type in ERROR_TYPES:
        short_type = error_type.replace("multi_turn:", "").replace("_", " ")[:8]
        header += f" {short_type:>8}"
    print(header)
    print("-" * 80)
    
    for category in TEST_CATEGORIES:
        if category not in results:
            continue
        stats = results[category]
        row = f"{category:<25}"
        for error_type in ERROR_TYPES:
            count = stats["errors"].get(error_type, 0)
            row += f" {count:>8}"
        print(row)
    
    print("-" * 80)


def export_to_csv(model_name: str, results: Dict, score_dir: str):
    """
    將結果匯出為 CSV 檔案，儲存在模型根目錄下。
    """
    # 輸出檔案路徑：模型根目錄下
    output_file = os.path.join(score_dir, model_name, "multi_turn_error_analysis.csv")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # 標題列
        header = ["test_category", "total", "correct", "accuracy"]
        for error_type in ERROR_TYPES:
            header.append(error_type.replace("multi_turn:", ""))
        header.extend(["", "fc_over", "fc_under", "fc_equal_correct", "fc_equal_wrong"])
        writer.writerow(header)
        
        # 彙總統計變數
        sum_total = 0
        sum_correct = 0
        sum_errors = defaultdict(int)
        sum_fc_over = 0
        sum_fc_under = 0
        sum_fc_equal_correct = 0
        sum_fc_equal_wrong = 0
        
        # 數據列
        for category in TEST_CATEGORIES:
            if category not in results:
                continue
            stats = results[category]
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
            
            row = [category, stats["total"], stats["correct"], f"{accuracy:.2f}"]
            for error_type in ERROR_TYPES:
                count = stats["errors"].get(error_type, 0)
                row.append(count)
                sum_errors[error_type] += count
            row.append("")  # 空欄位用於區分
            row.append(stats.get("fc_over", 0))
            row.append(stats.get("fc_under", 0))
            row.append(stats.get("fc_equal_correct", 0))
            row.append(stats.get("fc_equal_wrong", 0))
            writer.writerow(row)
            
            # 累計
            sum_total += stats["total"]
            sum_correct += stats["correct"]
            sum_fc_over += stats.get("fc_over", 0)
            sum_fc_under += stats.get("fc_under", 0)
            sum_fc_equal_correct += stats.get("fc_equal_correct", 0)
            sum_fc_equal_wrong += stats.get("fc_equal_wrong", 0)
        
        # Summary 列
        writer.writerow([])  # 空行
        sum_accuracy = (sum_correct / sum_total * 100) if sum_total > 0 else 0
        summary_row = ["SUMMARY", sum_total, sum_correct, f"{sum_accuracy:.2f}"]
        for error_type in ERROR_TYPES:
            summary_row.append(sum_errors[error_type])
        summary_row.extend(["", sum_fc_over, sum_fc_under, sum_fc_equal_correct, sum_fc_equal_wrong])
        writer.writerow(summary_row)
        
        # 收集所有錯誤題號
        all_error_questions = defaultdict(list)
        for category in TEST_CATEGORIES:
            if category not in results:
                continue
            stats = results[category]
            if "error_questions" in stats:
                for error_type, question_ids in stats["error_questions"].items():
                    all_error_questions[error_type].extend(question_ids)
        
        # 收集 fc 相關題號
        all_fc_over = []
        all_fc_under = []
        all_fc_equal_correct = []
        all_fc_equal_wrong = []
        
        for category in TEST_CATEGORIES:
            if category not in results:
                continue
            stats = results[category]
            all_fc_over.extend(stats.get("fc_over_questions", []))
            all_fc_under.extend(stats.get("fc_under_questions", []))
            all_fc_equal_correct.extend(stats.get("fc_equal_correct_questions", []))
            all_fc_equal_wrong.extend(stats.get("fc_equal_wrong_questions", []))
        
        # 錯誤題號列（每個題號佔一行，放在對應的 column 下）
        # 找出最長的題號列表長度
        max_questions = max(
            [len(questions) for questions in all_error_questions.values()] + 
            [len(all_fc_over), len(all_fc_under), len(all_fc_equal_correct), len(all_fc_equal_wrong)]
        ) if (all_error_questions or all_fc_over or all_fc_under or all_fc_equal_correct or all_fc_equal_wrong) else 0
        
        for i in range(max_questions):
            row = ["", "", "", ""]  # 前四欄留空
            for error_type in ERROR_TYPES:
                if error_type in all_error_questions and i < len(all_error_questions[error_type]):
                    row.append(all_error_questions[error_type][i])
                else:
                    row.append("")
            row.append("")  # 空欄位
            # fc 相關題號
            row.append(all_fc_over[i] if i < len(all_fc_over) else "")
            row.append(all_fc_under[i] if i < len(all_fc_under) else "")
            row.append(all_fc_equal_correct[i] if i < len(all_fc_equal_correct) else "")
            row.append(all_fc_equal_wrong[i] if i < len(all_fc_equal_wrong) else "")
            writer.writerow(row)
    
    print(f"✅ 已匯出至: {output_file}")
    return output_file


def export_all_models_to_csv(all_results: Dict[str, Dict], score_dir: str):
    """
    將所有模型的結果分別匯出到各自的根目錄下。
    """
    exported_files = []
    for model_name, results in sorted(all_results.items()):
        output_file = export_to_csv(model_name, results, score_dir)
        exported_files.append(output_file)
    
    return exported_files


def print_summary_table(all_results: Dict[str, Dict]):
    """
    印出所有模型的摘要表格。
    """
    print("\n" + "=" * 115)
    print("📊 所有模型 Multi-Turn 測試摘要")
    print("=" * 115)
    
    # 計算每個模型的彙總統計
    summaries = []
    for model_name, results in all_results.items():
        total = 0
        correct = 0
        error_counts = defaultdict(int)
        fc_over = 0
        fc_under = 0
        fc_equal_correct = 0
        fc_equal_wrong = 0
        
        for category, stats in results.items():
            total += stats["total"]
            correct += stats["correct"]
            fc_over += stats.get("fc_over", 0)
            fc_under += stats.get("fc_under", 0)
            fc_equal_correct += stats.get("fc_equal_correct", 0)
            fc_equal_wrong += stats.get("fc_equal_wrong", 0)
            for error_type, count in stats["errors"].items():
                error_counts[error_type] += count
        
        accuracy = (correct / total * 100) if total > 0 else 0
        summaries.append({
            "model": model_name,
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
            "errors": error_counts,
            "fc_over": fc_over,
            "fc_under": fc_under,
            "fc_equal_correct": fc_equal_correct,
            "fc_equal_wrong": fc_equal_wrong
        })
    
    # 按準確率排序
    summaries.sort(key=lambda x: x["accuracy"], reverse=True)
    
    # 印出表格
    print(f"\n{'模型名稱':<50} {'總數':>6} {'正確':>6} {'準確率':>8} {'FC多':>6} {'FC少':>6} {'FC正確':>7} {'FC錯誤':>7}")
    print("-" * 115)
    
    for s in summaries:
        model_short = s["model"][:48] + ".." if len(s["model"]) > 50 else s["model"]
        print(f"{model_short:<50} {s['total']:>6} {s['correct']:>6} {s['accuracy']:>7.1f}% {s['fc_over']:>6} {s['fc_under']:>6} {s['fc_equal_correct']:>7} {s['fc_equal_wrong']:>7}")
    
    print("-" * 115)


def main():
    parser = argparse.ArgumentParser(
        description="BFCL Multi-Turn 測試錯誤類型統計分析程式"
    )
    parser.add_argument(
        "model_names",
        nargs="*",
        help="要分析的模型名稱 (可多個，例如: model1 model2 model3)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="分析所有模型"
    )
    parser.add_argument(
        "--score-dir",
        default="./score",
        help="score 目錄路徑 (預設: ./score)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用的模型"
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="不輸出 CSV 檔案"
    )
    
    args = parser.parse_args()
    
    # 確認 score 目錄存在
    if not os.path.exists(args.score_dir):
        print(f"錯誤: 找不到 score 目錄: {args.score_dir}")
        sys.exit(1)
    
    # 列出所有模型
    if args.list:
        models = get_all_models(args.score_dir)
        print(f"\n📋 共有 {len(models)} 個模型有 multi-turn 測試結果:\n")
        for model in models:
            print(f"  - {model}")
        return
    
    # 分析所有模型
    if args.all:
        models = get_all_models(args.score_dir)
        if not models:
            print("錯誤: 找不到任何有 multi-turn 測試結果的模型")
            sys.exit(1)
        
        all_results = {}
        for model in models:
            print(f"分析中: {model}...")
            results = analyze_model(model, args.score_dir)
            if results:
                all_results[model] = results
        
        print_summary_table(all_results)
        
        if not args.no_csv:
            print("\n📁 匯出 CSV 檔案:")
            export_all_models_to_csv(all_results, args.score_dir)
        
        return
    
    # 分析指定的模型（支援多個）
    if not args.model_names:
        parser.print_help()
        print("\n錯誤: 請指定模型名稱或使用 --all 分析所有模型")
        sys.exit(1)
    
    all_results = {}
    for model_name in args.model_names:
        results = analyze_model(model_name, args.score_dir)
        
        if not results:
            print(f"警告: 找不到模型 '{model_name}' 的 multi-turn 測試結果")
            continue
        
        all_results[model_name] = results
        print_model_report(model_name, results)
        
        if not args.no_csv:
            export_to_csv(model_name, results, args.score_dir)
    
    # 如果分析多個模型，印出摘要
    if len(all_results) > 1:
        print_summary_table(all_results)


if __name__ == "__main__":
    main()
