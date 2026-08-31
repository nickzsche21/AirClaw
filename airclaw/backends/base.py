"""Backend descriptors.

A backend is anything that can answer an OpenAI-shaped chat completion.
Two kinds exist:

  "openai"  — an external server already speaking /v1 (Ollama, llama.cpp,
              LM Studio, vLLM, Jan, ...). AirClaw proxies to it.
  "inproc"  — AirLLM, loaded inside this process. AirClaw generates directly
              and synthesises the OpenAI envelope itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Backend:
    """A reachable local inference server."""

    name: str
    base_url: str
    kind: str = "openai"
    api_key: str = "airclaw-local"
    models: tuple[str, ...] = field(default=())
    note: str = ""

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"

    def describe(self) -> str:
        head = f"{self.name} @ {self.base_url}"
        if self.models:
            shown = ", ".join(self.models[:3])
            more = f" (+{len(self.models) - 3} more)" if len(self.models) > 3 else ""
            head += f" — {shown}{more}"
        return head


# Ordered by how good the default experience is. First one that answers wins.
CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("ollama",     "http://127.0.0.1:11434/v1", "Ollama"),
    ("lmstudio",   "http://127.0.0.1:1234/v1",  "LM Studio"),
    ("llamacpp",   "http://127.0.0.1:8080/v1",  "llama.cpp server"),
    ("vllm",       "http://127.0.0.1:8000/v1",  "vLLM"),
    ("jan",        "http://127.0.0.1:1337/v1",  "Jan"),
    ("tgw",        "http://127.0.0.1:5000/v1",  "text-generation-webui"),
)


# Models that cannot answer a chat completion. Ollama's /v1/models lists every
# pulled model, embedding and reranking ones included, so picking models[0]
# blindly can hand an agent an embedding model and fail every request.
_NOT_CHAT = (
    "embed", "embedding", "bge-", "bge:", "gte-", "gte:", "e5-", "e5:",
    "all-minilm", "nomic-embed", "mxbai-embed", "snowflake-arctic-embed",
    "rerank", "reranker", "-guard", "guardrail", "whisper", "clip-",
    "stable-diffusion", "sdxl", "tts-", "-tts",
)

# Signals that a model is instruction-tuned, and so a sane default.
_PREFERRED = ("coder", "instruct", "-it", "chat")


def is_chat_model(model_id: str) -> bool:
    """True if the id does not look like an embedding/rerank/audio model."""
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NOT_CHAT)


def choose_model(models: tuple[str, ...] | list[str]) -> str | None:
    """Pick a sensible default chat model from what a backend reports.

    Prefers an instruction-tuned model, falls back to any chat-capable one, and
    returns None when the backend only has things that cannot chat.
    """
    usable = [m for m in models if is_chat_model(m)]
    if not usable:
        return None
    for marker in _PREFERRED:
        for model in usable:
            if marker in model.lower():
                return model
    return usable[0]
