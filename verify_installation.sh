#!/bin/bash
# 驗證 Trading Bot 格式支援的所有修改

echo "=========================================="
echo "Trading Bot 格式支援 - 完整驗證"
echo "=========================================="
echo ""

cd /home/at0842/aaronwu901225master.ai13/pythonic-function-calling-data

# 顏色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 檢查計數
TOTAL_CHECKS=0
PASSED_CHECKS=0

# 輔助函數
check_file() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} 檔案存在: $1"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗${NC} 檔案缺失: $1"
        return 1
    fi
}

check_content() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if grep -q "$2" "$1" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} 內容驗證: $1 包含 '$3'"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗${NC} 內容驗證失敗: $1 應包含 '$3'"
        return 1
    fi
}

echo "1. 檢查修改的核心檔案..."
echo "----------------------------------------"
check_file "pipeline/tools/convert_to_multi_turn_eng.py"
check_file "pipeline/tools/merge_global_tools.py"
echo ""

echo "2. 檢查新增的測試檔案..."
echo "----------------------------------------"
check_file "test_trading_format.py"
check_file "examples_trading_format.py"
check_file "validate_trading_format.py"
echo ""

echo "3. 檢查新增的文檔..."
echo "----------------------------------------"
check_file "TRADING_FORMAT_CHANGES.md"
check_file "TRADING_FORMAT_README.md"
check_file "SUMMARY.md"
echo ""

echo "4. 驗證核心功能修改..."
echo "----------------------------------------"
check_content "pipeline/tools/convert_to_multi_turn_eng.py" "use_dict_type" "use_dict_type 參數"
check_content "pipeline/tools/convert_to_multi_turn_eng.py" '"type": "dict"' '"type": "dict"'
check_content "pipeline/tools/convert_to_multi_turn_eng.py" '"response":' 'response 欄位生成'
check_content "pipeline/tools/merge_global_tools.py" '"response"' 'response 欄位處理'
echo ""

echo "5. 執行基本格式測試..."
echo "----------------------------------------"
if python test_trading_format.py 2>/dev/null | grep -q "所有檢查通過"; then
    echo -e "${GREEN}✓${NC} 基本格式測試通過"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "${RED}✗${NC} 基本格式測試失敗"
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
echo ""

echo "=========================================="
echo "驗證結果"
echo "=========================================="
echo "總檢查項目: $TOTAL_CHECKS"
echo "通過項目: $PASSED_CHECKS"
echo "失敗項目: $((TOTAL_CHECKS - PASSED_CHECKS))"
echo ""

if [ $PASSED_CHECKS -eq $TOTAL_CHECKS ]; then
    echo -e "${GREEN}✓ 所有驗證通過！Trading Bot 格式支援已正確實作。${NC}"
    echo ""
    echo "下一步："
    echo "  1. 執行: python examples_trading_format.py  # 查看範例"
    echo "  2. 執行完整資料生成流程"
    echo "  3. 使用 validate_trading_format.py 驗證生成的資料"
    exit 0
else
    echo -e "${RED}✗ 部分驗證失敗，請檢查上述錯誤訊息。${NC}"
    exit 1
fi
