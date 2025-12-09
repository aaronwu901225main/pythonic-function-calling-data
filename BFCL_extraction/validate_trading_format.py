#!/usr/bin/env python3
"""驗證 multi_turn_eng.jsonl 檔案是否符合 trading_bot.json 格式"""

import json
import sys
import argparse
from typing import Dict, Any, List


def check_tool_format(tool: Dict[str, Any]) -> Dict[str, bool]:
    """檢查單個工具的格式"""
    checks = {
        "has_name": "name" in tool,
        "has_description": "description" in tool,
        "has_parameters": "parameters" in tool,
        "has_response": "response" in tool,
        "parameters_is_dict": tool.get("parameters", {}).get("type") == "dict",
        "response_is_dict": tool.get("response", {}).get("type") == "dict",
        "parameters_has_properties": "properties" in tool.get("parameters", {}),
        "parameters_has_required": "required" in tool.get("parameters", {}),
        "response_has_properties": "properties" in tool.get("response", {}),
    }
    return checks


def validate_file(filepath: str, verbose: bool = False) -> tuple[int, int, int]:
    """驗證整個檔案
    
    Returns:
        (total_samples, total_tools, failed_tools)
    """
    total_samples = 0
    total_tools = 0
    failed_tools = 0
    failed_details = []
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                sample = json.loads(line)
                total_samples += 1
                
                tools = sample.get("tools", [])
                for tool_idx, tool in enumerate(tools):
                    total_tools += 1
                    checks = check_tool_format(tool)
                    
                    if not all(checks.values()):
                        failed_tools += 1
                        failed_details.append({
                            "line": line_num,
                            "tool_name": tool.get("name", f"tool_{tool_idx}"),
                            "failed_checks": [k for k, v in checks.items() if not v]
                        })
                        
                        if verbose:
                            print(f"\n✗ Sample {total_samples}, Tool: {tool.get('name', 'unknown')}")
                            for check_name, passed in checks.items():
                                if not passed:
                                    print(f"  ✗ {check_name}")
            
            except json.JSONDecodeError as e:
                print(f"✗ Line {line_num}: JSON decode error: {e}")
                continue
    
    return total_samples, total_tools, failed_tools, failed_details


def main():
    parser = argparse.ArgumentParser(
        description="驗證 multi_turn_eng.jsonl 檔案是否符合 trading_bot.json 格式"
    )
    parser.add_argument("filepath", help="要驗證的 .jsonl 檔案路徑")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示詳細的失敗資訊")
    parser.add_argument("--show-failed", action="store_true", help="顯示所有失敗的工具清單")
    
    args = parser.parse_args()
    
    try:
        total_samples, total_tools, failed_tools, failed_details = validate_file(
            args.filepath, args.verbose
        )
        
        print("\n" + "=" * 80)
        print("驗證結果摘要")
        print("=" * 80)
        print(f"總樣本數: {total_samples}")
        print(f"總工具數: {total_tools}")
        print(f"失敗工具數: {failed_tools}")
        
        if failed_tools == 0:
            print("\n✓ 所有工具都符合 trading_bot.json 格式！")
            return 0
        else:
            success_rate = ((total_tools - failed_tools) / total_tools * 100) if total_tools > 0 else 0
            print(f"成功率: {success_rate:.2f}%")
            print(f"\n✗ 有 {failed_tools} 個工具不符合格式")
            
            if args.show_failed:
                print("\n失敗的工具清單:")
                for detail in failed_details[:20]:  # 限制顯示前 20 個
                    print(f"\n  Line {detail['line']}: {detail['tool_name']}")
                    print(f"    失敗檢查: {', '.join(detail['failed_checks'])}")
                
                if len(failed_details) > 20:
                    print(f"\n  ... 還有 {len(failed_details) - 20} 個失敗的工具")
            
            return 1
    
    except FileNotFoundError:
        print(f"✗ 檔案不存在: {args.filepath}")
        return 1
    except Exception as e:
        print(f"✗ 驗證過程發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
