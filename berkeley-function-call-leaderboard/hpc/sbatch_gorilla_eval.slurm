#!/usr/bin/env bash
#SBATCH -J gorilla-eval
#SBATCH -p defq
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH -o %x-%j.out

# 以 transformers + 本地 GPU 跑 gorilla/inference/gorilla_eval.py
# 預設輸入/輸出檔請自行確認是否存在。

set -euo pipefail
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export TMPDIR="$HOME/tmp"
mkdir -p "$TMPDIR"

if command -v module &>/dev/null; then
  module purge || true
  module load anaconda || true
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate BFCL

cd "$SLURM_SUBMIT_DIR"

MODEL_ID=${MODEL_ID:-"gorilla-llm/gorilla-openfunctions-v2"}  # 改成你可取用/已下載的 HF 權重
Q_FILE=${Q_FILE:-"gorilla/gorilla/eval/eval-data/questions/huggingface/questions_huggingface_bm25.jsonl"}
A_FILE=${A_FILE:-"gorilla/gorilla/eval/answers/answers_huggingface_bm25.jsonl"}
MAX_LEN=${MAX_LEN:-4096}
MAX_NEW_TOKENS=${MAX_NEW_TOKENS:-512}
BATCH=${BATCH:-1}

python gorilla/inference/gorilla_eval.py \
  --model-path "$MODEL_ID" \
  --question-file "$Q_FILE" \
  --answer-file "$A_FILE" \
  --max-input-tokens "$MAX_LEN" \
  --max-new-tokens "$MAX_NEW_TOKENS" \
  --batch-size "$BATCH"
