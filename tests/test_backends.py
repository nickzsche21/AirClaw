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
