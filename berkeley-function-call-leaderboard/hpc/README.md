# 在 HPC 上執行本專案（生成 + 評估）

本教學把你附的《HPC 使用問題收集一覽.txt》要點整合，提供一套可直接在 Slurm 環境執行的流程與範例腳本（sbatch）。內容涵蓋：
- Conda 環境準備（含 TMPDIR 防 tmp 爆滿）
- GPU/Queue 選擇與資源旗標
- 生成：Berkeley Function Calling Leaderboard（BFCL）— OpenFunctions v2 的 hosted 評測
- 評估：BFCL 評分、RAFT（OpenAI 介面）與 Gorilla HF 權重本地推論
- 常見問題（libnvidia-ml.so.1、IB/HCOLL 噪訊、PD 卡隊列）

建議先在 trialq 佇列做小型測試，再換 defq 或 h200q。

---

## 0) 佇列與資源基本觀念
- Queue/Partition（擇一）：
  - defq（預設，最長 7 天）
  - h200q（H200，高效能，最長 2 天）
  - trialq（測試用，最長 30 分鐘，CPU ≤ 24 cores）
- GPU 旗標：`#SBATCH --gres=gpu:1`（或 `:2`）
- 記憶體：`#SBATCH --mem=32G`（依需求調整）
- 時間：`#SBATCH --time=HH:MM:SS`
- 快速看目前空餘 GPU：登入 headnode 後用 `hpcs`

---

## 1) 建立與安裝環境

我們提供 `hpc/env-setup.sh` 可一次完成：
- module 載入 anaconda
- 設定 TMPDIR 到 $HOME/tmp（避免共用 /tmp 滿）
- 建立並啟用 conda 環境 `gorilla-hpc`（Python 3.11）
- 以 conda 安裝 PyTorch CUDA 11.8（符合叢集建議）
- 以 pip 安裝必要 Python 套件：
  - 安裝 BFCL 套件（`berkeley-function-call-leaderboard`）
  - transformers（給 `gorilla/inference/gorilla_eval.py` 用）
  - raft 相關零星依賴（coloredlogs、pyyaml、mdc、pytest…）

執行方式（headnode）：
```bash
bash hpc/env-setup.sh
```

注意：
- `raft/requirements.txt` 內含一行以文字形式的「pip install torch==…」指示，不可直接用 `pip -r` 安裝。我們在腳本中改以 conda 安裝 PyTorch + CUDA 11.8。
- 若你想安裝 BFCL 的本地推論（vLLM/sglang）選配，可在環境建立後額外安裝：
  - `pip install 'bfcl_eval[oss_eval_vllm]'` 或 `pip install 'bfcl_eval[oss_eval_sglang]'`
  - 但本專案的 OpenFunctions v2 生成預設走 UC Berkeley hosted 端點（需外網）。

---

## 2) 生成（BFCL OpenFunctions v2）

使用 UC Berkeley hosted Gorilla OpenFunctions v2 端點（免金鑰、需外網）。
- 腳本：`hpc/sbatch_bfcl_generate.slurm`
- 預設參數：
  - 模型：`gorilla-openfunctions-v2`
  - 類別：`all`
  - 溫度：`0.001`
- 產出：相對於 `berkeley-function-call-leaderboard/` 的 `result/` 目錄（CLI 會自動在該專案根下建立），即 `berkeley-function-call-leaderboard/result/...`

送出：
```bash
sbatch hpc/sbatch_bfcl_generate.slurm
```

若集群無外網，請改走「本地 OSS 模型 + vLLM/sglang」模式，並安裝對應選配，或改用你已有的可存取端點。這需要額外配置（可再告訴我你的限制，我幫你補一版）。

---

## 3) 評分（BFCL Evaluate）

- 腳本：`hpc/sbatch_bfcl_evaluate.slurm`
- 預設從 `result/`（相對於 `berkeley-function-call-leaderboard/`）讀取結果，輸出到 `score/`
- zh-TW 語義重判斷（LLM judge）預設關閉（`--zhtw-eval original`），如需開啟請依你可用之 LLM 端點調整。

送出：
```bash
sbatch hpc/sbatch_bfcl_evaluate.slurm
```

---

## 4) RAFT 評估（使用 OpenAI 介面）

RAFT 的 `raft/eval.py` 需要 OpenAI 相容 API（或 Azure/OpenAI Base URL），請準備 `.env`：
- 最簡：
  - `EVAL_OPENAI_API_KEY=...`
  - `EVAL_OPENAI_BASE_URL=https://api.openai.com/v1`（或你的相容端點）

把 `.env` 放在 `raft/` 目錄（`eval.py` 會自動讀）。
- 腳本：`hpc/sbatch_raft_eval.slurm`
- 你需要提供題目檔（JSONL），欄位預設：
  - `instruction`（輸入）
  - `answer`（輸出欄位名稱可用 `--output-answer-key` 改）

送出：
```bash
sbatch hpc/sbatch_raft_eval.slurm
```

---

## 5) Gorilla HF 權重本地推論（gorilla_eval.py）

- 腳本：`hpc/sbatch_gorilla_eval.slurm`
- 請把 `MODEL_ID` 換成可取用的 HF 模型（需授權/外網下載或先行下載到本機路徑）
- 題目範例可用：`gorilla/gorilla/eval/eval-data/questions/huggingface/questions_huggingface_bm25.jsonl`

送出：
```bash
sbatch hpc/sbatch_gorilla_eval.slurm
```

若 compute node 無外網，請先在可上網環境把權重同步到你的家目錄或共享磁碟，腳本裡把 `--model-path` 指到本地資料夾即可。

---

## 6) 常見問題與排錯

- TMP 爆滿導致 pip/conda 失敗：
  - 依附檔建議：將 TMPDIR 指到 `$HOME/tmp`（已寫入 env-setup.sh）
- libnvidia-ml.so.1 找不到：
  - 這是 NVIDIA 驅動/SDK 動態庫，headnode 沒 GPU 不會有；在 GPU compute node 上即可解決
  - 若你在 headnode 運行二進位會看到 not found，是正常；Python/PyTorch 工作在 GPU node 跑即可
- Infiniband/HCOLL 警告：
  - 本專案多為 Python 程序，不用 MPI；若看到 hcoll 噪訊，可加入 `export OMPI_MCA_coll=^hcoll` 抑制
- Slurm 任務卡 PD：
  - 核對資源是否超限（GPU/CPU/記憶體/時限），參考 Reason Code；必要時調整 `#SBATCH --mem`、`--time`、`--gres`、queue

- Windows 端行尾符（CRLF）導致 Linux 節點無法執行腳本：
  - 若你在 Windows 編輯腳本，請確保提交到 HPC 前轉為 LF（在 VS Code 右下角切換行尾；或用 `dos2unix` 轉換）。

---

## 7) 你可能想調的參數
- Queue：在各 sbatch 頭部把 `#SBATCH -p defq` 改為 `h200q` 或 `trialq`
- GPU 數：`#SBATCH --gres=gpu:1` 改為你需要的數量
- 記憶體/時間：`--mem`、`--time`
- BFCL 生成的 `--test-category`/`--model`/`--temperature` 等
- RAFT 的 `--model`、`--mode`、`--workers` 等

---

## 8) 檔案一覽
- `hpc/env-setup.sh`：建立 conda 環境與安裝依賴
- `hpc/sbatch_bfcl_generate.slurm`：BFCL 生成（OpenFunctions v2，hosted）
- `hpc/sbatch_bfcl_evaluate.slurm`：BFCL 評分
- `hpc/sbatch_raft_eval.slurm`：RAFT 評估（需 `.env` 與題目 JSONL）
- `hpc/sbatch_gorilla_eval.slurm`：Gorilla HF 權重本地推論

若你需要 enroot/SquashFS 容器流程，我可以再幫你補一版（你已附的步驟可直接套用，注意 image 需有 /bin/sh）。
