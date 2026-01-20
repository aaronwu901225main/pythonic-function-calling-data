# Miss Function / Miss Parameter 資料生成指南

本文件說明如何使用 pythonic 專案生成「函數缺失」(miss_function) 和「參數缺失」(miss_param) 類型的多輪對話資料。

## 快速開始

### 生成函數缺失資料
```bash
GEN_MODE=miss_function MISS_TURNS=1-2 bash pythonic.sh
```

### 生成參數缺失資料
```bash
GEN_MODE=miss_param MISS_TURNS=1 bash pythonic.sh
```

### 生成所有類型資料（包含 base、miss_function、miss_param）
```bash
GEN_MODE=all MISS_TURNS=1-2 bash pythonic.sh
```

## 環境變數說明

### GEN_MODE
控制生成的題目類型：
- `base`（預設）: 一般多輪對話
- `miss_function` 或 `miss_func`: 函數缺失情境
- `miss_param` 或 `miss_parameter`: 參數缺失情境
- `all`: 生成所有類型

### MISS_TURNS
控制每題中缺失情境的 turn 數量：
- `1`: 每題 1 個缺失 turn
- `1-2`: 每題 1~2 個缺失 turn（隨機選取）
- `2`: 每題固定 2 個缺失 turn

### LANG_CODE
控制生成資料的語言：
- `en`（預設）: 英文版
- `zh_tw`: 繁體中文版

## 輸出檔案

生成的資料位於 `pipeline/data/{RUN_ID}/` 目錄下：

| GEN_MODE | 輸出檔案 |
|----------|----------|
| base | `multi_turn_{lang}.jsonl`, `multi_turn_{lang}_function_mix.jsonl` |
| miss_function | `multi_turn_miss_func_{lang}.jsonl` |
| miss_param | `multi_turn_miss_param_{lang}.jsonl` |
| all | 以上所有檔案 |

## 資料格式說明

### miss_function 格式

```json
{
  "id": "run_xxx_miss_func_000001",
  "sample_index": 1,
  "tools": [...],           // 初始工具列表（不含缺失函數）
  "missing_function_tool": {...},  // 缺失的函數定義
  "all_tools": [...],       // 完整工具列表（包含缺失函數）
  "messages": [...],        // 對話訊息
  "dataset": "miss_function",
  "total_turns": 6,
  "miss_turn_indices": [2, 3],  // 哪些 turn 是缺失情境
  "scenario_type": "miss_function"
}
```

**對話流程範例：**
1. User: "請幫我排序這個檔案"
2. Assistant: "抱歉，我目前沒有排序功能。您能提供 sort 函數的定義嗎？"
3. User: [提供 sort 函數定義]
4. Assistant: [使用 sort 函數並回傳結果]

### miss_param 格式

```json
{
  "id": "run_xxx_miss_param_000001",
  "sample_index": 1,
  "tools": [...],           // 工具列表
  "messages": [...],        // 對話訊息
  "dataset": "miss_param",
  "total_turns": 5,
  "miss_turn_indices": [1, 2],  // 哪些 turn 是缺失情境
  "missing_params": ["filename", "destination"],  // 缺失的參數
  "target_function_name": "move_file",
  "scenario_type": "miss_param"
}
```

**對話流程範例：**
1. User: "請幫我移動文件到資料夾"（缺少 filename 和 destination）
2. Assistant: "請問您要移動哪個文件？目標資料夾是什麼？"
3. User: "report.pdf，移到 backup 資料夾"
4. Assistant: [使用完整參數調用 move_file 函數]

## 驗證資料

使用驗證工具檢查生成的資料格式：

```bash
python pipeline/tools/validate_miss_scenarios.py pipeline/data/$RUN_ID/multi_turn_miss_func_zh_tw.jsonl
python pipeline/tools/validate_miss_scenarios.py pipeline/data/$RUN_ID/multi_turn_miss_param_zh_tw.jsonl
```

## Pipeline 流程

```
Stage 1: 生成情境 (scenarios.json)
    ↓
Stage 2: 生成函數定義 (functions.json)
    ↓
Stage 3: 生成多輪對話 (multi_turn_queries.json)
    ↓
Stage 5: 生成缺失情境對話 [只在 GEN_MODE != base 時執行]
    - miss_function_queries.json
    - miss_param_queries.json
    ↓
轉換為最終格式
    - convert_to_multi_turn_eng.py (base)
    - convert_to_miss_scenarios.py (miss_function, miss_param)
```

## 注意事項

1. **miss_function 的 tool list 處理：**
   - 初始 `tools` 欄位不包含缺失函數
   - `missing_function_tool` 欄位包含缺失函數的完整定義
   - `all_tools` 欄位包含所有函數（用於參考）

2. **miss_param 的參數處理：**
   - 缺失的參數**不能**出現在先前的對話中
   - 這確保了情境的真實性——助手確實沒有這些資訊

3. **turn 數量：**
   - 每個缺失情境通常包含兩個 turn：
     1. 用戶請求 + 助手說無法執行/詢問資訊
     2. 用戶提供資訊 + 助手執行

## 範例使用情境

### 情境 1：只生成繁體中文的 miss_function 資料
```bash
LANG_CODE=zh_tw GEN_MODE=miss_function MISS_TURNS=1 bash pythonic.sh
```

### 情境 2：生成英文的所有資料類型
```bash
LANG_CODE=en GEN_MODE=all MISS_TURNS=1-2 bash pythonic.sh
```

### 情境 3：在現有 run_id 上額外生成 miss 資料
```bash
# 假設已有 run_id 和 functions.json
GEN_MODE=miss_function MISS_TURNS=2 bash pythonic.sh
```
