"""Test setup: GameDash's code runs against a throwaway data folder, never the real one."""
import os
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="gamedash-test-")
os.environ["GAMEDASH_HOME"] = _HOME           # read by app/paths.py when it is first imported
os.environ["GAMEDASH_QUIET_LOG"] = "1"
os.environ.setdefault("GAMEDASH_BACKUPS", os.path.join(_HOME, "backups"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
