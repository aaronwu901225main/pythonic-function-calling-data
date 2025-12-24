#!/bin/bash

# Pythonic Function Calling - 多行組合生成腳本
# 用於避免生成類似的題目，通過隨機組合多個 curriculum 行來增加多樣性

set -e

echo "========================================"
echo "Pythonic 多行組合生成模式"
echo "========================================"
echo ""

# 檢查是否設定了多行配置
if [ -z "$S1_MULTIROW_CONFIG" ]; then
    echo "警告: 未設定 S1_MULTIROW_CONFIG 環境變數"
    echo "將使用單行模式（原始模式）"
    echo ""
    echo "範例設定:"
    echo "  export S1_MULTIROW_CONFIG='2*500,3*250,4*250'"
    echo "  (表示: 抽2行生成500題, 抽3行生成250題, 抽4行生成250題)"
    echo ""
else
    echo "多行配置: $S1_MULTIROW_CONFIG"
    echo ""
fi

# 顯示其他相關設定
echo "其他設定:"
echo "  CURRICULUM_CSV: ${CURRICULUM_CSV:-pipeline/data/curriculum.csv}"
echo "  S1_NUM_SCENARIOS: ${S1_NUM_SCENARIOS:-1}"
echo "  OPENAI_RATE_SLEEP: ${OPENAI_RATE_SLEEP:-0}"
echo ""

# 確認執行
read -p "是否繼續? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 1
fi

# Step 1: 生成場景 (多行模式)
echo ""
echo "Step 1: 生成場景 (多行組合模式)..."
python run_s1_openai_multirow.py

# 讀取 run_id
if [ ! -f "run_id" ]; then
    echo "錯誤: 找不到 run_id 檔案"
    exit 1
fi

RUN_ID=$(cat run_id)
echo ""
echo "Run ID: $RUN_ID"

# Step 2: 生成函數
echo ""
echo "Step 2: 生成函數..."
python run_s2_openai.py

# Step 3: 生成查詢
echo ""
echo "Step 3: 生成查詢..."
python run_s3_openai.py

# Step 4: 生成偽函數 (可選)
if [ "$SKIP_S4" != "1" ]; then
    echo ""
    echo "Step 4: 生成偽函數..."
    python run_s4_openai.py
else
    echo ""
    echo "Step 4: 跳過偽函數生成 (SKIP_S4=1)"
fi

# 轉換格式
echo ""
echo "轉換為 multi_turn_eng 格式..."
python -m pipeline.tools.convert_to_multi_turn_eng

# Merge 全域工具
echo ""
echo "Merge 全域工具..."
python -m pipeline.tools.merge_global_tools \
    --input "pipeline/data/${RUN_ID}/multi_turn_eng.jsonl" \
    --output "pipeline/data/${RUN_ID}/multi_turn_eng_function_mix.jsonl"

echo ""
echo "========================================"
echo "✓ 多行組合生成完成!"
echo "========================================"
echo ""
echo "生成的檔案位於: pipeline/data/${RUN_ID}/"
echo ""
echo "主要輸出檔案:"
echo "  - scenarios.json (場景)"
echo "  - scenarios_stats.json (統計報告)"
echo "  - functions.json (函數)"
echo "  - multi_turn_queries.json (查詢)"
echo "  - multi_turn_eng.jsonl (最終格式)"
echo "  - multi_turn_eng_function_mix.jsonl (含全域工具)"
echo ""

# 顯示統計
if [ -f "pipeline/data/${RUN_ID}/scenarios_stats.json" ]; then
    echo "生成統計:"
    cat "pipeline/data/${RUN_ID}/scenarios_stats.json"
    echo ""
fi
