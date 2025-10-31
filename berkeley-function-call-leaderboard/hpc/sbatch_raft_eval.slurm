#!/usr/bin/env bash
#SBATCH -J raft-eval
#SBATCH -p defq
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH -o %x-%j.out

# 使用 RAFT 的 openai 相容 API 評估。需在 raft/ 目錄準備 .env：
#   EVAL_OPENAI_API_KEY=...
#   EVAL_OPENAI_BASE_URL=https://api.openai.com/v1  # 或你的相容端點

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

# 參數
QUESTION_FILE=${QUESTION_FILE:-"raft/sample_data/synthetic_10.jsonl"}
ANSWER_FILE=${ANSWER_FILE:-"raft/sample_data/synthetic_10.answers.jsonl"}
MODEL=${MODEL:-"gpt-4o-mini"}
MODE=${MODE:-"openai"}           # openai|azure 等
WORKERS=${WORKERS:-8}
TEMPERATURE=${TEMPERATURE:-0.2}
MAX_TOKENS=${MAX_TOKENS:-256}

python raft/eval.py \
  --dataset-path "$QUESTION_FILE" \
  --answer-file "$ANSWER_FILE" \
  --model "$MODEL" \
  --mode "$MODE" \
  --workers "$WORKERS" \
  --temperature "$TEMPERATURE" \
  --max-tokens "$MAX_TOKENS"
