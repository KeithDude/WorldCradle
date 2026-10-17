"""Test setup: RealmCradle's code runs against a throwaway data folder, never the real one."""
import os
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="realmcradle-test-")
os.environ["REALMCRADLE_HOME"] = _HOME           # read by app/paths.py when it is first imported
os.environ["REALMCRADLE_QUIET_LOG"] = "1"
os.environ.setdefault("REALMCRADLE_BACKUPS", os.path.join(_HOME, "backups"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/ helpers (provision_snapshots)
