#!/usr/bin/env bash
#SBATCH -J pythonic-func-call
#SBATCH -p defq
#SBATCH --gres=gpu:0
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



export API_DAILY_LIMIT_TOKENS=2500000
export API_ROTATE_MARGIN=25000
export API_ROTATE_VERBOSE=1 

if [ ! -f run_id ]; then
  echo "run_id not found, running Stage 1 (OpenAI)..."
  python run_s1_openai.py
fi

RUN_ID=$(cat run_id)

# Ensure scenarios.json exists for this run_id; if missing, rerun Stage 1
if [ ! -f "pipeline/data/$RUN_ID/scenarios.json" ]; then
  echo "scenarios.json not found for run_id=$RUN_ID, running Stage 1 (OpenAI)..."
  python run_s1_openai.py
  RUN_ID=$(cat run_id)
fi

if [ ! -f "pipeline/data/$RUN_ID/functions.json" ]; then
  echo "functions.json not found for run_id=$RUN_ID, running Stage 2 (OpenAI)..."
  python run_s2_openai.py
fi

if [ ! -f "pipeline/data/$RUN_ID/multi_turn_queries.json" ]; then
  echo "multi_turn_queries.json not found for run_id=$RUN_ID, running Stage 3 (OpenAI)..."
  export ONLY_MULTI_TURN=1
  python run_s3_openai.py
fi

if [ ! -f "pipeline/data/$RUN_ID/pseudo_functions.json" ]; then
  echo "pseudo_functions.json not found for run_id=$RUN_ID, running Stage 4 (OpenAI pseudo functions)..."
  export PSEUDO_STYLE=related
  export S4_MAX_RETRIES=3
  export S4_TOPUP_EXTRA=2
  export PSEUDO_RELAX_IF_EMPTY=1
  export S4_PSEUDO_PER_SAMPLE=10
  export PSEUDO_DEBUG=1
  python run_s4_openai.py
fi

python pipeline/tools/convert_to_multi_turn_eng.py
python pipeline/tools/validate_multi_turn_eng.py pipeline/data/$RUN_ID/multi_turn_eng.jsonl

echo "All done. Outputs in pipeline/data/$RUN_ID/"

python 