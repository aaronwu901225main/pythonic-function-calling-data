#!/usr/bin/env bash
#SBATCH -J bfcl-eval
#SBATCH -p defq
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH -o %x-%j.out

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
conda activate gorilla-hpc

cd "$SLURM_SUBMIT_DIR"

## 注意：bfcl 期望路徑為相對於 berkeley-function-call-leaderboard 專案根目錄
RESULT_DIR=${RESULT_DIR:-"result"}
SCORE_DIR=${SCORE_DIR:-"score"}
ZHTW_EVAL=${ZHTW_EVAL:-original} # 可選 original|llm-judge

# BFCL 的 evaluate 會自動找結果並產出分數
bfcl evaluate \
  --result-dir "$RESULT_DIR" \
  --score-dir "$SCORE_DIR" \
  --zhtw-eval "$ZHTW_EVAL"
