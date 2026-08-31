# AirClaw

**Run OpenClaw on a local model. Zero API cost.**

AirClaw puts one stable OpenAI-compatible endpoint in front of whatever local
inference server you already run, then writes the OpenClaw config that points at
it. Configure OpenClaw once; swap Ollama for llama.cpp for vLLM underneath
without touching agent config again.

```bash
pip install airclaw

airclaw detect     # what's running locally?
airclaw start      # gateway on :4096  (leave running)
airclaw patch      # wire OpenClaw to it
```

Restart OpenClaw. That's it — your agent now runs on your own hardware.

Something not working? `airclaw doctor` checks all three links in the chain and
tells you which one is broken.

---

## Backends

AirClaw finds these automatically, in this order:

| Backend | Default port | Notes |
|---|---|---|
| [Ollama](https://ollama.com) | 11434 | Easiest. `ollama pull qwen2.5-coder:7b` |
| [LM Studio](https://lmstudio.ai) | 1234 | GUI, `lms server start` |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | 8080 | `llama-server -m model.gguf` |
| [vLLM](https://docs.vllm.ai) | 8000 | Fastest if you have the VRAM |
| [Jan](https://jan.ai) | 1337 | |
| text-generation-webui | 5000 | |

Force one, or point at something else entirely:

```bash
airclaw start --backend ollama
airclaw start --backend http://192.168.1.50:8000/v1
airclaw start --model qwen2.5-coder:14b
```

### AirLLM mode

AirLLM streams model layers off disk one at a time, which is how it fits a 70B
model into about 4GB of VRAM.

It is slow. Expect **seconds per token, not tokens per second.** It is a genuine
way to run a model your GPU cannot hold, and it is not a way to run an
interactive coding agent. It is opt-in for exactly that reason:

```bash
pip install 'airclaw[airllm]'
airclaw start --airllm --model coder
```

Aliases: `7b` `8b` `13b` `70b` `qwen` `coder` `deepseek` `phi`, or any Hugging
Face model id. `airclaw models` lists them. Tool calling is not available in
this mode — the gateway returns a clear 400 rather than pretending.

---

## How it works

```
OpenClaw ──> AirClaw gateway :4096 ──> Ollama / llama.cpp / vLLM / LM Studio
             (stable alias                (whatever is actually running)
              "airclaw/airclaw")
```

`airclaw patch` writes a `models.providers.airclaw` block into your OpenClaw
config and sets `agents.defaults.model.primary` to `airclaw/airclaw`. It backs
the file up first, merges rather than overwrites, and refuses to write a config
it could not parse. `airclaw restore` puts the original back.

The gateway forwards streaming, tool/function calling, and sampling parameters
untouched. It does not truncate prompts.

---

## Commands

| Command | What it does |
|---|---|
| `airclaw detect` | List running local inference servers |
| `airclaw start` | Start the gateway on :4096 |
| `airclaw patch` | Write AirClaw into the OpenClaw config |
| `airclaw doctor` | Diagnose the whole chain, top to bottom |
| `airclaw status` | Is the gateway up? |
| `airclaw restore` | Undo the config change |
| `airclaw models` | List AirLLM aliases |

Useful flags: `--port`, `--host`, `--config`, `--no-default` (register the
provider without making it the default model), `--create` (make the config file
if OpenClaw hasn't yet).

---

## Upgrading from 2.x

**If you installed AirClaw 2.x, `airclaw patch` did not work.** It wrote
`agent.provider = "opencode"` with `hostname`/`port` keys into
`~/.openclaw/config.json`. OpenClaw reads `~/.openclaw/openclaw.json` and expects
a `models.providers` block, so the old patcher wrote a shape OpenClaw ignores
into a file it never opens — and printed a success message.

Also fixed in 3.0:

- **Prompts are no longer truncated.** 2.x capped input at 512 tokens, which for
  a coding agent meant discarding nearly the whole request.
- **Streaming works.** 2.x accepted `stream: true` and replied with a non-SSE
  JSON body, which hangs clients that asked for a stream.
- **Tool calling is forwarded.** 2.x dropped `tools`/`tool_choice` entirely, so
  agents could not call tools.
- **Correct chat templates.** 2.x hardcoded Llama-2 `[INST]` formatting for every
  model, including Qwen, Phi-3 and Llama-3, which use different templates.
- **No home-directory scan.** 2.x ran `glob("**/openclaw/config.json")` across
  your entire home directory.
- **The package is actually in this repo.** 2.x's `pyproject.toml` declared a
  package and a CLI entry point against a directory that was never committed, so
  `pip install .` from a clone produced an empty package.

To upgrade:

```bash
pip install --upgrade airclaw
airclaw restore   # only if 2.x touched a config you want reverted
airclaw patch
airclaw doctor
```

---

## Development

```bash
uv venv --python 3.12
uv pip install -e '.[dev]'
pytest
```

Tests run against a stub OpenAI-compatible server over a real socket — no GPU,
no model download, no network.

## License

MIT
