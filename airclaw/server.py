"""AirClaw gateway — one stable OpenAI-compatible endpoint over whatever
local inference server you happen to be running.

Why a gateway at all, when Ollama already speaks /v1? Because OpenClaw's config
should be written once. Point it at :4096 and swap Ollama for llama.cpp for
vLLM underneath without touching the agent config again.

What it does that AirClaw 2.x did not:
  * streams (2.x accepted stream:true and returned a non-SSE blob, which hangs
    or breaks any client that asked for streaming)
  * forwards tool / function-calling fields untouched, so agents can call tools
  * does not truncate prompts
  * fails loudly instead of silently degrading
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from airclaw import __version__
from airclaw.backends import Backend, detect_backends, pick_backend
from airclaw.backends.airllm import AirLLMBackend
from airclaw.backends.base import choose_model

DEFAULT_PORT = int(os.environ.get("AIRCLAW_PORT", "4096"))
DEFAULT_HOST = os.environ.get("AIRCLAW_HOST", "127.0.0.1")

# The alias OpenClaw is configured with. Never changes, whatever runs underneath.
ALIAS = "airclaw"
_ALIASES = {ALIAS, "local-model", "default"}

# Fields we forward verbatim. Tool calling lives here — dropping these is what
# stops an agent from working.
_PASSTHROUGH = (
    "messages", "temperature", "top_p", "max_tokens", "max_completion_tokens",
    "stop", "presence_penalty", "frequency_penalty", "seed", "n",
    "tools", "tool_choice", "functions", "function_call",
    "response_format", "logprobs", "top_logprobs", "parallel_tool_calls",
    "reasoning_effort", "stream_options", "user", "logit_bias",
)


class Gateway:
    """Holds the active backend and the model name to hand it."""

    def __init__(self) -> None:
        self.backend: Backend | None = None
        self.airllm: AirLLMBackend | None = None
        self.model: str | None = None
        self.mode: str = "unconfigured"
        self.last_error: str | None = None

    def use_served(self, backend: Backend, model: str | None) -> None:
        self.backend = backend
        self.airllm = None
        self.mode = "served"
        self.model = model or choose_model(backend.models)

    def use_airllm(self, model: str | None) -> None:
        self.airllm = AirLLMBackend(model)
        self.backend = None
        self.mode = "airllm"
        self.model = self.airllm.model_id

    def resolve_model(self, requested: str | None) -> str:
        """Map the stable alias onto the backend's real model name."""
        if requested and requested not in _ALIASES:
            return requested
        if self.model:
            return self.model
        if self.backend is not None and self.backend.models:
            raise HTTPException(
                status_code=503,
                detail=f"{self.backend.name} has no chat-capable model — it reports only "
                       f"{', '.join(self.backend.models)}. Those look like embedding or "
                       f"rerank models. Pull a chat model (e.g. `ollama pull "
                       f"qwen2.5-coder:7b`), or name one with --model.",
            )
        raise HTTPException(
            status_code=503,
            detail="No model available. Pull one (e.g. `ollama pull qwen2.5-coder:7b`) "
                   "and restart AirClaw, or pass --model.",
        )

    def status(self) -> dict[str, Any]:
        if self.mode == "airllm" and self.airllm is not None:
            ready = self.airllm.status == "ready"
            return {"status": self.airllm.status, "backend": "airllm",
                    "model": self.airllm.model_id, "ready": ready,
                    "error": self.airllm.error}
        if self.mode == "served" and self.backend is not None:
            return {"status": "ready", "backend": self.backend.name,
                    "base_url": self.backend.base_url, "model": self.model,
                    "ready": True, "error": None}
        return {"status": "error", "backend": None, "model": None, "ready": False,
                "error": self.last_error or "No local inference backend detected."}


GW = Gateway()
app = FastAPI(title="AirClaw", version=__version__)


def _client():
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise HTTPException(status_code=500, detail=f"httpx is required: {exc}") from exc
    return httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))


def _upstream_body(payload: dict, model: str, stream: bool) -> dict:
    body = {k: payload[k] for k in _PASSTHROUGH if k in payload}
    body["model"] = model
    body["stream"] = stream
    return body


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/")
def root() -> dict:
    return {"service": "AirClaw", "version": __version__, **GW.status()}


@app.get("/health")
def health() -> dict:
    return GW.status()


@app.get("/v1/models")
def list_models() -> dict:
    now = int(time.time())
    ids = [ALIAS]
    if GW.mode == "served" and GW.backend is not None:
        ids.extend(m for m in GW.backend.models if m != ALIAS)
    elif GW.model:
        ids.append(GW.model)
    return {
        "object": "list",
        "data": [{"id": i, "object": "model", "created": now, "owned_by": "airclaw"}
                 for i in dict.fromkeys(ids)],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    if not isinstance(payload, dict) or not payload.get("messages"):
        raise HTTPException(status_code=400, detail="`messages` is required")

    stream = bool(payload.get("stream"))
    model = GW.resolve_model(payload.get("model"))

    if GW.mode == "airllm":
        return await _airllm_completion(payload, model, stream)
    if GW.mode == "served" and GW.backend is not None:
        return await _proxy_completion(payload, model, stream)
    raise HTTPException(status_code=503, detail=GW.status()["error"])


async def _proxy_completion(payload: dict, model: str, stream: bool):
    backend = GW.backend
    assert backend is not None
    body = _upstream_body(payload, model, stream)
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {backend.api_key}"}

    if not stream:
        client = _client()
        try:
            r = await client.post(backend.chat_url, json=body, headers=headers)
        except Exception as exc:
            await client.aclose()
            raise HTTPException(status_code=502,
                                detail=f"{backend.name} unreachable: {exc}") from exc
        try:
            content = r.content
            status = r.status_code
        finally:
            await client.aclose()
        return JSONResponse(content=json.loads(content or b"{}"), status_code=status)

    async def relay():
        client = _client()
        try:
            async with client.stream("POST", backend.chat_url, json=body,
                                     headers=headers) as r:
                if r.status_code != 200:
                    detail = (await r.aread()).decode("utf-8", "replace")[:500]
                    yield _sse_error(f"{backend.name} returned {r.status_code}: {detail}")
                    return
                async for chunk in r.aiter_raw():
                    if chunk:
                        yield chunk
        except Exception as exc:  # noqa: BLE001
            yield _sse_error(f"{backend.name} stream failed: {exc}")
        finally:
            await client.aclose()

    return StreamingResponse(relay(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


async def _airllm_completion(payload: dict, model: str, stream: bool):
    import anyio

    backend = GW.airllm
    assert backend is not None
    if backend.status != "ready":
        raise HTTPException(
            status_code=503,
            detail=backend.error or "AirLLM model still loading — this can take minutes",
        )

    messages = payload["messages"]
    max_tokens = int(payload.get("max_tokens") or payload.get("max_completion_tokens") or 512)
    temperature = float(payload.get("temperature", 0.7))

    if payload.get("tools") or payload.get("functions"):
        raise HTTPException(
            status_code=400,
            detail="The AirLLM backend does not support tool calling. Use a served "
                   "backend (Ollama, llama.cpp, vLLM) for agent workloads.",
        )

    try:
        text = await anyio.to_thread.run_sync(
            lambda: backend.generate(messages, max_tokens, temperature)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference failed: {exc}") from exc

    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if not stream:
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    async def synth():
        head = {"id": cid, "object": "chat.completion.chunk", "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"},
                             "finish_reason": None}]}
        yield f"data: {json.dumps(head)}\n\n".encode()
        body = dict(head)
        body["choices"] = [{"index": 0, "delta": {"content": text}, "finish_reason": None}]
        yield f"data: {json.dumps(body)}\n\n".encode()
        tail = dict(head)
        tail["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        yield f"data: {json.dumps(tail)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return StreamingResponse(synth(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


def _sse_error(message: str) -> bytes:
    payload = {"error": {"message": message, "type": "airclaw_upstream_error"}}
    return f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n".encode()


# ── entry ────────────────────────────────────────────────────────────────────
def configure(prefer: str | None = None, model: str | None = None,
              use_airllm: bool = False) -> Gateway:
    """Resolve which backend the gateway will serve."""
    if use_airllm:
        GW.use_airllm(model)
        GW.airllm.load_async()
        return GW

    backend = pick_backend(prefer)
    if backend is None:
        live = detect_backends()
        GW.last_error = (
            f"Could not reach '{prefer}'." if prefer else
            "No local inference server found on the usual ports."
        )
        if live:
            GW.last_error += " Detected instead: " + ", ".join(b.name for b in live)
        return GW

    GW.use_served(backend, model)
    return GW


def start_server(prefer: str | None = None, model: str | None = None,
                 host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 use_airllm: bool = False) -> None:
    import uvicorn

    configure(prefer=prefer, model=model, use_airllm=use_airllm)
    st = GW.status()

    if not st["ready"] and GW.mode == "unconfigured":
        print(f"\n[AirClaw] {st['error']}\n")
        print("  Start one of these, then run `airclaw start` again:")
        print("    ollama serve                 # then: ollama pull qwen2.5-coder:7b")
        print("    llama-server -m model.gguf --port 8080")
        print("    lms server start             # LM Studio")
        print("\n  Or run the giant-model-on-a-small-GPU path (slow):")
        print("    airclaw start --airllm --model coder\n")
        raise SystemExit(1)

    label = st.get("backend") or "none"
    print(f"""
  AirClaw v{__version__}
  backend : {label}
  model   : {st.get('model')}
  api     : http://{host}:{port}/v1
  status  : {st.get('status')}

  Wire OpenClaw to it:  airclaw patch
""")
    uvicorn.run(app, host=host, port=port, log_level="warning")
