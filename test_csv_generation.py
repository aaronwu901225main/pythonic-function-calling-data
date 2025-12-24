#!/usr/bin/env python3
"""
測試 CSV 生成功能
"""

import sys
import os
import csv
import tempfile
sys.path.insert(0, os.path.dirname(__file__))

from run_s1_openai_multirow import _generate_curriculum_usage_csv


def test_csv_generation():
    """測試 CSV 生成"""
    print("=" * 60)
    print("測試 CSV 生成功能")
    print("=" * 60)
    
    # 模擬生成的資料
    test_data = [
        {
            "domain": "Personal Assistant, Devops",
            "subdomain": "Calendar + CI/CD",
            "scenario": "Test scenario 1",
            "meta": {
                "rows_per_sample": 2,
                "original_rows": [
                    {"domain": "Personal Assistant", "subdomain": "Calendar_Management", "entities": "['calendar', 'mail']"},
                    {"domain": "Devops", "subdomain": "Continuous_Integration", "entities": "['docker', 'jenkins']"},
                ]
            }
        },
        {
            "domain": "Finance, Healthcare, ML",
            "subdomain": "Budget + Records + Training",
            "scenario": "Test scenario 2",
            "meta": {
                "rows_per_sample": 3,
                "original_rows": [
                    {"domain": "Finance", "subdomain": "Budget_Tracking", "entities": "['excel']"},
                    {"domain": "Healthcare", "subdomain": "Patient_Records", "entities": "['database']"},
                    {"domain": "ML", "subdomain": "Model_Training", "entities": "['pytorch']"},
                ]
            }
        },
        {
            "domain": "E-commerce, Marketing",
            "subdomain": "Orders + Campaigns",
            "scenario": "Test scenario 3",
            "meta": {
                "rows_per_sample": 2,
                "original_rows": [
                    {"domain": "E-commerce", "subdomain": "Order_Management", "entities": "['cart', 'payment']"},
                    {"domain": "Marketing", "subdomain": "Campaign_Analytics", "entities": "['metrics']"},
                ]
            }
        },
    ]
    
    # 生成 CSV 到臨時檔案
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        csv_path = f.name
    
    try:
        _generate_curriculum_usage_csv(test_data, csv_path)
        
        # 讀取並驗證 CSV
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        print(f"\n生成的 CSV 檔案:")
        print(f"  路徑: {csv_path}")
        print(f"  總行數: {len(rows)} (含標題)")
        print(f"  欄位數: {len(rows[0])}")
        
        # 顯示標題
        print(f"\n標題:")
        print(f"  {rows[0]}")
        
        # 顯示數據
        print(f"\n數據範例:")
        for i, row in enumerate(rows[1:], 1):
            print(f"\n  樣本 {i}:")
            print(f"    題號: {row[0]}")
            # 根據欄位數計算有幾組
            num_groups = (len(row) - 1) // 3
            for g in range(num_groups):
                base_idx = 1 + g * 3
                if base_idx < len(row):
                    domain = row[base_idx] if base_idx < len(row) else ""
                    subdomain = row[base_idx + 1] if base_idx + 1 < len(row) else ""
                    entities = row[base_idx + 2] if base_idx + 2 < len(row) else ""
                    if domain:  # 只顯示有資料的組
                        print(f"    第{g+1}組: {domain} / {subdomain}")
                        print(f"         Entities: {entities}")
        
        # 驗證格式
        print(f"\n驗證:")
        
        # 檢查標題
        expected_headers = ["題號", "domain1", "subdomain1", "entities1", 
                          "domain2", "subdomain2", "entities2",
                          "domain3", "subdomain3", "entities3"]
        assert rows[0] == expected_headers, f"標題不符: {rows[0]}"
        print(f"  ✓ 標題正確 (10欄)")
        
        # 檢查資料行數
        assert len(rows) == 4, f"資料行數不符: {len(rows)}"  # 1標題 + 3資料
        print(f"  ✓ 資料行數正確 (4行)")
        
        # 檢查第一筆資料（2行組合）
        assert rows[1][0] == "1", "題號不符"
        assert rows[1][1] == "Personal Assistant", "domain1 不符"
        assert rows[1][4] == "Devops", "domain2 不符"
        assert rows[1][7] == "", "domain3 應為空"
        print(f"  ✓ 2行組合資料正確")
        
        # 檢查第二筆資料（3行組合）
        assert rows[2][0] == "2", "題號不符"
        assert rows[2][1] == "Finance", "domain1 不符"
        assert rows[2][4] == "Healthcare", "domain2 不符"
        assert rows[2][7] == "ML", "domain3 不符"
        print(f"  ✓ 3行組合資料正確")
        
        print(f"\n✓ 所有測試通過!")
        
    finally:
        # 清理臨時檔案
        if os.path.exists(csv_path):
            os.unlink(csv_path)


if __name__ == "__main__":
    test_csv_generation()
