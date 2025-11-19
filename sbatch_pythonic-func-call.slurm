#!/usr/bin/env bash
#SBATCH -J pythonic-func-call
#SBATCH -p defq
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=70G
#SBATCH --time=24:00:00
#SBATCH -o %x-%j.out

# 透過 UC Berkeley hosted OpenFunctions v2 生成（免金鑰，需外網）。
# 若集群無外網或需本地 OSS 模型，請改用 vLLM/sglang（需另安裝 extras），或提供可存取之 API。

set -euo pipefail
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

# 載入 conda
if command -v module &>/dev/null; then
  module purge || true
  module load anaconda || true
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate pythonic-function-calling-data

cd "$SLURM_SUBMIT_DIR"

export S4_PSEUDO_PER_SAMPLE=10
python run_s4_openai.py