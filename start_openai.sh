#!/usr/bin/env sh
# OpenAI-only pipeline (no Dria dependency)
# Requirements:
# - Environment variable OPENAI_API_KEY set to your key
# - Optional: OPENAI_MODEL (default gpt-5-mini)

set -e

python run_s1_openai.py
python run_s2_openai.py
python run_s3_openai.py
