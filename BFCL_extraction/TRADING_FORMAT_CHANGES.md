# Pythonic Function Calling Data - Trading Bot 格式支援

## 修改摘要

為了讓 pythonic-function-calling-data 生成的工具列表符合 `trading_bot.json` 格式，我們進行了以下修改：

## 修改內容

### 1. convert_to_multi_turn_eng.py

#### 1.1 修改 `_python_type_to_jsonschema()` 函數

**位置**: Line 11-32

**變更**:
- 新增 `use_dict_type` 參數（預設為 True）
- 將 Dict 類型的 JSON Schema type 從 `"object"` 改為 `"dict"`
- 遞迴調用時傳遞 `use_dict_type` 參數

**目的**: 符合 trading_bot.json 使用 `"type": "dict"` 的格式

#### 1.2 修改 `build_tool_from_signature()` 函數

**位置**: Line 36-130

**變更**:
1. 新增提取 `return_type` 從 parsed signature
2. 新增 response schema 生成邏輯：
   - 從函數的 return type annotation 生成 response schema
   - 如果 return type 是 dict，直接使用
   - 否則包裝在 `{"result": ...}` 結構中
   - 將 docstring 的 `:return:` 描述加入 response schema
3. 將 parameters 的 type 從 `"object"` 改為 `"dict"`
4. 在調用 `_python_type_to_jsonschema()` 時傳遞 `use_dict_type=True`
5. 在返回的 schema 中新增 `"response"` 欄位

**範例輸出**:
```json
{
  "name": "add_to_watchlist",
  "description": "Add a stock to the watchlist.",
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
    "properties": {
      "symbol": {
        "type": "string",
        "description": "Dictionary containing the symbol that was successfully added."
      }
    }
  }
}
```

### 2. merge_global_tools.py

#### 2.1 修改 `build_global_tool_pool()` 函數

**位置**: Line 53-68

**變更**:
1. 將 parameters 的預設 type 從 `"object"` 改為 `"dict"`
2. 新增 response 欄位的預設值：`{"type": "dict", "properties": {}}`
3. 更新函數 docstring 說明包含 response 欄位

#### 2.2 修改 `main()` 函數中的工具處理邏輯

**位置**: Line 89-106

**變更**:
1. 在處理 base_tools 時確保 response 欄位存在
2. 將 parameters 預設 type 從 `"object"` 改為 `"dict"`
3. 在移除 pseudo 標記時保留 response 欄位
4. 更新註解說明保留所有欄位

**目的**: 確保在 merge 過程中不會遺失 response 欄位

## 格式對照

### 修改前 (原始格式)
```json
{
  "name": "function_name",
  "description": "...",
  "parameters": {
    "type": "object",
    "properties": {...},
    "required": [...]
  }
}
```

### 修改後 (trading_bot.json 格式)
```json
{
  "name": "function_name",
  "description": "...",
  "parameters": {
    "type": "dict",
    "properties": {...},
    "required": [...]
  },
  "response": {
    "type": "dict",
    "properties": {...}
  }
}
```

## 測試方法

執行測試腳本驗證格式：

```bash
cd /home/at0842/aaronwu901225master.ai13/pythonic-function-calling-data
python test_trading_format.py
```

## 使用流程

完整的資料生成流程保持不變：

```bash
# Step 1: 生成場景
python run_s1_openai.py

# Step 2: 生成函數
python run_s2_openai.py

# Step 3: 生成查詢
python run_s3_openai.py

# Step 4: 生成偽函數 (可選)
python run_s4_openai.py

# 轉換為 multi_turn_eng 格式（現在會包含 response 欄位）
python -m pipeline.tools.convert_to_multi_turn_eng

# Merge 全域工具（保留 response 欄位）
python -m pipeline.tools.merge_global_tools \
  --input pipeline/data/<run_id>/multi_turn_eng.jsonl \
  --output pipeline/data/<run_id>/multi_turn_eng_merged.jsonl \
  --include-pseudo \
  --token-budget 100000
```

## 相容性說明

- 所有修改都向後相容
- `use_dict_type` 參數預設為 True，可設為 False 恢復舊格式
- response 欄位會自動生成，即使函數沒有 return type annotation 也會有預設值
- merge 過程會確保所有工具都有 response 欄位

## 注意事項

1. **Response Schema 生成**：
   - 優先從函數的 return type annotation 生成
   - 如果有 `:return:` docstring，會加入描述
   - 如果沒有 return type，會生成空的 dict schema

2. **Type 映射**：
   - `Dict` -> `{"type": "dict"}`
   - `List` -> `{"type": "array", "items": ...}`
   - 其他基本類型維持不變

3. **Merge 保留**：
   - response 欄位在 merge 過程中會被保留
   - pseudo 標記會被移除，但 response 不會

## 參考文件

- 原始格式範例：`/home/at0842/aaronwu901225master.ai13/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/multi_turn_func_doc/trading_bot.json`
- 修改的主要文件：
  - `pipeline/tools/convert_to_multi_turn_eng.py`
  - `pipeline/tools/merge_global_tools.py`
