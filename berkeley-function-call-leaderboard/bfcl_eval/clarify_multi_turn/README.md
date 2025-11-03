# Clarify-format Multi-turn Conversions

This folder contains clarify-style JSONL converted from BFCL multi-turn datasets.

Files:
- clarify_mt_eng_base.jsonl: English multi-turn (base) → clarify format.
- clarify_mt_eng_long_context.jsonl: English multi-turn (long_context) → clarify format.
- clarify_mt_eng_miss_func.jsonl: English multi-turn (miss_func) → clarify format.
- clarify_mt_eng_miss_param.jsonl: English multi-turn (miss_param) → clarify format.
- clarify_mt_zh_base.jsonl: Chinese multi-turn (base) → clarify format.
- clarify_mt_zh_long_context.jsonl: Chinese multi-turn (long_context) → clarify format.
- clarify_mt_zh_miss_func.jsonl: Chinese multi-turn (miss_func) → clarify format.
- clarify_mt_zh_miss_param.jsonl: Chinese multi-turn (miss_param) → clarify format.

Notes:
- Tools: collected from involved_classes function docs; order prioritizes functions actually invoked per ground_truth.
- Messages: follow clarify_eng.jsonl schema with assistant.tool_calls and corresponding tool outputs.
- Ground truth for Chinese variants is mapped from the corresponding English possible_answer files by id (e.g., multi_turn_base_*), ensuring identical tool call sequences.

Regeneration (optional):
Use the script bfcl_eval/scripts/convert_multiturn_to_clarify.py with --dataset, --possible_answer, and --output.
