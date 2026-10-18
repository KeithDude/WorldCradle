"""Test setup: WorldCradle's code runs against a throwaway data folder, never the real one."""
import os
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="worldcradle-test-")
os.environ["WORLDCRADLE_HOME"] = _HOME           # read by app/paths.py when it is first imported
os.environ["WORLDCRADLE_QUIET_LOG"] = "1"
os.environ.setdefault("WORLDCRADLE_BACKUPS", os.path.join(_HOME, "backups"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/ helpers (provision_snapshots)
