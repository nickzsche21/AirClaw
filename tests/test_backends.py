from airclaw.backends import probe
from airclaw.backends.base import Backend


def test_probe_finds_live_server(upstream):
    b = probe("stub", upstream["base_url"], "Stub")
    assert b is not None
    assert b.models == ("qwen2.5-coder:7b", "llama3.2:3b")
    assert b.chat_url == upstream["base_url"] + "/chat/completions"


def test_probe_returns_none_for_dead_port():
    assert probe("dead", "http://127.0.0.1:1/v1", "Dead", timeout=0.2) is None


def test_probe_does_not_raise_on_garbage_host():
    assert probe("bad", "http://127.0.0.1:2/v1", "Bad", timeout=0.2) is None


def test_describe_is_readable():
    b = Backend(name="ollama", base_url="http://x/v1", models=("a", "b", "c", "d"))
    assert "+1 more" in b.describe()


# ── default model selection ──────────────────────────────────────────────────
# Ollama's /v1/models lists every pulled model. Picking models[0] blindly could
# select an embedding model and fail every request with a confusing error.

from airclaw.backends.base import choose_model, is_chat_model  # noqa: E402


def test_skips_embedding_models():
    # nomic-embed-text is the most commonly pulled embedding model.
    assert choose_model(("nomic-embed-text", "qwen2.5-coder:7b")) == "qwen2.5-coder:7b"


def test_skips_embedding_models_even_when_first():
    models = ("all-minilm", "bge-large", "mxbai-embed-large", "llama3.2:3b")
    assert choose_model(models) == "llama3.2:3b"


def test_prefers_instruction_tuned():
    assert choose_model(("llama3.2:3b", "qwen2.5-coder:7b")) == "qwen2.5-coder:7b"
    assert choose_model(("base-model", "mistral-7b-instruct")) == "mistral-7b-instruct"


def test_returns_none_when_nothing_can_chat():
    assert choose_model(("nomic-embed-text", "bge-reranker-v2")) is None


def test_empty_backend_returns_none():
    assert choose_model(()) is None


def test_falls_back_to_first_usable():
    assert choose_model(("some-random-model", "another")) == "some-random-model"


def test_is_chat_model_classification():
    assert is_chat_model("qwen2.5-coder:7b")
    assert not is_chat_model("nomic-embed-text")
    assert not is_chat_model("bge-reranker-large")
    assert not is_chat_model("whisper-large-v3")
