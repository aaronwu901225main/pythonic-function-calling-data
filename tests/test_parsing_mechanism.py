#!/usr/bin/env python3
"""完整的 parsing 機制測試 - 從 LLM 輸出到最終 tool schema"""

import json
import sys
import re
from typing import List, Dict, Any

# 模擬各個 parsing 階段
from openai_utils import extract_tags, extract_code_fence
from pipeline.s2_functions.parser import parse_signature
from pipeline.tools.convert_to_multi_turn_eng import build_tool_from_signature

def test_stage_1_llm_output_parsing():
    """測試階段 1: 從 LLM 輸出提取函數"""
    print("=" * 80)
    print("階段 1: LLM 輸出解析測試")
    print("=" * 80)
    
    # 模擬 LLM 的輸出
    llm_output = """
Based on the scenario, here are the function signatures:

<function>
<signature>
```python
def add_to_watchlist(stock: str) -> Dict[str, str]:
    \"\"\"Add a stock to the watchlist.
    
    :param stock: The stock symbol to add to the watchlist.
    :return_fields:
      - symbol (str): The symbol that was successfully added to the watchlist.
    :raises ValueError: If the stock symbol is invalid.
    \"\"\"
    pass
```
</signature>
<expected>
{"symbol": "AAPL"}
</expected>
</function>

<function>
<signature>
```python
def get_account_info() -> Dict[str, Any]:
    \"\"\"Get account information.
    
    :return_fields:
      - account_id (int): ID of the account.
      - balance (float): Current balance of the account.
      - binding_card (int): Card number associated with the account.
    \"\"\"
    pass
```
</signature>
<expected>
{"account_id": 12345, "balance": 10000.50, "binding_card": 987654321}
</expected>
</function>
"""
    
    # 測試 extract_tags
    func_blocks = extract_tags(llm_output, "function")
    print(f"\n提取到 {len(func_blocks)} 個 <function> 區塊")
    
    if len(func_blocks) != 2:
        print(f"✗ 預期 2 個函數，實際得到 {len(func_blocks)} 個")
        return False
    
    # 測試每個 function 區塊
    for i, fb in enumerate(func_blocks, 1):
        print(f"\n--- 函數 {i} ---")
        
        # 提取 signature
        sig_blocks = extract_tags(fb, "signature")
        if not sig_blocks:
            print(f"✗ 無法提取 signature")
            return False
        print(f"✓ 提取到 signature 區塊")
        
        # 提取 Python code fence
        code_blocks = extract_code_fence(sig_blocks[0], lang="python")
        if not code_blocks:
            print(f"✗ 無法提取 Python code fence")
            return False
        print(f"✓ 提取到 Python 程式碼")
        
        # 提取 expected
        exp_blocks = extract_tags(fb, "expected")
        if not exp_blocks:
            print(f"✗ 無法提取 expected")
            return False
        print(f"✓ 提取到 expected 值")
    
    print(f"\n✓ 階段 1 通過: LLM 輸出解析正常")
    return True


def test_stage_2_signature_parsing():
    """測試階段 2: 函數簽名解析"""
    print("\n" + "=" * 80)
    print("階段 2: 函數簽名解析測試")
    print("=" * 80)
    
    test_signatures = [
        {
            "name": "簡單函數",
            "code": '''def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: The stock symbol to add to the watchlist.
    :return_fields:
      - symbol (str): The symbol that was successfully added to the watchlist.
    """
    pass
''',
            "expected": {
                "function_name": "add_to_watchlist",
                "return_type": "Dict[str, str]",
                "parameters": [("stock", "str", None)]
            }
        },
        {
            "name": "複雜函數",
            "code": '''def filter_stocks_by_price(stocks: List[str], min_price: float, max_price: float) -> Dict[str, List[str]]:
    """Filter stocks based on a price range.
    
    :param stocks: List of stock symbols to filter.
    :param min_price: Minimum stock price.
    :param max_price: Maximum stock price.
    :return_fields:
      - filtered_stocks (List[str]): Filtered list of stock symbols within the price range.
    """
    pass
''',
            "expected": {
                "function_name": "filter_stocks_by_price",
                "return_type": "Dict[str, List[str]]",
                "parameters": [
                    ("stocks", "List[str]", None),
                    ("min_price", "float", None),
                    ("max_price", "float", None)
                ]
            }
        }
    ]
    
    for test in test_signatures:
        print(f"\n測試: {test['name']}")
        parsed = parse_signature(test['code'])
        
        # 檢查函數名
        if parsed.get('function_name') != test['expected']['function_name']:
            print(f"✗ 函數名錯誤: 預期 {test['expected']['function_name']}, 得到 {parsed.get('function_name')}")
            return False
        print(f"  ✓ 函數名: {parsed.get('function_name')}")
        
        # 檢查返回類型
        if parsed.get('return_type') != test['expected']['return_type']:
            print(f"✗ 返回類型錯誤: 預期 {test['expected']['return_type']}, 得到 {parsed.get('return_type')}")
            return False
        print(f"  ✓ 返回類型: {parsed.get('return_type')}")
        
        # 檢查參數
        if parsed.get('parameters') != test['expected']['parameters']:
            print(f"✗ 參數錯誤")
            print(f"  預期: {test['expected']['parameters']}")
            print(f"  得到: {parsed.get('parameters')}")
            return False
        print(f"  ✓ 參數: {len(parsed.get('parameters', []))} 個")
    
    print(f"\n✓ 階段 2 通過: 函數簽名解析正常")
    return True


def test_stage_3_tool_schema_generation():
    """測試階段 3: Tool Schema 生成"""
    print("\n" + "=" * 80)
    print("階段 3: Tool Schema 生成測試")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "帶 return_fields 的函數",
            "signature": '''def get_account_info() -> Dict[str, Any]:
    """Get account information.
    
    :return_fields:
      - account_id (int): ID of the account.
      - balance (float): Current balance of the account.
      - binding_card (int): Card number associated with the account.
    """
    pass
''',
            "checks": [
                ("response.type", lambda t: t.get("response", {}).get("type") == "dict"),
                ("response.properties 不為空", lambda t: len(t.get("response", {}).get("properties", {})) > 0),
                ("response.properties 有 3 個欄位", lambda t: len(t.get("response", {}).get("properties", {})) == 3),
                ("account_id 類型正確", lambda t: t.get("response", {}).get("properties", {}).get("account_id", {}).get("type") == "integer"),
                ("balance 類型正確", lambda t: t.get("response", {}).get("properties", {}).get("balance", {}).get("type") == "number"),
                ("所有欄位都有 description", lambda t: all("description" in v for v in t.get("response", {}).get("properties", {}).values())),
            ]
        },
        {
            "name": "帶參數描述的函數",
            "signature": '''def send_message(receiver_id: str, message: str) -> Dict[str, Any]:
    """Send a message to a user.
    
    :param receiver_id: User ID of the user to send the message to.
    :param message: Message to be sent.
    :return_fields:
      - sent_status (bool): True if the message was sent successfully, False otherwise.
      - message_id (int): ID of the sent message.
    """
    pass
''',
            "checks": [
                ("parameters.type", lambda t: t.get("parameters", {}).get("type") == "dict"),
                ("parameters 有 2 個屬性", lambda t: len(t.get("parameters", {}).get("properties", {})) == 2),
                ("receiver_id 有描述", lambda t: "description" in t.get("parameters", {}).get("properties", {}).get("receiver_id", {})),
                ("response 有 2 個欄位", lambda t: len(t.get("response", {}).get("properties", {})) == 2),
                ("sent_status 是 boolean", lambda t: t.get("response", {}).get("properties", {}).get("sent_status", {}).get("type") == "boolean"),
            ]
        }
    ]
    
    for test in test_cases:
        print(f"\n測試: {test['name']}")
        tool = build_tool_from_signature(test['signature'])
        
        all_passed = True
        for check_name, check_func in test['checks']:
            try:
                result = check_func(tool)
                if result:
                    print(f"  ✓ {check_name}")
                else:
                    print(f"  ✗ {check_name}")
                    all_passed = False
            except Exception as e:
                print(f"  ✗ {check_name} (錯誤: {e})")
                all_passed = False
        
        if not all_passed:
            print(f"\n實際生成的 tool schema:")
            print(json.dumps(tool, indent=2, ensure_ascii=False))
            return False
    
    print(f"\n✓ 階段 3 通過: Tool Schema 生成正常")
    return True


def test_stage_4_end_to_end():
    """測試階段 4: 端到端流程"""
    print("\n" + "=" * 80)
    print("階段 4: 端到端流程測試")
    print("=" * 80)
    
    # 完整的 LLM 輸出
    llm_output = """
<function>
<signature>
```python
def cancel_order(order_id: int) -> Dict[str, Any]:
    \"\"\"Cancel an order.
    
    :param order_id: ID of the order to cancel.
    :return_fields:
      - order_id (int): ID of the cancelled order.
      - status (str): New status of the order after cancellation attempt.
    :raises ValueError: If order_id is invalid.
    \"\"\"
    pass
```
</signature>
<expected>
{"order_id": 12345, "status": "cancelled"}
</expected>
</function>
"""
    
    print("\n模擬完整流程...")
    
    # 步驟 1: 提取函數區塊
    func_blocks = extract_tags(llm_output, "function")
    if not func_blocks:
        print("✗ 無法提取函數區塊")
        return False
    print("✓ 步驟 1: 提取函數區塊")
    
    # 步驟 2: 提取簽名
    sig_blocks = extract_tags(func_blocks[0], "signature")
    if not sig_blocks:
        print("✗ 無法提取簽名")
        return False
    print("✓ 步驟 2: 提取簽名")
    
    # 步驟 3: 提取程式碼
    code_blocks = extract_code_fence(sig_blocks[0], lang="python")
    if not code_blocks:
        print("✗ 無法提取程式碼")
        return False
    print("✓ 步驟 3: 提取程式碼")
    
    # 步驟 4: 解析簽名
    parsed = parse_signature(code_blocks[0])
    if not parsed.get('function_name'):
        print("✗ 無法解析函數簽名")
        return False
    print(f"✓ 步驟 4: 解析簽名 ({parsed.get('function_name')})")
    
    # 步驟 5: 生成 tool schema
    tool = build_tool_from_signature(code_blocks[0])
    if not tool.get('name'):
        print("✗ 無法生成 tool schema")
        return False
    print("✓ 步驟 5: 生成 tool schema")
    
    # 驗證最終結果
    print("\n最終生成的 tool:")
    print(json.dumps(tool, indent=2, ensure_ascii=False))
    
    # 關鍵檢查
    checks = [
        ("name", tool.get("name") == "cancel_order"),
        ("parameters.type", tool.get("parameters", {}).get("type") == "dict"),
        ("response.type", tool.get("response", {}).get("type") == "dict"),
        ("response 有 2 個欄位", len(tool.get("response", {}).get("properties", {})) == 2),
        ("order_id 在 response 中", "order_id" in tool.get("response", {}).get("properties", {})),
        ("status 在 response 中", "status" in tool.get("response", {}).get("properties", {})),
    ]
    
    print("\n驗證結果:")
    all_passed = True
    for check_name, result in checks:
        if result:
            print(f"  ✓ {check_name}")
        else:
            print(f"  ✗ {check_name}")
            all_passed = False
    
    if not all_passed:
        return False
    
    print(f"\n✓ 階段 4 通過: 端到端流程正常")
    return True


def main():
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "完整 Parsing 機制測試" + " " * 36 + "║")
    print("╚" + "═" * 78 + "╝")
    
    tests = [
        ("LLM 輸出解析", test_stage_1_llm_output_parsing),
        ("函數簽名解析", test_stage_2_signature_parsing),
        ("Tool Schema 生成", test_stage_3_tool_schema_generation),
        ("端到端流程", test_stage_4_end_to_end),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} 發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # 最終總結
    print("\n" + "=" * 80)
    print("測試總結")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✓ 通過" if passed else "✗ 失敗"
        print(f"{status}: {test_name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 所有 Parsing 機制測試通過！")
        print("\n整個流程從 LLM 輸出到最終 tool schema 都能正確處理。")
        return 0
    else:
        print("✗ 部分測試失敗，請檢查上述錯誤。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
