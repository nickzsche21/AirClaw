"""AirClaw command line."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from airclaw import __version__
from airclaw.backends import detect_backends
from airclaw.backends.airllm import MODEL_ALIASES

BANNER = rf"""
    _    _       ____ _
   / \  (_)_ __ / ___| | __ ___      __
  / _ \ | | '__| |   | |/ _` \ \ /\ / /
 / ___ \| | |  | |___| | (_| |\ V  V /
/_/   \_\_|_|   \____|_|\__,_| \_/\_/   v{__version__}

 Run OpenClaw on a local model. Zero API cost.
"""


def cmd_detect(args) -> int:
    live = detect_backends(timeout=args.timeout)
    if not live:
        print("No local inference server found.\n")
        print("  Looked for Ollama, LM Studio, llama.cpp, vLLM, Jan, text-generation-webui")
        print("  on their default localhost ports.\n")
        print("  Quickest fix:")
        print("    ollama serve")
        print("    ollama pull qwen2.5-coder:7b")
        return 1
    print(f"Found {len(live)} local backend(s):\n")
    for i, b in enumerate(live):
        marker = "->" if i == 0 else "  "
        print(f"  {marker} {b.describe()}")
    print(f"\nAirClaw would use: {live[0].name}")
    return 0


def cmd_start(args) -> int:
    from airclaw.server import start_server

    print(BANNER)
    start_server(prefer=args.backend, model=args.model, host=args.host,
                 port=args.port, use_airllm=args.airllm)
    return 0


def cmd_patch(args) -> int:
    from airclaw.patch import patch_openclaw

    print(BANNER)
    ok = patch_openclaw(host=args.host, port=args.port, config_path=args.config,
                        context_window=args.context_window, max_tokens=args.max_tokens,
                        set_default=not args.no_default, create=args.create)
    if ok:
        print("\nNext:")
        print("  1. airclaw start      (leave it running)")
        print("  2. restart OpenClaw")
        print("\nUndo any time:  airclaw restore")
        return 0
    return 1


def cmd_restore(args) -> int:
    from airclaw.patch import restore
    return 0 if restore(args.config) else 1


def _gateway_health(port: int) -> dict | None:
    """Return the gateway's /health payload, or None if nothing answers."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def cmd_status(args) -> int:
    data = _gateway_health(args.port)
    if data is None:
        print(f"AirClaw is not running on :{args.port}")
        print("  Start it:  airclaw start")
        return 1
    status = data.get("status")
    if status == "ready":
        print(f"AirClaw ready on :{args.port}")
        print(f"  backend : {data.get('backend')}")
        print(f"  model   : {data.get('model')}")
        return 0
    if status == "loading":
        print(f"AirClaw on :{args.port} — model still loading")
        return 0
    print(f"AirClaw on :{args.port} — {data.get('error')}")
    return 1


def cmd_doctor(args) -> int:
    """One command that tells you exactly which link in the chain is broken."""
    from airclaw.patch import PROVIDER_ID, find_config, load_config

    print(BANNER)
    problems = 0

    print("1. local inference backend")
    live = detect_backends(timeout=args.timeout)
    if live:
        for b in live:
            print(f"     ok    {b.describe()}")
    else:
        problems += 1
        print("     FAIL  nothing listening on the usual ports")
        print("           fix: ollama serve && ollama pull qwen2.5-coder:7b")

    print("\n2. airclaw gateway")
    info = _gateway_health(args.port)
    if info is None:
        problems += 1
        print(f"     FAIL  nothing answering on :{args.port}")
        print("           fix: airclaw start")
    elif info.get("status") == "ready":
        print(f"     ok    :{args.port} -> {info.get('backend')} / {info.get('model')}")
    elif info.get("status") == "loading":
        print(f"     warn  :{args.port} up, model still loading")
    else:
        problems += 1
        print(f"     FAIL  :{args.port} -> {info.get('error')}")

    print("\n3. openclaw config")
    path = find_config()
    if path is None:
        problems += 1
        print("     FAIL  no OpenClaw config found")
        print("           fix: run OpenClaw once, then: airclaw patch")
    else:
        print(f"     ok    {path}")
        try:
            cfg = load_config(path)
        except Exception as exc:  # noqa: BLE001
            problems += 1
            print(f"     FAIL  cannot parse: {exc}")
        else:
            providers = cfg.get("models", {}).get("providers", {})
            if PROVIDER_ID in providers:
                url = providers[PROVIDER_ID].get("baseUrl")
                print(f"     ok    provider 'airclaw' -> {url}")
                primary = (cfg.get("agents", {}).get("defaults", {})
                              .get("model", {}).get("primary"))
                if primary == f"{PROVIDER_ID}/airclaw":
                    print(f"     ok    default model -> {primary}")
                else:
                    print(f"     warn  default model is {primary!r}, not airclaw/airclaw")
                    print("           fix: airclaw patch")
            else:
                problems += 1
                print("     FAIL  no 'airclaw' provider in config")
                print("           fix: airclaw patch")

    print()
    if problems:
        print(f"{problems} problem(s) found. Fix the FAIL lines above, top to bottom.")
        return 1
    print("All good. OpenClaw is wired to your local model.")
    return 0


def cmd_models(args) -> int:
    print("AirLLM aliases (--airllm mode):\n")
    for alias, repo in MODEL_ALIASES.items():
        print(f"  {alias:<9} {repo}")
    print("\nServed backends expose their own models. See them with:  airclaw detect")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="airclaw",
        description="Run OpenClaw on a local model. Zero API cost.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
typical use:
  airclaw detect          see what local backends are running
  airclaw start           serve the gateway on :4096
  airclaw patch           point OpenClaw at it
  airclaw doctor          diagnose a broken setup
  airclaw restore         undo the config change
""",
    )
    p.add_argument("--version", action="version", version=f"airclaw {__version__}")
    sub = p.add_subparsers(dest="command")

    d = sub.add_parser("detect", help="list running local inference servers")
    d.add_argument("--timeout", type=float, default=1.0)
    d.set_defaults(func=cmd_detect)

    s = sub.add_parser("start", help="start the AirClaw gateway")
    s.add_argument("--backend", default=None,
                   help="ollama|lmstudio|llamacpp|vllm|jan|tgw, or a full base URL")
    s.add_argument("--model", default=None, help="model name to serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=4096)
    s.add_argument("--airllm", action="store_true",
                   help="use in-process AirLLM (big model, small GPU, very slow)")
    s.set_defaults(func=cmd_start)

    pt = sub.add_parser("patch", help="write AirClaw into the OpenClaw config")
    pt.add_argument("--host", default="127.0.0.1")
    pt.add_argument("--port", type=int, default=4096)
    pt.add_argument("--config", default=None, help="explicit config path")
    pt.add_argument("--context-window", type=int, default=32768)
    pt.add_argument("--max-tokens", type=int, default=8192)
    pt.add_argument("--no-default", action="store_true",
                    help="register the provider but do not make it the default model")
    pt.add_argument("--create", action="store_true",
                    help="create the config file if it does not exist")
    pt.set_defaults(func=cmd_patch)

    r = sub.add_parser("restore", help="restore the config backup")
    r.add_argument("--config", default=None)
    r.set_defaults(func=cmd_restore)

    st = sub.add_parser("status", help="check whether the gateway is up")
    st.add_argument("--port", type=int, default=4096)
    st.set_defaults(func=cmd_status)

    dc = sub.add_parser("doctor", help="diagnose the whole chain")
    dc.add_argument("--port", type=int, default=4096)
    dc.add_argument("--timeout", type=float, default=1.0)
    dc.set_defaults(func=cmd_doctor)

    m = sub.add_parser("models", help="list AirLLM model aliases")
    m.set_defaults(func=cmd_models)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        print(BANNER)
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
