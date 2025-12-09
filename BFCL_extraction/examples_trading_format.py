#!/usr/bin/env python3
"""展示各種函數簽名生成的工具格式範例"""

import json
from pipeline.tools.convert_to_multi_turn_eng import build_tool_from_signature

# 測試案例
test_cases = [
    {
        "name": "簡單 Dict 返回值",
        "signature": '''def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: the stock symbol to add to the watchlist.
    :return: Dictionary containing the symbol that was successfully added.
    """
    pass
'''
    },
    {
        "name": "多參數與複雜返回值",
        "signature": '''def filter_stocks_by_price(stocks: List[str], min_price: float, max_price: float) -> Dict[str, Any]:
    """Filter stocks based on a price range.
    
    :param stocks: List of stock symbols to filter.
    :param min_price: Minimum stock price.
    :param max_price: Maximum stock price.
    :return: Filtered list of stock symbols within the price range.
    """
    pass
'''
    },
    {
        "name": "無參數",
        "signature": '''def get_account_info() -> Dict[str, Any]:
    """Get account information.
    
    :return: Account details including balance and holdings.
    """
    pass
'''
    },
    {
        "name": "字串返回值",
        "signature": '''def get_symbol_by_name(company_name: str) -> str:
    """Get the symbol of a stock by company name.
    
    :param company_name: The name of the company.
    :return: The stock symbol.
    """
    pass
'''
    },
    {
        "name": "布林返回值",
        "signature": '''def trading_login(username: str, password: str) -> bool:
    """Handle user login.
    
    :param username: The username for login.
    :param password: The password for login.
    :return: True if login successful, False otherwise.
    """
    pass
'''
    },
]

def main():
    print("=" * 80)
    print("Pythonic Function Calling - Trading Bot 格式範例")
    print("=" * 80)
    print()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 80}")
        print(f"範例 {i}: {test_case['name']}")
        print('=' * 80)
        print("\n原始函數簽名:")
        print(test_case['signature'])
        
        tool = build_tool_from_signature(test_case['signature'])
        
        print("\n生成的工具 Schema:")
        print(json.dumps(tool, indent=2, ensure_ascii=False))
        
        # 驗證關鍵欄位
        checks = [
            ("parameters.type", tool.get("parameters", {}).get("type") == "dict"),
            ("response.type", tool.get("response", {}).get("type") == "dict"),
            ("response.properties 存在", "properties" in tool.get("response", {})),
        ]
        
        print("\n格式驗證:")
        for check_name, result in checks:
            print(f"  {'✓' if result else '✗'} {check_name}")
    
    print("\n" + "=" * 80)
    print("所有範例生成完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
