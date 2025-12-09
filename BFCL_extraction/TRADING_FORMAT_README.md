# Trading Bot 格式整合指南

## 概述

本專案已修改為生成符合 `trading_bot.json` 格式的工具列表，主要變更包括：

1. **參數類型**：使用 `"type": "dict"` 代替 `"type": "object"`
2. **回應欄位**：新增 `response` 欄位定義函數返回值的結構
3. **完整保留**：在 merge 過程中保留所有必要欄位

## 快速開始

### 1. 測試格式生成

執行測試腳本驗證格式是否正確：

```bash
cd /home/at0842/aaronwu901225master.ai13/pythonic-function-calling-data
python test_trading_format.py
```

預期輸出：
```
✓ 所有檢查通過！格式符合 trading_bot.json 標準。
```

### 2. 查看格式範例

查看不同類型函數的工具格式範例：

```bash
python examples_trading_format.py
```

這會展示多種情況下的工具格式，包括：
- 簡單 Dict 返回值
- 多參數與複雜返回值
- 無參數函數
- 字串/布林返回值

### 3. 完整資料生成流程

```bash
# 設定環境變數（可選）
export OPENAI_API_KEY="your-api-key"
export S1_NUM_SCENARIOS="3"
export S3_SIMPLE_NUM="2"
export OPENAI_RATE_SLEEP="1"

# Step 1: 生成場景
python run_s1_openai.py

# Step 2: 生成函數（會包含 response 欄位）
python run_s2_openai.py

# Step 3: 生成查詢
python run_s3_openai.py

# Step 4: 生成偽函數（可選）
python run_s4_openai.py

# 轉換為 multi_turn_eng 格式
python -m pipeline.tools.convert_to_multi_turn_eng

# 讀取 run_id
RUN_ID=$(cat run_id)

# Merge 全域工具（保留 response 欄位）
python -m pipeline.tools.merge_global_tools \
  --input pipeline/data/${RUN_ID}/multi_turn_eng.jsonl \
  --output pipeline/data/${RUN_ID}/multi_turn_eng_merged.jsonl \
  --include-pseudo \
  --token-budget 100000 \
  --seed 42
```

## 格式說明

### 標準格式結構

```json
{
  "name": "function_name",
  "description": "Function description with Return and Raises info",
  "parameters": {
    "type": "dict",
    "properties": {
      "param1": {
        "type": "string",
        "description": "Parameter description"
      }
    },
    "required": ["param1"]
  },
  "response": {
    "type": "dict",
    "properties": {
      "result_field": {
        "type": "string",
        "description": "Response field description"
      }
    }
  }
}
```

### Response 欄位生成規則

1. **Dict 返回值** (`-> Dict[str, Any]`)：
   ```json
   "response": {
     "type": "dict",
     "properties": {},
     "description": "從 :return: docstring 提取"
   }
   ```

2. **基本類型返回值** (`-> str`, `-> int`, `-> bool`)：
   ```json
   "response": {
     "type": "dict",
     "properties": {
       "result": {
         "type": "string",  // or integer, boolean
         "description": "從 :return: docstring 提取"
       }
     }
   }
   ```

3. **無返回值或 None**：
   ```json
   "response": {
     "type": "dict",
     "properties": {}
   }
   ```

## 與 trading_bot.json 的對照

### Trading Bot 範例

```json
{
  "name": "add_to_watchlist",
  "description": "This tool belongs to the trading system...",
  "parameters": {
    "type": "dict",
    "properties": {
      "stock": {
        "type": "string",
        "description": "the stock symbol to add..."
      }
    },
    "required": ["stock"]
  },
  "response": {
    "type": "dict",
    "properties": {
      "symbol": {
        "type": "string",
        "description": "the symbol that were successfully added..."
      }
    }
  }
}
```

### Pythonic 生成的格式

從以下函數簽名：

```python
def add_to_watchlist(stock: str) -> Dict[str, str]:
    """Add a stock to the watchlist.
    
    :param stock: the stock symbol to add to the watchlist.
    :return: Dictionary containing the symbol that was successfully added.
    """
    pass
```

生成：

```json
{
  "name": "add_to_watchlist",
  "description": "Add a stock to the watchlist. \nReturn: Dictionary containing...",
  "parameters": {
    "type": "dict",
    "properties": {
      "stock": {
        "type": "string",
        "description": "the stock symbol to add to the watchlist."
      }
    },
    "required": ["stock"]
  },
  "response": {
    "type": "dict",
    "properties": {},
    "description": "Dictionary containing the symbol that was successfully added."
  }
}
```

## 重要變更文件

1. **convert_to_multi_turn_eng.py**
   - `_python_type_to_jsonschema()`: 支援 `use_dict_type` 參數
   - `build_tool_from_signature()`: 生成 response 欄位

2. **merge_global_tools.py**
   - `build_global_tool_pool()`: 確保 response 欄位存在
   - `main()`: merge 時保留 response 欄位

詳細變更請參閱：`TRADING_FORMAT_CHANGES.md`

## 環境變數參考

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `S1_NUM_SCENARIOS` | Step 1 每個 curriculum 生成的場景數 | `1` |
| `S1_LIMIT_ROWS` | Step 1 處理的 curriculum 行數上限 | 無限制 |
| `S2_LIMIT_SCENARIOS` | Step 2 處理的場景數上限 | 無限制 |
| `S3_SIMPLE_NUM` | Step 3 simple queries 數量 | `2` |
| `S3_PARALLEL_NUM` | Step 3 parallel queries 數量 | `2` |
| `S4_PSEUDO_PER_SAMPLE` | Step 4 每個 sample 生成的偽函數數 | `6` |
| `S4_MAX_RETRIES` | Step 4 重試次數 | `2` |
| `PSEUDO_STYLE` | Step 4 偽函數風格 (`distractor`/`related`) | `distractor` |
| `INCLUDE_PSEUDO_TOOLS` | 轉換時是否包含偽工具 | `1` |
| `OPENAI_RATE_SLEEP` | API 調用間隔（秒） | `0` |

## 疑難排解

### 問題：response 欄位缺失

**症狀**：生成的工具沒有 response 欄位

**解決方法**：
1. 確認使用最新版的 `convert_to_multi_turn_eng.py`
2. 檢查函數簽名是否有 return type annotation
3. 即使沒有 return type，也應該有空的 response 結構

### 問題：type 是 "object" 而非 "dict"

**症狀**：parameters.type 或 response.type 是 "object"

**解決方法**：
1. 確認 `_python_type_to_jsonschema()` 的 `use_dict_type` 參數為 `True`
2. 重新生成資料

### 問題：merge 後 response 欄位消失

**症狀**：merge_global_tools.py 執行後 response 欄位遺失

**解決方法**：
1. 確認使用最新版的 `merge_global_tools.py`
2. 檢查是否有正確保留 response 欄位（不應在 `cleaned.pop()` 中）

## 參考資料

- 原始格式範例：`gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/multi_turn_func_doc/trading_bot.json`
- 變更文檔：`TRADING_FORMAT_CHANGES.md`
- 測試腳本：`test_trading_format.py`
- 範例展示：`examples_trading_format.py`

## 聯絡方式

如有問題或建議，請查閱：
- 專案文檔：`TRADING_FORMAT_CHANGES.md`
- 測試輸出：執行 `test_trading_format.py` 和 `examples_trading_format.py`
