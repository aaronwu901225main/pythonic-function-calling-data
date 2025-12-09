import os
import re
import json
import datetime
from typing import Dict, List, Any

try:
    from dotenv import load_dotenv  # optional
    load_dotenv()
except Exception:
    pass

# Simple template rendering: replace {{var}} with value

def render_template(template_path: str, variables: Dict[str, str]) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    for k, v in variables.items():
        content = content.replace("{{" + k + "}}", str(v))
    return content


def extract_tags(text: str, tag: str) -> List[str]:
    pattern = re.compile(rf"<{tag}>(.*?)</{tag}>", re.DOTALL | re.IGNORECASE)
    return [m.strip() for m in pattern.findall(text or "")] 


# Minimal OpenAI chat wrapper

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
        return json.load(open(path, "r", encoding="utf-8"))
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


def _select_api_key(usage: Dict[str, Any], keys: List[str], limit: int, margin: int, today: str) -> str:
    # Ensure structures
    if today not in usage:
        usage[today] = {}
    day_usage = usage[today]
    for k in keys:
        used = int(day_usage.get(k, 0))
        if used < max(0, limit - margin):
            return k
    # All exceeded threshold; return the last key (continue but will go over)
    return keys[-1]


def chat_complete(prompt: str, model: str | None = None, system: str | None = None) -> str:
    """Call OpenAI Chat Completions with automatic API key rotation.

    Rotation logic:
    - Provide multiple keys via OPENAI_API_KEYS (comma-separated).
    - Track daily token usage in .api_usage_daily.json using ISO date.
    - Rotate to next key when current key usage >= (API_DAILY_LIMIT_TOKENS - API_ROTATE_MARGIN).
    Defaults: limit=2_500_000, margin=25_000.
    """
    from openai import OpenAI

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Collect keys
    keys_env = os.getenv("OPENAI_API_KEYS") or os.getenv("OPENAI_API_KEY", "")
    keys = [k.strip() for k in keys_env.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("No OpenAI API keys provided. Set OPENAI_API_KEY or OPENAI_API_KEYS.")

    limit = int(os.getenv("API_DAILY_LIMIT_TOKENS", "2500000"))
    margin = int(os.getenv("API_ROTATE_MARGIN", "25000"))
    usage_path = os.getenv("API_USAGE_FILE", ".api_usage_daily.json")
    
    # Reset at 08:00 instead of 00:00
    now = datetime.datetime.now()
    if now.hour < 8:
        # Before 08:00, use yesterday's date
        today = (now.date() - datetime.timedelta(days=1)).isoformat()
    else:
        # After 08:00, use today's date
        today = now.date().isoformat()
    
    usage_data = _load_usage_file(usage_path)

    active_key = _select_api_key(usage_data, keys, limit, margin, today)
    os.environ["OPENAI_API_KEY"] = active_key  # ensure client picks this key

    # Build messages
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
    }

    max_tokens_env = os.getenv("OPENAI_MAX_TOKENS")
    if max_tokens_env:
        try:
            max_tokens_value = int(max_tokens_env)
            max_tokens_field = os.getenv("OPENAI_MAX_TOKENS_FIELD", "max_completion_tokens")
            if max_tokens_field == "max_tokens":
                kwargs["max_tokens"] = max_tokens_value
            else:
                kwargs["max_completion_tokens"] = max_tokens_value
        except ValueError:
            pass

    client = OpenAI()
    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""

    # Usage accounting
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    try:
        # Newer responses may have usage fields
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

    if today not in usage_data:
        usage_data[today] = {}
    usage_data[today][active_key] = int(usage_data[today].get(active_key, 0)) + int(total_tokens)
    _save_usage_file(usage_path, usage_data)

    # Optional verbose logging
    if os.getenv("API_ROTATE_VERBOSE", "0") == "1":
        over = usage_data[today][active_key] >= max(0, limit - margin)
        print(f"[api-rotate] key=***{active_key[-4:]} used={usage_data[today][active_key]} tokens (added {total_tokens}) limit={limit} rotate_next={over}")

    return content


def extract_code_fence(text: str, lang: str = "python") -> List[str]:
    """Extract fenced code blocks ```lang ... ``` from text.
    Returns a list of code strings (without fences).
    """
    if not text:
        return []
    pattern = re.compile(
        rf"```{lang}\s*(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    return [m.strip() for m in pattern.findall(text)]
