# BFCL Multi-turn miss_function 邏輯修正

## 日期
2025-12-11

## 問題描述

原始的 `add_tool_responses.py` 在處理 `miss_function` 時有邏輯錯誤:

### 錯誤邏輯 ❌
- 在每個 turn **移除** `missed_function` 中指定的函數
- 導致這些函數永久消失

### 正確邏輯 ✅
- 這些函數在資料載入時就被**永久移除**
- 但在特定 turn (holdout turn) 會被**加回來**
- Holdout turn 的 question 是空的 `[]`

## BFCL 的實際流程

### 1. 資料預處理 (utils.py line 822-832)

```python
if "missed_function" in entry:
    for turn_index, missed_func_names in entry["missed_function"].items():
        entry["missed_function"][turn_index] = []
        for missed_func_name in missed_func_names:
            for i, func_doc in enumerate(entry["function"]):
                if func_doc["name"] == missed_func_name:
                    # 將函數 schema 儲存到 missed_function
                    entry["missed_function"][turn_index].append(func_doc)
                    # 從 function 列表中移除
                    entry["function"].pop(i)
                    break
```

**結果**:
- `entry["function"]`: 移除指定函數後的列表
- `entry["missed_function"]["3"]`: 從字串列表變成函數 schema 列表

### 2. 推理時 (base_handler.py line 173-187)

```python
holdout_function: dict[int, list] = test_entry.get("missed_function", {})

for turn_idx, current_turn_message in enumerate(all_multi_turn_messages):
    if str(turn_idx) in holdout_function:
        # 將 holdout 的函數加回來
        test_entry["function"].extend(holdout_function[str(turn_idx)])
        # 重新編譯 tools
        inference_data = self._compile_tools(inference_data, test_entry)
        # Holdout turn 沒有 user message,注入預設提示
        assert len(current_turn_message) == 0
        current_turn_message = [
            {
                "role": "user",
                "content": DEFAULT_USER_PROMPT_FOR_ADDITIONAL_FUNCTION_FC,
            }
        ]
```

## 修正內容

### 修正 1: 使用官方映射表

**問題**: 手動轉換 class name 到檔案名不準確
- `TwitterAPI` → `twitter_api.json` ❌
- 實際應該是 → `posting_api.json` ✅

**修正**:
```python
from bfcl_eval.constants.executable_backend_config import MULTI_TURN_FUNC_DOC_FILE_MAPPING

func_doc_file = MULTI_TURN_FUNC_DOC_FILE_MAPPING.get(class_name)
```

### 修正 2: 正確實現 miss_function 邏輯

**錯誤 1** - 在每個 turn 移除函數:
```python
for turn_idx, (question_turn, gt_turn) in enumerate(zip(questions, ground_truths)):
    turn_functions = functions.copy()
    
    # ❌ 錯誤: 在每個 turn 移除函數
    if str(turn_idx) in missed_function:
        missed_func_names = missed_function[str(turn_idx)]
        turn_functions = [f for f in turn_functions if f['name'] not in missed_func_names]
```

**錯誤 2** - 將新函數加到 system message:
```python
# ❌ 錯誤: 更新 system message
if turn_str in holdout_functions:
    active_functions.extend(holdout_functions[turn_str])
    # 更新 system message
    all_messages[0] = {"role": "system", "content": ...}
```

**正確做法**:
```python
# ✅ 在開始前就移除所有 missed functions
holdout_functions: Dict[str, List[Dict]] = {}
current_functions = functions.copy()

if missed_function:
    for turn_str, func_names in missed_function.items():
        holdout_functions[turn_str] = []
        for func_name in func_names:
            for i, func in enumerate(current_functions):
                if func['name'] == func_name:
                    holdout_functions[turn_str].append(func)
                    current_functions.pop(i)
                    break

# System message 只在 Turn 0 設定一次,之後不變
for turn_idx, (question_turn, gt_turn) in enumerate(zip(questions, ground_truths)):
    turn_str = str(turn_idx)
    
    if turn_idx == 0:
        # 設定 system message (使用移除後的函數列表)
        system_content = ... + current_functions
        all_messages.append({"role": "system", "content": system_content})
    
    # ✅ 正確: 在 holdout turn 的 USER MESSAGE 中加入新函數
    if turn_str in holdout_functions:
        active_functions.extend(holdout_functions[turn_str])
        
        # 在 user message 中包含新函數 schema
        holdout_message = str(holdout_functions[turn_str])
        holdout_message += "\nI have updated some more functions you can choose from. What about now?"
        
        all_messages.append({"role": "user", "content": holdout_message})
```

## 驗證結果

### 測試案例: multi_turn_miss_func_0

**missed_function**: `{"3": ["sort"]}`

**期望行為**:
- Turn 0-2: 31 個函數 (sort 被移除)
- Turn 3-4: 32 個函數 (sort 被加回來)
- Turn 3 的 ground truth: `['sort']` (測試模型是否能用新加入的函數)

**實際結果** ✅:
```
Turn 0: 31 functions, Has 'sort': False
Turn 1: 31 functions, Has 'sort': False
Turn 2: 31 functions, Has 'sort': False
Turn 3: 32 functions, Has 'sort': True  ← sort 被加回來
Turn 4: 32 functions, Has 'sort': True
```

## 訓練資料結構

每個 turn 的資料:
```json
{
  "id": "multi_turn_miss_func_0_turn_3",
  "turn_index": 3,
  "total_turns": 5,
  "messages": [
    {"role": "system", "content": "... 32 functions ..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "content": "..."},
    ...
  ],
  "ground_truth": [{"name": "sort", "arguments": {...}}],
  "tool_responses": ["execution result"]
}
```

## 文件

- **修正後的腳本**: `add_tool_responses_v2.py`
- **輸出**: `bfcl_multiturn_xlam_with_responses.jsonl`
- **總 turns**: 3380 (745 base + 745 long_context + 945 miss_func + 945 miss_param)

## 關鍵發現

1. **miss_function 是 holdout mechanism**: 測試模型是否能使用新加入的函數
2. **函數在資料載入時移除**: 不是在推理時決定
3. **Holdout turn 沒有 user message**: question 欄位是空的 `[]`
4. **需要使用官方映射表**: `MULTI_TURN_FUNC_DOC_FILE_MAPPING`

## 相關代碼位置

- BFCL 預處理邏輯: `bfcl_eval/utils.py` line 822-832
- BFCL 推理邏輯: `bfcl_eval/model_handler/base_handler.py` line 108, 173-187
- 官方映射表: `bfcl_eval/constants/executable_backend_config.py`
