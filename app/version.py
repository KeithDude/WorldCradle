"""version.py — WorldCradle's version number (from the VERSION file at the top of the project)."""
import os

_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")


def version() -> str:
    try:
        with open(_FILE, encoding="utf-8") as f:
            return f.read().strip() or "unknown"
    except OSError:
        return "unknown"
