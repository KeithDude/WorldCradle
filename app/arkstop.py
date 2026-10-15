#!/usr/bin/env python3
"""arkstop.py <rcon_port> <password> — graceful ARK shutdown via RCON
(SaveWorld then DoExit). Used as the ExecStop of gamedash-managed ARK units so
they save before stopping, without depending on any external script.
"""
import sys

try:
    from rcon.source import Client
except ImportError:
    sys.exit(0)  # no rcon module → let systemd just stop the process

if len(sys.argv) < 3:
    sys.exit(0)
port, passwd = int(sys.argv[1]), sys.argv[2]
for cmd in ("SaveWorld", "DoExit"):
    try:
        with Client("127.0.0.1", port, passwd=passwd, timeout=12) as c:
            c.run(cmd)
    except Exception:
        pass
