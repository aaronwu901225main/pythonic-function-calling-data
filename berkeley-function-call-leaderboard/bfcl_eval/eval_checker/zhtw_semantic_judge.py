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

# Optional HF backends
try:  # pragma: no cover
    import vllm  # type: ignore
    from vllm import LLM
    from vllm.sampling_params import SamplingParams
    _HAS_VLLM = True
except Exception:  # pragma: no cover
    _HAS_VLLM = False

try:  # pragma: no cover
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    _HAS_TRANSFORMERS = True
except Exception:  # pragma: no cover
    _HAS_TRANSFORMERS = False

JUDGE_SYSTEM_PROMPT = (
    "你是一個函式呼叫語義評測助手。\n"
    "給你: 問題(question)、函式描述與參數(schema)、模型輸出的函式呼叫(prediction)、以及一組可能正確的參考函式呼叫(reference list)。\n"
    "請判斷 prediction 是否在語義上滿足問題需求並且符合函式描述 (參數型別/意圖)，且與任一 reference 在功能與關鍵參數值上等價。\n"
    "只允許輸出 yes 或 no。不要加解釋。若 prediction 明顯不符合、缺重要參數、型別錯誤或語義偏離，就回答 no。\n"
)

@dataclass
class JudgeConfig:
    mode: str  # 'original' | 'openai' | 'hf'
    model_id: Optional[str] = None
    judge_backend: str = "auto"   # for HF: auto|vllm|transformers
    vllm_tp: int = 1
    vllm_dtype: str = "auto"
    debug: bool = False


def parse_zhtw_eval_arg(arg: str, judge_backend: str = "auto", vllm_tp: int = 1, vllm_dtype: str = "auto", debug: bool = False) -> JudgeConfig:
    if arg == "original":
        return JudgeConfig(mode="original", judge_backend=judge_backend, vllm_tp=vllm_tp, vllm_dtype=vllm_dtype, debug=debug)
    # Detect openai
    if arg.startswith("openai:"):
        model_id = arg.split(":",1)[1]
        return JudgeConfig(mode="openai", model_id=model_id, judge_backend=judge_backend, vllm_tp=vllm_tp, vllm_dtype=vllm_dtype, debug=debug)
    # Heuristic: if looks like a known OpenAI model id, treat as openai
    if any(prefix in arg for prefix in ["gpt-", "o4", "o3", "text-"]):
        return JudgeConfig(mode="openai", model_id=arg, judge_backend=judge_backend, vllm_tp=vllm_tp, vllm_dtype=vllm_dtype, debug=debug)
    # Otherwise treat as HF local model id
    return JudgeConfig(mode="hf", model_id=arg, judge_backend=judge_backend, vllm_tp=vllm_tp, vllm_dtype=vllm_dtype, debug=debug)


def build_judge_prompt_text(question: str, function_doc: List[Dict[str, Any]], prediction: Any, references: List[Any]) -> str:
    payload = {
        "question": question,
        "function": function_doc,
        "prediction": prediction,
        "references": references,
    }
    return (
        JUDGE_SYSTEM_PROMPT
        + "以下是輸入的 JSON：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n請你只輸出 yes 或 no："
    )


def openai_judge(client: Any, model: str, prompt_text: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        temperature=0,
        max_tokens=4,
    )
    text = (resp.choices[0].message.content or "").strip().lower()
    return "yes" if text.startswith("yes") else "no"


class _HFJudgeEngine:
    def __init__(self, model_id: str, judge_backend: str = "auto", vllm_tp: int = 1, vllm_dtype: str = "auto"):
        self.model_id = model_id
        self.backend = judge_backend  # auto|vllm|transformers
        self.vllm_tp = vllm_tp
        self.vllm_dtype = vllm_dtype
        self._init_backend()

    def _init_backend(self):  # pragma: no cover
        prefer_vllm = (self.backend in ("auto", "vllm")) and _HAS_VLLM
        if prefer_vllm:
            # vLLM engine
            self.vllm_engine = LLM(model=self.model_id, tensor_parallel_size=self.vllm_tp, dtype=self.vllm_dtype)
            self.vllm_sampling = SamplingParams(temperature=0.0, max_tokens=4)
            self._mode = "vllm"
            return

        if _HAS_TRANSFORMERS:
            # Transformers engine
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, use_fast=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto",
            )
            self._mode = "transformers"
            return

        raise RuntimeError("Neither vLLM nor transformers is available for HF judge.")

    def judge(self, prompt_text: str) -> str:
        if self._mode == "vllm":  # pragma: no cover
            outputs = self.vllm_engine.generate([prompt_text], self.vllm_sampling)
            text = outputs[0].outputs[0].text.strip().lower()
            return "yes" if text.startswith("yes") else "no"
        # transformers
        inputs = self.tokenizer(prompt_text, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            gen = self.model.generate(
                **inputs,
                max_new_tokens=4,
                do_sample=False,
                temperature=0.0,
                eos_token_id=self.tokenizer.eos_token_id,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        out = self.tokenizer.decode(gen[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        text = out.strip().lower()
        return "yes" if text.startswith("yes") else "no"


def semantic_judge(config: JudgeConfig, question: str, function_doc: List[Dict[str,Any]], prediction: Any, references: List[Any]) -> Optional[bool]:
    """Return True/False if judged, or None if fallback to original pipeline."""
    if config.mode == "original":
        return None
    prompt_text = build_judge_prompt_text(question, function_doc, prediction, references)
    if config.mode == "openai":
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for openai judge mode")
        client = OpenAI(api_key=api_key)
        result = openai_judge(client, config.model_id, prompt_text)
        return True if result == "yes" else False
    if config.mode == "hf":
        # Lazy singleton per model id
        global _HF_ENGINES
        if '_HF_ENGINES' not in globals():
            _HF_ENGINES = {}
        engine = _HF_ENGINES.get((config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype))
        if engine is None:
            engine = _HFJudgeEngine(config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype)
            _HF_ENGINES[(config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype)] = engine
        result = engine.judge(prompt_text)
        return True if result == "yes" else False
    return None