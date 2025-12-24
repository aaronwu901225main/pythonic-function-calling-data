#!/usr/bin/env python3
"""
比較分析工具：多行模式 vs 單行模式

比較兩種模式生成的資料在多樣性上的差異
"""

import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict


def analyze_scenarios(scenarios_file: Path) -> Dict:
    """分析場景檔案"""
    with open(scenarios_file, 'r', encoding='utf-8') as f:
        scenarios = json.load(f)
    
    # 基本統計
    total = len(scenarios)
    
    # 分析 domain 分佈
    domain_counter = Counter()
    subdomain_counter = Counter()
    domain_combinations = Counter()
    
    for sce in scenarios:
        domain = sce.get('domain', '')
        subdomain = sce.get('subdomain', '')
        
        # 單個 domain
        for d in domain.split(','):
            d = d.strip()
            if d:
                domain_counter[d] += 1
        
        # subdomain
        subdomain_counter[subdomain] += 1
        
        # domain 組合 (多行模式特有)
        if ',' in domain:
            domain_combinations[domain] += 1
    
    # 檢查是否為多行模式
    is_multirow = any('meta' in sce for sce in scenarios)
    
    multirow_stats = None
    if is_multirow:
        multirow_stats = {
            'config_distribution': Counter(),
            'rows_per_sample_distribution': Counter(),
        }
        
        for sce in scenarios:
            if 'meta' in sce:
                config_idx = sce['meta'].get('config_index', -1)
                rows_count = sce['meta'].get('rows_per_sample', 1)
                
                multirow_stats['config_distribution'][config_idx] += 1
                multirow_stats['rows_per_sample_distribution'][rows_count] += 1
    
    return {
        'total_scenarios': total,
        'unique_domains': len(domain_counter),
        'unique_subdomains': len(subdomain_counter),
        'unique_domain_combinations': len(domain_combinations),
        'is_multirow': is_multirow,
        'domain_distribution': dict(domain_counter.most_common(10)),
        'subdomain_distribution': dict(subdomain_counter.most_common(10)),
        'domain_combinations': dict(domain_combinations.most_common(10)),
        'multirow_stats': multirow_stats,
    }


def compare_diversity(single_row_stats: Dict, multi_row_stats: Dict):
    """比較兩種模式的多樣性"""
    
    print("\n" + "=" * 80)
    print("多樣性比較分析")
    print("=" * 80)
    
    # 基本統計比較
    print("\n基本統計:")
    print(f"{'':20} {'單行模式':>20} {'多行模式':>20} {'改進':>15}")
    print("-" * 80)
    
    metrics = [
        ('總場景數', 'total_scenarios'),
        ('唯一 Domain 數', 'unique_domains'),
        ('唯一 Subdomain 數', 'unique_subdomains'),
        ('Domain 組合數', 'unique_domain_combinations'),
    ]
    
    for label, key in metrics:
        single = single_row_stats.get(key, 0)
        multi = multi_row_stats.get(key, 0)
        
        if single > 0:
            improvement = (multi - single) / single * 100
            improvement_str = f"+{improvement:.1f}%"
        else:
            improvement_str = "N/A"
        
        print(f"{label:20} {single:>20} {multi:>20} {improvement_str:>15}")
    
    # Domain 分佈比較
    print("\n" + "=" * 80)
    print("Domain 分佈比較 (前5名)")
    print("=" * 80)
    
    print("\n單行模式:")
    for domain, count in list(single_row_stats['domain_distribution'].items())[:5]:
        pct = count / single_row_stats['total_scenarios'] * 100
        print(f"  {domain:30} {count:>5} ({pct:>5.1f}%)")
    
    print("\n多行模式:")
    for domain, count in list(multi_row_stats['domain_distribution'].items())[:5]:
        pct = count / multi_row_stats['total_scenarios'] * 100
        print(f"  {domain:30} {count:>5} ({pct:>5.1f}%)")
    
    # 多行模式特有統計
    if multi_row_stats['multirow_stats']:
        print("\n" + "=" * 80)
        print("多行模式特有統計")
        print("=" * 80)
        
        rows_dist = multi_row_stats['multirow_stats']['rows_per_sample_distribution']
        print("\n每題抽取行數分佈:")
        for rows_count in sorted(rows_dist.keys()):
            count = rows_dist[rows_count]
            pct = count / multi_row_stats['total_scenarios'] * 100
            print(f"  {rows_count} 行: {count:>5} 題 ({pct:>5.1f}%)")
        
        print("\nDomain 組合範例 (前5個):")
        for combo, count in list(multi_row_stats['domain_combinations'].items())[:5]:
            print(f"  {combo}")
            print(f"    出現次數: {count}")
    
    # 多樣性分數
    print("\n" + "=" * 80)
    print("多樣性分數")
    print("=" * 80)
    
    def calculate_diversity_score(stats):
        total = stats['total_scenarios']
        if total == 0:
            return 0
        
        # 計算多樣性分數 (0-100)
        domain_diversity = min(stats['unique_domains'] / total * 10, 1.0)
        subdomain_diversity = min(stats['unique_subdomains'] / total, 1.0)
        combination_diversity = min(stats['unique_domain_combinations'] / total, 1.0)
        
        score = (
            domain_diversity * 30 +
            subdomain_diversity * 40 +
            combination_diversity * 30
        ) * 100
        
        return score
    
    single_score = calculate_diversity_score(single_row_stats)
    multi_score = calculate_diversity_score(multi_row_stats)
    
    print(f"\n單行模式多樣性分數: {single_score:.1f}/100")
    print(f"多行模式多樣性分數: {multi_score:.1f}/100")
    
    if multi_score > single_score:
        improvement = multi_score - single_score
        print(f"\n✓ 多行模式多樣性提升: +{improvement:.1f} 分")
    else:
        print(f"\n⚠ 多行模式多樣性未改善")


def main():
    parser = argparse.ArgumentParser(description='比較單行模式和多行模式的多樣性')
    parser.add_argument('--single', type=str, required=True, help='單行模式的 scenarios.json 路徑')
    parser.add_argument('--multi', type=str, required=True, help='多行模式的 scenarios.json 路徑')
    
    args = parser.parse_args()
    
    single_path = Path(args.single)
    multi_path = Path(args.multi)
    
    if not single_path.exists():
        print(f"錯誤: 找不到 {single_path}")
        return
    
    if not multi_path.exists():
        print(f"錯誤: 找不到 {multi_path}")
        return
    
    print("分析中...")
    
    print("\n分析單行模式...")
    single_stats = analyze_scenarios(single_path)
    
    print("分析多行模式...")
    multi_stats = analyze_scenarios(multi_path)
    
    # 比較
    compare_diversity(single_stats, multi_stats)
    
    print("\n" + "=" * 80)
    print("分析完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
