COLUMNS_NON_LIVE = [
    "Rank",
    "Model",
    "Non-Live Overall Acc",
    "AST Summary",
    "Simple AST",
    "Python Simple AST",
    "Java Simple AST",
    "JavaScript Simple AST",
    "Multiple AST",
    "Parallel AST",
    "Parallel Multiple AST",
    "Irrelevance Detection",
]

COLUMNS_LIVE = [
    "Rank",
    "Model",
    "Live Overall Acc",
    "AST Summary",
    "Python Simple AST",
    "Python Multiple AST",
    "Python Parallel AST",
    "Python Parallel Multiple AST",
    "Irrelevance Detection",
    "Relevance Detection",
]


COLUMNS_MULTI_TURN = [
    "Rank",
    "Model",
    "Multi Turn Overall Acc",
    "Base",
    "Miss Func",
    "Miss Param",
    "Long Context",
]


COLUMNS_AGENTIC = [
    "Rank",
    "Model",
    "Agentic Overall Acc",
    "Web Search Summary",
    "Web Search Base",
    "Web Search No Snippet",
    "Memory Summary",
    "Memory KV",
    "Memory Vector",
    "Memory Recursive Summarization",
]

# Format Sensitivity columns are not scored but informative
COLUMNS_FORMAT_SENS_PREFIX = [
    "Rank",
    "Model",
    "Format Sensitivity Max Delta",
    "Format Sensitivity Standard Deviation",
]

COLUMNS_OVERALL = [
    "Rank",
    "Overall Acc",
    "Model",
    "Model Link",
    "Total Cost ($)",
    "Latency Mean (s)",
    "Latency Standard Deviation (s)",
    "Latency 95th Percentile (s)",
    "Non-Live AST Acc",
    "Non-Live Simple AST",
    "Non-Live Multiple AST",
    "Non-Live Parallel AST",
    "Non-Live Parallel Multiple AST",
    "Live Acc",
    "Live Simple AST",
    "Live Multiple AST",
    "Live Parallel AST",
    "Live Parallel Multiple AST",
    "Multi Turn Acc",
    "Multi Turn Base",
    "Multi Turn Miss Func",
    "Multi Turn Miss Param",
    "Multi Turn Long Context",
    "Web Search Acc",
    "Web Search Base",
    "Web Search No Snippet",
    "Memory Acc",
    "Memory KV",
    "Memory Vector",
    "Memory Recursive Summarization",
    "Relevance Detection",
    "Irrelevance Detection",
    "Format Sensitivity Max Delta",
    "Format Sensitivity Standard Deviation",
    "Organization",
    "License",
]
# 在現有的 COLUMNS_* 旁邊加：
COLUMNS_CHINESE = [
    "Rank",
    "Model",
    "AST (ZH) Summary",
    "ZH: Simple",
    "ZH: Multiple",
    "ZH: Parallel",
    "ZH: Parallel Multiple",
    "ZH: Relevance",
]
# 中文 Multi-Turn 表頭
COLUMNS_CHINESE_MULTI_TURN = [
    "Rank",
    "Model",
    "Multi Turn (ZH) Overall Acc",
    "ZH: Multi Turn Base",
    "ZH: Multi Turn Miss Func",
    "ZH: Multi Turn Miss Param",
    "ZH: Multi Turn Long Context",
]
# 先建一個「含中文欄位」的 overall 標頭（在原本 COLUMNS_OVERALL 後面拼接）
COLUMNS_OVERALL_WITH_ZH = COLUMNS_OVERALL + [
    # 建議順序：先 Overall 再 Summary 再細項
    "Summary (ZH)",
    "ZH Simple-Python",
    "ZH Multiple",
    "ZH Parallel",
    "ZH Parallel-Multiple",
]

# 全中文 Overall（權重依題數，僅中文單輪 + 中文多輪，不含英文）
COLUMNS_OVERALL_ZH = [
    "Rank",
    "Overall (ZH) Acc",
    "Model",
    "AST (ZH) Summary",
    "ZH: Simple",
    "ZH: Multiple",
    "ZH: Parallel",
    "ZH: Parallel Multiple",
    "ZH: Relevance",
    "Multi Turn (ZH) Overall Acc",
    "ZH: Multi Turn Base",
    "ZH: Multi Turn Miss Func",
    "ZH: Multi Turn Miss Param",
    "ZH: Multi Turn Long Context",
]