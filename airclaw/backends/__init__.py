"""Backend detection.

Probing is deliberately cheap: a GET /v1/models with a short timeout against a
handful of known localhost ports. No home-directory scanning, no subprocess
spelunking. If a server answers, it exists; if it doesn't answer in a second,
it may as well not.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import urllib.error
import urllib.request

from airclaw.backends.base import CANDIDATES, Backend

__all__ = ["Backend", "detect_backends", "pick_backend", "probe"]

PROBE_TIMEOUT = float(os.environ.get("AIRCLAW_PROBE_TIMEOUT", "1.0"))


def _get_json(url: str, timeout: float) -> dict | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return None
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _model_ids(payload: dict | None) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    data = payload.get("data")
    if not isinstance(data, list):
        return ()
    out = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(item["id"])
    return tuple(out)


def probe(name: str, base_url: str, label: str, timeout: float = PROBE_TIMEOUT) -> Backend | None:
    """Return a Backend if something OpenAI-shaped answers at base_url."""
    payload = _get_json(f"{base_url.rstrip('/')}/models", timeout)
    if payload is None:
        return None
    return Backend(name=name, base_url=base_url, kind="openai",
                   models=_model_ids(payload), note=label)


def detect_backends(timeout: float = PROBE_TIMEOUT) -> list[Backend]:
    """Probe all known local ports in parallel. Returns live ones, best first."""
    found: dict[str, Backend] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(CANDIDATES)) as pool:
        futures = {
            pool.submit(probe, name, url, label, timeout): name
            for name, url, label in CANDIDATES
        }
        for fut in concurrent.futures.as_completed(futures):
            backend = fut.result()
            if backend is not None:
                found[backend.name] = backend
    # Preserve CANDIDATES priority order rather than completion order.
    return [found[name] for name, _, _ in CANDIDATES if name in found]


def pick_backend(prefer: str | None = None, timeout: float = PROBE_TIMEOUT) -> Backend | None:
    """Pick a backend, honouring an explicit preference.

    `prefer` may be a known backend name (``ollama``) or a full base URL for
    anything not in the candidate list.
    """
    if prefer and "://" in prefer:
        return probe("custom", prefer, "custom endpoint", timeout)

    live = detect_backends(timeout)
    if prefer:
        for backend in live:
            if backend.name == prefer:
                return backend
        return None
    return live[0] if live else None
