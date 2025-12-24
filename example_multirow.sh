#!/bin/bash

# 多行組合生成 - 快速範例
# 這是一個小規模測試，只生成少量資料以驗證功能

echo "========================================"
echo "多行組合生成 - 快速範例"
echo "========================================"
echo ""
echo "此範例將生成:"
echo "  - 2行組合: 5題"
echo "  - 3行組合: 3題"
echo "  總計: 8題"
echo ""
echo "預計 API 調用次數: ~8 次 (取決於 S1_NUM_SCENARIOS)"
echo "預計耗時: ~1-2分鐘"
echo ""

# 設定為小規模測試
export S1_MULTIROW_CONFIG="2*5,3*3"
export S1_NUM_SCENARIOS="1"
export OPENAI_RATE_SLEEP="1"
export SKIP_S4="1"  # 跳過偽函數生成以加快速度

# Step 3 控制：只生成 multi-turn queries（減少 API 調用）
export S3_ONLY_MULTI="1"  # 只生成多輪對話，跳過 simple/parallel queries

# 檢查 API Key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "錯誤: 請設定 OPENAI_API_KEY 環境變數"
    echo "export OPENAI_API_KEY='sk-...'"
    exit 1
fi

printf "是否繼續? (y/n) "
read -r REPLY
echo ""
if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
    echo "已取消"
    exit 1
fi

# Step 1: 生成場景
echo ""
echo "Step 1: 生成場景 (多行組合)..."
python run_s1_openai_multirow.py

# 讀取 run_id
RUN_ID=$(cat run_id)
echo ""
echo "Run ID: $RUN_ID"

# 查看統計
echo ""
echo "生成統計:"
cat "pipeline/data/${RUN_ID}/scenarios_stats.json"
echo ""

# 詢問是否繼續後續步驟
printf "Step 1 完成。是否繼續後續步驟 (Step 2-4)? (y/n) "
read -r REPLY
echo ""
if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
    echo "已停止。你可以稍後手動執行後續步驟。"
    exit 0
fi

# Step 2: 生成函數
echo ""
echo "Step 2: 生成函數..."
python run_s2_openai.py

# Step 3: 生成查詢
echo ""
echo "Step 3: 生成查詢..."
python run_s3_openai.py

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
echo "✓ 快速範例完成!"
echo "========================================"
echo ""
echo "生成的檔案位於: pipeline/data/${RUN_ID}/"
echo ""

# 顯示一些樣本
echo "範例場景 (前2個):"
python -c "
import json
with open('pipeline/data/${RUN_ID}/scenarios.json', 'r') as f:
    data = json.load(f)
    for i in range(min(2, len(data))):
        print(f'\n{i+1}. Domain: {data[i][\"domain\"]}')
        print(f'   Subdomain: {data[i][\"subdomain\"]}')
        print(f'   Scenario: {data[i][\"scenario\"][:150]}...')
        print(f'   Meta: {data[i][\"meta\"][\"rows_per_sample\"]} rows, config {data[i][\"meta\"][\"config_index\"]}')
"

echo ""
echo "如需查看完整結果，請查看:"
echo "  cat pipeline/data/${RUN_ID}/scenarios.json"
echo "  cat pipeline/data/${RUN_ID}/multi_turn_eng_function_mix.jsonl"
