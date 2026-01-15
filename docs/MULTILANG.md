# 多語言資料集生成指南

## 概述

本專案支援生成英文和繁體中文兩種語言的 function-calling 資料集。透過 `LANG_CODE` 環境變數來切換語言版本。

## 語言選項

| LANG_CODE | 語言 | 輸出檔名 |
|-----------|------|---------|
| `en` (預設) | 英文 | `multi_turn_eng.jsonl` |
| `zh_tw` | 繁體中文 | `multi_turn_zh_tw.jsonl` |

## 使用方式

### 方法 1：使用環境變數

```bash
# 生成英文版資料集 (預設)
bash pythonic.sh

# 生成繁體中文版資料集
LANG_CODE=zh_tw bash pythonic.sh
```

### 方法 2：使用專用腳本

```bash
# 生成繁體中文版資料集
bash pythonic_zh_tw.sh
```

### 方法 3：直接執行個別步驟

```bash
# 設定語言環境
export LANG_CODE=zh_tw

# 執行 Stage 1: 生成情境
python run_s1_openai_multirow.py

# 執行 Stage 2: 生成函數簽名
python run_s2_openai.py

# 執行 Stage 3: 生成多輪對話
python run_s3_openai.py

# 轉換格式
python pipeline/tools/convert_to_multi_turn_eng.py
```

## 輸出檔案

根據語言設定，輸出檔案會有不同的命名：

### 英文版 (`LANG_CODE=en`)
- `pipeline/data/{run_id}/multi_turn_eng.jsonl`
- `pipeline/data/{run_id}/multi_turn_eng_function_mix.jsonl`

### 繁體中文版 (`LANG_CODE=zh_tw`)
- `pipeline/data/{run_id}/multi_turn_zh_tw.jsonl`
- `pipeline/data/{run_id}/multi_turn_zh_tw_function_mix.jsonl`

## 繁體中文版特點

繁體中文版的資料集有以下特點：

1. **情境描述**：使用繁體中文撰寫情境
2. **用戶查詢**：所有 user query 使用繁體中文
3. **函數文檔**：docstring 使用繁體中文（函數名稱保持英文）
4. **人名地名**：使用中文人名（如：王小明、李美玲）和中文地名

## Prompt 模板

每個階段都有對應的中文 prompt 模板：

| 階段 | 英文 Prompt | 繁體中文 Prompt |
|------|-------------|-----------------|
| S1 情境 | `pipeline/s1_scenario/prompt.md` | `pipeline/s1_scenario/prompt_zh_tw.md` |
| S2 函數 | `pipeline/s2_functions/prompt.md` | `pipeline/s2_functions/prompt_zh_tw.md` |
| S3 簡單查詢 | `pipeline/s3_queries/simple/prompt.md` | `pipeline/s3_queries/simple/prompt_zh_tw.md` |
| S3 平行查詢 | `pipeline/s3_queries/parallel/prompt.md` | `pipeline/s3_queries/parallel/prompt_zh_tw.md` |
| S3 多輪對話 | `pipeline/s3_queries/multiturn/prompt.md` | `pipeline/s3_queries/multiturn/prompt_zh_tw.md` |

## 同時生成兩種語言

如果需要同時生成英文和繁體中文版本，可以分別執行兩次：

```bash
# 先生成英文版
LANG_CODE=en bash pythonic.sh

# 重新生成繁體中文版（需要先刪除 run_id 或使用不同的 run_id）
rm -f run_id
LANG_CODE=zh_tw bash pythonic.sh
```

或者使用專用的繁體中文腳本（會使用獨立的 `run_id_zh_tw` 檔案）：

```bash
# 生成英文版
bash pythonic.sh

# 生成繁體中文版（獨立的 run_id）
bash pythonic_zh_tw.sh
```

## 注意事項

1. 繁體中文版本會消耗更多的 token（中文字元編碼較長）
2. 確保 OpenAI API 支援生成繁體中文內容
3. 驗證工具 `validate_multi_turn_eng.py` 同時支援兩種語言的檔案
