"""
OpenAI-compatible chat-completions client for free, no-credit-card providers.

Works with any endpoint that speaks the OpenAI `/chat/completions` format.
Two presets are built in; set LLM_PROVIDER to pick one:

    LLM_PROVIDER=groq        base URL https://api.groq.com/openai/v1
    LLM_PROVIDER=openrouter  base URL https://openrouter.ai/api/v1

Or point at any other compatible endpoint with LLM_BASE_URL.
Always required: LLM_API_KEY and LLM_MODEL (copy the model id from the
provider's console; it is recorded in every eval result).

Contract matches gemini_llm.gemini_llm_call(): returns a dict on success, or
None on any failure (missing config, network error, bad JSON). None makes the
hybrid extractor escalate to a human instead of guessing.
"""
import json
import logging
import os

import requests

from llm_prompt import EXTRACTION_PROMPT, PROMPTS, runtime_prompt, strip_json_fence

PRESETS = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def config():
    """Resolve (base_url, api_key, model) from the environment, or None if incomplete."""
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    base_url = os.environ.get("LLM_BASE_URL") or PRESETS.get(provider)
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not (base_url and api_key and model):
        return None
    return base_url.rstrip("/"), api_key, model


def config_base():
    """(base_url, api_key) without requiring a chat model -- used for speech-to-text."""
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    base_url = os.environ.get("LLM_BASE_URL") or PRESETS.get(provider)
    api_key = os.environ.get("LLM_API_KEY")
    return (base_url.rstrip("/"), api_key) if base_url and api_key else None


def chat_extract(message, base_url, api_key, model, timeout=30, post=requests.post,
                 system=EXTRACTION_PROMPT):
    """One raw call. Returns (response_or_None, http_status). Never logs the key or bodies."""
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message or "(empty message)"},
        ],
    }
    resp = post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    return resp


def parse_response(body):
    """Return (parsed_dict_or_None, input_tokens, output_tokens)."""
    usage = body.get("usage") or {}
    in_tok, out_tok = usage.get("prompt_tokens"), usage.get("completion_tokens")
    try:
        text = body["choices"][0]["message"]["content"]
        parsed = json.loads(strip_json_fence(text))
        return (parsed if isinstance(parsed, dict) else None), in_tok, out_tok
    except (KeyError, IndexError, TypeError, ValueError):
        return None, in_tok, out_tok


def openai_compat_llm_call(message: str, timeout: int = 15):
    cfg = config()
    if cfg is None:
        return None
    base_url, api_key, model = cfg
    try:
        resp = chat_extract(message, base_url, api_key, model, timeout=timeout, system=runtime_prompt())
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        parsed, _, _ = parse_response(resp.json())
        return parsed
    except (requests.RequestException, ValueError) as exc:
        logging.getLogger(__name__).warning(
            "OpenAI-compatible extraction failed (%s); escalating instead of guessing.", type(exc).__name__
        )
        return None


if __name__ == "__main__":
    import sys

    print(openai_compat_llm_call(sys.argv[1] if len(sys.argv) > 1 else "kal nahi ho payega, Saturday chalega?"))
