"""
Helper module to execute BFCL tool calls and get responses
"""
import sys
import json
sys.path.insert(0, '/home/at0842/aaronwu901225master.ai13/gorilla/berkeley-function-call-leaderboard')

from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import execute_multi_turn_func_call


def execute_ground_truth_calls(
    ground_truth_calls: list[str],
    initial_config: dict,
    involved_classes: list[str],
    test_entry_id: str,
    long_context: bool = False
) -> list[str]:
    """
    執行 ground truth function calls 並回傳結果
    
    Args:
        ground_truth_calls: List of function call strings (e.g., ["cd(folder='document')", ...])
        initial_config: Initial configuration for the test
        involved_classes: List of class names involved
        test_entry_id: Test entry ID
        long_context: Whether to use long context mode
    
    Returns:
        List of execution results (as strings)
    """
    try:
        results, _ = execute_multi_turn_func_call(
            func_call_list=ground_truth_calls,
            initial_config=initial_config,
            involved_classes=involved_classes,
            model_name="training_data",  # 使用固定的 model_name
            test_entry_id=test_entry_id,
            long_context=long_context,
            is_evaL_run=False
        )
        return results
    except Exception as e:
        # 如果執行失敗,回傳錯誤訊息
        return [f"Error: {str(e)}"] * len(ground_truth_calls)


if __name__ == "__main__":
    # 測試
    test_calls = ["cd(folder='document')"]
    test_config = {"GorillaFileSystem": {}}
    test_classes = ["GorillaFileSystem"]
    
    results = execute_ground_truth_calls(
        test_calls,
        test_config,
        test_classes,
        "test_0",
        long_context=False
    )
    print("Test results:", results)
