"""
在原有的 extract_bfcl_multiturn_for_xlam.py 基礎上
添加 tool response 的功能
"""

import json
import os
import re
import ast
from pathlib import Path
from typing import List, Dict, Any
import sys

# 加入 BFCL 路徑
sys.path.insert(0, '/home/at0842/aaronwu901225master.ai13/gorilla/berkeley-function-call-leaderboard')

from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import execute_multi_turn_func_call
from bfcl_eval.constants.executable_backend_config import MULTI_TURN_FUNC_DOC_FILE_MAPPING

# xLAM system prompt (參考 salesforce_llama.py)
XLAM_SYSTEM_PROMPT = "You are a helpful assistant that can use tools. You are developed by Salesforce xLAM team."

XLAM_TOOL_INSTRUCTION = """You have access to a set of tools. When using tools, make calls in a single JSON array: 

[{"name": "tool_call_name", "arguments": {"arg1": "value1", "arg2": "value2"}}, ... (additional parallel tool calls as needed)]

If no tool is suitable, state that explicitly. If the user's input lacks required parameters, ask for clarification. Do not interpret or respond until tool results are returned. Once they are available, process them or make additional calls if needed. For tasks that don't require tools, such as casual conversation or general advice, respond directly in plain text."""


def load_multi_turn_data(data_file: str) -> List[Dict]:
    """載入 BFCL multi-turn 資料"""
    with open(data_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    data = []
    for line in lines:
        if line.strip():
            data.append(json.loads(line))
    return data


def load_possible_answers(answer_file: str) -> Dict[str, List[List[str]]]:
    """載入 ground truth answers"""
    with open(answer_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    answers = {}
    for line in lines:
        if line.strip():
            entry = json.loads(line)
            answers[entry['id']] = entry['ground_truth']
    return answers


def load_function_docs(func_doc_dir: str, involved_classes: List[str], long_context: bool = False) -> List[Dict]:
    """載入 function schemas"""
    functions = []
    
    for class_name in involved_classes:
        # 使用 BFCL 的官方映射表
        func_doc_file = MULTI_TURN_FUNC_DOC_FILE_MAPPING.get(class_name)
        if not func_doc_file:
            print(f"Warning: No mapping found for class {class_name}")
            continue
        func_doc_path = os.path.join(func_doc_dir, func_doc_file)
        
        if os.path.exists(func_doc_path):
            with open(func_doc_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # 檔案格式是多個 JSON object 直接相鄰
                decoder = json.JSONDecoder()
                idx = 0
                while idx < len(content):
                    content_from_idx = content[idx:].lstrip()
                    if not content_from_idx:
                        break
                    try:
                        obj, end_idx = decoder.raw_decode(content_from_idx)
                        functions.append(obj)
                        idx += len(content[idx:]) - len(content_from_idx) + end_idx
                    except json.JSONDecodeError as e:
                        print(f"Error parsing {func_doc_file} at position {idx}: {e}")
                        break
    
    # 如果是 long_context,需要加入擴充資料標記
    if long_context:
        functions = add_long_context_extensions(functions)
    
    return functions


def add_long_context_extensions(functions: List[Dict]) -> List[Dict]:
    """為 long_context 加入擴充資料標記"""
    extension_mapping = {
        'get_symbol_by_name': 'WATCH_LIST_EXTENSION',
        'get_transaction_history': 'TRANSACTION_HISTORY_EXTENSION'
    }
    
    for func in functions:
        func_name = func.get('name', '')
        if func_name in extension_mapping:
            # 在 response 的 description 中註明有大量資料
            if 'response' in func and 'properties' in func['response']:
                for prop_name, prop_value in func['response']['properties'].items():
                    if 'description' in prop_value:
                        prop_value['description'] += f" (Note: In long context scenarios, this may include extensive data from {extension_mapping[func_name]})."
    
    return functions


def execute_tool_calls(
    ground_truth_calls: List[str],
    test_entry: Dict,
    long_context: bool = False,
    accumulated_instances: Dict = None
) -> List[str]:
    """
    執行 ground truth tool calls 並回傳結果
    """
    if not ground_truth_calls:
        return []
    
    try:
        # 使用累積的 instances (如果有的話)
        initial_config = test_entry.get('initial_config', {})
        involved_classes = test_entry.get('involved_classes', [])
        test_id = test_entry.get('id', 'unknown')
        
        results, instances = execute_multi_turn_func_call(
            func_call_list=ground_truth_calls,
            initial_config=initial_config,
            involved_classes=involved_classes,
            model_name="xlam_training",
            test_entry_id=test_id,
            long_context=long_context,
            is_evaL_run=False
        )
        
        # 更新累積的 instances
        if accumulated_instances is not None:
            accumulated_instances.update(instances)
        
        return results
    except Exception as e:
        print(f"Error executing tools for {test_entry.get('id', 'unknown')}: {e}")
        return [f"Error: {str(e)}"] * len(ground_truth_calls)


def format_xlam_conversation_with_responses(
    test_entry: Dict,
    functions: List[Dict],
    ground_truths: List[List[str]],
    dataset_name: str,
    long_context: bool = False
) -> List[Dict]:
    """
    將 BFCL multi-turn 資料轉換成 xLAM training format (包含 tool responses)
    
    miss_func 邏輯:
    - missed_function 是 string -> list 的映射
    - 在資料載入時,這些函數就已經被移除了
    - 但在指定的 turn,這些函數會被**加回來**
    - 原本的 question 在那個 turn 是空的 []
    """
    conversations = []
    questions = test_entry['question']
    
    # miss_func: 取得哪些 turn 需要加回哪些函數
    # 注意: 在原始資料中,這些函數名稱列表已經在 utils.py 中被轉換成函數 schema 列表
    # 但我們這裡直接從原始資料讀取,所以還是字串列表
    missed_function = test_entry.get('missed_function', {})
    
    # 從 functions 中移除所有 missed functions (模擬 BFCL 的預處理)
    # 並建立 holdout_functions 字典
    holdout_functions: Dict[str, List[Dict]] = {}
    current_functions = functions.copy()
    
    if missed_function:
        for turn_str, func_names in missed_function.items():
            holdout_functions[turn_str] = []
            # 從 current_functions 中移除這些函數
            for func_name in func_names:
                for i, func in enumerate(current_functions):
                    if func['name'] == func_name:
                        holdout_functions[turn_str].append(func)
                        current_functions.pop(i)
                        break
    
    # 現在 current_functions 是移除 missed functions 後的列表
    # 這是大部分 turns 看到的函數列表
    
    # 累積所有歷史訊息
    all_messages = []
    
    # 累積的 class instances (用於多輪對話的狀態保持)
    accumulated_instances = {}
    
    # 追蹤當前可用的函數 (會在 holdout turn 改變)
    active_functions = current_functions.copy()
    
    for turn_idx, (question_turn, gt_turn) in enumerate(zip(questions, ground_truths)):
        turn_str = str(turn_idx)
        
        # 第一個 turn 需要設定 system message (不會再改變)
        if turn_idx == 0:
            system_content = XLAM_SYSTEM_PROMPT + "\n" + XLAM_TOOL_INSTRUCTION
            system_content += "The available tools are:\n\n"
            for func in current_functions:
                system_content += json.dumps(func, indent=4, ensure_ascii=False) + "\n\n"
            
            all_messages.append({
                "role": "system",
                "content": system_content
            })
        
        # 添加當前 turn 的 user message(s)
        if turn_str in holdout_functions:
            # Holdout turn: 將新函數加回來
            active_functions.extend(holdout_functions[turn_str])
            
            # 在 user message 中包含新函數的 schema (模仿 BFCL 的做法)
            holdout_message = str(holdout_functions[turn_str])  # Python dict 的字串表示
            holdout_message += "\nI have updated some more functions you can choose from. What about now?"
            
            all_messages.append({
                "role": "user",
                "content": holdout_message
            })
        else:
            # 正常 turn: 添加原本的 user message(s)
            for msg in question_turn:
                all_messages.append(msg)
        
        # 將 ground truth 轉換為 JSON array format
        ground_truth_json = []
        for call_str in gt_turn:
            # 解析 function_name(arg1=val1, arg2=val2) 格式
            # 使用 ast 模組來正確處理複雜參數值(如列表、布林值等)
            match = re.match(r'(\w+)\((.*)\)', call_str, re.DOTALL)
            if match:
                func_name = match.group(1)
                args_str = match.group(2)
                
                # 使用 ast 解析參數
                args = {}
                if args_str.strip():
                    try:
                        # 構造一個假的函數呼叫來解析
                        fake_call = f"func({args_str})"
                        tree = ast.parse(fake_call, mode='eval')
                        call_node = tree.body
                        
                        # 提取 keyword arguments
                        for keyword in call_node.keywords:
                            key = keyword.arg
                            # 使用 ast.literal_eval 來評估值
                            try:
                                value = ast.literal_eval(keyword.value)
                            except:
                                # 如果無法評估,使用原始字串
                                value = ast.unparse(keyword.value) if hasattr(ast, 'unparse') else str(keyword.value)
                            args[key] = value
                        
                        # 提取 positional arguments (如果有的話)
                        # 這種情況較少見,但為了完整性還是處理
                        for i, arg_node in enumerate(call_node.args):
                            try:
                                value = ast.literal_eval(arg_node)
                            except:
                                value = ast.unparse(arg_node) if hasattr(ast, 'unparse') else str(arg_node)
                            args[f"arg_{i}"] = value
                            
                    except Exception as e:
                        # 如果 ast 解析失敗,回退到簡單解析
                        print(f"Warning: ast parsing failed for '{call_str}': {e}")
                        # 簡單的 fallback 邏輯
                        for part in args_str.split(','):
                            if '=' in part:
                                k, v = part.split('=', 1)
                                args[k.strip()] = v.strip()
                
                ground_truth_json.append({
                    "name": func_name,
                    "arguments": args
                })
        
        # 執行 ground truth tool calls 取得 responses
        tool_responses = []
        if gt_turn:  # 只有當有 ground truth 時才執行
            tool_responses = execute_tool_calls(
                gt_turn,
                test_entry,
                long_context=long_context,
                accumulated_instances=accumulated_instances
            )
        
        # 儲存當前狀態(包含所有歷史)
        conversations.append({
            "id": f"{test_entry['id']}_turn_{turn_idx}",
            "messages": all_messages.copy(),
            "tools": active_functions.copy(),  # 新增: 當前可用的 tools
            "ground_truth": ground_truth_json,
            "tool_responses": tool_responses,  # 新增: tool execution 結果
            "turn_index": turn_idx,
            "total_turns": len(questions),
            "dataset": dataset_name
        })
        
        # 添加 assistant 的回覆到歷史(用於下一個 turn)
        if ground_truth_json:
            # Assistant message (tool calls)
            assistant_msg = {
                "role": "assistant",
                "content": json.dumps(ground_truth_json, ensure_ascii=False)
            }
            all_messages.append(assistant_msg)
            
            # Tool responses
            for tool_call, tool_response in zip(ground_truth_json, tool_responses):
                tool_msg = {
                    "role": "tool",
                    "name": tool_call["name"],
                    "content": tool_response
                }
                all_messages.append(tool_msg)
    
    return conversations


def main():
    """主程式"""
    # 設定路徑
    BFCL_DATA_DIR = Path("/home/at0842/aaronwu901225master.ai13/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data")
    func_doc_dir = BFCL_DATA_DIR / "multi_turn_func_doc"
    output_file = Path("bfcl_multiturn_xlam_with_responses.jsonl")
    
    # 定義所有 4 個 multi-turn 資料集
    datasets = [
        "BFCL_v4_multi_turn_base",
        "BFCL_v4_multi_turn_long_context",
        "BFCL_v4_multi_turn_miss_func",
        "BFCL_v4_multi_turn_miss_param"
    ]
    
    all_conversations = []
    
    # 處理每個資料集
    for dataset_name in datasets:
        print(f"\n{'='*60}")
        print(f"Processing {dataset_name}...")
        print(f"{'='*60}")
        
        test_file = BFCL_DATA_DIR / f"{dataset_name}.json"
        answer_file = BFCL_DATA_DIR / "possible_answer" / f"{dataset_name}.json"
        
        # 載入測試資料
        print(f"Loading test data...")
        test_data = load_multi_turn_data(str(test_file))
        print(f"✓ Loaded {len(test_data)} test entries")
        
        # 載入 ground truth answers
        print(f"Loading ground truth answers...")
        answers = load_possible_answers(str(answer_file))
        print(f"✓ Loaded answers for {len(answers)} entries")
        
        # 處理每個測試案例
        dataset_conversations = []
        
        # 判斷是否為 long_context
        is_long_context = 'long_context' in dataset_name
        
        for idx, entry in enumerate(test_data):
            entry_id = entry['id']
            involved_classes = entry.get('involved_classes', [])
            
            # 載入相關的 function schemas,若是 long_context 加入擴充資料標記
            functions = load_function_docs(str(func_doc_dir), involved_classes, long_context=is_long_context)
            
            # 獲取 ground truth
            ground_truths = answers.get(entry_id, [])
            
            try:
                # 轉換成 xLAM 格式(包含 tool responses)
                conversations = format_xlam_conversation_with_responses(
                    entry, 
                    functions, 
                    ground_truths, 
                    dataset_name,
                    long_context=is_long_context
                )
                dataset_conversations.extend(conversations)
                
                if (idx + 1) % 10 == 0:
                    print(f"  Processed {idx + 1}/{len(test_data)} entries...")
            except Exception as e:
                print(f"  Error processing {entry_id}: {e}")
                continue
        
        all_conversations.extend(dataset_conversations)
        print(f"✓ Generated {len(dataset_conversations)} conversation turns")
    
    # 寫入輸出檔案
    print(f"\n{'='*60}")
    print(f"Writing all {len(all_conversations)} conversation turns to {output_file}...")
    print(f"{'='*60}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for conv in all_conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + '\n')
    
    print(f"✓ Successfully wrote {len(all_conversations)} conversation turns")
    
    # 顯示統計資訊
    print(f"\n{'='*60}")
    print("=== Overall Statistics ===")
    print(f"{'='*60}")
    print(f"Total datasets processed: {len(datasets)}")
    print(f"Total conversation turns: {len(all_conversations)}")
    
    # 按資料集分組統計
    print(f"\n=== Dataset Breakdown ===")
    dataset_counts = {}
    for conv in all_conversations:
        ds = conv.get('dataset', 'unknown')
        dataset_counts[ds] = dataset_counts.get(ds, 0) + 1
    
    for ds_type, count in sorted(dataset_counts.items()):
        print(f"{ds_type:40s}: {count:4d} turns")
    
    # 顯示第一個範例
    print(f"\n{'='*60}")
    print("=== First Example with Tool Response ===")
    print(f"{'='*60}")
    if all_conversations:
        first_conv = all_conversations[0]
        print(f"ID: {first_conv['id']}")
        print(f"Turn: {first_conv['turn_index'] + 1}/{first_conv['total_turns']}")
        print(f"Number of messages: {len(first_conv['messages'])}")
        print(f"Ground truth: {len(first_conv['ground_truth'])} tool calls")
        print(f"Tool responses: {len(first_conv.get('tool_responses', []))} responses")
        print(f"\nGround truth (JSON format):")
        print(f"  {json.dumps(first_conv['ground_truth'], ensure_ascii=False)}")
        print(f"\nTool responses:")
        for i, resp in enumerate(first_conv.get('tool_responses', [])):
            print(f"  [{i}] {resp[:100]}{'...' if len(resp) > 100 else ''}")


if __name__ == "__main__":
    main()
