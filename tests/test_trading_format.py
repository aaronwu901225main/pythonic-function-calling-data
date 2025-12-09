#!/usr/bin/env python3
"""測試生成的工具格式是否符合 trading_bot.json 格式"""

import json
import sys
from pipeline.tools.convert_to_multi_turn_eng import build_tool_from_signature

# 測試範例函數簽名
test_signature = '''def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: the stock symbol to add to the watchlist.
    :return: Dictionary containing the symbol that was successfully added.
    """
    pass
'''

def main():
    # 生成工具 schema
    tool = build_tool_from_signature(test_signature)
    
    # 打印結果
    print("生成的工具 Schema:")
    print(json.dumps(tool, indent=2, ensure_ascii=False))
    
    # 驗證必要欄位
    print("\n驗證結果:")
    checks = {
        "name 欄位": "name" in tool,
        "description 欄位": "description" in tool,
        "parameters 欄位": "parameters" in tool,
        "response 欄位": "response" in tool,
        "parameters.type 是 'dict'": tool.get("parameters", {}).get("type") == "dict",
        "response.type 是 'dict'": tool.get("response", {}).get("type") == "dict",
        "parameters 有 properties": "properties" in tool.get("parameters", {}),
        "parameters 有 required": "required" in tool.get("parameters", {}),
        "response 有 properties": "properties" in tool.get("response", {}),
    }
    
    all_passed = True
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"{status} {check}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n✓ 所有檢查通過！格式符合 trading_bot.json 標準。")
        return 0
    else:
        print("\n✗ 部分檢查失敗，請檢查格式。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
