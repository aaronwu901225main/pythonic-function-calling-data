# Trading Bot 格式 - 快速參考

## 🎯 主要目標
讓 pythonic-function-calling-data 生成符合 trading_bot.json 格式的工具列表

## ✅ 完成狀態
所有修改已完成並測試通過 ✓

## 📋 快速檢查清單

### 驗證安裝
```bash
cd /home/at0842/aaronwu901225master.ai13/pythonic-function-calling-data
./verify_installation.sh
```
預期結果：`✓ 所有驗證通過！`

### 測試格式
```bash
# 基本測試
python test_trading_format.py

# 查看範例
python examples_trading_format.py
```

## 🔧 主要修改

### 1. 核心檔案修改
- ✓ `pipeline/tools/convert_to_multi_turn_eng.py`
  - 新增 `use_dict_type` 參數
  - 生成 `response` 欄位
  - 使用 `"type": "dict"`

- ✓ `pipeline/tools/merge_global_tools.py`
  - 保留 `response` 欄位
  - 使用 `"type": "dict"`

### 2. 格式變更對照

| 項目 | 舊格式 | 新格式 |
|------|--------|--------|
| parameters.type | `"object"` | `"dict"` |
| response 欄位 | ❌ | ✓ |
| response.type | N/A | `"dict"` |
| response.properties | N/A | ✓ |

### 3. 範例格式

**輸入（Python 函數）：**
```python
def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: the stock symbol to add.
    :return: Symbol that was added.
    """
    pass
```

**輸出（JSON Schema）：**
```json
{
  "name": "add_to_watchlist",
  "description": "Add a stock to the watchlist. \nReturn: Symbol that was added.",
  "parameters": {
    "type": "dict",
    "properties": {
      "stock": {
        "type": "string",
        "description": "the stock symbol to add."
      }
    },
    "required": ["stock"]
  },
  "response": {
    "type": "dict",
    "properties": {},
    "description": "Symbol that was added."
  }
}
```

## 🚀 使用流程

### 完整資料生成
```bash
# 1. 生成場景
python run_s1_openai.py

# 2. 生成函數（自動包含 response）
python run_s2_openai.py

# 3. 生成查詢
python run_s3_openai.py

# 4. 生成偽函數（可選）
python run_s4_openai.py

# 5. 轉換為 eng 格式
python -m pipeline.tools.convert_to_multi_turn_eng

# 6. Merge 工具（保留 response）
RUN_ID=$(cat run_id)
python -m pipeline.tools.merge_global_tools \
  --input pipeline/data/${RUN_ID}/multi_turn_eng.jsonl \
  --output pipeline/data/${RUN_ID}/multi_turn_eng_merged.jsonl \
  --include-pseudo \
  --token-budget 100000
```

### 驗證生成的資料
```bash
RUN_ID=$(cat run_id)
python validate_trading_format.py \
  pipeline/data/${RUN_ID}/multi_turn_eng.jsonl \
  -v --show-failed
```

## 📚 文檔索引

| 文檔 | 用途 |
|------|------|
| `TRADING_FORMAT_README.md` | 使用指南（推薦閱讀） |
| `TRADING_FORMAT_CHANGES.md` | 技術細節 |
| `SUMMARY.md` | 完整摘要 |
| `QUICK_REFERENCE.md` | 本文檔 |

## 🔍 測試工具

| 腳本 | 功能 |
|------|------|
| `verify_installation.sh` | 驗證所有修改是否正確 |
| `test_trading_format.py` | 測試基本格式生成 |
| `examples_trading_format.py` | 展示多種範例 |
| `validate_trading_format.py` | 驗證完整 .jsonl 檔案 |

## ⚙️ 環境變數（可選）

```bash
export OPENAI_API_KEY="your-key"
export S1_NUM_SCENARIOS="3"          # 每個 curriculum 生成的場景數
export S3_SIMPLE_NUM="2"             # simple queries 數量
export OPENAI_RATE_SLEEP="1"         # API 調用間隔（秒）
export INCLUDE_PSEUDO_TOOLS="1"      # 是否包含偽工具
```

## ❓ 疑難排解

### 問題：response 欄位缺失
**檢查：**
```bash
python test_trading_format.py
```
**解決：**確認使用最新版 `convert_to_multi_turn_eng.py`

### 問題：type 是 "object" 而非 "dict"
**檢查：**
```bash
grep 'use_dict_type' pipeline/tools/convert_to_multi_turn_eng.py
```
**解決：**重新套用修改或重新生成資料

### 問題：merge 後 response 消失
**檢查：**
```bash
grep 'response' pipeline/tools/merge_global_tools.py
```
**解決：**確認使用最新版 `merge_global_tools.py`

## 📞 獲取幫助

1. 執行驗證：`./verify_installation.sh`
2. 查看範例：`python examples_trading_format.py`
3. 閱讀文檔：`TRADING_FORMAT_README.md`
4. 檢查測試：`python test_trading_format.py`

## 🎉 成功指標

執行以下命令應該全部通過：
```bash
./verify_installation.sh && \
python test_trading_format.py && \
echo "✓ 所有測試通過！可以開始使用。"
```

---

**最後更新：** 2025-12-08  
**狀態：** ✓ 完成並測試通過
