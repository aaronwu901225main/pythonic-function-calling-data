#!/usr/bin/env sh
# Generate ONLY multi-turn dataset using OpenAI mode.
# Prerequisites: OPENAI_API_KEY set; will run Stage 1/2 if needed.

set -e

if [ ! -f run_id ]; then
  echo "run_id not found, running Stage 1 (OpenAI)..."
  python run_s1_openai.py
fi

RUN_ID=$(cat run_id)

# Ensure scenarios.json exists for this run_id; if missing, rerun Stage 1 to create a fresh run_id
if [ ! -f "pipeline/data/$RUN_ID/scenarios.json" ]; then
  echo "scenarios.json not found for run_id=$RUN_ID, running Stage 1 (OpenAI)..."
  python run_s1_openai.py
  RUN_ID=$(cat run_id)
fi

if [ ! -f "pipeline/data/$RUN_ID/functions.json" ]; then
  echo "functions.json not found for run_id=$RUN_ID, running Stage 2 (OpenAI)..."
  python run_s2_openai.py
fi

export ONLY_MULTI_TURN=1
python run_s3_openai.py
