# LLM-counsel / compare_counsel.py 使用說明

這個目錄包含一支主要腳本 `compare_counsel.py`，用來「比較兩個中文語義評估 (semantic judge) 輸出的 decision 差異」，並可生成統計、混淆矩陣 (2x2)、CSV 與圖像。

---
## 功能總覽
1. 掃描兩個評分結果資料夾 (A/B)，自動遞迴尋找：`*zhtw_semantic_judge*/*_judge_log.jsonl`。
2. 將同一題 (依選擇的 key 粒度) 的多次 decision 做合併（多數決，平手取最後非 None）。
3. 對齊出現在 A 與 B 的題目集合，分類為：
   - `both_true`：A/B 都為 True
   - `both_false`：A/B 都為 False
   - `a_true_b_false`：A=True, B=False
   - `b_true_a_false`：A=False, B=True
   - `different_null_cases`：任一方為 None（無法再細分）
4. 輸出：
   - 終端統計（數量 + 百分比 + 2x2 矩陣文字）
   - 可選主 CSV (`--output`)
   - 可選：分組統計（by model / category / model+category）
   - 可選：每個模型與整體的 2x2 混淆矩陣 CSV 與 PNG (`--matrix-dir`)
   - 詳細對齊檔：`all_keys_detailed.csv`

---
## 輸入資料格式假設
每個評分主目錄 (例如 `score-gpt-4.1-mini`) 底下結構可任意，只要最終能匹配通配：
```
.../任意路徑/*zhtw_semantic_judge*/<任意>_judge_log.jsonl
```
`*_judge_log.jsonl`：一行一個 JSON 物件，至少具備欄位：
- `id`: 題目 / 測試案例 ID
- `decision`: 可為 `true` / `false` / `null`（對應 Python `True/False/None`）
- `model_name` (建議) ：用於 full 粒度鍵
- `test_category` (建議)：用於 full 粒度鍵

例如一行：
```json
{"id": 123, "decision": true, "model_name": "meta-llama_Llama-3.1-8B-Instruct", "test_category": "FC"}
```

---
## 決策合併策略 (同一 key 多次出現)
1. 過濾掉空行或無 `id` 的行。
2. 收集同一 key (= 依 `--key-mode` 決定) 的所有 `decision` 列表。
3. 若全部為 None → 結果 None。
4. 否則計數 True/False：
   - True 多 → True
   - False 多 → False
   - 平手 → 取「最後一個非 None」的值。

---
## Key 粒度說明 (`--key-mode`)
| 模式 | 組成 | 適用場合 | 風險 |
|------|------|----------|------|
| `full` (預設) | `model_name::test_category::id` | 最精細，不混淆不同模型 / 類別 | 無 |
| `model_id` | `model_name::id` | 想合併不同 category 的同一模型 | 不同類別資料會被視為同題 |
| `id` | `id` | 舊相容 / 特殊分析 | 不同模型/類別同一 id 會混在一起 |

建議：一般使用 `full`，確保不會錯配。

---
## 安裝需求
- Python 3.9+（建議）
- 內建使用標準函式庫即可輸出統計/CSV。
- 產生圖檔 (PNG)：需安裝 `matplotlib` 與 `numpy`。

安裝可選依賴：
```powershell
pip install matplotlib numpy
```

---
## 基本使用範例
在專案根（或確保路徑正確）執行：
```powershell
python berkeley-function-call-leaderboard/LLM-counsel/compare_counsel.py `
  --dir-a score-gpt-4.1-mini `
  --dir-b score-Qwen3-8B `
  --root berkeley-function-call-leaderboard/LLM-counsel `
  --key-mode full
```
輸出會顯示：
- 各分類計數
- 百分比（排除含 None）
- 2x2 矩陣（A=列, B=欄）

---
## 進階：同時產出分組與矩陣圖
```powershell
python berkeley-function-call-leaderboard/LLM-counsel/compare_counsel.py `
  --dir-a score-gpt-4.1-mini `
  --dir-b score-Qwen3-8B `
  --root berkeley-function-call-leaderboard/LLM-counsel `
  --key-mode full `
  --by-model --by-category --by-model-category `
  --matrix-dir berkeley-function-call-leaderboard/LLM-counsel/matrix_output `
  --output comparison_full.csv
```
將產出：
- `comparison_full.csv`
- `matrix_output/` 內：
  - `matrix_<model>.csv` / `matrix_<model>.png`
  - `matrix_overall.csv` / `matrix_overall.png`
  - `all_keys_detailed.csv`

---
## 2x2 矩陣解讀 (非 None 範圍)
|        | B=True | B=False |
|--------|--------|---------|
| A=True | both_true | a_true_b_false |
| A=False| b_true_a_false | both_false |

`overall_agreement = (both_true + both_false) / (non-None 配對總數)`

---
## 主要參數一覽
| 參數 | 預設 | 說明 |
|------|------|------|
| `--dir-a` | score-gpt-4.1-mini | Judge A 評分目錄 |
| `--dir-b` | score-Qwen3-8B | Judge B 評分目錄 |
| `--root` | `.` | 上述兩個目錄所在根路徑 |
| `--output` | (無) | 匯出主比較結果 CSV |
| `--key-mode` | full | 決策對齊鍵粒度 (full/model_id/id) |
| `--by-model` | False | 顯示以 model_name 聚合統計 |
| `--by-category` | False | 顯示以 test_category 聚合統計 |
| `--by-model-category` | False | 顯示 (model, category) 粒度統計 |
| `--matrix-dir` | (無) | 產出 per-model + overall 2x2 圖與 CSV |

---
## 常見問題 (FAQ)
**Q1: 為什麼 shared_ids=0?**  
A: 可能路徑錯 / 沒有符合命名規則的 log / A 與 B 沒有任何相同 key。請檢查 `--root`、`--dir-a`、`--dir-b` 與實際檔名。

**Q2: 為何沒有 PNG 只有 CSV?**  
A: 未安裝 `matplotlib` / `numpy`，或安裝後未重新執行。請先 `pip install matplotlib numpy`。

**Q3: 顯示字體缺字 (Glyph missing) 警告?**  
A: matplotlib 預設字體無中文字，可安裝 Noto Sans CJK 或使用系統字體；程式有嘗試設定 `Microsoft JhengHei`。

**Q4: 為什麼很多 `different_null_cases`?**  
A: 代表至少一側 decision=None。可能 judge 還沒寫入或遇錯誤；可另外調查原始 log。

**Q5: 我想加入 Kappa/MCC/F1?**  
A: 目前未內建，可在後續版本中於矩陣統計位置增加計算（腳本內已有混淆四格計數基礎）。

**Q6: 檔名太長?**  
A: 程式會簡單清理非法字元並截斷到 120 字元內。若仍過長，可自行裁短 model 名。

---
## 效能建議
- 初次執行會掃描所有 JSONL；若資料很多可先篩選或壓縮舊紀錄。
- 若僅關心統計，可省略 `--matrix-dir`。
- `--key-mode full` 避免錯配，除非確定需要合併才改。

---
## 擴充建議（未實作）
- Cohen's Kappa / MCC / Precision / Recall / F1
- 拆分 `different_null_cases` 為 (A=None,B!=None) / (A!=None,B=None)
- 輸出 summary 總表 (`summary_models.csv`)
- 加入題目原文 (需從原始資料源補充)
- 產出 HTML Dashboard

---
## 授權
遵循上層專案 `LICENSE`。

---
## 回饋 / 修改
若需要新增指標或調整輸出格式，可直接編輯 `compare_counsel.py` 或提出 issue / PR。

---
## 簡短快速指令備忘
```powershell
# 基本比較
python berkeley-function-call-leaderboard/LLM-counsel/compare_counsel.py --dir-a score-gpt-4.1-mini --dir-b score-Qwen3-8B --root berkeley-function-call-leaderboard/LLM-counsel

# 全功能 (含矩陣/分組/CSV)
python berkeley-function-call-leaderboard/LLM-counsel/compare_counsel.py --dir-a score-gpt-4.1-mini --dir-b score-Qwen3-8B --root berkeley-function-call-leaderboard/LLM-counsel --key-mode full --by-model --by-category --by-model-category --matrix-dir berkeley-function-call-leaderboard/LLM-counsel/matrix_output --output comparison_full.csv
```

---
若要我幫忙加進階統計或改輸出格式，告訴我你的需求即可。
