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
