#!/usr/bin/env bash
#SBATCH -J bfcl-gen
#SBATCH -p defq
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH -o %x-%j.out

# 透過 UC Berkeley hosted OpenFunctions v2 生成（免金鑰，需外網）。
# 若集群無外網或需本地 OSS 模型，請改用 vLLM/sglang（需另安裝 extras），或提供可存取之 API。

set -euo pipefail
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

# 推薦將 tmp 指到家目錄
export TMPDIR="$HOME/tmp"
mkdir -p "$TMPDIR"

# 載入 conda
if command -v module &>/dev/null; then
  module purge || true
  module load anaconda || true
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gorilla-hpc

cd "$SLURM_SUBMIT_DIR"

# 主要參數（可在 sbatch --export 覆蓋）
MODEL_NAME=${MODEL_NAME:-BitAgent/BitAgent-Bounty-8B}
TEST_CATEGORY=${TEST_CATEGORY:-all}

# 注意：bfcl 期望此路徑為相對於 berkeley-function-call-leaderboard 專案根目錄
RESULT_DIR=${RESULT_DIR:-"result"}
ALLOW_OVERWRITE=${ALLOW_OVERWRITE:-false}

# bfcl CLI 由 berkeley-function-call-leaderboard 套件提供
bfcl generate \
  --model "$MODEL_NAME" \
  --test-category "$TEST_CATEGORY" \
  --result-dir "$RESULT_DIR" \
  $( [ "$ALLOW_OVERWRITE" = "true" ] && echo "--allow-overwrite" )
