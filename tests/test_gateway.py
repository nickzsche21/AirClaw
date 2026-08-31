"""Gateway behaviour, including the three things 2.x got wrong:
streaming, tool passthrough, and prompt truncation."""


import pytest
from fastapi.testclient import TestClient

from airclaw import server as S
from airclaw.backends import probe


@pytest.fixture
def client(upstream):
    backend = probe("stub", upstream["base_url"], "Stub")
    S.GW.use_served(backend, model=None)
    with TestClient(S.app) as c:
        yield c


def test_health_reports_backend(client, upstream):
    body = client.get("/health").json()
    assert body["status"] == "ready"
    assert body["model"] == "qwen2.5-coder:7b"


def test_models_exposes_stable_alias(client):
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert ids[0] == "airclaw"
    assert "qwen2.5-coder:7b" in ids


def test_alias_maps_to_real_model(client, upstream):
    r = client.post("/v1/chat/completions",
                    json={"model": "airclaw", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    # OpenClaw says "airclaw"; the backend must receive its own model name.
    assert upstream["received"][-1]["model"] == "qwen2.5-coder:7b"


def test_explicit_model_is_respected(client, upstream):
    client.post("/v1/chat/completions",
                json={"model": "llama3.2:3b", "messages": [{"role": "user", "content": "hi"}]})
    assert upstream["received"][-1]["model"] == "llama3.2:3b"


def test_streaming_returns_sse_not_json(client):
    with client.stream("POST", "/v1/chat/completions",
                       json={"model": "airclaw", "stream": True,
                             "messages": [{"role": "user", "content": "hi"}]}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    # 2.x accepted stream:true and replied with a plain JSON body.
    assert "data: " in text
    assert "[DONE]" in text
    assert '"Hel"' in text or "Hel" in text


def test_tools_are_forwarded(client, upstream):
    tools = [{"type": "function",
              "function": {"name": "read_file",
                           "parameters": {"type": "object",
                                          "properties": {"path": {"type": "string"}}}}}]
    client.post("/v1/chat/completions",
                json={"model": "airclaw", "tools": tools, "tool_choice": "auto",
                      "messages": [{"role": "user", "content": "read x"}]})
    sent = upstream["received"][-1]
    # Without this an agent cannot call a single tool.
    assert sent["tools"] == tools
    assert sent["tool_choice"] == "auto"


def test_long_prompt_is_not_truncated(client, upstream):
    # 2.x capped input at 512 tokens and silently dropped the rest.
    big = "x " * 20000
    client.post("/v1/chat/completions",
                json={"model": "airclaw",
                      "messages": [{"role": "system", "content": big},
                                   {"role": "user", "content": "go"}]})
    sent = upstream["received"][-1]
    assert sent["messages"][0]["content"] == big
    assert len(sent["messages"]) == 2


def test_sampling_params_pass_through(client, upstream):
    client.post("/v1/chat/completions",
                json={"model": "airclaw", "temperature": 0.1, "top_p": 0.9,
                      "max_tokens": 1234, "stop": ["</end>"], "seed": 7,
                      "messages": [{"role": "user", "content": "hi"}]})
    sent = upstream["received"][-1]
    assert sent["temperature"] == 0.1
    assert sent["max_tokens"] == 1234
    assert sent["stop"] == ["</end>"]
    assert sent["seed"] == 7


def test_missing_messages_is_400(client):
    assert client.post("/v1/chat/completions", json={"model": "airclaw"}).status_code == 400


def test_unconfigured_gateway_is_503():
    S.GW.__init__()
    with TestClient(S.app) as c:
        r = c.post("/v1/chat/completions",
                   json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


def test_dead_upstream_is_502(upstream):
    backend = probe("stub", upstream["base_url"], "Stub")
    S.GW.use_served(backend, model=None)
    S.GW.backend = type(backend)(name="stub", base_url="http://127.0.0.1:1/v1",
                                 models=("m",))
    with TestClient(S.app) as c:
        r = c.post("/v1/chat/completions",
                   json={"model": "airclaw", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 502
