"""AirClaw — point OpenClaw at a local model and stop paying per token."""

__version__ = "3.0.0"

from airclaw.backends import Backend, detect_backends, pick_backend

__all__ = ["Backend", "__version__", "detect_backends", "pick_backend"]
