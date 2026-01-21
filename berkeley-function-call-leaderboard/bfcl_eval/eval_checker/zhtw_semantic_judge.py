"""Semantic (zh-TW) function-call evaluation helper.

This module provides a unified interface to judge whether a model predicted function call
(its arguments) semantically satisfies the function description and matches any of the
reference (possible) answers, using a secondary LLM judge. The judge must output strictly
"yes" or "no" (lowercase) so we can aggregate accuracy.

Modes:
1. original -> bypass semantic judge; rely on existing exact matching pipeline.
2. HF local model id (e.g. meta-llama/Llama-3.1-8B-Instruct) -> launch vLLM / use existing endpoint (future work).
3. OpenAI model id or prefixed openai:MODEL -> call OpenAI ChatCompletion API (requires OPENAI_API_KEY or OPENAI_API_KEYS).

The integration point will be inside eval_runner.* runners after decoding predictions but before
calling traditional matchers, when zhtw_eval != original.

For now we implement a minimal abstraction + OpenAI path. vLLM path is left as TODO.

API Key Rotation (for OpenAI mode):
- Provide multiple keys via OPENAI_API_KEYS (comma-separated) for automatic rotation.
- Track daily token usage in .api_usage_daily.json.
- Reset at 08:00 instead of 00:00 (matching OpenAI's free tier reset).
- Rotate to next key when usage >= (API_DAILY_LIMIT_TOKENS - API_ROTATE_MARGIN).
- Defaults: limit=2_500_000, margin=25_000.
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass
import subprocess
from typing import List, Dict, Any, Optional

# Import our API key rotation utilities
try:
    from .openai_utils import (
        get_rotating_client,
        update_usage_after_call,
        _estimate_tokens,
        get_usage_summary,
    )
    _HAS_OPENAI_UTILS = True
except ImportError:
    _HAS_OPENAI_UTILS = False

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

# 更嚴格的 multi-turn 規則：逐回合全覆蓋
JUDGE_SYSTEM_PROMPT_MULTI_TURN = (
    "你是一個多輪函式呼叫語義評測助手。\n"
    "你將收到: 問題(question)、函式描述與參數(schema)、模型在每一回合的函式呼叫(prediction_by_turn)、以及每一回合的參考函式呼叫(reference_by_turn)。\n"
    "評分準則：\n"
    "1) 必須逐回合檢查；每一回合都需要覆蓋該回合參考中的所有必要操作，允許等價/同義替代與輕微格式/單位差異。\n"
    "2) 若某回合缺少必要步驟、或關鍵參數錯誤、或導致狀態上不可能與參考等價，則整題回答 no。\n"
    "3) 僅輸出 yes 或 no，禁止任何解釋。\n"
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


def build_param_judge_prompt_text(pred_params: Dict[str, Any], ref_params: Dict[str, Any]) -> str:
    payload = {
        "prediction_params": pred_params,
        "reference_params": ref_params,
    }
    return (
        "你是一個函式參數語義等價判定助手。給定兩組參數 (A 為模型預測、B 為參考答案)，"  # zh-TW
        "請判斷 A 與 B 是否在語義上等價，能導致相同的函式意圖與結果。"
        "允許表述差異、同義替換、單位/格式等小差異，但若關鍵資訊缺失或語義偏離則視為不等價。\n\n"
        "以下是 JSON：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n請你只輸出 yes 或 no："
    )


def build_multi_turn_judge_prompt_text(question: str, function_doc: List[Dict[str, Any]], prediction_by_turn: List[Any], references_by_turn: List[Any]) -> str:
    payload = {
        "question": question,
        "function": function_doc,
        "prediction_by_turn": prediction_by_turn,
        "reference_by_turn": references_by_turn,
        "rule": "逐回合全覆蓋；每回合都需涵蓋參考的所有必要操作，允許語義等價替代；任一回合缺少關鍵步驟則判 no。",
    }
    return (
        JUDGE_SYSTEM_PROMPT_MULTI_TURN
        + "以下是輸入的 JSON：\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n請你只輸出 yes 或 no："
    )


def openai_judge(client: Any, model: str, prompt_text: str, active_key: str = None, today: str = None, usage_path: str = None, limit: int = 2500000, margin: int = 25000) -> str:
    """Call OpenAI to judge the prompt. Tracks token usage if rotation info is provided."""
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
    
    # Track usage if rotation info is provided
    if active_key and today and usage_path and _HAS_OPENAI_UTILS:
        try:
            usage_obj = getattr(resp, "usage", None)
            if usage_obj:
                prompt_tokens = getattr(usage_obj, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage_obj, "completion_tokens", 0) or 0
                total_tokens = getattr(usage_obj, "total_tokens", prompt_tokens + completion_tokens) or 0
            else:
                # Fallback estimation
                prompt_tokens = _estimate_tokens(prompt_text)
                completion_tokens = _estimate_tokens(text)
                total_tokens = prompt_tokens + completion_tokens
            
            update_usage_after_call(
                active_key, today, usage_path,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                limit=limit,
                margin=margin,
            )
        except Exception:
            pass  # Don't fail the judge if usage tracking fails
    
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
            # Auto-detect GPU count if tp is not explicitly >1
            tp = self.vllm_tp
            if tp is None or tp <= 1:
                tp = self._auto_detect_gpu_count()
            if tp <= 0:
                tp = 1
            self.vllm_engine = LLM(model=self.model_id, tensor_parallel_size=tp, dtype=self.vllm_dtype)
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

    def _auto_detect_gpu_count(self) -> int:
        # Prefer torch if available
        try:
            import torch as _torch  # local import to avoid global dependency when unused
            if _torch.cuda.is_available():
                cnt = _torch.cuda.device_count()
                if isinstance(cnt, int) and cnt > 0:
                    return cnt
        except Exception:
            pass
        # Fallback to nvidia-smi
        try:
            out = subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.STDOUT, text=True)
            # each line usually describes a GPU
            lines = [l for l in out.strip().splitlines() if l.strip()]
            if len(lines) > 0:
                return len(lines)
        except Exception:
            pass
        return 1


def semantic_judge(config: JudgeConfig, question: str, function_doc: List[Dict[str,Any]], prediction: Any, references: List[Any]) -> Optional[bool]:
    """Return True/False if judged, or None if fallback to original pipeline."""
    if config.mode == "original":
        return None
    prompt_text = build_judge_prompt_text(question, function_doc, prediction, references)
    if config.mode == "openai":
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        
        # Use API key rotation if available
        if _HAS_OPENAI_UTILS:
            try:
                client, active_key, limit, margin, today, usage_path = get_rotating_client()
                result = openai_judge(
                    client, config.model_id, prompt_text,
                    active_key=active_key, today=today, usage_path=usage_path,
                    limit=limit, margin=margin
                )
                return True if result == "yes" else False
            except Exception as e:
                if config.debug:
                    print(f"[zhtw-judge] API rotation failed, falling back: {e}")
                # Fall through to legacy method
        
        # Legacy: single API key
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


def semantic_param_judge(config: JudgeConfig, pred_params: Dict[str, Any], ref_params: Dict[str, Any]) -> Optional[bool]:
    """Compare only parameters for semantic equivalence. Return True/False or None if not executed."""
    if config.mode == "original":
        return None
    prompt_text = build_param_judge_prompt_text(pred_params, ref_params)
    if config.mode == "openai":
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        
        # Use API key rotation if available
        if _HAS_OPENAI_UTILS:
            try:
                client, active_key, limit, margin, today, usage_path = get_rotating_client()
                result = openai_judge(
                    client, config.model_id, prompt_text,
                    active_key=active_key, today=today, usage_path=usage_path,
                    limit=limit, margin=margin
                )
                return True if result == "yes" else False
            except Exception as e:
                if config.debug:
                    print(f"[zhtw-judge] API rotation failed, falling back: {e}")
                # Fall through to legacy method
        
        # Legacy: single API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for openai judge mode")
        client = OpenAI(api_key=api_key)
        result = openai_judge(client, config.model_id, prompt_text)
        return True if result == "yes" else False
    if config.mode == "hf":
        global _HF_ENGINES
        if '_HF_ENGINES' not in globals():
            _HF_ENGINES = {}
        key = (config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype)
        engine = _HF_ENGINES.get(key)
        if engine is None:
            engine = _HFJudgeEngine(config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype)
            _HF_ENGINES[key] = engine
        result = engine.judge(prompt_text)
        return True if result == "yes" else False
    return None


def semantic_multi_turn_judge(config: JudgeConfig, question: str, function_doc: List[Dict[str, Any]], prediction_by_turn: List[Any], references_by_turn: List[Any]) -> Optional[bool]:
    """Multi-turn judge enforcing per-turn full-coverage semantics. Return True/False if judged, or None if fallback."""
    if config.mode == "original":
        return None
    prompt_text = build_multi_turn_judge_prompt_text(question, function_doc, prediction_by_turn, references_by_turn)
    if config.mode == "openai":
        if OpenAI is None:
            raise RuntimeError("openai package not available")
        
        # Use API key rotation if available
        if _HAS_OPENAI_UTILS:
            try:
                client, active_key, limit, margin, today, usage_path = get_rotating_client()
                result = openai_judge(
                    client, config.model_id, prompt_text,
                    active_key=active_key, today=today, usage_path=usage_path,
                    limit=limit, margin=margin
                )
                return True if result == "yes" else False
            except Exception as e:
                if config.debug:
                    print(f"[zhtw-judge] API rotation failed, falling back: {e}")
                # Fall through to legacy method
        
        # Legacy: single API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for openai judge mode")
        client = OpenAI(api_key=api_key)
        result = openai_judge(client, config.model_id, prompt_text)
        return True if result == "yes" else False
    if config.mode == "hf":
        global _HF_ENGINES
        if '_HF_ENGINES' not in globals():
            _HF_ENGINES = {}
        key = (config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype)
        engine = _HF_ENGINES.get(key)
        if engine is None:
            engine = _HFJudgeEngine(config.model_id, config.judge_backend, config.vllm_tp, config.vllm_dtype)
            _HF_ENGINES[key] = engine
        result = engine.judge(prompt_text)
        return True if result == "yes" else False
    return None