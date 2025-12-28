#!/usr/bin/env bash
set -euo pipefail

JOB1_SCRIPT="bfcl-gen.slurm"

job1_id=$(sbatch --parsable "$JOB1_SCRIPT")
echo "Submitted job1: $job1_id"

# 等 job1 結束（不在 squeue 裡表示已結束）
while squeue -j "$job1_id" -h >/dev/null 2>&1 && squeue -j "$job1_id" -h | grep -q .; do
  echo "[wait] job1 ($job1_id) still running/pending..."
  sleep 20
done

# 檢查 job1 最終狀態（COMPLETED 才繼續）
state=$(sacct -j "${job1_id}.batch" --format=State -n | head -n 1 | awk '{print $1}')
echo "[done] job1 state: $state"

if [[ "$state" == "COMPLETED" ]]; then
  sh eval.sh
else
  echo "job1 not completed, skip eval.sh"
  exit 1
fi
