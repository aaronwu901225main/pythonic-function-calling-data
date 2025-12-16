#!/usr/bin/env bash
set -euo pipefail

JOB1_SCRIPT="bfcl-gen.slurm"
JOB2_SCRIPT="bfcl-eval.slurm"

# 送出第一個，抓 jobid（--parsable 會只吐 jobid）

# 當前面有相依問題時可用下面這行測試
#job1_id=$(sbatch --parsable --dependency=afterok:35581 "$JOB1_SCRIPT")
job1_id=$(sbatch --parsable "$JOB1_SCRIPT")
echo "Submitted job1: $job1_id"

# 第一個成功完成（exit code=0）後才送出第二個
job2_id=$(sbatch --parsable --dependency=afterok:${job1_id} "$JOB2_SCRIPT")
echo "Submitted job2 (afterok job1): $job2_id"
