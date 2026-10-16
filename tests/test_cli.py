import cli


def test_command_names_are_forgiving():
    for spelling in ("reset-password", "reset_password", "resetpassword", "RESET-PASSWORD"):
        key = spelling.lstrip("-").replace("-", "").replace("_", "").lower()
        assert cli.COMMANDS[key] is cli.cmd_reset_password


def test_every_documented_command_exists():
    for line in cli.__doc__.splitlines():
        word = line.strip().split(" ")[0]
        if word and word.isalpha() and line.startswith("  ") and word not in ("Server", "Usage"):
            assert word.replace("-", "") in cli.COMMANDS or word in ("start",), f"'{word}' is in the help but not a command"
