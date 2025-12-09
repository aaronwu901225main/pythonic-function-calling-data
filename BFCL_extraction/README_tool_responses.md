# BFCL Multi-turn Training Data with Tool Responses

## 概述

這個資料集從 BFCL (Berkeley Function Calling Leaderboard) multi-turn 測試資料中提取,並加入了**實際 tool execution responses**,適合用於訓練 function calling 模型。

## 資料來源

- **BFCL v4 Multi-turn 資料集**:
  - `BFCL_v4_multi_turn_base` (745 turns)
  - `BFCL_v4_multi_turn_long_context` (745 turns)
  - `BFCL_v4_multi_turn_miss_func` (945 turns)
  - `BFCL_v4_multi_turn_miss_param` (945 turns)
- **總計**: 3380 conversation turns

## 輸出檔案

```
bfcl_multiturn_xlam_with_responses.jsonl
```

每一行是一個 JSON object,代表一個對話 turn。

## 資料格式

每個 turn 包含以下欄位:

```json
{
  "id": "multi_turn_base_0_turn_0",
  "dataset": "BFCL_v4_multi_turn_base",
  "turn_index": 0,
  "total_turns": 4,
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    // (後續 turns 會包含歷史 assistant 和 tool messages)
  ],
  "ground_truth": [
    {"name": "function_name", "arguments": {...}},
    ...
  ],
  "tool_responses": [
    "execution result 1",
    "execution result 2",
    ...
  ]
}
```

### 欄位說明

1. **`messages`**: 對話歷史(輸入)
   - 包含從開始到當前 turn 的所有訊息
   - Turn 0: 只有 system + user
   - Turn 1+: system + (歷史 user/assistant/tool) + 當前 user

2. **`ground_truth`**: Ground truth tool calls(期望輸出)
   - xLAM format: JSON array of tool calls
   - 格式: `[{"name": "...", "arguments": {...}}]`

3. **`tool_responses`**: 實際執行結果
   - 對應 ground_truth 的執行結果
   - 使用 BFCL 的 `execute_multi_turn_func_call()` 執行
   - 保持多輪對話的狀態連續性

## 特殊功能

### 1. Long Context (long_context)

在 `BFCL_v4_multi_turn_long_context` 資料集中:

- **Function schemas**: 在 description 中標註可能有大量資料
- **Tool responses**: 包含實際的擴充資料
  - `get_symbol_by_name`: 包含 WATCH_LIST_EXTENSION (1000+ symbols)
  - `get_transaction_history`: 包含 TRANSACTION_HISTORY_EXTENSION (1000+ transactions)
- **範例**: 回應長度可達 30,000+ 字元

### 2. Missing Functions (miss_func)

在 `BFCL_v4_multi_turn_miss_func` 資料集中:

- **特定 turns 移除特定函數**
- 函數從 system message 的 tool schemas 中永久移除
- Ground truth 仍然包含對這些函數的呼叫(測試模型的錯誤處理)
- Tool responses 會顯示執行錯誤(因為函數不可用)

### 3. Missing Parameters (miss_param)

在 `BFCL_v4_multi_turn_miss_param` 資料集中:

- 這是**評估時特性**,資料本身沒有修改
- Ground truth 會缺少必要參數
- Tool responses 會顯示執行錯誤(參數缺失)

## 使用方式

### 訓練

```python
import json

with open('bfcl_multiturn_xlam_with_responses.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        
        # 輸入: data['messages']
        # 期望輸出: data['ground_truth']
        # 驗證: 比對模型生成的 tool calls 執行結果與 data['tool_responses']
```

### 對話流程範例

**Turn 0**:
```
USER: Move 'final_report.pdf' to 'temp' directory

→ Model should output:
[
  {"name": "cd", "arguments": {"folder": "document"}},
  {"name": "mkdir", "arguments": {"dir_name": "temp"}},
  {"name": "mv", "arguments": {"source": "final_report.pdf", "destination": "temp"}}
]

→ Tool execution results:
[
  '{"current_working_directory": "document"}',
  'None',
  '{"result": "\'final_report.pdf\' moved to \'temp/final_report.pdf\'"}'
]
```

**Turn 1** (包含上一輪的歷史):
```
SYSTEM: ...
USER: Move 'final_report.pdf' to 'temp' directory
ASSISTANT: [{"name": "cd", ...}, {"name": "mkdir", ...}, {"name": "mv", ...}]
TOOL (cd): {"current_working_directory": "document"}
TOOL (mkdir): None
TOOL (mv): {"result": "..."}
USER: Now list the contents of temp directory

→ Model should output:
[{"name": "ls", "arguments": {"path": "temp"}}]
```

## 生成腳本

```bash
cd /home/at0842/aaronwu901225master.ai13/pythonic-function-calling-data/BFCL_extraction
python add_tool_responses.py
```

## 驗證

```bash
python verify_tool_responses.py
```

驗證項目:
- ✓ 所有項目都包含 tool_responses
- ✓ Long context 回應包含擴充資料
- ✓ Miss function 效果正確呈現
- ✓ Messages 包含完整對話流程

## 統計資訊

| Dataset | Turns | w/ Tool Responses | Long Responses (>10KB) |
|---------|-------|-------------------|------------------------|
| base | 745 | 742 | 0 |
| long_context | 745 | 742 | 63 |
| miss_func | 945 | 742 | 0 |
| miss_param | 945 | 742 | 0 |
| **TOTAL** | **3380** | **2968** | **63** |

註: 有些 turns 沒有 ground truth calls,所以沒有 tool responses

## 技術細節

### Tool Execution

- 使用 BFCL 的 `execute_multi_turn_func_call()` 函數
- 動態載入相關類別 (e.g., `TradingBot`, `GorillaFileSystem`)
- 保持多輪對話的狀態 (透過 `accumulated_instances`)
- Long context flag 會影響回應內容

### 狀態管理

多輪對話中,某些操作會改變狀態:
- `cd`: 改變當前目錄
- `mkdir`: 創建資料夾
- `fund_account`: 更新帳戶餘額
- 等等

`accumulated_instances` 確保這些狀態在多個 turns 間保持一致。

## 與原始 BFCL 的差異

1. **格式**: BFCL 原始格式 → xLAM chat template
2. **Ground truth**: Function call strings → JSON array
3. **新增**: `tool_responses` 欄位(實際執行結果)
4. **新增**: 完整的對話歷史(包含 tool role messages)

## 相關檔案

- `add_tool_responses.py`: 生成腳本
- `verify_tool_responses.py`: 驗證腳本
- `execute_tools_helper.py`: Tool execution 輔助模組(已棄用,直接使用 BFCL 函數)
- `extract_bfcl_multiturn_for_xlam.py.backup2`: 之前沒有 tool responses 的版本
