#!/usr/bin/env python3
"""arkstop.py <rcon_port> <password> — graceful ARK shutdown via RCON
(SaveWorld then DoExit). Used as the ExecStop of gamedash-managed ARK units so
they save before stopping, without depending on any external script.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monitor  # noqa: E402  (GameDash's own RCON client)

if len(sys.argv) < 3:
    sys.exit(0)
port, passwd = int(sys.argv[1]), sys.argv[2]
for cmd in ("SaveWorld", "DoExit"):
    monitor.source_rcon(port, passwd, cmd, timeout=12)
