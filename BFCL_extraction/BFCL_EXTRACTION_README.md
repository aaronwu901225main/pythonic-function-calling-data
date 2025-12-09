# BFCL Multi-turn Data Extraction for xLAM

## 概述
此專案將 BFCL (Berkeley Function-Calling Leaderboard) 的 multi-turn 資料提取並轉換成 Salesforce xLAM 系列模型的訓練格式。

## 資料來源
- **測試資料**: `gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/BFCL_v4_multi_turn_base.json`
- **Ground Truth**: `gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/possible_answer/BFCL_v4_multi_turn_base.json`
- **Function Schemas**: `gorilla/berkeley-function-call-leaderboard/bfcl_eval/data/multi_turn_func_doc/*.json`

## 輸出格式

### 檔案
- **輸出檔案**: `bfcl_multiturn_xlam_format.jsonl`
- **格式**: JSONL (每行一個 JSON 物件)
- **大小**: 20.9 MB
- **總數**: 745 conversation turns (來自 200 個測試案例)

### 資料結構
每一行包含以下欄位:

```json
{
  "id": "multi_turn_base_0_turn_0",
  "messages": [
    {
      "role": "system",
      "content": "系統提示 + tool instruction + 所有 function schemas"
    },
    {
      "role": "user", 
      "content": "使用者的第一個問題"
    },
    {
      "role": "assistant",
      "content": "[{\"name\": \"tool_name\", \"arguments\": {...}}]"
    },
    {
      "role": "user",
      "content": "使用者的第二個問題"
    }
    // ... 更多對話歷史
  ],
  "tools": [
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
    // ... 更多 tools
  ],
  "ground_truth": [
    "function_call_1(arg1='value1', arg2='value2')",
    "function_call_2(arg='value')"
  ],
  "initial_config": {...},
  "turn_index": 0,
  "total_turns": 4
}
```

## 關鍵特性

### 1. xLAM Chat Template
- **System Prompt**: "You are a helpful assistant that can use tools. You are developed by Salesforce xLAM team."
- **Tool Instruction**: 指示模型使用 JSON array 格式呼叫 tools
- **Function Schemas**: 完整的 function schemas(包含 `response` 欄位)直接嵌入 system message

### 2. 對話歷史累積
- 每個 turn 包含完整的對話歷史
- Turn 0: system + user_0
- Turn 1: system + user_0 + assistant_0 + user_1
- Turn 2: system + user_0 + assistant_0 + user_1 + assistant_1 + user_2
- ... 以此類推

### 3. Response Field 保留
根據 BFCL 的 `convert_to_tool()` 函數,xLAM 使用 `ModelStyle.OSSMODEL`,會保留完整的 `response` 欄位:
```python
# From bfcl_eval/model_handler/utils.py
if model_style not in [
    ModelStyle.ANTHROPIC, ModelStyle.GOOGLE, 
    ModelStyle.FIREWORK_AI, ...
]:
    # xLAM (OSSMODEL) 走這條路徑,保留 response
    converted_function["response"] = func.get("response", {})
```

### 4. Ground Truth 格式
- **原始格式**: Python function call 字串,例如 `"cd(folder='document')"`
- **訓練格式**: 
  - 在 `messages` 中的 assistant 回應: JSON array format `[{"name": "cd", "arguments": {"folder": "document"}}]`
  - 在 `ground_truth` 欄位: 保留原始 Python 格式供驗證使用

## 資料統計

### Turn 分布
- 1 turns: 3 entries
- 2 turns: 76 entries  
- 3 turns: 144 entries
- 4 turns: 204 entries
- 5 turns: 220 entries
- 6 turns: 84 entries
- 7 turns: 14 entries

**平均每個測試案例**: 3.73 turns

### 涵蓋的 Tool Classes
資料集涵蓋多種工具類別,包括:
- GorillaFileSystem (18 個檔案系統操作工具)
- TwitterAPI
- MessageAPI
- TicketAPI
- TravelAPI
- 等等...

## 使用方式

### 1. 執行提取腳本
```bash
python extract_bfcl_multiturn_for_xlam.py
```

### 2. 載入訓練資料
```python
import json

# 讀取資料
with open('bfcl_multiturn_xlam_format.jsonl', 'r') as f:
    for line in f:
        entry = json.loads(line)
        messages = entry['messages']
        tools = entry['tools']
        ground_truth = entry['ground_truth']
        # ... 進行訓練
```

### 3. 訓練格式範例
每個 entry 可以直接用於訓練:
- `messages`: 對話歷史(含 system prompt, user, assistant)
- `tools`: 可用的工具列表(含 response field)
- `ground_truth`: 當前 turn 的正確答案

## 技術細節

### Function Doc 解析
Function doc 檔案格式為多個 JSON objects 連續排列(非 JSONL 也非 JSON array):
```json
{
  "name": "cat",
  ...
}
{
  "name": "cd",
  ...
}
```

使用 `JSONDecoder.raw_decode()` 逐個解析。

### 駝峰轉底線命名
Class name 轉檔名規則:
- `GorillaFileSystem` → `gorilla_file_system.json`
- `TwitterAPI` → `twitter_api.json`

### Ground Truth 解析
使用正則表達式解析 Python function call:
```python
# 輸入: "cd(folder='document')"
# 輸出: {"name": "cd", "arguments": {"folder": "document"}}
```

## 驗證

所有 745 個 conversation turns 均包含:
- ✅ `id`: 唯一識別碼
- ✅ `messages`: 完整對話歷史
- ✅ `tools`: 完整 function schemas(含 response)
- ✅ `ground_truth`: 正確答案
- ✅ `initial_config`: 初始設定
- ✅ `turn_index`: 當前 turn 索引
- ✅ `total_turns`: 總 turn 數

## 參考資料
- [BFCL GitHub](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)
- [Salesforce xLAM](https://huggingface.co/Salesforce)
- [BFCL Model Handler Utils](gorilla/berkeley-function-call-leaderboard/bfcl_eval/model_handler/utils.py)
- [xLAM Salesforce Llama Handler](gorilla/berkeley-function-call-leaderboard/bfcl_eval/model_handler/local_inference/salesforce_llama.py)
