# Multi-turn English 轉換與驗證使用指南

本文件說明如何：
1. 將 `functions.json` + `multi_turn_queries.json` 轉成 `multi_turn_eng.jsonl`
2. 以 JSON Schema 驗證輸出格式
3. 了解產出資料結構與常見問題排除

---
## 1. 生成 multi_turn_eng.jsonl

讀取 `run_id` 對應目錄下的 `functions.json` 與 `multi_turn_queries.json`，產生 English 版多輪資料。

```bash
uv run python pipeline/tools/convert_to_multi_turn_eng.py
```

執行成功後輸出位於：
```
pipeline/data/<run_id>/multi_turn_eng.jsonl
```

### 指定自訂路徑或 run_id
如果你有多個資料版本，可用同一行指令顯式指定（程式會透過 `run_id` 變數或參數，你可在程式內部調整；若已支援命令列參數請依實作）：

```bash
uv run python pipeline/tools/convert_to_multi_turn_eng.py
```
> 備註：若要支援 `--run_id` 或輸出自訂路徑，請在程式中加入 argparse；目前文件僅示範基本呼叫方式。

---
## 2. 驗證資料格式（JSON Schema）

使用 Schema 驗證每一行是否符合 `tools/messages/label_kind` 結構：

```bash
uv run python pipeline/tools/validate_multi_turn_eng.py pipeline/data/<run_id>/multi_turn_eng.jsonl
```

通過會顯示：
```
Validation PASS: All lines conform to schema.
```

失敗則列出：
```
Line <n>: <錯誤訊息>
```
請依錯誤回溯來源資料或調整 prompt/流程再重新轉換。

---
## 3. 產物結構說明

轉換器會：
- 將 `functions.json` 的 Python 函式簽名轉成 `tools` 物件（含 JSON Schema 參數）。
- 解析多輪 trace 的三件組並輸出為每行 JSON：
  1. `<query>` → `{"role":"user","content":...}`
  2. `<function_call>` → `{"role":"assistant","tool_calls":[{...}]}`
  3. `<tool>` → `{"role":"tool","content":...}`

每條資料都有：
- 唯一 `id`
- `label_kind: "full"`
- 結構對齊你給的 `multi_turn_eng.jsonl` 格式。

---
## 4. 常見問題與排除

### A. 找不到檔案 / Required files not found
可能原因：
- `pipeline/data/<run_id>/functions.json` 不存在
- `pipeline/data/<run_id>/multi_turn_queries.json` 不存在
- 指錯 `run_id`

處理方式：
1. 列出目錄確認：
	```bash
	ls -1 pipeline/data/<run_id>/
	```
2. 確認兩個檔案皆存在後再執行轉換。

### B. 驗證失敗
常見錯誤：
- `assistant` 行既沒有 `content` 也沒有 `tool_calls`
- `tool_calls` 內結構缺欄位（如 `name`, `arguments`）
- 序列化後的 JSON Schema 型別不符（字串 vs 物件）

處理方式：
1. 先查看錯誤行：
	```bash
	sed -n '<n>p' pipeline/data/<run_id>/multi_turn_eng.jsonl
	```
2. 回頭比對原始 trace 或函式定義，修正後重新轉換與驗證。

### C. 重複或缺少 id
確保轉換程式在生成時使用遞增或 UUID，避免多輪合併後衝突。

### D. Tool 參數 Schema 不吻合
檢查 `functions.json` 中參數型別是否為標準 JSON Schema（`type`, `properties`, `required`）。必要時補全。

---
## 5. 建議工作流程
1. 準備或更新 `functions.json`、`multi_turn_queries.json`
2. 執行轉換：
	```bash
	uv run python pipeline/tools/convert_to_multi_turn_eng.py
	```
3. 驗證格式：
	```bash
	uv run python pipeline/tools/validate_multi_turn_eng.py pipeline/data/<run_id>/multi_turn_eng.jsonl
	```
4. 如有錯 → 修正來源資料 → 重跑 2、3
5. 通過後交給下游訓練 / 評估流程

---
## 6. 延伸改進建議 (可選)
- 為 `convert_to_multi_turn_eng.py` 加入 `--run_id`、`--out`、`--schema` 參數。
- 在 `validate_multi_turn_eng.py` 加上 `--fail_fast` 與 `--report report.json`。
- 增加 quick smoke test：檢查每筆是否至少包含一組 user→assistant→tool 三件組。

---
## 7. 範例片段 (示意)
```json
{"id":"abc123","label_kind":"full","messages":[
  {"role":"user","content":"請列出今天天氣"},
  {"role":"assistant","tool_calls":[{"name":"get_weather","arguments":{"city":"Taipei"}}]},
  {"role":"tool","content":"{\"city\":\"Taipei\",\"temp\":23}"}
]}
```

---
## 8. 回饋
若有新錯誤型態或希望擴充欄位，請在 Issue 中附上：
- 出錯行號與 JSON 內容
- 預期結構
- 版本／提交哈希

---
## 9. 摘要速查
| 動作 | 指令 | 輸出/結果 |
|------|------|-----------|
| 轉換 | `uv run python pipeline/tools/convert_to_multi_turn_eng.py` | 生成 `multi_turn_eng.jsonl` |
| 驗證 | `uv run python pipeline/tools/validate_multi_turn_eng.py pipeline/data/<run_id>/multi_turn_eng.jsonl` | PASS 或列出錯誤行 |
| 查看特定行 | `sed -n '<n>p' ...` | 顯示問題行 |
| 列出目錄 | `ls -1 pipeline/data/<run_id>/` | 檔案存在性確認 |

---
## 10. 版次
初版美化：增加章節、表格、範例與排錯指引。

---
## 11. 全域工具合併 (Global Tool Merge)

在多筆樣本中，`tools` 陣列通常僅包含該樣本相關函式。若要將所有樣本的工具函式統一整合為一組全域列表（並打亂順序）後附加在每一行，以模擬更大工具空間或增加干擾度，可使用以下方式。

### 11.1 獨立腳本方式（建議）
 `merge_global_tools.py`

#### 執行範例
包含 pseudo：
```bash
python pipeline/tools/merge_global_tools.py \
  --input pipeline/data/$RUN_ID/multi_turn_eng.jsonl \
  --output pipeline/data/$RUN_ID/multi_turn_eng.global.jsonl \
  --include-pseudo \
  --seed 42
```
不包含 pseudo：
```bash
python pipeline/tools/merge_global_tools.py \
  --input pipeline/data/$RUN_ID/multi_turn_eng.jsonl \
  --output pipeline/data/$RUN_ID/multi_turn_eng.global.no_pseudo.jsonl \
  --seed 42
```
限制最多 300 個工具：
```bash
python pipeline/tools/merge_global_tools.py \
  --input pipeline/data/$RUN_ID/multi_turn_eng.jsonl \
  --output pipeline/data/$RUN_ID/multi_turn_eng.global.top300.jsonl \
  --include-pseudo \
  --max-tools 300 \
  --seed 7
```

### 11.2 參數說明
| 參數 | 說明 |
|------|------|
| `--include-pseudo` | 是否包含標記 `x_pseudo` 的擬似/干擾工具 |
| `--seed` | 設定後打亂順序可重現 |
| `--max-tools` | 控制最終工具數量上限（0 = 不限制） |

### 11.3 使用注意事項
- 全域合併後每行的 `tools` 內容相同；可能使樣本 prompt 長度大幅增加。
- 若訓練策略希望模型只看到「局部子集合」，則不要啟用此合併。
- 建議在實驗前統計：
  ```bash
  wc -l pipeline/data/<run_id>/multi_turn_eng.jsonl
  grep -m1 '"tools"' pipeline/data/<run_id>/multi_turn_eng.jsonl | jq '.tools | length'
  ```
- 可再加「只保留實際被呼叫過的工具 + 少量隨機干擾」的進階模式（目前腳本未內建）。

### 11.4 失敗排查
常見問題：
- JSON 讀取失敗：確認輸入檔是否為正確的 `multi_turn_eng.jsonl`。
- 工具數過大導致後續訓練 OOM：使用 `--max-tools` 截斷或不合併。
- pseudo 工具缺失：確認原始行中 pseudo 工具是否帶有 `"x_pseudo": true` 標記。

### 11.5 快速回滾
若要回到未合併版本，直接使用原始的 `multi_turn_eng.jsonl`，或重新執行轉換流程再產生。

---
## 12. 全域合併速查表
| 動作 | 指令 | 備註 |
|------|------|------|
| 全域合併含 pseudo | `python merge_global_tools.py --input ... --output ... --include-pseudo --seed 42` | 增加工具干擾度 |
| 全域合併不含 pseudo | `python merge_global_tools.py --input ... --output ... --seed 42` | 僅真實工具 |
| 限制工具數量 | `--max-tools N` | 控制 token 成本 |
| 檢查工具總數 | `grep -m1 '"tools"' ... | jq '.tools | length'` | 確認合併後大小 |
