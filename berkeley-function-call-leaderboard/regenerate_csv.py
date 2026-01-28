#!/usr/bin/env python3
"""
重新生成 leaderboard CSV 檔案
"""
from pathlib import Path
from bfcl_eval.eval_checker.eval_runner_helper import (
    generate_leaderboard_csv,
    update_leaderboard_table_with_local_score_file,
)

if __name__ == "__main__":
    score_dir = Path('./score')
    
    print("正在讀取 score 資料夾...")
    leaderboard_table = {}
    update_leaderboard_table_with_local_score_file(leaderboard_table, score_dir)
    
    print("正在生成 CSV 檔案...")
    generate_leaderboard_csv(leaderboard_table, score_dir)
    
    print("CSV 生成完成！")
