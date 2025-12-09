#!/usr/bin/env python3
"""測試 :return_fields: 解析和 response schema 生成"""

import json
import sys
from pipeline.tools.convert_to_multi_turn_eng import build_tool_from_signature

# 測試案例：符合新 prompt 格式的函數
test_cases = [
    {
        "name": "簡單返回欄位",
        "signature": '''def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: The stock symbol to add to the watchlist.
    :return_fields:
      - symbol (str): The symbol that was successfully added to the watchlist.
    :raises ValueError: If the stock symbol is invalid.
    """
    pass
''',
        "expected_response_properties": {
            "symbol": {
                "type": "string",
                "description": "The symbol that was successfully added to the watchlist."
            }
        }
    },
    {
        "name": "多個返回欄位",
        "signature": '''def get_account_info() -> Dict[str, Any]:
    """Get account information.
    
    :return_fields:
      - account_id (int): ID of the account.
      - balance (float): Current balance of the account.
      - binding_card (int): Card number associated with the account.
    """
    pass
''',
        "expected_response_properties": {
            "account_id": {
                "type": "integer",
                "description": "ID of the account."
            },
            "balance": {
                "type": "number",
                "description": "Current balance of the account."
            },
            "binding_card": {
                "type": "integer",
                "description": "Card number associated with the account."
            }
        }
    },
    {
        "name": "包含 List 類型的返回欄位",
        "signature": '''def filter_stocks_by_price(stocks: List[str], min_price: float, max_price: float) -> Dict[str, List[str]]:
    """Filter stocks based on a price range.
    
    :param stocks: List of stock symbols to filter.
    :param min_price: Minimum stock price.
    :param max_price: Maximum stock price.
    :return_fields:
      - filtered_stocks (List[str]): Filtered list of stock symbols within the price range.
    :raises ValueError: If min_price is greater than max_price.
    """
    pass
''',
        "expected_response_properties": {
            "filtered_stocks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filtered list of stock symbols within the price range."
            }
        }
    },
    {
        "name": "複雜返回結構",
        "signature": '''def send_message(receiver_id: str, message: str) -> Dict[str, Any]:
    """Send a message to a user.
    
    :param receiver_id: User ID of the user to send the message to.
    :param message: Message to be sent.
    :return_fields:
      - sent_status (bool): True if the message was sent successfully, False otherwise.
      - message_id (int): ID of the sent message.
      - message (str): A message describing the result of the send attempt.
    """
    pass
''',
        "expected_response_properties": {
            "sent_status": {
                "type": "boolean",
                "description": "True if the message was sent successfully, False otherwise."
            },
            "message_id": {
                "type": "integer",
                "description": "ID of the sent message."
            },
            "message": {
                "type": "string",
                "description": "A message describing the result of the send attempt."
            }
        }
    }
]

def compare_schemas(actual, expected, path=""):
    """遞迴比較兩個 schema"""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False, f"{path}: expected dict, got {type(actual)}"
        for key, expected_value in expected.items():
            if key not in actual:
                return False, f"{path}.{key}: missing in actual"
            match, msg = compare_schemas(actual[key], expected_value, f"{path}.{key}")
            if not match:
                return False, msg
        return True, ""
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            return False, f"{path}: expected list, got {type(actual)}"
        return True, ""
    else:
        if actual != expected:
            return False, f"{path}: expected {expected}, got {actual}"
        return True, ""

def main():
    print("=" * 80)
    print("測試 :return_fields: 解析和 response schema 生成")
    print("=" * 80)
    
    all_passed = True
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n測試 {i}: {test_case['name']}")
        print("-" * 80)
        
        # 生成工具 schema
        tool = build_tool_from_signature(test_case['signature'])
        
        print(f"\n生成的 response schema:")
        print(json.dumps(tool.get("response", {}), indent=2, ensure_ascii=False))
        
        # 驗證 response.properties
        actual_properties = tool.get("response", {}).get("properties", {})
        expected_properties = test_case["expected_response_properties"]
        
        match, msg = compare_schemas(actual_properties, expected_properties, "response.properties")
        
        if match:
            print(f"\n✓ 測試通過")
        else:
            print(f"\n✗ 測試失敗: {msg}")
            print(f"\n預期:")
            print(json.dumps(expected_properties, indent=2, ensure_ascii=False))
            print(f"\n實際:")
            print(json.dumps(actual_properties, indent=2, ensure_ascii=False))
            all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 所有測試通過！")
        print("\n新的 prompt 格式可以正確生成詳細的 response schema。")
        return 0
    else:
        print("✗ 部分測試失敗")
        return 1

if __name__ == "__main__":
    sys.exit(main())
