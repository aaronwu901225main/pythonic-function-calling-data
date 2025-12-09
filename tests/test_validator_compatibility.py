#!/usr/bin/env python3
"""測試 validate_multi_turn_eng.py 是否支援新舊兩種格式"""

import json
import tempfile
import subprocess
import sys

# 測試資料：包含新格式（dict）和舊格式（object）
test_samples = [
    {
        "id": "test-new-format",
        "tools": [
            {
                "name": "test_function",
                "description": "Test function with new format",
                "parameters": {
                    "type": "dict",  # 新格式
                    "properties": {
                        "param1": {"type": "string"}
                    },
                    "required": ["param1"]
                },
                "response": {
                    "type": "dict",  # 新格式
                    "properties": {}
                }
            }
        ],
        "messages": [
            {"role": "user", "content": "test"}
        ]
    },
    {
        "id": "test-old-format",
        "tools": [
            {
                "name": "test_function_old",
                "description": "Test function with old format",
                "parameters": {
                    "type": "object",  # 舊格式
                    "properties": {
                        "param1": {"type": "string"}
                    },
                    "required": ["param1"]
                }
                # 沒有 response 欄位（舊格式）
            }
        ],
        "messages": [
            {"role": "user", "content": "test"}
        ]
    },
    {
        "id": "test-mixed-format",
        "tools": [
            {
                "name": "new_func",
                "description": "New format tool",
                "parameters": {
                    "type": "dict",
                    "properties": {},
                    "required": []
                },
                "response": {
                    "type": "dict",
                    "properties": {}
                }
            },
            {
                "name": "old_func",
                "description": "Old format tool",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ],
        "messages": [
            {"role": "user", "content": "test"}
        ]
    }
]

def main():
    # 創建臨時檔案
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        temp_path = f.name
        for sample in test_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print("=" * 80)
    print("測試 validate_multi_turn_eng.py 的向後相容性")
    print("=" * 80)
    print(f"\n測試檔案: {temp_path}")
    print(f"測試樣本數: {len(test_samples)}")
    print("\n測試內容:")
    print("  1. 新格式 (type: dict, 包含 response)")
    print("  2. 舊格式 (type: object, 無 response)")
    print("  3. 混合格式 (同時包含新舊格式工具)")
    
    # 執行驗證
    print("\n執行驗證...")
    print("-" * 80)
    
    result = subprocess.run(
        [sys.executable, "pipeline/tools/validate_multi_turn_eng.py", temp_path],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("錯誤輸出:", result.stderr)
    
    # 清理
    import os
    os.unlink(temp_path)
    
    # 檢查結果
    print("-" * 80)
    if result.returncode == 0 and "PASS" in result.stdout:
        print("✓ 測試通過！驗證器支援新舊兩種格式。")
        return 0
    else:
        print("✗ 測試失敗！驗證器無法正確處理格式。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
