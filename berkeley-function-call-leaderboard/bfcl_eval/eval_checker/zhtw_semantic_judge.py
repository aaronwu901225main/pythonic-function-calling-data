"""Semantic (zh-TW) function-call evaluation helper.

This module provides a unified interface to judge whether a model predicted function call
(its arguments) semantically satisfies the function description and matches any of the
reference (possible) answers, using a secondary LLM judge. The judge must output strictly
"yes" or "no" (lowercase) so we can aggregate accuracy.

Modes:
1. original -> bypass semantic judge; rely on existing exact matching pipeline.
2. HF local model id (e.g. meta-llama/Llama-3.1-8B-Instruct) -> launch vLLM / use existing endpoint (future work).
3. OpenAI model id or prefixed openai:MODEL -> call OpenAI ChatCompletion API (requires OPENAI_API_KEY).

The integration point will be inside eval_runner.* runners after decoding predictions but before
calling traditional matchers, when zhtw_eval != original.

For now we implement a minimal abstraction + OpenAI path. vLLM path is left as TODO.
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

try:
    from openai import OpenAI  # openai>=1.x
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

JUDGE_SYSTEM_PROMPT = (
    "你是一個函式呼叫語義評測助手。給你: 問題(question)、函式描述與參數(schema)、模型輸出的函式呼叫(prediction)、以及一組可能正確的參考函式呼叫(reference list)。"\
    "請判斷 prediction 是否在語義上滿足問題需求並且符合函式描述 (參數型別/意圖)，且與任一 reference 在功能與關鍵參數值上等價。"\
    "只允許輸出 yes 或 no。不要加解釋。若 prediction 明顯不符合、缺重要參數、型別錯誤或語義偏離，就回答 no。"\
)

@dataclass
class JudgeConfig:
    mode: str  # 'original' | 'openai' | 'hf'
    model_id: Optional[str] = None


def parse_zhtw_eval_arg(arg: str) -> JudgeConfig:
    if arg == "original":
        return JudgeConfig(mode="original")
    # Detect openai
    if arg.startswith("openai:"):
        model_id = arg.split(":",1)[1]
        return JudgeConfig(mode="openai", model_id=model_id)
    # Heuristic: if looks like a known OpenAI model id, treat as openai
    if any(prefix in arg for prefix in ["gpt-", "o4", "o3", "text-"]):
        return JudgeConfig(mode="openai", model_id=arg)
    # Otherwise treat as HF local model id (vLLM)
    return JudgeConfig(mode="hf", model_id=arg)


def build_judge_messages(question: str, function_doc: List[Dict[str, Any]], prediction: Any, references: List[Any]) -> List[Dict[str,str]]:
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "question": question,
            "function": function_doc,
            "prediction": prediction,
            "references": references,
        }, ensure_ascii=False, indent=2)},
    ]


def openai_judge(client: OpenAI, model: str, messages: List[Dict[str,str]]) -> str:
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0)
    text = resp.choices[0].message.content.strip().lower()
    return "yes" if text.startswith("yes") else "no"


def semantic_judge(config: JudgeConfig, question: str, function_doc: List[Dict[str,Any]], prediction: Any, references: List[Any]) -> Optional[bool]:
    """Return True/False if judged, or None if fallback to original pipeline."""
    if config.mode == "original":
        return None
    messages = build_judge_messages(question, function_doc, prediction, references)
    if config.mode == "openai":
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for openai judge mode")
        client = OpenAI(api_key=api_key)
        result = openai_judge(client, config.model_id, messages)
        return True if result == "yes" else False
    if config.mode == "hf":
        # TODO: integrate local vLLM inference (launch or reuse endpoint)
        # For now return None to fall back so we don't break existing flow.
        return None
    return None