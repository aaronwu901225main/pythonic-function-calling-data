import os
import re
from typing import Dict, List

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

def chat_complete(prompt: str, model: str | None = None, system: str | None = None) -> str:
    """Call OpenAI Chat Completions with a single user prompt.
    Requires OPENAI_API_KEY in environment.
    """
    from openai import OpenAI

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
    }

    # Token limit handling:
    # To avoid API incompatibility, we DO NOT send any token limit by default.
    # If you explicitly set OPENAI_MAX_TOKENS, we will include it using the field
    # specified by OPENAI_MAX_TOKENS_FIELD (default: max_completion_tokens).
    max_tokens_env = os.getenv("OPENAI_MAX_TOKENS")
    if max_tokens_env:
        try:
            max_tokens_value = int(max_tokens_env)
            max_tokens_field = os.getenv(
                "OPENAI_MAX_TOKENS_FIELD", "max_completion_tokens"
            )
            if max_tokens_field == "max_tokens":
                kwargs["max_tokens"] = max_tokens_value
            else:
                kwargs["max_completion_tokens"] = max_tokens_value
        except ValueError:
            # ignore invalid value, proceed without token cap
            pass

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


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
