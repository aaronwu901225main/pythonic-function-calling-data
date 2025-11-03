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
conda activate BFCL

cd "$SLURM_SUBMIT_DIR"

# BFCL 的 evaluate 會自動找結果並產出分數
bfcl evaluate  --test-category all --zhtw-eval gpt-4.1-mini --model BitAgent/BitAgent-Bounty-8B
