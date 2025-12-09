#!/usr/bin/env python3
"""
驗證生成的資料是否包含完整的 tool responses
特別檢查:
1. 所有項目都有 tool_responses
2. long_context 的回應包含擴充資料
3. miss_func 的函數確實被移除
4. messages 包含 tool role 的訊息
"""

import json
from collections import defaultdict

def verify_data(input_file: str):
    """驗證生成的資料"""
    
    print("="*70)
    print("BFCL Multi-turn xLAM Training Data Verification")
    print("="*70)
    
    with open(input_file, 'r') as f:
        lines = f.readlines()
    
    total_entries = len(lines)
    print(f"\n總共 {total_entries} 個 conversation turns")
    
    # 統計資訊
    stats = defaultdict(lambda: defaultdict(int))
    
    # 特殊檢查
    long_context_found = False
    miss_func_found = False
    has_tool_messages = 0
    
    for line in lines:
        data = json.loads(line)
        dataset = data['dataset']
        
        # 基本統計
        stats[dataset]['total'] += 1
        
        # 檢查是否有 tool_responses
        tool_responses = data.get('tool_responses', [])
        if tool_responses:
            stats[dataset]['with_tool_responses'] += 1
            
            # 檢查 messages 中是否有 tool role
            has_tool_role = any(msg['role'] == 'tool' for msg in data['messages'])
            if has_tool_role:
                has_tool_messages += 1
        
        # 檢查 long_context 的大型回應
        if 'long_context' in dataset:
            for resp in tool_responses:
                if len(resp) > 10000:  # 大於 10KB 的回應
                    if not long_context_found:
                        print(f"\n✓ 發現 long_context 擴充資料:")
                        print(f"  ID: {data['id']}")
                        print(f"  Response length: {len(resp)} chars")
                        print(f"  Preview: {resp[:100]}...")
                        long_context_found = True
                    stats[dataset]['long_responses'] += 1
        
        # 檢查 miss_func
        if 'miss_func' in dataset:
            # 檢查 system message 中的函數數量
            system_msg = data['messages'][0]['content']
            # 簡單計算 function definitions 的數量
            func_count = system_msg.count('"name":')
            
            # 如果函數數量 < 預期,可能是 miss_func 的效果
            if func_count < 10:  # 假設正常情況有更多函數
                if not miss_func_found:
                    print(f"\n✓ 發現 miss_func 效果:")
                    print(f"  ID: {data['id']}")
                    print(f"  Available functions: {func_count}")
                    miss_func_found = True
    
    # 顯示統計
    print(f"\n{'='*70}")
    print("=== 資料集統計 ===")
    print(f"{'='*70}")
    print(f"{'Dataset':<45} {'Total':>8} {'w/Resp':>8} {'Long':>8}")
    print("-"*70)
    
    for dataset in sorted(stats.keys()):
        s = stats[dataset]
        print(f"{dataset:<45} {s['total']:>8} {s['with_tool_responses']:>8} {s.get('long_responses', 0):>8}")
    
    print("-"*70)
    print(f"{'TOTAL':<45} {total_entries:>8} {has_tool_messages:>8}")
    
    # 驗證結果
    print(f"\n{'='*70}")
    print("=== 驗證結果 ===")
    print(f"{'='*70}")
    
    checks = [
        ("所有項目都有 tool_responses", has_tool_messages == total_entries),
        ("發現 long_context 擴充資料", long_context_found),
        ("發現 miss_func 效果", miss_func_found),
    ]
    
    for check_name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check_name}")
    
    # 顯示範例
    print(f"\n{'='*70}")
    print("=== 範例: 完整對話流程 (包含 tool responses) ===")
    print(f"{'='*70}")
    
    # 找一個有多個 tool calls 的範例
    for line in lines:
        data = json.loads(line)
        if len(data.get('ground_truth', [])) >= 2:
            print(f"\nID: {data['id']}")
            print(f"Turn: {data['turn_index'] + 1}/{data['total_turns']}")
            print(f"\n訊息流程:")
            
            for i, msg in enumerate(data['messages']):
                role = msg['role']
                content = msg['content']
                
                if role == 'system':
                    print(f"  [{i}] SYSTEM: {len(content)} chars (略)")
                elif role == 'user':
                    print(f"  [{i}] USER: {content[:80]}...")
                elif role == 'assistant':
                    # 解析 tool calls
                    try:
                        calls = json.loads(content)
                        print(f"  [{i}] ASSISTANT: {len(calls)} tool calls")
                        for call in calls:
                            print(f"       - {call['name']}({list(call['arguments'].keys())})")
                    except:
                        print(f"  [{i}] ASSISTANT: {content[:80]}...")
                elif role == 'tool':
                    tool_name = msg.get('name', 'unknown')
                    print(f"  [{i}] TOOL ({tool_name}): {content[:60]}...")
            
            break
    
    print(f"\n{'='*70}")


if __name__ == "__main__":
    verify_data("bfcl_multiturn_xlam_with_responses.jsonl")
