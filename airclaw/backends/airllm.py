"""AirLLM in-process backend — the 'giant model on a small GPU' mode.

AirLLM streams model layers off disk one at a time. That is what lets a 70B run
in ~4GB of VRAM, and it is also why it is slow: expect seconds per token, not
tokens per second. It is opt-in for that reason. For interactive agent work use
a served backend (Ollama et al) instead.

Fixes over AirClaw 2.x:
  * prompts are built with the model's own chat template, not a hardcoded
    Llama-2 [INST] string that silently mangled Qwen/Phi-3/Llama-3
  * no 512-token input truncation (2.x discarded everything past 512 tokens,
    which for a coding agent meant discarding the entire request)
  * new tokens are sliced by input length instead of string-prefix matching
"""

from __future__ import annotations

import os
import threading

MODEL_ALIASES = {
    "7b":       "mistralai/Mistral-7B-Instruct-v0.2",
    "8b":       "meta-llama/Meta-Llama-3-8B-Instruct",
    "13b":      "meta-llama/Llama-2-13b-chat-hf",
    "70b":      "meta-llama/Llama-2-70b-chat-hf",
    "qwen":     "Qwen/Qwen2.5-7B-Instruct",
    "coder":    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "deepseek": "deepseek-ai/deepseek-llm-7b-chat",
    "phi":      "microsoft/Phi-3-mini-4k-instruct",
}

DEFAULT_MODEL = os.environ.get("AIRCLAW_MODEL", MODEL_ALIASES["coder"])


def resolve_alias(name: str | None) -> str:
    if not name:
        return DEFAULT_MODEL
    return MODEL_ALIASES.get(name, name)


class AirLLMBackend:
    """Lazily-loaded AirLLM model behind a chat-completions shaped call."""

    def __init__(self, model_id: str | None = None):
        self.model_id = resolve_alias(model_id)
        self._model = None
        self._error: str | None = None
        self._lock = threading.Lock()
        self._loading = False

    # ── lifecycle ────────────────────────────────────────────────────────────
    @property
    def status(self) -> str:
        if self._model is not None:
            return "ready"
        if self._error:
            return "error"
        return "loading" if self._loading else "idle"

    @property
    def error(self) -> str | None:
        return self._error

    def load(self) -> None:
        """Blocking load. Safe to call from a background thread."""
        with self._lock:
            if self._model is not None or self._loading:
                return
            self._loading = True

        try:
            model_cls = _import_airllm()
            print(f"[AirClaw] loading {self.model_id} via AirLLM")
            print("[AirClaw] first run downloads weights (4-40GB) and is slow by design")
            model = model_cls.from_pretrained(self.model_id)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as state
            self._error = f"{type(exc).__name__}: {exc}"
            print(f"[AirClaw] AirLLM load failed: {self._error}")
        else:
            self._model = model
            print(f"[AirClaw] {self.model_id} ready")
        finally:
            self._loading = False

    def load_async(self) -> threading.Thread:
        t = threading.Thread(target=self.load, name="airclaw-airllm-load", daemon=True)
        t.start()
        return t

    # ── inference ────────────────────────────────────────────────────────────
    def build_prompt(self, messages: list[dict]) -> str:
        """Render messages using the model's own chat template when it has one."""
        tok = getattr(self._model, "tokenizer", None)
        normalised = [
            {"role": m.get("role", "user"), "content": _flatten_content(m.get("content"))}
            for m in messages
        ]

        if tok is not None and getattr(tok, "chat_template", None):
            try:
                return tok.apply_chat_template(
                    normalised, tokenize=False, add_generation_prompt=True
                )
            except Exception:  # noqa: BLE001 - fall through to the generic format
                pass

        # Generic fallback. Not perfect for any model, wrong for none of them.
        parts = []
        for m in normalised:
            role = m["role"]
            label = {"system": "System", "user": "User", "assistant": "Assistant"}.get(role, role.title())
            parts.append(f"{label}: {m['content']}")
        parts.append("Assistant:")
        return "\n\n".join(parts)

    def generate(self, messages: list[dict], max_tokens: int, temperature: float) -> str:
        if self._model is None:
            raise RuntimeError(
                self._error or "AirLLM model is still loading — retry in a moment"
            )

        prompt = self.build_prompt(messages)
        tok = self._model.tokenizer

        # No truncation. If the prompt genuinely exceeds the model's context the
        # backend will raise, and a real error beats a silently gutted request.
        encoded = tok([prompt], return_tensors="pt", return_attention_mask=False)
        input_ids = encoded["input_ids"]
        input_len = input_ids.shape[1]

        try:
            import torch
            if torch.cuda.is_available():
                input_ids = input_ids.cuda()
        except ImportError:
            pass

        with self._lock:
            output = self._model.generate(
                input_ids,
                max_new_tokens=max_tokens,
                temperature=temperature,
                use_cache=True,
                return_dict_in_generate=True,
            )

        sequences = output.sequences if hasattr(output, "sequences") else output
        new_tokens = sequences[0][input_len:]
        return tok.decode(new_tokens, skip_special_tokens=True).strip()


def _flatten_content(content) -> str:
    """OpenAI allows content to be a list of parts. Collapse to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(part.get("text", ""))
            elif isinstance(part, str):
                chunks.append(part)
        return "".join(chunks)
    return "" if content is None else str(content)


def _import_airllm():
    try:
        from airllm import AutoModel
        return AutoModel
    except ImportError:
        pass
    raise RuntimeError(
        "AirLLM is not installed. Install it with:  pip install 'airclaw[airllm]'"
    )
