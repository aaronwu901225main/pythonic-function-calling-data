#!/usr/bin/env python3
"""
測試多行組合生成功能
不實際調用 OpenAI API，只測試組合邏輯
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from run_s1_openai_multirow import (
    parse_multirow_config,
    generate_row_combinations,
    merge_rows,
    read_curriculum
)


def test_parse_config():
    """測試配置解析"""
    print("=" * 60)
    print("測試 1: 配置解析")
    print("=" * 60)
    
    test_cases = [
        ("2*500", [(2, 500)]),
        ("2*500,3*250", [(2, 500), (3, 250)]),
        ("2*400,3*300,4*200,5*100", [(2, 400), (3, 300), (4, 200), (5, 100)]),
        ("", []),
        ("invalid", []),
    ]
    
    for config_str, expected in test_cases:
        result = parse_multirow_config(config_str)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{config_str}' → {result}")
    
    print()


def test_combinations():
    """測試組合生成"""
    print("=" * 60)
    print("測試 2: 組合生成")
    print("=" * 60)
    
    # 創建測試資料
    test_rows = [
        {"domain": f"Domain{i}", "subdomain": f"Sub{i}", "entities": ""}
        for i in range(10)
    ]
    
    # 測試案例
    test_cases = [
        (2, 5),   # 從10行中抽2行，生成5個組合
        (3, 10),  # 從10行中抽3行，生成10個組合
        (4, 3),   # 從10行中抽4行，生成3個組合
    ]
    
    for rows_per_sample, num_samples in test_cases:
        try:
            combinations = generate_row_combinations(test_rows, rows_per_sample, num_samples)
            
            # 檢查組合數量
            assert len(combinations) == num_samples, f"組合數不符: {len(combinations)} != {num_samples}"
            
            # 檢查每個組合的行數
            for combo in combinations:
                assert len(combo) == rows_per_sample, f"組合行數不符: {len(combo)} != {rows_per_sample}"
            
            # 檢查唯一性
            combo_signatures = []
            for combo in combinations:
                signature = tuple(sorted([row["domain"] for row in combo]))
                combo_signatures.append(signature)
            
            unique_combos = len(set(combo_signatures))
            assert unique_combos == len(combinations), f"存在重複組合: {unique_combos} != {len(combinations)}"
            
            print(f"✓ {rows_per_sample}行*{num_samples}題: 生成 {len(combinations)} 個唯一組合")
            
        except Exception as e:
            print(f"✗ {rows_per_sample}行*{num_samples}題: {e}")
    
    print()


def test_merge_rows():
    """測試行合併"""
    print("=" * 60)
    print("測試 3: 行合併")
    print("=" * 60)
    
    test_rows = [
        {
            "domain": "Personal Assistant",
            "subdomain": "Calendar_Management",
            "entities": "['calendar', 'mail']"
        },
        {
            "domain": "Devops",
            "subdomain": "Continuous_Integration",
            "entities": "['docker', 'jenkins']"
        }
    ]
    
    merged = merge_rows(test_rows)
    
    print(f"Domain: {merged['domain']}")
    print(f"Subdomain: {merged['subdomain']}")
    print(f"Entities: {merged['entities']}")
    print(f"Original rows count: {len(merged['original_rows'])}")
    
    # 驗證
    assert "Personal Assistant" in merged["domain"], "Domain 合併失敗"
    assert "Devops" in merged["domain"], "Domain 合併失敗"
    assert "Calendar_Management" in merged["subdomain"], "Subdomain 合併失敗"
    assert "Continuous_Integration" in merged["subdomain"], "Subdomain 合併失敗"
    
    print("✓ 行合併測試通過")
    print()


def test_with_real_curriculum():
    """使用真實的 curriculum 測試"""
    print("=" * 60)
    print("測試 4: 真實 Curriculum")
    print("=" * 60)
    
    csv_path = "pipeline/data/curriculum.csv"
    
    if not os.path.exists(csv_path):
        print(f"✗ 找不到 {csv_path}")
        return
    
    try:
        rows = read_curriculum(csv_path)
        print(f"✓ 成功讀取 {len(rows)} 行 curriculum")
        
        # 顯示前3行
        print("\n前3行:")
        for i, row in enumerate(rows[:3]):
            print(f"  {i+1}. {row['domain']}/{row['subdomain']}")
        
        # 測試小規模組合
        if len(rows) >= 5:
            print(f"\n測試組合生成 (從 {len(rows)} 行中抽取):")
            
            test_configs = [
                (2, 3),
                (3, 2),
            ]
            
            for rows_per_sample, num_samples in test_configs:
                try:
                    combinations = generate_row_combinations(rows, rows_per_sample, num_samples)
                    print(f"  ✓ {rows_per_sample}行*{num_samples}題: 成功生成 {len(combinations)} 個組合")
                    
                    # 顯示第一個組合
                    if combinations:
                        first_combo = combinations[0]
                        domains = [r["domain"] for r in first_combo]
                        print(f"    範例組合: {' + '.join(domains)}")
                        
                except Exception as e:
                    print(f"  ✗ {rows_per_sample}行*{num_samples}題: {e}")
        
    except Exception as e:
        print(f"✗ 讀取 curriculum 失敗: {e}")
    
    print()


def test_max_combinations():
    """測試最大組合數限制"""
    print("=" * 60)
    print("測試 5: 最大組合數限制")
    print("=" * 60)
    
    # 創建小量測試資料
    test_rows = [
        {"domain": f"Domain{i}", "subdomain": f"Sub{i}", "entities": ""}
        for i in range(5)
    ]
    
    # C(5,2) = 10，但要求 20 個
    print("測試: 從5行中抽2行，但要求20個組合 (理論最大10個)")
    try:
        combinations = generate_row_combinations(test_rows, 2, 20)
        print(f"✓ 自動調整為 {len(combinations)} 個組合 (最大值)")
        assert len(combinations) == 10, f"應該是10個組合，但得到 {len(combinations)}"
    except Exception as e:
        print(f"✗ 錯誤: {e}")
    
    print()


def main():
    print("\n" + "=" * 60)
    print("多行組合生成功能測試")
    print("=" * 60)
    print()
    
    test_parse_config()
    test_combinations()
    test_merge_rows()
    test_max_combinations()
    test_with_real_curriculum()
    
    print("=" * 60)
    print("測試完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
