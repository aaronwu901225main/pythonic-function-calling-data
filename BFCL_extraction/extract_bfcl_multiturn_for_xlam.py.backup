"""
提取 BFCL multi-turn 資料並轉換成 xLAM chat template 格式
包含:
1. 完整的 conversation history (multi-turn)
2. Tool schemas (從 multi_turn_func_doc/)
3. Ground truth answers
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any

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
    """載入 function schemas,並在 long_context 時加入擴充資料"""
    functions = []
    
    for class_name in involved_classes:
        # 根據 BFCL 的命名規則: GorillaFileSystem -> gorilla_file_system.json
        # TwitterAPI -> twitter_api.json
        file_name = class_name.replace('API', '_api')
        # 將駝峰命名轉成底線命名
        func_doc_file = ''.join(['_' + c.lower() if c.isupper() else c for c in file_name]).lstrip('_') + '.json'
        func_doc_path = os.path.join(func_doc_dir, func_doc_file)
        
        if os.path.exists(func_doc_path):
            with open(func_doc_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # 檔案格式是多個 JSON object 直接相鄰(pattern: }\n{)
                # 使用 JSONDecoder 逐個解析
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
    
    # 如果是 long_context,需要加入擴充資料到特定函數的 response
    if long_context:
        functions = add_long_context_extensions(functions)
    
    return functions


def add_long_context_extensions(functions: List[Dict]) -> List[Dict]:
    """為 long_context 加入擴充資料到函數的 response 中"""
    # 找出需要加入擴充資料的函數及其對應的擴充資料
    # TradingBot.get_symbol_by_name 需要 WATCH_LIST_EXTENSION
    # TradingBot.get_transaction_history 需要 TRANSACTION_HISTORY_EXTENSION
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


def format_xlam_conversation(
    test_entry: Dict,
    functions: List[Dict],
    ground_truths: List[List[str]]
) -> List[Dict]:
    """
    將 BFCL multi-turn 資料轉換成 xLAM training format
    
    Returns:
        List of conversation turns, each containing:
        {
            "messages": [...],  # xLAM format messages with tool instructions
            "tools": [...],     # function schemas
            "ground_truth": [...] # expected tool calls for this turn
        }
    """
    conversations = []
    questions = test_entry['question']
    
    # 累積所有歷史訊息
    all_messages = []
    
    # System message (只需加一次)
    system_content = XLAM_SYSTEM_PROMPT + "\n" + XLAM_TOOL_INSTRUCTION
    
    # 添加 function schemas 到 system message
    system_content += "The available tools are:\n\n"
    for func in functions:
        system_content += json.dumps(func, indent=4, ensure_ascii=False) + "\n\n"
    
    all_messages.append({
        "role": "system",
        "content": system_content
    })
    
    for turn_idx, (question_turn, gt_turn) in enumerate(zip(questions, ground_truths)):
        # 添加當前 turn 的 user message(s)
        for msg in question_turn:
            all_messages.append(msg)
        
        # 將 ground truth 轉換為 JSON array format
        ground_truth_json = []
        for call_str in gt_turn:
            # 解析 function_name(arg1=val1, arg2=val2) 格式
            import re
            match = re.match(r'(\w+)\((.*)\)', call_str)
            if match:
                func_name = match.group(1)
                args_str = match.group(2)
                
                # 解析參數
                args = {}
                if args_str:
                    for arg in args_str.split(','):
                        if '=' in arg:
                            k, v = arg.split('=', 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            args[k] = v
                
                ground_truth_json.append({
                    "name": func_name,
                    "arguments": args
                })
        
        # 儲存當前狀態(包含所有歷史)
        conversations.append({
            "id": f"{test_entry['id']}_turn_{turn_idx}",
            "messages": all_messages.copy(),  # 複製當前所有訊息(tools 已在 system message 中)
            "ground_truth": ground_truth_json,  # JSON array format
            "turn_index": turn_idx,
            "total_turns": len(questions)
        })
        
        # 添加 assistant 的回覆到歷史(用於下一個 turn)
        if ground_truth_json:
            assistant_msg = {
                "role": "assistant",
                "content": json.dumps(ground_truth_json, ensure_ascii=False)
            }
            all_messages.append(assistant_msg)
    
    return conversations


def main():
    # 設定路徑
    BFCL_DATA_DIR = Path("/home/at0842/aaronwu901225master.ai13/gorilla/berkeley-function-call-leaderboard/bfcl_eval/data")
    func_doc_dir = BFCL_DATA_DIR / "multi_turn_func_doc"
    output_file = Path("bfcl_multiturn_xlam_format.jsonl")
    
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
        
        for entry in test_data:
            entry_id = entry['id']
            involved_classes = entry.get('involved_classes', [])
            
            # 載入相關的 function schemas
            functions = load_function_docs(str(func_doc_dir), involved_classes)
            
            # 獲取 ground truth
            ground_truths = answers.get(entry_id, [])
            
            # 轉換成 xLAM 格式
            conversations = format_xlam_conversation(entry, functions, ground_truths)
            dataset_conversations.extend(conversations)
        
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
    print(f"Total test entries: {sum(len(load_multi_turn_data(str(BFCL_DATA_DIR / f'{ds}.json'))) for ds in datasets)}")
    print(f"Total conversation turns: {len(all_conversations)}")
    
    # 按資料集分組統計
    print(f"\n=== Dataset Breakdown ===")
    dataset_counts = {}
    for conv in all_conversations:
        # 從 ID 提取資料集類型
        conv_id = conv['id']
        if 'long_context' in conv_id:
            ds_type = 'long_context'
        elif 'miss_func' in conv_id:
            ds_type = 'miss_func'
        elif 'miss_param' in conv_id:
            ds_type = 'miss_param'
        else:
            ds_type = 'base'
        dataset_counts[ds_type] = dataset_counts.get(ds_type, 0) + 1
    
    for ds_type, count in sorted(dataset_counts.items()):
        print(f"{ds_type:20s}: {count:4d} turns")

    
    # 顯示第一個範例
    print(f"\n{'='*60}")
    print("=== First Example ===")
    print(f"{'='*60}")
    first_conv = all_conversations[0]
    print(f"ID: {first_conv['id']}")
    print(f"Turn: {first_conv['turn_index'] + 1}/{first_conv['total_turns']}")
    print(f"Number of messages: {len(first_conv['messages'])}")
    print(f"Ground truth: {len(first_conv['ground_truth'])} tool calls")
    print(f"\nFirst user message:")
    for msg in first_conv['messages']:
        if msg['role'] == 'user':
            print(f"  {msg['content'][:100]}...")
            break
    print(f"\nGround truth (JSON format):")
    print(f"  {json.dumps(first_conv['ground_truth'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
