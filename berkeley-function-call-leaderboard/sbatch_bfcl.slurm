#!/usr/bin/env bash
#SBATCH -J bfcl-gen
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

# 使用短路徑 tmp 以避免 Ray UNIX socket 超長
mkdir -p /tmp/ray || true
export RAY_TMPDIR=/tmp/ray
export TMPDIR=/tmp/ray

# 載入 conda
if command -v module &>/dev/null; then
  module purge || true
  module load anaconda || true
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate BFCL

cd "$SLURM_SUBMIT_DIR"

# bfcl CLI 由 berkeley-function-call-leaderboard 套件提供
bfcl generate  --test-category all  --gpu-memory-utilization 0.9 --num-gpus 1 --backend vllm \
  --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-20-merged-3epoch-accumulate32-toollist-2K-only-new \
  --local-model-path merge_lora_model/Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models-3epoch-accumulate32-toollist-2K-only-new/checkpoint-20_merged

bfcl generate  --test-category all  --gpu-memory-utilization 0.9 --num-gpus 1 --backend vllm \
  --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-80-merged-3epoch-accumulate32-toollist-2K-only-new \
  --local-model-path merge_lora_model/Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models-3epoch-accumulate32-toollist-2K-only-new/checkpoint-80_merged

bfcl generate  --test-category all  --gpu-memory-utilization 0.9 --num-gpus 1 --backend vllm \
  --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-177-merged-3epoch-accumulate32-toollist-2K-only-new \
  --local-model-path merge_lora_model/Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models-3epoch-accumulate32-toollist-2K-only-new/checkpoint-177_merged

export OPENAI_API_KEY=
bfcl evaluate  --test-category all --zhtw-eval gpt-4.1-mini --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-20-merged-3epoch-accumulate32-toollist-2K-only-new,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-80-merged-3epoch-accumulate32-toollist-2K-only-new,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-177-merged-3epoch-accumulate32-toollist-2K-only-new

#bfcl generate  --test-category all  --gpu-memory-utilization 0.9 --num-gpus 1 --backend vllm \
#  --model BitAgent/BitAgent-Bounty-8B
#bfcl evaluate  --test-category all --zhtw-eval original --model BitAgent/BitAgent-Bounty-8B