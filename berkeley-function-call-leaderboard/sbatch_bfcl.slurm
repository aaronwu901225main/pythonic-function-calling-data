#!/usr/bin/env bash
#SBATCH -J bfcl-gen
#SBATCH -p h200q
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32G
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
  --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-168-merged-1epoch-accumulate32-toollist-17K \
  --local-model-path merge_lora_model/Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models-1epoch-accumulate32-toollist-17K/checkpoint-168_merged

bfcl generate  --test-category all  --gpu-memory-utilization 0.9 --num-gpus 1 --backend vllm \
  --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-336-merged-1epoch-accumulate32-toollist-17K \
  --local-model-path merge_lora_model/Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models-1epoch-accumulate32-toollist-17K/checkpoint-336_merged

bfcl generate  --test-category all  --gpu-memory-utilization 0.9 --num-gpus 1 --backend vllm \
  --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-504-merged-1epoch-accumulate32-toollist-17K \
  --local-model-path merge_lora_model/Llama-xLAM-2-8b-fc-r_lora_finetune_merged_models-1epoch-accumulate32-toollist-17K/checkpoint-504_merged

# bfcl evaluate  --test-category all --zhtw-eval gpt-4.1-mini --model Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-168-merged-1epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-336-merged-1epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-504-merged-1epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-168-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-336-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-504-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-672-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-840-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-1008-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-1176-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-1344-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-1512-merged-3epoch-accumulate32-new-multiturn,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-168-merged-1epoch-accumulate32-toollist-17K,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-336-merged-1epoch-accumulate32-toollist-17K,Salesforce/Llama-xLAM-2-8b-fc-r-checkpoint-504-merged-1epoch-accumulate32-toollist-17K \
