"""OpenAI API utilities with automatic key rotation for token limits.

This module provides a unified interface to call OpenAI Chat Completions API
with automatic API key rotation when daily token limits are approached.

Rotation logic:
- Provide multiple keys via OPENAI_API_KEYS (comma-separated) or OPENAI_API_KEY (single key).
- Track daily token usage in .api_usage_daily.json using ISO date.
- Reset at 08:00 instead of 00:00 (to match OpenAI's free tier reset time).
- Rotate to next key when current key usage >= (API_DAILY_LIMIT_TOKENS - API_ROTATE_MARGIN).
- Defaults: limit=2_500_000, margin=25_000.

Environment variables:
- OPENAI_API_KEYS: Comma-separated list of API keys (preferred)
- OPENAI_API_KEY: Single API key (fallback)
- API_DAILY_LIMIT_TOKENS: Token limit per key per day (default: 2500000)
- API_ROTATE_MARGIN: Margin before rotating (default: 25000)
- API_USAGE_FILE: Path to usage tracking file (default: .api_usage_daily.json)
- API_ROTATE_VERBOSE: Set to "1" for verbose logging
- OPENAI_MODEL: Default model to use (default: gpt-4o-mini)
- OPENAI_TEMPERATURE: Default temperature (default: 0.7)
- OPENAI_MAX_TOKENS: Max tokens for completion (optional)
- OPENAI_MAX_TOKENS_FIELD: Field name for max tokens (default: max_completion_tokens)
"""
from __future__ import annotations
import os
import json
import datetime
import fcntl
import threading
from typing import Dict, List, Any, Optional

try:
    from dotenv import load_dotenv  # optional
    load_dotenv()
except Exception:
    pass

# Global lock for thread-safe usage file access
_usage_file_lock = threading.Lock()


def _estimate_tokens(text: str) -> int:
    """Rough token estimation fallback when API doesn't return usage.
    Uses 4 characters per token heuristic."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def _load_usage_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_usage_file(path: str, data: Dict[str, Any]) -> None:
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def _atomic_update_usage(path: str, key: str, today: str, tokens: int) -> int:
    """Thread-safe and process-safe atomic update of usage file.
    Returns the new total for this key today."""
    with _usage_file_lock:  # Thread lock
        try:
            # Use file lock for cross-process safety
            lock_path = path + ".lock"
            with open(lock_path, "w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    # Read current data
                    usage_data = _load_usage_file(path)
                    if today not in usage_data:
                        usage_data[today] = {}
                    # Update
                    current = int(usage_data[today].get(key, 0))
                    new_total = current + int(tokens)
                    usage_data[today][key] = new_total
                    # Write back
                    _save_usage_file(path, usage_data)
                    return new_total
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            # Fallback: just try to update without lock
            usage_data = _load_usage_file(path)
            if today not in usage_data:
                usage_data[today] = {}
            current = int(usage_data[today].get(key, 0))
            new_total = current + int(tokens)
            usage_data[today][key] = new_total
            _save_usage_file(path, usage_data)
            return new_total


def _select_api_key(usage: Dict[str, Any], keys: List[str], limit: int, margin: int, today: str) -> str:
    """Select an API key that has not exceeded the daily limit.
    Returns the first key that is under the threshold, or the last key if all exceeded."""
    if today not in usage:
        usage[today] = {}
    day_usage = usage[today]
    for k in keys:
        used = int(day_usage.get(k, 0))
        if used < max(0, limit - margin):
            return k
    # All exceeded threshold; return the last key (continue but will go over)
    return keys[-1]


def _get_today_key() -> str:
    """Get the date key for today, reset at 08:00 instead of 00:00."""
    now = datetime.datetime.now()
    if now.hour < 8:
        # Before 08:00, use yesterday's date
        return (now.date() - datetime.timedelta(days=1)).isoformat()
    else:
        # After 08:00, use today's date
        return now.date().isoformat()


def get_api_keys() -> List[str]:
    """Get list of API keys from environment variables.
    Prioritizes OPENAI_API_KEYS (comma-separated), falls back to OPENAI_API_KEY.
    Ignores 'stop' as a special terminator key."""
    keys_env = os.getenv("OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEY", "")
    keys = [k.strip() for k in keys_env.split(",") if k.strip() and k.strip().lower() != "stop"]
    return keys


def get_rotating_client(usage_path: Optional[str] = None) -> tuple:
    """Get an OpenAI client with the currently active key.
    
    Returns:
        tuple: (client, active_key, limit, margin, today, usage_path)
    
    Usage:
        client, key, limit, margin, today, path = get_rotating_client()
        # ... use client to make API calls ...
        # After call, update usage with:
        # _atomic_update_usage(path, key, today, total_tokens)
    """
    from openai import OpenAI
    
    keys = get_api_keys()
    if not keys:
        raise RuntimeError("No OpenAI API keys provided. Set OPENAI_API_KEY or OPENAI_API_KEYS.")
    
    limit = int(os.getenv("API_DAILY_LIMIT_TOKENS", "2500000"))
    margin = int(os.getenv("API_ROTATE_MARGIN", "25000"))
    path = usage_path or os.getenv("API_USAGE_FILE", ".api_usage_daily.json")
    today = _get_today_key()
    
    usage_data = _load_usage_file(path)
    active_key = _select_api_key(usage_data, keys, limit, margin, today)
    
    client = OpenAI(api_key=active_key)
    return client, active_key, limit, margin, today, path


def update_usage_after_call(
    active_key: str,
    today: str,
    usage_path: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: Optional[int] = None,
    limit: int = 2500000,
    margin: int = 25000,
) -> int:
    """Update usage after an API call.
    
    Args:
        active_key: The API key used for the call
        today: The date key (from get_rotating_client)
        usage_path: Path to usage file (from get_rotating_client)
        prompt_tokens: Number of prompt tokens used
        completion_tokens: Number of completion tokens used
        total_tokens: Total tokens (if None, computed from prompt + completion)
        limit: Daily token limit
        margin: Rotation margin
    
    Returns:
        int: New total usage for this key today
    """
    if total_tokens is None:
        total_tokens = prompt_tokens + completion_tokens
    
    new_total = _atomic_update_usage(usage_path, active_key, today, total_tokens)
    
    # Optional verbose logging
    if os.getenv("API_ROTATE_VERBOSE", "0") == "1":
        over = new_total >= max(0, limit - margin)
        print(f"[api-rotate] key=***{active_key[-4:]} used={new_total} tokens (added {total_tokens}) limit={limit} rotate_next={over}")
    
    return new_total


def chat_complete(
    prompt: str,
    model: Optional[str] = None,
    system: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Call OpenAI Chat Completions with automatic API key rotation.
    
    Rotation logic:
    - Provide multiple keys via OPENAI_API_KEYS (comma-separated).
    - Track daily token usage in .api_usage_daily.json using ISO date.
    - Rotate to next key when current key usage >= (API_DAILY_LIMIT_TOKENS - API_ROTATE_MARGIN).
    Defaults: limit=2_500_000, margin=25_000.
    
    Args:
        prompt: The user prompt
        model: Model to use (default: from OPENAI_MODEL env or gpt-4o-mini)
        system: Optional system message
        temperature: Temperature for sampling (default: from OPENAI_TEMPERATURE env or 0.7)
        max_tokens: Max tokens for completion (optional)
    
    Returns:
        str: The model's response content
    """
    from openai import OpenAI
    
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if temperature is None:
        temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    
    client, active_key, limit, margin, today, usage_path = get_rotating_client()
    
    # Build messages
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    
    if max_tokens:
        max_tokens_field = os.getenv("OPENAI_MAX_TOKENS_FIELD", "max_completion_tokens")
        if max_tokens_field == "max_tokens":
            kwargs["max_tokens"] = max_tokens
        else:
            kwargs["max_completion_tokens"] = max_tokens
    elif os.getenv("OPENAI_MAX_TOKENS"):
        try:
            max_tokens_value = int(os.getenv("OPENAI_MAX_TOKENS"))
            max_tokens_field = os.getenv("OPENAI_MAX_TOKENS_FIELD", "max_completion_tokens")
            if max_tokens_field == "max_tokens":
                kwargs["max_tokens"] = max_tokens_value
            else:
                kwargs["max_completion_tokens"] = max_tokens_value
        except ValueError:
            pass
    
    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    
    # Usage accounting
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    try:
        usage_obj = getattr(resp, "usage", None)
        if usage_obj:
            prompt_tokens = getattr(usage_obj, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage_obj, "completion_tokens", 0) or 0
            total_tokens = getattr(usage_obj, "total_tokens", prompt_tokens + completion_tokens) or 0
        else:
            # Fallback estimation
            prompt_tokens = _estimate_tokens(prompt)
            completion_tokens = _estimate_tokens(content)
            total_tokens = prompt_tokens + completion_tokens
    except Exception:
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(content)
        total_tokens = prompt_tokens + completion_tokens
    
    # Atomic update with file locking (thread-safe and process-safe)
    update_usage_after_call(
        active_key, today, usage_path,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        limit=limit,
        margin=margin,
    )
    
    return content


def get_usage_summary(usage_path: Optional[str] = None) -> Dict[str, Any]:
    """Get a summary of current API usage.
    
    Returns:
        Dict with keys:
        - today: The current date key
        - usage_by_key: Dict mapping each API key to its usage today
        - total_today: Total tokens used today across all keys
        - limit_per_key: Token limit per key
        - keys_available: Number of keys that haven't exceeded limit
    """
    path = usage_path or os.getenv("API_USAGE_FILE", ".api_usage_daily.json")
    today = _get_today_key()
    limit = int(os.getenv("API_DAILY_LIMIT_TOKENS", "2500000"))
    margin = int(os.getenv("API_ROTATE_MARGIN", "25000"))
    
    keys = get_api_keys()
    usage_data = _load_usage_file(path)
    
    day_usage = usage_data.get(today, {})
    
    usage_by_key = {}
    total_today = 0
    keys_available = 0
    
    for k in keys:
        used = int(day_usage.get(k, 0))
        # Mask key for display
        masked_key = f"***{k[-4:]}" if len(k) > 4 else "****"
        usage_by_key[masked_key] = {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "exceeded": used >= max(0, limit - margin),
        }
        total_today += used
        if used < max(0, limit - margin):
            keys_available += 1
    
    return {
        "today": today,
        "usage_by_key": usage_by_key,
        "total_today": total_today,
        "limit_per_key": limit,
        "keys_count": len(keys),
        "keys_available": keys_available,
    }
