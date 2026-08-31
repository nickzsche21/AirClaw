# Changelog

## 3.0.1

**Fixed: an embedding model could be auto-selected as your chat model.**

Ollama's `/v1/models` lists every model you have pulled, embedding and rerank
models included. AirClaw took the first entry, so anyone with a common
embedding model such as `nomic-embed-text` pulled could have it chosen as the
chat model, and every request would fail with a confusing upstream error.

AirClaw now skips embedding, rerank, audio and image models when picking a
default, prefers instruction-tuned models (`coder`, `instruct`, `-it`, `chat`),
and returns a 503 naming the actual problem when a backend has nothing that can
hold a conversation.

## 3.0.0

Restores AirClaw after the repository spent several months as an unrelated
voice-AI demo, and fixes the reasons it did not work.

**The package was never in the repository.** `pyproject.toml` and `setup.py`
declared `packages=["airclaw*"]` and an `airclaw.cli:main` entry point against a
directory that was never committed, so `pip install .` from a clone built an
empty package and the CLI failed with `ModuleNotFoundError`.

**`airclaw patch` did nothing.** It wrote `agent.provider = "opencode"` with
`hostname`/`port` keys into `~/.openclaw/config.json`. OpenClaw reads
`~/.openclaw/openclaw.json` and expects a `models.providers.<id>` block with
`baseUrl`/`apiKey`/`api`, so the patcher wrote a shape OpenClaw ignores into a
file it never opens, then printed a success message.

Also fixed:

- Prompts are no longer truncated. A 512-token input cap discarded nearly the
  whole request for any coding agent.
- Streaming works. `stream: true` was accepted and answered with a non-SSE body,
  hanging clients that asked for a stream.
- `tools` and `tool_choice` are forwarded, so agents can call tools at all.
- Chat templates come from the model rather than a hardcoded Llama-2 `[INST]`
  string that mangled Qwen, Phi-3 and Llama-3.
- Config lookup no longer globs the entire home directory.
- JS config rewriting by regular expression is gone; it could corrupt configs.

Added:

- Multi-backend detection across Ollama, LM Studio, llama.cpp, vLLM, Jan and
  text-generation-webui, behind one stable endpoint, so OpenClaw is configured
  once and the backend can change underneath.
- `airclaw doctor`, which checks the backend, the gateway and the OpenClaw
  config in order and names the broken link.
- A patcher that backs up first, merges instead of overwriting, and refuses to
  write a config it could not parse. `airclaw restore` undoes it.
- 34 tests covering the patcher, backend probing, and the gateway's streaming,
  tool passthrough and prompt handling, run against a stub OpenAI-compatible
  server over a real socket.

AirLLM remains available as an opt-in mode for running a model larger than the
GPU, documented as seconds-per-token rather than presented as fast.
