#!/usr/bin/env bash
#SBATCH -J bfcl-gen
#SBATCH -p h200q
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=10G
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
conda activate pythonic-function-calling-data

cd "$SLURM_SUBMIT_DIR"

python pipeline/countoken/countoken.py --input pipeline/data/087190226fd447b5b4595971dc8a8728/multi_turn_eng.jsonl --bin_size 30