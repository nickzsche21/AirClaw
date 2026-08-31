"""Wire OpenClaw to the AirClaw gateway.

AirClaw 2.x wrote `agent.provider = "opencode"` with hostname/port keys into
`~/.openclaw/config.json`. OpenClaw reads `~/.openclaw/openclaw.json` and
expects a `models.providers.<id>` block. The old patcher therefore wrote a
shape OpenClaw ignores into a file it never opens — `airclaw patch` reported
success and changed nothing. This writes the documented schema.

Rules this module follows:
  * never write a config it could not first parse
  * always back up before writing
  * merge into existing config, clobber nothing but our own provider block
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

PROVIDER_ID = "airclaw"
MODEL_ID = "airclaw"
API_KEY = "airclaw-local"

# OpenClaw's real config locations, most current first. No home-directory glob:
# 2.x ran `home.glob("**/openclaw/config.json")`, which walks every file you own.
CONFIG_PATHS = (
    "~/.openclaw/openclaw.json",
    "~/.config/openclaw/openclaw.json",
    "~/.clawdbot/clawdbot.json",          # legacy name
    "~/.config/clawdbot/clawdbot.json",
)


def candidate_paths() -> list[Path]:
    paths = []
    env_dir = os.environ.get("OPENCLAW_CONFIG_DIR")
    if env_dir:
        paths.append(Path(env_dir).expanduser() / "openclaw.json")
    paths.extend(Path(p).expanduser() for p in CONFIG_PATHS)
    return paths


def find_config() -> Path | None:
    for path in candidate_paths():
        if path.is_file():
            return path
    return None


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments outside strings, and trailing commas."""
    out, i, n = [], 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                in_str = False
            i += 1
            continue
        if ch in "\"'":
            in_str, quote = True, ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_config(path: Path) -> dict[str, Any]:
    """Parse a config, tolerating comments. Raises if it cannot be understood."""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    data = json.loads(_strip_jsonc(raw))  # let this one propagate
    print(f"[AirClaw] note: {path.name} contained comments; they will not be preserved")
    return data


def backup(path: Path) -> Path:
    target = path.with_suffix(path.suffix + ".airclaw-backup")
    shutil.copy2(path, target)
    print(f"[AirClaw] backup: {target}")
    return target


def provider_block(base_url: str, context_window: int, max_tokens: int,
                   label: str) -> dict[str, Any]:
    return {
        "baseUrl": base_url,
        "apiKey": API_KEY,
        "api": "openai-completions",
        "timeoutSeconds": 600,
        "models": [{
            "id": MODEL_ID,
            "name": label,
            "reasoning": False,
            "input": ["text"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": context_window,
            "maxTokens": max_tokens,
        }],
    }


def apply(config: dict[str, Any], base_url: str, context_window: int,
          max_tokens: int, label: str, set_default: bool) -> dict[str, Any]:
    """Merge the AirClaw provider into an existing config."""
    models = config.setdefault("models", {})
    if not isinstance(models, dict):
        raise ValueError("`models` in your config is not an object; refusing to overwrite it")

    # "merge" keeps hosted models available as fallbacks alongside ours.
    models.setdefault("mode", "merge")
    providers = models.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("`models.providers` is not an object; refusing to overwrite it")

    providers[PROVIDER_ID] = provider_block(base_url, context_window, max_tokens, label)

    if set_default:
        agents = config.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        model = defaults.setdefault("model", {})
        if isinstance(model, dict):
            model["primary"] = f"{PROVIDER_ID}/{MODEL_ID}"
        else:
            defaults["model"] = {"primary": f"{PROVIDER_ID}/{MODEL_ID}"}

    return config


MANUAL = """
Add this to your OpenClaw config by hand:

  "models": {
    "mode": "merge",
    "providers": {
      "airclaw": {
        "baseUrl": "%s",
        "apiKey": "airclaw-local",
        "api": "openai-completions",
        "models": [{ "id": "airclaw", "name": "AirClaw (local)",
                     "contextWindow": %d, "maxTokens": %d,
                     "input": ["text"],
                     "cost": {"input":0,"output":0,"cacheRead":0,"cacheWrite":0} }]
      }
    }
  },
  "agents": { "defaults": { "model": { "primary": "airclaw/airclaw" } } }
"""


def patch_openclaw(host: str = "127.0.0.1", port: int = 4096,
                   config_path: str | None = None, context_window: int = 32768,
                   max_tokens: int = 8192, label: str = "AirClaw (local)",
                   set_default: bool = True, create: bool = False) -> bool:
    base_url = f"http://{host}:{port}/v1"

    if config_path:
        path = Path(config_path).expanduser()
        if not path.is_file():
            if not create:
                print(f"[AirClaw] not found: {path}")
                return False
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
            print(f"[AirClaw] created {path}")
    else:
        path = find_config()

    if path is None:
        if not create:
            print("[AirClaw] no OpenClaw config found. Looked in:")
            for p in candidate_paths():
                print(f"    {p}")
            print("\n  Run OpenClaw once to create it, then retry.")
            print("  Or create it now:  airclaw patch --create")
            print(MANUAL % (base_url, context_window, max_tokens))
            return False
        path = Path(CONFIG_PATHS[0]).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        print(f"[AirClaw] created {path}")

    try:
        config = load_config(path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[AirClaw] could not parse {path}: {exc}")
        print("[AirClaw] refusing to write over a config I cannot read.")
        print(MANUAL % (base_url, context_window, max_tokens))
        return False

    if not isinstance(config, dict):
        print(f"[AirClaw] {path} is not a JSON object; refusing to touch it.")
        return False

    try:
        updated = apply(config, base_url, context_window, max_tokens, label, set_default)
    except ValueError as exc:
        print(f"[AirClaw] {exc}")
        print(MANUAL % (base_url, context_window, max_tokens))
        return False

    backup(path)
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    print(f"[AirClaw] patched {path}")
    print(f"[AirClaw] provider 'airclaw' -> {base_url}")
    if set_default:
        print("[AirClaw] default model -> airclaw/airclaw")
    return True


def restore(config_path: str | None = None) -> bool:
    path = Path(config_path).expanduser() if config_path else find_config()
    if path is None:
        print("[AirClaw] no OpenClaw config found.")
        return False
    b = path.with_suffix(path.suffix + ".airclaw-backup")
    if not b.exists():
        print(f"[AirClaw] no backup at {b}")
        return False
    shutil.copy2(b, path)
    print(f"[AirClaw] restored {path} from {b}")
    return True
