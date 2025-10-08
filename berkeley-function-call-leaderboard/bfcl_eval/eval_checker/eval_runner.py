import argparse
import os
import json
import csv
import statistics
from collections import defaultdict

from bfcl_eval.constants.enums import Language, ReturnFormat
from bfcl_eval.constants.eval_config import *
from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING
from bfcl_eval.eval_checker.agentic_eval.agentic_checker import agentic_checker
from bfcl_eval.eval_checker.ast_eval.ast_checker import ast_checker
from bfcl_eval.eval_checker.eval_runner_helper import *
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_checker import (
    multi_turn_checker,
    multi_turn_irrelevance_checker,
)
from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_utils import (
    is_empty_execute_response,
)
from bfcl_eval.eval_checker.zhtw_semantic_judge import (
    parse_zhtw_eval_arg,
    semantic_param_judge,
)
from bfcl_eval.model_handler.base_handler import BaseHandler
from bfcl_eval.model_handler.utils import parse_prompt_variation_params
from bfcl_eval.utils import *
from dotenv import load_dotenv
from tqdm import tqdm


def get_handler(model_name: str) -> BaseHandler:
    config = MODEL_CONFIG_MAPPING[model_name]
    handler: BaseHandler = config.model_handler(
        model_name=config.model_name,
        temperature=0,
        registry_name=model_name,
        is_fc_model=config.is_fc_model,
    )
    return handler


def _subset_entries_by_model_ids(
    model_result_entries: list[dict],
    prompt_entries: list[dict],
    ground_truth_entries: list[dict] = None,  # Irrelevance entries don't have ground truth
    allow_missing: bool = False,
):
    """
    Filter the prompt and ground truth entries so that its order/length matches the IDs present in `model_result`. When `allow_missing` is False, all IDs must be present; otherwise, any missing IDs are silently ignored.
    """
    if not model_result_entries:
        return [], []

    if not allow_missing and (len(model_result_entries) != len(prompt_entries)):
        raise ValueError(
            f"Length of model result ({len(model_result_entries)}) does not match length of test entries ({len(prompt_entries)}). If you intended to run only on a subset (eg. entries present in the model result), please pass the `--partial-eval` flag."
        )

    all_present_ids = {entry["id"]: entry for entry in model_result_entries}

    # Align prompt and ground-truth using the *index* of the prompt entry. Some
    # ground-truth items use a different ID format, but the order between the
    # prompt list and the ground-truth list is guaranteed to be identical. We
    # therefore keep the element at index *i* in both lists whenever the
    # prompt entry at that index has an ID present in the model results.
    filtered_prompt_entries: list[dict] = []
    filtered_ground_truth_entries: list[dict] = []
    for idx, prompt_entry in enumerate(prompt_entries):
        if prompt_entry["id"] in all_present_ids:
            filtered_prompt_entries.append(prompt_entry)
            # ground_truth_entries and prompt_entries are aligned by index.
            if ground_truth_entries is not None:
                filtered_ground_truth_entries.append(ground_truth_entries[idx])

    return filtered_prompt_entries, filtered_ground_truth_entries


def _evaluate_single_agentic_entry(
    handler: BaseHandler,
    index,
    model_result_list,
    possible_answer_item,
    prompt_entry,
    model_name,
    test_category,
):
    """Helper method to process a single agentic entry."""
    # Remove the function doc from the score file for better readability
    if "function" in prompt_entry:
        del prompt_entry["function"]

    # Agentic test is a single-turn multi-step test, so the model result should be a list of one element
    if type(model_result_list) != list or len(model_result_list) != 1:
        return {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": False,
            "error": {
                "error_message": [
                    "Error during inference phase. Model did not output a list of model responses."
                ],
                "error_type": "agentic:inference_error",
            },
            "prompt": prompt_entry,
            "model_result": model_result_list,
            "possible_answer": possible_answer_item,
        }

    # Try decoding the model results into executable function calls
    # Note: We only care about the last non-function-call message, which should fail to get decoded.
    # We don't care about the function calls in the middle of the conversation.
    # We only check if the expected answer is mentioned in the last message.
    # decode_execute returns a list of strings
    model_result_list_decoded: list[list[str]] = []
    last_unsuccessful_decoding_message = None

    for model_result_item in model_result_list[0]:
        # model_result_item is per step
        try:
            decoded_result: list[str] = handler.decode_execute(
                model_result_item, has_tool_call_tag=False
            )
            if is_empty_execute_response(decoded_result):
                last_unsuccessful_decoding_message = model_result_item
                continue
            model_result_list_decoded.append(decoded_result)
        except Exception as e:
            last_unsuccessful_decoding_message = model_result_item
            continue

    if not last_unsuccessful_decoding_message:
        return {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": False,
            "error": {
                "error_message": [
                    "Cannot find the last chat message that is not a function call."
                ],
                "error_type": "agentic:no_last_message",
            },
            "prompt": prompt_entry,
            "model_result": model_result_list,
            "model_result_decoded": model_result_list_decoded,
            "possible_answer": possible_answer_item,
        }

    # Check if the model output contains the expected answer
    accuracy_checker_result = agentic_checker(
        last_unsuccessful_decoding_message,
        possible_answer_item,
    )

    if not accuracy_checker_result["valid"]:
        return {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": accuracy_checker_result.pop("valid"),
            "error": accuracy_checker_result,
            "prompt": prompt_entry["question"],
            "model_result_raw": model_result_list,
            "last_non_fc_message": last_unsuccessful_decoding_message,
            "possible_answer": possible_answer_item,
        }

    return {"valid": True}


def _evaluate_single_multi_turn_entry(
    handler: BaseHandler,
    test_entry_id,
    model_result_list,
    ground_truth_list,
    prompt_entry,
    model_name,
    test_category,
):
    """Helper method to process a single multi-turn entry."""
    # Remove the function doc from the score file for better readability
    if "function" in prompt_entry:
        del prompt_entry["function"]

    if type(model_result_list) != list:
        return {
            "id": test_entry_id,
            "model_name": model_name,
            "test_category": test_category,
            "valid": False,
            "error": {
                "error_message": [
                    "Error during inference phase. Model did not output a list of model responses."
                ],
                "error_type": "multi_turn:inference_error",
            },
            "prompt": prompt_entry,
            "model_result": model_result_list,
            "possible_answer": ground_truth_list,
        }

    # Check if force-terminated during inference phase.
    # This happens when the model has retried too many times and still haven't figured out the answer.
    # When force-terminated, no further evaluation is needed. This whole entry will be failed.
    if len(model_result_list) != len(ground_truth_list):
        return {
            "id": test_entry_id,
            "model_name": model_name,
            "test_category": test_category,
            "valid": False,
            "error": {
                "error_message": [
                    f"Model was force-terminated during inference phase. The length of the model result turns ({len(model_result_list)}) does not match the length of the ground truth turns ({len(ground_truth_list)})."
                ],
                "error_type": "multi_turn:force_terminated",
            },
            "prompt": prompt_entry,
            "model_result": model_result_list,
            "possible_answer": ground_truth_list,
        }

    # decode_execute returns a list of strings
    multi_turn_model_result_list_decoded: list[list[list[str]]] = []
    # Try decoding the model results into executable function calls
    for single_turn_model_result_list in model_result_list:
        single_turn_model_result_list_decoded = []
        for model_result_item in single_turn_model_result_list:
            # model_result_item is per step
            try:
                decoded_result: list[str] = handler.decode_execute(
                    model_result_item, has_tool_call_tag=False
                )
                if is_empty_execute_response(decoded_result):
                    # Empty output is not considered as a valid function call
                    continue
                single_turn_model_result_list_decoded.append(decoded_result)
            except Exception as e:
                # Ignore any failed decoding and continue to the next message
                # We only care about the decoded function call, not the error message or if the model is chatting
                continue
        multi_turn_model_result_list_decoded.append(single_turn_model_result_list_decoded)

    # Check if the model output the correct function calls
    accuracy_checker_result = multi_turn_checker(
        multi_turn_model_result_list_decoded,
        ground_truth_list,
        prompt_entry,
        test_category,
        model_name,
    )

    if not accuracy_checker_result["valid"]:
        return {
            "id": test_entry_id,
            "model_name": model_name,
            "test_category": test_category,
            "valid": accuracy_checker_result.pop("valid"),
            "error": accuracy_checker_result,
            "prompt": prompt_entry,
            "model_result_raw": model_result_list,
            "model_result_decoded": multi_turn_model_result_list_decoded,
            "possible_answer": ground_truth_list,
        }

    return {"valid": True}


def _evaluate_single_relevance_entry(
    handler: BaseHandler,
    index,
    model_result_item,
    prompt_entry,
    model_name,
    test_category,
):
    """Helper method to process a single relevance/irrelevance entry."""
    contain_func_call = False
    decoded_result = None
    decode_error = None

    try:
        decoded_result = handler.decode_ast(
            model_result_item, language=ReturnFormat.PYTHON, has_tool_call_tag=False
        )
        # Decode successfully, which means the model output is in valid function call format
        contain_func_call = True
        if is_empty_output(decoded_result):
            # Empty output is not considered as a valid function call
            contain_func_call = False
    except Exception as e:
        # Decode failed, which means the model output is not in valid function call format
        contain_func_call = False
        decode_error = str(e)

    # irrelevance test means no function call outputted
    if "irrelevance" in test_category:
        success = not contain_func_call
    else:
        success = contain_func_call

    if not success:
        temp = {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": success,
            "prompt": prompt_entry,
            "model_result": model_result_item,
            "decoded_result": decoded_result,
        }
        if "irrelevance" in test_category:
            temp["error"] = ["Valid syntax. Successfully decode AST when it should not."]
            temp["error_type"] = "irrelevance_error:decoder_success"
        else:
            temp["error"] = [
                f"Invalid syntax. Failed to decode AST when it should have. {decode_error}"
            ]
            temp["error_type"] = "relevance_error:decoder_failed"
        return temp

    return {"valid": True}


def _evaluate_single_ast_entry(
    handler: BaseHandler,
    index,
    model_result_item,
    possible_answer_item,
    prompt_entry,
    model_name,
    test_category,
    language: Language,
    return_format: ReturnFormat,
    has_tool_call_tag=False,
):
    """Helper method to process a single AST entry."""
    prompt_function = prompt_entry["function"]

    try:
        model_result_item_raw = model_result_item
        model_result_item = handler.decode_ast(
            model_result_item, return_format, has_tool_call_tag
        )
    except Exception as e:
        return {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": False,
            "error": [f"Invalid syntax. Failed to decode AST. {str(e)}"],
            "error_type": "ast_decoder:decoder_failed",
            "prompt": prompt_entry,
            "model_result_raw": model_result_item_raw,
            "possible_answer": possible_answer_item,
        }

    decoder_output_valid = is_function_calling_format_output(model_result_item)
    if not decoder_output_valid:
        return {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": False,
            "error": [
                "Did not output in the specified format. Note: the model_result is wrapped in a string to ensure json serializability."
            ],
            "error_type": "ast_decoder:decoder_wrong_output_format",
            "prompt": prompt_entry,
            "model_result_raw": str(model_result_item_raw),
            "model_result_decoded": str(model_result_item),
            "possible_answer": possible_answer_item,
        }

    checker_result = ast_checker(
        prompt_function,
        model_result_item,
        possible_answer_item,
        language,
        test_category,
        model_name,
    )

    if not checker_result["valid"]:
        return {
            "id": index,
            "model_name": model_name,
            "test_category": test_category,
            "valid": checker_result["valid"],
            "error": checker_result["error"],
            "error_type": checker_result["error_type"],
            "prompt": prompt_entry,
            "model_result_raw": model_result_item_raw,
            "model_result_decoded": model_result_item,
            "possible_answer": possible_answer_item,
        }
    return {"valid": True}


def format_sensitivity_runner(
    handler: BaseHandler,
    model_result,
    prompt,
    possible_answer,
    model_name,
    test_category,
    score_dir,
):
    assert (
        len(model_result) == len(prompt) == len(possible_answer)
    ), f"The length of the model result ({len(model_result)}) does not match the length of the prompt ({len(prompt)}) or possible answer ({len(possible_answer)}). Please check the input files for completeness."

    # The format sensitivity tests are all single-turn tests, so we use a similar logic to the ast_file_runner to evaluate them.

    result = []
    correct_count = 0
    # Track stats per format sensitivity configuration
    config_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "total": 0}
    )

    for i in range(len(model_result)):
        index = model_result[i]["id"]
        model_result_item = model_result[i]["result"]
        prompt_entry = prompt[i]
        possible_answer_item = possible_answer[i]["ground_truth"]

        assert (
            ":" in index and len(index.split(":")) == 3
        ), f"Test entry ID {index} should contain exactly two colons, since they are supposed to be the format sensitivity ids."

        format_sensitivity_config = index.split(":")[1]
        (
            return_format,
            has_tool_call_tag,
            function_doc_format,
            prompt_format,
            prompt_style,
        ) = parse_prompt_variation_params(format_sensitivity_config)

        return_format = ReturnFormat(return_format)

        entry_result = _evaluate_single_ast_entry(
            handler,
            index,
            model_result_item,
            possible_answer_item,
            prompt_entry,
            model_name,
            test_category,
            # Format sensitivity tests are all python tests
            language=Language.PYTHON,
            return_format=return_format,
            has_tool_call_tag=has_tool_call_tag,
        )

        # Update stats for this configuration
        config_stats[format_sensitivity_config]["total"] += 1
        if entry_result["valid"]:
            correct_count += 1
            config_stats[format_sensitivity_config]["correct"] += 1
        else:
            result.append(entry_result)

    # Compute accuracy per configuration
    accuracy_by_config = {
        cfg: {
            "accuracy": stats["correct"] / stats["total"],
            "correct_count": stats["correct"],
            "total_count": stats["total"],
        }
        for cfg, stats in config_stats.items()
    }

    # Calculate statistics across different prompt configurations
    config_accuracies = [v["accuracy"] for v in accuracy_by_config.values()]
    if len(config_accuracies) > 1:
        accuracy_variance = round(statistics.variance(config_accuracies) * 100**2, 2)
        accuracy_std = round(statistics.stdev(config_accuracies) * 100, 2)
        accuracy_max_delta = round(
            (max(config_accuracies) - min(config_accuracies)) * 100, 2
        )
    else:
        accuracy_variance = 0.0
        accuracy_std = 0.0
        accuracy_max_delta = 0.0

    extra_header_fields = {
        "accuracy_max_delta": accuracy_max_delta,
        "accuracy_variance": accuracy_variance,
        "accuracy_std": accuracy_std,
        **accuracy_by_config,
    }

    return save_eval_results(
        result,
        correct_count,
        model_result,
        test_category,
        model_name,
        score_dir,
        extra_header_fields=extra_header_fields,
    )


def agentic_runner(
    handler: BaseHandler,
    model_result,
    prompt,
    possible_answer,
    model_name,
    test_category,
    score_dir,
):
    assert (
        len(model_result) == len(prompt) == len(possible_answer)
    ), f"The length of the model result ({len(model_result)}) does not match the length of the prompt ({len(prompt)}) or possible answer ({len(possible_answer)}). Please check the input files for completeness."

    result = []
    correct_count = 0
    for i in range(len(model_result)):
        index = model_result[i]["id"]
        model_result_list = model_result[i]["result"]
        possible_answer_item = possible_answer[i]["ground_truth"]
        test_entry = prompt[i]

        entry_result = _evaluate_single_agentic_entry(
            handler,
            index,
            model_result_list,
            possible_answer_item,
            test_entry,
            model_name,
            test_category,
        )

        if entry_result["valid"]:
            correct_count += 1
        else:
            entry_result["inference_log"] = model_result[i].get("inference_log", "")
            result.append(entry_result)

    return save_eval_results(
        result, correct_count, model_result, test_category, model_name, score_dir
    )


def multi_turn_runner(
    handler: BaseHandler,
    model_result,
    prompt,
    possible_answer,
    model_name,
    test_category,
    score_dir,
):
    assert (
        len(model_result) == len(prompt) == len(possible_answer)
    ), f"The length of the model result ({len(model_result)}) does not match the length of the prompt ({len(prompt)}) or possible answer ({len(possible_answer)}). Please check the input files for completeness."

    result = []
    correct_count = 0
    for i in range(len(model_result)):
        index = model_result[i]["id"]
        multi_turn_model_result_list = model_result[i]["result"]
        multi_turn_ground_truth_list = possible_answer[i]["ground_truth"]
        test_entry = prompt[i]

        entry_result = _evaluate_single_multi_turn_entry(
            handler,
            index,
            multi_turn_model_result_list,
            multi_turn_ground_truth_list,
            test_entry,
            model_name,
            test_category,
        )

        if entry_result["valid"]:
            correct_count += 1
        else:
            entry_result["inference_log"] = model_result[i].get("inference_log", "")
            result.append(entry_result)

    return save_eval_results(
        result, correct_count, model_result, test_category, model_name, score_dir
    )


def relevance_file_runner(
    handler: BaseHandler, model_result, prompt, model_name, test_category, score_dir
):
    # This function serves for both relevance and irrelevance tests, which share the exact opposite logic.
    # If `test_category` is "irrelevance", the model is expected to output no function call.
    # No function call means either the AST decoding fails (a error message is generated) or the decoded AST does not contain any function call (such as a empty list, `[]`).
    # If `test_category` is "relevance", the model is expected to output to a function call, and empty list doesn't count as a function call.
    result = []
    correct_count = 0
    for i in range(len(model_result)):
        index = model_result[i]["id"]
        model_result_item = model_result[i]["result"]
        prompt_entry = prompt[i]

        entry_result = _evaluate_single_relevance_entry(
            handler, index, model_result_item, prompt_entry, model_name, test_category
        )

        if entry_result["valid"]:
            correct_count += 1
        else:
            result.append(entry_result)

    return save_eval_results(
        result, correct_count, model_result, test_category, model_name, score_dir
    )


def ast_file_runner(
    handler: BaseHandler,
    model_result,
    prompt,
    possible_answer,
    test_category,
    model_name,
    score_dir,
    zhtw_eval_config=None,
):
    assert (
        len(model_result) == len(prompt) == len(possible_answer)
    ), f"The length of the model result ({len(model_result)}) does not match the length of the prompt ({len(prompt)}) or possible answer ({len(possible_answer)}). Please check the input files for completeness."

    if is_java(test_category):
        language = Language.JAVA
        return_format = ReturnFormat.JAVA
    elif is_js(test_category):
        language = Language.JAVASCRIPT
        return_format = ReturnFormat.JAVASCRIPT
    else:
        language = Language.PYTHON
        return_format = ReturnFormat.PYTHON

    result = []
    correct_count = 0
    # For zh_* semantic judge logging and recovery stats
    judge_logs = []
    recovered_count = 0
    for i in range(len(model_result)):
        index = model_result[i]["id"]
        model_result_item = model_result[i]["result"]
        prompt_entry = prompt[i]
        possible_answer_item = possible_answer[i]["ground_truth"]

        entry_result = _evaluate_single_ast_entry(
            handler,
            index,
            model_result_item,
            possible_answer_item,
            prompt_entry,
            model_name,
            test_category,
            language=language,
            return_format=return_format,
            has_tool_call_tag=False,
        )

        # Semantic judge override (only if base evaluation failed and config active)
        if (
            zhtw_eval_config is not None
            and getattr(zhtw_eval_config, "mode", "original") != "original"
            and str(test_category).startswith("zh_")
        ):
            if not entry_result["valid"]:
                # 僅在錯誤訊息包含 "Invalid value for parameter" 時觸發 LLM evaluator
                base_errors = entry_result.get("error", [])
                has_invalid_value_error = False
                if isinstance(base_errors, list):
                    for _e in base_errors:
                        # 直接在頂層字串比對
                        if isinstance(_e, str) and "Invalid value for parameter" in _e:
                            has_invalid_value_error = True
                            break
                        # 平行/多函式錯誤：物件內含有 Model Result Index 與 sub_error 陣列
                        if isinstance(_e, dict):
                            try:
                                # 取第一層 value
                                for _k, _v in _e.items():
                                    if isinstance(_v, dict) and "sub_error" in _v and isinstance(_v["sub_error"], list):
                                        for _se in _v["sub_error"]:
                                            if isinstance(_se, str) and "Invalid value for parameter" in _se:
                                                has_invalid_value_error = True
                                                raise StopIteration  # 跳出多層迴圈
                            except StopIteration:
                                break
                if not has_invalid_value_error:
                    # 非數值內容不符 (如型別錯誤、缺參數、函式名錯誤等) 不進入 LLM 評估
                    pass
                else:
                    try:
                        if zhtw_eval_config.debug:
                            print(f"[semantic_judge] start id={index} category={test_category} mode={zhtw_eval_config.mode}")
                        # Decode predicted and reference function-calling outputs to check function names
                        # Use handler.decode_ast to get structure, then compare first-level keys
                        pred_decoded = handler.decode_ast(model_result_item, return_format, has_tool_call_tag=False)
                        # pred_decoded should be like: [{func: {params...}}, ...]; use first item as primary
                        pred_funcs = [list(d.keys())[0] for d in pred_decoded if isinstance(d, dict) and len(d) == 1]
                        ref_list = possible_answer_item if isinstance(possible_answer_item, list) else [possible_answer_item]
                        ref_funcs_all = []
                        for ref in ref_list:
                            if isinstance(ref, list):
                                # a list like decoded output
                                for d in ref:
                                    if isinstance(d, dict) and len(d) == 1:
                                        ref_funcs_all.append(list(d.keys())[0])
                            elif isinstance(ref, dict) and len(ref) == 1:
                                ref_funcs_all.append(list(ref.keys())[0])

                        # If any predicted function matches any reference function by name, we only judge params
                        func_match = any(f in ref_funcs_all for f in pred_funcs)
                        if not func_match:
                            # No function name match; stick to original failure
                            if zhtw_eval_config.debug:
                                print(f"[semantic_judge] skip param judge due to function-name mismatch. pred={pred_funcs} ref={ref_funcs_all}")
                        else:
                            # Extract param dicts for first matching pair and ask LLM if semantically equivalent
                            decided = None
                            for pf in pred_funcs:
                                if pf in ref_funcs_all:
                                    # find pred params
                                    pred_params = None
                                    for d in pred_decoded:
                                        if isinstance(d, dict) and pf in d:
                                            pred_params = d[pf]
                                            break
                                    if pred_params is None:
                                        continue
                                    # collect all reference params with same func
                                    ref_params_list = []
                                    for ref in ref_list:
                                        items = ref if isinstance(ref, list) else [ref]
                                        for d in items:
                                            if isinstance(d, dict) and pf in d:
                                                ref_params_list.append(d[pf])
                                    # judge against any one reference (OR semantics)
                                    for ref_params in ref_params_list:
                                        judge_bool = semantic_param_judge(zhtw_eval_config, pred_params, ref_params)
                                        judge_logs.append({
                                            "id": index,
                                            "test_category": test_category,
                                            "model_name": model_name,
                                            "judge_mode": zhtw_eval_config.mode,
                                            "judge_backend": getattr(zhtw_eval_config, "judge_backend", None),
                                            "judge_model": getattr(zhtw_eval_config, "model_id", None),
                                            # 保存完整的問題與解答脈絡
                                            "question": prompt_entry.get("question"),
                                            "function_schema": prompt_entry.get("function"),
                                            "model_result_raw": model_result_item,
                                            "prediction_decoded": pred_decoded,
                                            "references_all": ref_list,
                                            # 參數等價評估的實際輸入
                                            "prompt": {
                                                "prediction_params": pred_params,
                                                "reference_params": ref_params,
                                            },
                                            # LLM judge 的輸出（yes/no）
                                            "decision": True if judge_bool is True else False if judge_bool is False else None,
                                            "semantic_scope": "params_only",
                                        })
                                        if judge_bool is True:
                                            entry_result = {"valid": True, "semantic_judge": True, "semantic_scope": "params_only"}
                                            recovered_count += 1
                                            decided = True
                                            break
                                    if decided:
                                        break
                            if zhtw_eval_config.debug:
                                print(f"[semantic_judge] decision id={index} -> {decided}")
                    except Exception as sj_e:
                        # If judge fails, keep original result and tag error
                        entry_result["semantic_judge_error"] = str(sj_e)
                        if zhtw_eval_config.debug:
                            print(f"[semantic_judge] error id={index} err={sj_e}")

        if entry_result["valid"]:
            correct_count += 1
        else:
            result.append(entry_result)

    acc, total = save_eval_results(
        result, correct_count, model_result, test_category, model_name, score_dir
    )

    # If zh_* and judge active, persist judge logs and recovery rate
    if (
        zhtw_eval_config is not None
        and getattr(zhtw_eval_config, "mode", "original") != "original"
        and str(test_category).startswith("zh_")
        and len(judge_logs) > 0
    ):
        # Write JSONL logs per model-category
        safe_model = model_name.replace("/", "_")
        log_file = ZHTW_JUDGE_LOG_PATH / f"{safe_model}__{test_category}__judge_log.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            for entry in judge_logs:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Append recovery rate row into a central CSV
        csv_file = ZHTW_JUDGE_LOG_PATH / "recovery_rate.csv"
        write_header = not csv_file.exists()
        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["model", "category", "recovered", "judged", "recovery_rate"])
            judged = len(judge_logs)
            recovery_rate = (recovered_count / judged) if judged else 0.0
            writer.writerow([safe_model, test_category, recovered_count, judged, recovery_rate])

    return acc, total


#### Main runner function ####
def evaluate_task(
    test_category,
    result_dir,
    score_dir,
    model_result,
    model_name,
    handler,
    leaderboard_table,
    zhtw_eval_config,
    allow_missing: bool = False,
):
    print(f"🔍 Running test: {test_category}")

    record_cost_latency(leaderboard_table, model_name, model_result)

    # Find the corresponding prompt entries
    prompt = load_dataset_entry(
        test_category, include_prereq=False, include_language_specific_hint=False
    )

    if is_relevance_or_irrelevance(test_category):
        prompt, _ = _subset_entries_by_model_ids(
            model_result, prompt, None, allow_missing=allow_missing
        )

        accuracy, total_count = relevance_file_runner(
            handler, model_result, prompt, model_name, test_category, score_dir
        )

    else:
        # Find the corresponding possible answer entries
        possible_answer = load_ground_truth_entry(test_category)
        # Sanity: prompt and ground truth should be 1:1
        assert len(prompt) == len(
            possible_answer
        ), f"Length of ground truth ({len(possible_answer)}) should match prompt entries ({len(prompt)})."

        prompt, possible_answer = _subset_entries_by_model_ids(
            model_result, prompt, possible_answer, allow_missing=allow_missing
        )

        if is_format_sensitivity(test_category):
            accuracy, total_count = format_sensitivity_runner(
                handler,
                model_result,
                prompt,
                possible_answer,
                model_name,
                test_category,
                score_dir,
            )

        elif is_multi_turn(test_category):
            accuracy, total_count = multi_turn_runner(
                handler,
                model_result,
                prompt,
                possible_answer,
                model_name,
                test_category,
                score_dir,
            )

        elif is_agentic(test_category):
            accuracy, total_count = agentic_runner(
                handler,
                model_result,
                prompt,
                possible_answer,
                model_name,
                test_category,
                score_dir,
            )
        # Single turn test
        else:
            accuracy, total_count = ast_file_runner(
                handler,
                model_result,
                prompt,
                possible_answer,
                test_category,
                model_name,
                score_dir,
                zhtw_eval_config=zhtw_eval_config,
            )

    record_result(leaderboard_table, model_name, test_category, accuracy, total_count)

    print(f"✅ Test completed: {test_category}. 🎯 Accuracy: {accuracy:.2%}")

    return leaderboard_table


def runner(model_names, test_categories, result_dir, score_dir, zhtw_eval_config, allow_missing: bool = False):

    # A dictionary to store the evaluation scores.
    # Key is model name, value is a dictionary with keys as test category
    # and values as a dictionary with accuracy and total count.
    # TODO: use defaultdict to initialize the leaderboard table
    leaderboard_table = {}

    # Get a list of all entries in the folder
    entries = result_dir.iterdir()

    # Filter out the subdirectories
    subdirs = [entry for entry in entries if entry.is_dir()]

    # Traverse each subdirectory
    for subdir in tqdm(subdirs, desc="Number of models evaluated"):

        model_name = subdir.relative_to(result_dir).name
        if model_names is not None and model_name not in model_names:
            continue

        model_name_escaped = model_name.replace("_", "/")

        print(f"🦍 Model: {model_name}")

        # Find and process all result JSON files recursively in the subdirectory
        for model_result_json in subdir.rglob(RESULT_FILE_PATTERN):
            test_category = extract_test_category(model_result_json)
            if test_category not in test_categories:
                continue

            handler = get_handler(model_name_escaped)

            # We don't evaluate the following categories in the current iteration of the benchmark
            if (
                is_chatable(test_category)
                or is_sql(test_category)
                or is_executable(test_category)
                or is_memory_prereq(test_category)
            ):
                continue

            model_result = load_file(model_result_json, sort_by_id=True)

            leaderboard_table = evaluate_task(
                test_category,
                result_dir,
                score_dir,
                model_result,
                model_name,
                handler,
                leaderboard_table,
                zhtw_eval_config,
                allow_missing=allow_missing,
            )

    # This function reads all the score files from local folder and updates the
    # leaderboard table. This is helpful when you only want to run the
    # evaluation for a subset of models and test categories.
    update_leaderboard_table_with_local_score_file(leaderboard_table, score_dir)
    # Write the leaderboard table to a file
    generate_leaderboard_csv(leaderboard_table, score_dir)


def main(
    model,
    test_categories,
    result_dir,
    score_dir,
    partial_eval: bool = False,
    zhtw_eval="original",
    zhtw_judge_backend="auto",
    zhtw_vllm_tp=1,
    zhtw_vllm_dtype="auto",
    zhtw_judge_debug=False,
):
    if result_dir is None:
        result_dir = RESULT_PATH
    else:
        result_dir = (PROJECT_ROOT / result_dir).resolve()

    if score_dir is None:
        score_dir = SCORE_PATH
    else:
        score_dir = (PROJECT_ROOT / score_dir).resolve()

    if type(test_categories) is not list:
        test_categories = [test_categories]

    all_test_categories = parse_test_category_argument(test_categories)

    model_names = None
    if model:
        model_names = []
        for model_name in model:
            if model_name not in MODEL_CONFIG_MAPPING:
                raise ValueError(f"Invalid model name '{model_name}'.")
            # Runner takes in the model name that contains "_", instead of "/", for the sake of file path issues.
            # This is differnet than the model name format that the generation script "openfunctions_evaluation.py" takes in (where the name contains "/").
            # We patch it here to avoid confusing the user.
            model_names.append(model_name.replace("/", "_"))

    # Driver function to run the evaluation for all categories involved.
    # zhtw_eval is currently handled inside runner/evaluate_task in future extension; for now we just propagate.
    # TODO: integrate semantic judge path when zhtw_eval != 'original'
    zhtw_eval_config = parse_zhtw_eval_arg(
        zhtw_eval,
        judge_backend=zhtw_judge_backend,
        vllm_tp=int(zhtw_vllm_tp),
        vllm_dtype=str(zhtw_vllm_dtype),
        debug=bool(zhtw_judge_debug),
    )
    runner(model_names, all_test_categories, result_dir, score_dir, zhtw_eval_config, allow_missing=partial_eval)

    print(
        f"🏁 Evaluation completed. See {score_dir / 'data_overall.csv'} for overall evaluation results on BFCL V4."
    )
    if partial_eval:
        print(
            "⚠️  Partial evaluation for a single category is enabled (--partial-run flag is set). Accuracy scores are computed only on the subset of entries present in the model result files, which may differ from a full evaluation and from the official leaderboard score."
        )
    print(
        f"See {score_dir / 'data_live.csv'}, {score_dir / 'data_non_live.csv'}, {score_dir / 'data_multi_turn.csv'}, {score_dir / 'data_agentic.csv'} and {score_dir / 'data_format_sensitivity.csv'} for detailed evaluation results on each sub-section categories respectively."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process two lists of strings.")

    # Add arguments for two lists of strings
    parser.add_argument(
        "--model", nargs="+", type=str, help="A list of model names to evaluate"
    )
    parser.add_argument(
        "--test-category",
        nargs="+",
        type=str,
        default="all",
        help="A list of test categories to run the evaluation on",
    )
    parser.add_argument(
        "--result-dir",
        default=None,
        type=str,
        help="Path to the folder where the model response files are stored; relative to the `berkeley-function-call-leaderboard` root folder",
    )
    parser.add_argument(
        "--score-dir",
        default=None,
        type=str,
        help="Path to the folder where the evaluation score files will be stored; relative to the `berkeley-function-call-leaderboard` root folder",
    )
    parser.add_argument(
        "--partial-eval",
        default=False,
        action="store_true",
        help="Run evaluation on a partial set of benchmark entries (eg. entries present in the model result files) without raising for missing IDs.",
    )

    args = parser.parse_args()

    load_dotenv(dotenv_path=DOTENV_PATH, verbose=True, override=True)  # Load the .env file
    main(
        args.model,
        args.test_category,
        args.result_dir,
        args.score_dir,
        partial_eval=args.partial_eval,
    )
