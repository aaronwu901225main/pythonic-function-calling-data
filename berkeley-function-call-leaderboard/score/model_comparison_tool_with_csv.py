#!/usr/bin/env python3
"""
模型比較統計工具
作者：AI助手
用途：統計兩個評測模型的比較結果，分析ab都對、a對b錯、b對a錯、ab都錯的題目占比
"""

import json
import os
import argparse
import csv
from typing import Dict, Set, List, Tuple
from pathlib import Path


class ModelComparisonTool:
    def __init__(self, score_dir: str, eval_dir: str):
        """
        初始化模型比較工具
        
        Args:
            score_dir: score資料夾路徑
            eval_dir: bfcl_eval資料夾路徑
        """
        self.score_dir = Path(score_dir)
        self.eval_dir = Path(eval_dir)
        
    def _get_folder_name(self, test_category: str) -> str:
        """根據測試類別獲取對應的資料夾名稱"""
        if test_category.startswith('multi_turn'):
            return 'multi_turn'
        elif test_category.startswith('live'):
            return 'live'
        elif test_category.startswith('agentic'):
            return 'agentic'
        elif test_category.startswith('format_sensitivity'):
            return 'format_sensitivity'
        elif test_category in ['memory', 'multiple', 'parallel', 'parallel_multiple', 
                               'simple_java', 'simple_javascript', 'simple_python', 
                               'irrelevance', 'web_search']:
            return 'non_live'
        else:
            return test_category
        
    def get_wrong_questions(self, model_name: str, test_category: str) -> Set[str]:
        """
        獲取模型答錯的題目ID
        
        Args:
            model_name: 模型名稱
            test_category: 測試類別
            
        Returns:
            答錯題目的ID集合
        """
        # 根據類別名稱決定資料夾名稱
        folder_name = self._get_folder_name(test_category)
        score_file = self.score_dir / model_name / folder_name / f"BFCL_v4_{test_category}_score.json"
        
        if not score_file.exists():
            print(f"警告：找不到 {score_file}")
            return set()
        
        wrong_questions = set()
        
        with open(score_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # 跳過第一行統計資訊
            for line in lines[1:]:
                try:
                    data = json.loads(line.strip())
                    if not data.get('valid', True):  # valid為False代表答錯
                        wrong_questions.add(data['id'])
                except json.JSONDecodeError:
                    continue
                    
        return wrong_questions
    
    def get_all_question_ids(self, test_category: str) -> Set[str]:
        """
        獲取所有題目ID
        
        Args:
            test_category: 測試類別
            
        Returns:
            所有題目ID的集合
        """
        eval_file = self.eval_dir / "data" / f"BFCL_v4_{test_category}.json"
        
        if not eval_file.exists():
            print(f"錯誤：找不到 {eval_file}")
            return set()
            
        question_ids = set()
        try:
            with open(eval_file, 'r', encoding='utf-8') as f:
                for line in f:
                    data = json.loads(line.strip())
                    question_ids.add(data['id'])
        except Exception as e:
            print(f"讀取文件錯誤：{e}")
            
        return question_ids
    
    def get_available_categories(self) -> List[str]:
        """
        獲取所有可用的測試類別
        """
        categories = []
        data_dir = self.eval_dir / "data"
        
        if data_dir.exists():
            for file in data_dir.glob("BFCL_v4_*.json"):
                # 從檔案名提取類別名稱
                category = file.stem.replace("BFCL_v4_", "")
                categories.append(category)
        
        return sorted(categories)
    
    def compare_models(self, model_a: str, model_b: str, test_category: str) -> Dict:
        """
        比較兩個模型的結果
        
        Args:
            model_a: 模型A名稱
            model_b: 模型B名稱
            test_category: 測試類別或"all"表示全部類別
            
        Returns:
            比較結果統計
        """
        if test_category.lower() in ['all', '全部', 'all_categories']:
            return self.compare_all_categories(model_a, model_b)
        
        print(f"開始比較模型 {model_a} 和 {model_b} 在 {test_category} 的表現...")
        
        # 獲取錯誤題目
        wrong_a = self.get_wrong_questions(model_a, test_category)
        wrong_b = self.get_wrong_questions(model_b, test_category)
        
        # 獲取所有題目ID
        all_questions = self.get_all_question_ids(test_category)
        
        if not all_questions:
            print("錯誤：無法獲取題目列表")
            return {}
        
        total_questions = len(all_questions)
        print(f"總題數: {total_questions}")
        print(f"模型A ({model_a}) 錯誤題數: {len(wrong_a)}")
        print(f"模型B ({model_b}) 錯誤題數: {len(wrong_b)}")
        
        # 計算各種情況
        correct_a = all_questions - wrong_a
        correct_b = all_questions - wrong_b
        
        # 統計四種情況
        both_correct = correct_a & correct_b  # ab都對
        a_correct_b_wrong = correct_a & wrong_b  # a對b錯
        b_correct_a_wrong = correct_b & wrong_a  # b對a錯
        both_wrong = wrong_a & wrong_b  # ab都錯
        
        # 計算占比
        results = {
            'total_questions': total_questions,
            'both_correct': {
                'count': len(both_correct),
                'percentage': len(both_correct) / total_questions * 100,
                'questions': sorted(list(both_correct))
            },
            'a_correct_b_wrong': {
                'count': len(a_correct_b_wrong),
                'percentage': len(a_correct_b_wrong) / total_questions * 100,
                'questions': sorted(list(a_correct_b_wrong))
            },
            'b_correct_a_wrong': {
                'count': len(b_correct_a_wrong),
                'percentage': len(b_correct_a_wrong) / total_questions * 100,
                'questions': sorted(list(b_correct_a_wrong))
            },
            'both_wrong': {
                'count': len(both_wrong),
                'percentage': len(both_wrong) / total_questions * 100,
                'questions': sorted(list(both_wrong))
            }
        }
        
        # 驗證總數
        total_check = len(both_correct) + len(a_correct_b_wrong) + len(b_correct_a_wrong) + len(both_wrong)
        print(f"驗證：四種情況總數 {total_check} 應該等於總題數 {total_questions}")
        
        return results
    
    def compare_all_categories(self, model_a: str, model_b: str) -> Dict:
        """
        比較兩個模型在所有類別上的結果
        """
        categories = self.get_available_categories()
        print(f"找到 {len(categories)} 個測試類別: {', '.join(categories)}")
        
        all_results = {
            'total_questions': 0,
            'both_correct': {'count': 0, 'percentage': 0, 'questions': []},
            'a_correct_b_wrong': {'count': 0, 'percentage': 0, 'questions': []},
            'b_correct_a_wrong': {'count': 0, 'percentage': 0, 'questions': []},
            'both_wrong': {'count': 0, 'percentage': 0, 'questions': []},
            'categories': {}
        }
        
        for category in categories:
            print(f"\n處理類別: {category}")
            result = self.compare_models(model_a, model_b, category)
            
            if result:
                # 保存各類別的詳細結果
                all_results['categories'][category] = result
                
                # 累加總體統計
                all_results['total_questions'] += result['total_questions']
                all_results['both_correct']['count'] += result['both_correct']['count']
                all_results['both_correct']['questions'].extend(result['both_correct']['questions'])
                all_results['a_correct_b_wrong']['count'] += result['a_correct_b_wrong']['count']
                all_results['a_correct_b_wrong']['questions'].extend(result['a_correct_b_wrong']['questions'])
                all_results['b_correct_a_wrong']['count'] += result['b_correct_a_wrong']['count']
                all_results['b_correct_a_wrong']['questions'].extend(result['b_correct_a_wrong']['questions'])
                all_results['both_wrong']['count'] += result['both_wrong']['count']
                all_results['both_wrong']['questions'].extend(result['both_wrong']['questions'])
        
        # 計算總體占比
        if all_results['total_questions'] > 0:
            all_results['both_correct']['percentage'] = all_results['both_correct']['count'] / all_results['total_questions'] * 100
            all_results['a_correct_b_wrong']['percentage'] = all_results['a_correct_b_wrong']['count'] / all_results['total_questions'] * 100
            all_results['b_correct_a_wrong']['percentage'] = all_results['b_correct_a_wrong']['count'] / all_results['total_questions'] * 100
            all_results['both_wrong']['percentage'] = all_results['both_wrong']['count'] / all_results['total_questions'] * 100
        
        print(f"\n=== 所有類別總計 ===")
        print(f"總題數: {all_results['total_questions']}")
        print(f"模型A ({model_a}) 總錯誤題數: {len(set(all_results['a_correct_b_wrong']['questions'] + all_results['both_wrong']['questions']))}")
        print(f"模型B ({model_b}) 總錯誤題數: {len(set(all_results['b_correct_a_wrong']['questions'] + all_results['both_wrong']['questions']))}")
        
        return all_results
    
    def print_results(self, results: Dict, model_a: str, model_b: str, test_category: str):
        """
        輸出比較結果
        """
        if 'categories' in results:
            # 全部類別的結果
            print(f"\n{'='*80}")
            print(f"模型比較結果：{model_a} vs {model_b} (所有類別)")
            print(f"{'='*80}")
            
            # 顯示各類別詳細結果
            for category, cat_result in results['categories'].items():
                print(f"\n--- {category} ---")
                print(f"題數：{cat_result['total_questions']} | AB都對：{cat_result['both_correct']['percentage']:.1f}% | A對B錯：{cat_result['a_correct_b_wrong']['percentage']:.1f}% | B對A錯：{cat_result['b_correct_a_wrong']['percentage']:.1f}% | AB都錯：{cat_result['both_wrong']['percentage']:.1f}%")
            
            print(f"\n{'='*80}")
            print(f"總體統計 (所有類別合計)")
            print(f"{'='*80}")
        else:
            print(f"\n{'='*60}")
            print(f"模型比較結果：{model_a} vs {model_b} ({test_category})")
            print(f"{'='*60}")
        
        print(f"\n總題數：{results['total_questions']}")
        
        print(f"\n1. AB都對的題目：")
        print(f"   數量：{results['both_correct']['count']}")
        print(f"   占比：{results['both_correct']['percentage']:.2f}%")
        
        print(f"\n2. A對B錯的題目：")
        print(f"   數量：{results['a_correct_b_wrong']['count']}")
        print(f"   占比：{results['a_correct_b_wrong']['percentage']:.2f}%")
        if results['a_correct_b_wrong']['questions']:
            print(f"   題號：{', '.join(results['a_correct_b_wrong']['questions'][:10])}{'...' if len(results['a_correct_b_wrong']['questions']) > 10 else ''}")
        
        print(f"\n3. B對A錯的題目：")
        print(f"   數量：{results['b_correct_a_wrong']['count']}")
        print(f"   占比：{results['b_correct_a_wrong']['percentage']:.2f}%")
        if results['b_correct_a_wrong']['questions']:
            print(f"   題號：{', '.join(results['b_correct_a_wrong']['questions'][:10])}{'...' if len(results['b_correct_a_wrong']['questions']) > 10 else ''}")
        
        print(f"\n4. AB都錯的題目：")
        print(f"   數量：{results['both_wrong']['count']}")
        print(f"   占比：{results['both_wrong']['percentage']:.2f}%")
        if results['both_wrong']['questions']:
            print(f"   題號：{', '.join(results['both_wrong']['questions'][:10])}{'...' if len(results['both_wrong']['questions']) > 10 else ''}")
        
        print(f"\n{'='*60}")
        
        # 輸出完整的 b對a錯 和 ab都錯 題號
        print(f"\n詳細題號列表：")
        
        if results['b_correct_a_wrong']['questions']:
            print(f"\nB對A錯的所有題號：")
            for i, q in enumerate(results['b_correct_a_wrong']['questions']):
                if i % 10 == 0:
                    print()
                print(f"{q:<20}", end="")
            print()
        
        if results['both_wrong']['questions']:
            print(f"\nAB都錯的所有題號：")
            for i, q in enumerate(results['both_wrong']['questions']):
                if i % 10 == 0:
                    print()
                print(f"{q:<20}", end="")
            print()
    
    def export_to_csv(self, results: Dict, model_a: str, model_b: str, test_category: str, output_file: str = None):
        """
        將結果匯出為CSV格式
        """
        if not output_file:
            if 'categories' in results:
                output_file = f"comparison_{model_a}_vs_{model_b}_all_categories.csv"
            else:
                output_file = f"comparison_{model_a}_vs_{model_b}_{test_category}.csv"
        
        # 準備CSV數據
        csv_data = []
        
        if 'categories' in results:
            # 全部類別的情況 - 計算最大題號數量以確定欄位數
            max_questions = 0
            for category, cat_result in results['categories'].items():
                max_questions = max(max_questions, 
                                  len(cat_result['both_correct']['questions']),
                                  len(cat_result['a_correct_b_wrong']['questions']),
                                  len(cat_result['b_correct_a_wrong']['questions']),
                                  len(cat_result['both_wrong']['questions']))
            
            # 建立表頭
            header = ["測試類別", "統計類別", "數量", "占比(%)", "模型A", "模型B"]
            for i in range(max_questions):
                header.append(f"題號{i+1}")
            csv_data.append(header)
            
            for category, cat_result in results['categories'].items():
                # AB都對
                row = [category, "AB都對", cat_result['both_correct']['count'], 
                       f"{cat_result['both_correct']['percentage']:.2f}", model_a, model_b]
                row.extend(cat_result['both_correct']['questions'])
                row.extend([''] * (max_questions - len(cat_result['both_correct']['questions'])))
                csv_data.append(row)
                
                # A對B錯
                row = [category, "A對B錯", cat_result['a_correct_b_wrong']['count'], 
                       f"{cat_result['a_correct_b_wrong']['percentage']:.2f}", model_a, model_b]
                row.extend(cat_result['a_correct_b_wrong']['questions'])
                row.extend([''] * (max_questions - len(cat_result['a_correct_b_wrong']['questions'])))
                csv_data.append(row)
                
                # B對A錯
                row = [category, "B對A錯", cat_result['b_correct_a_wrong']['count'], 
                       f"{cat_result['b_correct_a_wrong']['percentage']:.2f}", model_a, model_b]
                row.extend(cat_result['b_correct_a_wrong']['questions'])
                row.extend([''] * (max_questions - len(cat_result['b_correct_a_wrong']['questions'])))
                csv_data.append(row)
                
                # AB都錯
                row = [category, "AB都錯", cat_result['both_wrong']['count'], 
                       f"{cat_result['both_wrong']['percentage']:.2f}", model_a, model_b]
                row.extend(cat_result['both_wrong']['questions'])
                row.extend([''] * (max_questions - len(cat_result['both_wrong']['questions'])))
                csv_data.append(row)
        else:
            # 單一類別的情況 - 計算最大題號數量
            max_questions = max(len(results['both_correct']['questions']),
                              len(results['a_correct_b_wrong']['questions']),
                              len(results['b_correct_a_wrong']['questions']),
                              len(results['both_wrong']['questions']))
            
            # 建立表頭
            header = ["統計類別", "數量", "占比(%)", "模型A", "模型B", "測試類別"]
            for i in range(max_questions):
                header.append(f"題號{i+1}")
            csv_data.append(header)
            
            # AB都對
            row = ["AB都對", results['both_correct']['count'], 
                   f"{results['both_correct']['percentage']:.2f}", model_a, model_b, test_category]
            row.extend(results['both_correct']['questions'])
            row.extend([''] * (max_questions - len(results['both_correct']['questions'])))
            csv_data.append(row)
            
            # A對B錯
            row = ["A對B錯", results['a_correct_b_wrong']['count'], 
                   f"{results['a_correct_b_wrong']['percentage']:.2f}", model_a, model_b, test_category]
            row.extend(results['a_correct_b_wrong']['questions'])
            row.extend([''] * (max_questions - len(results['a_correct_b_wrong']['questions'])))
            csv_data.append(row)
            
            # B對A錯
            row = ["B對A錯", results['b_correct_a_wrong']['count'], 
                   f"{results['b_correct_a_wrong']['percentage']:.2f}", model_a, model_b, test_category]
            row.extend(results['b_correct_a_wrong']['questions'])
            row.extend([''] * (max_questions - len(results['b_correct_a_wrong']['questions'])))
            csv_data.append(row)
            
            # AB都錯
            row = ["AB都錯", results['both_wrong']['count'], 
                   f"{results['both_wrong']['percentage']:.2f}", model_a, model_b, test_category]
            row.extend(results['both_wrong']['questions'])
            row.extend([''] * (max_questions - len(results['both_wrong']['questions'])))
            csv_data.append(row)
        
        # 寫入CSV文件
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerows(csv_data)
            
            print(f"\n✅ CSV結果已匯出至: {output_file}")
            print(f"   包含 {results['total_questions']} 個題目的詳細比較結果")
            return output_file
            
        except Exception as e:
            print(f"❌ CSV匯出失敗: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description='模型評測結果比較工具')
    parser.add_argument('model_a', help='模型A名稱（例如：Qwen_Qwen3-8B）')
    parser.add_argument('model_b', help='模型B名稱（例如：meta-llama_Llama-3.1-8B-Instruct）')
    parser.add_argument('--category', '-c', default='all', 
                      help='測試類別（預設：all表示所有類別，也可指定具體類別如multi_turn_base）')
    parser.add_argument('--score-dir', default='./',
                      help='score資料夾路徑（預設：./）')
    parser.add_argument('--eval-dir', default='../bfcl_eval',
                      help='bfcl_eval資料夾路徑（預設：../bfcl_eval）')
    parser.add_argument('--csv', '-o', 
                      help='輸出CSV文件路徑（如果指定則匯出為CSV格式）')
    parser.add_argument('--csv-only', action='store_true',
                      help='僅輸出CSV，不顯示控制台結果')
    
    args = parser.parse_args()
    
    # 創建比較工具
    tool = ModelComparisonTool(args.score_dir, args.eval_dir)
    
    # 執行比較
    results = tool.compare_models(args.model_a, args.model_b, args.category)
    
    if results:
        # 輸出結果
        if not args.csv_only:
            tool.print_results(results, args.model_a, args.model_b, args.category)
        
        # 如果指定了CSV輸出
        if args.csv or args.csv_only:
            csv_file = args.csv if args.csv else f"comparison_{args.model_a}_vs_{args.model_b}_{args.category}.csv"
            tool.export_to_csv(results, args.model_a, args.model_b, args.category, csv_file)
    else:
        print("比較失敗，請檢查模型名稱和檔案路徑")


if __name__ == "__main__":
    main()