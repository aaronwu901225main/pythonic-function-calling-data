"""
Validate miss_function and miss_param multi-turn data.

Checks:
- Required fields exist
- Miss turn indices are valid
- Tool calls structure is correct
- For miss_function: missing_function_tool is properly formatted
- For miss_param: missing_params list is present
"""
import json
import sys
import os
from typing import Any, Dict, List


def validate_miss_function_sample(sample: Dict[str, Any], idx: int) -> List[str]:
    """Validate a single miss_function sample."""
    errors = []
    
    # Required fields
    required_fields = ["id", "tools", "messages", "scenario_type"]
    for field in required_fields:
        if field not in sample:
            errors.append(f"Sample {idx}: Missing required field '{field}'")
    
    # Check scenario_type
    if sample.get("scenario_type") != "miss_function":
        errors.append(f"Sample {idx}: Expected scenario_type='miss_function', got '{sample.get('scenario_type')}'")
    
    # Check missing_function_tool exists
    if "missing_function_tool" not in sample or sample["missing_function_tool"] is None:
        errors.append(f"Sample {idx}: Missing or null 'missing_function_tool'")
    else:
        mft = sample["missing_function_tool"]
        if not isinstance(mft, dict) or "name" not in mft:
            errors.append(f"Sample {idx}: 'missing_function_tool' should have 'name' field")
    
    # Check miss_turn_indices
    if "miss_turn_indices" in sample:
        indices = sample["miss_turn_indices"]
        total_turns = sample.get("total_turns", 0)
        for i in indices:
            if not isinstance(i, int) or i < 0 or i >= total_turns:
                errors.append(f"Sample {idx}: Invalid miss_turn_index {i} (total_turns={total_turns})")
    
    # Check messages structure
    messages = sample.get("messages", [])
    if not messages:
        errors.append(f"Sample {idx}: Empty messages list")
    
    for msg_idx, msg in enumerate(messages):
        if "role" not in msg:
            errors.append(f"Sample {idx}, Message {msg_idx}: Missing 'role' field")
    
    return errors


def validate_miss_param_sample(sample: Dict[str, Any], idx: int) -> List[str]:
    """Validate a single miss_param sample."""
    errors = []
    
    # Required fields
    required_fields = ["id", "tools", "messages", "scenario_type", "missing_params"]
    for field in required_fields:
        if field not in sample:
            errors.append(f"Sample {idx}: Missing required field '{field}'")
    
    # Check scenario_type
    if sample.get("scenario_type") != "miss_param":
        errors.append(f"Sample {idx}: Expected scenario_type='miss_param', got '{sample.get('scenario_type')}'")
    
    # Check missing_params
    missing_params = sample.get("missing_params", [])
    if not isinstance(missing_params, list) or not missing_params:
        errors.append(f"Sample {idx}: 'missing_params' should be a non-empty list")
    
    # Check miss_turn_indices
    if "miss_turn_indices" in sample:
        indices = sample["miss_turn_indices"]
        total_turns = sample.get("total_turns", 0)
        for i in indices:
            if not isinstance(i, int) or i < 0 or i >= total_turns:
                errors.append(f"Sample {idx}: Invalid miss_turn_index {i} (total_turns={total_turns})")
    
    # Check messages structure
    messages = sample.get("messages", [])
    if not messages:
        errors.append(f"Sample {idx}: Empty messages list")
    
    return errors


def validate_file(filepath: str) -> bool:
    """Validate a JSONL file containing miss scenarios."""
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return False
    
    errors = []
    sample_count = 0
    
    # Detect type from filename
    is_miss_func = "miss_func" in filepath
    is_miss_param = "miss_param" in filepath
    
    if not is_miss_func and not is_miss_param:
        print(f"WARNING: Cannot determine scenario type from filename: {filepath}")
        print("Assuming miss_function format")
        is_miss_func = True
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: JSON parse error - {e}")
                continue
            
            sample_count += 1
            
            if is_miss_func:
                sample_errors = validate_miss_function_sample(sample, line_num)
            else:
                sample_errors = validate_miss_param_sample(sample, line_num)
            
            errors.extend(sample_errors)
    
    # Print summary
    print(f"Validated: {filepath}")
    print(f"Total samples: {sample_count}")
    print(f"Errors found: {len(errors)}")
    
    if errors:
        print("\nErrors:")
        for err in errors[:20]:  # Limit to first 20 errors
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")
        return False
    else:
        print("✓ All samples passed validation")
        return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_miss_scenarios.py <filepath.jsonl>")
        print("Example: python validate_miss_scenarios.py pipeline/data/run_xxx/multi_turn_miss_func_zh_tw.jsonl")
        sys.exit(1)
    
    filepath = sys.argv[1]
    success = validate_file(filepath)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
