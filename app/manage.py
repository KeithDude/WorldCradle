#!/usr/bin/env python3
"""manage.py — small admin CLI for the dashboard.

  manage.py set-password [PASSWORD]   set/replace the admin password
                                      (prompts securely if PASSWORD omitted)
  manage.py setup-code                print a one-time code for choosing the admin
                                      password in the browser (first-run setup)
  manage.py show                      print non-secret config
  manage.py install-cert              put a renewed certificate in place
                                      (run by the renewal timer)

Everyday jobs have friendlier versions in the `gamedash` command (cli.py).
"""
import getpass
import sys

import config


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "set-password":
        if len(sys.argv) >= 3:
            pw = sys.argv[2]
        else:
            pw = getpass.getpass("New admin password: ")
            if pw != getpass.getpass("Confirm: "):
                print("Passwords do not match.", file=sys.stderr)
                return 1
        if len(pw) < config.MIN_ADMIN_PASSWORD:
            print(f"Password must be at least {config.MIN_ADMIN_PASSWORD} characters — this login is the only thing "
                  "between the internet and full control of the servers.", file=sys.stderr)
            return 1
        config.set_password(pw)
        print("Admin password set.")
        return 0
    if cmd == "setup-code":
        if not config.needs_setup():
            print("An admin password is already set — sign in with it, or use "
                  "'manage.py set-password' to replace it.", file=sys.stderr)
            return 1
        print(config.new_setup_code())
        return 0
    if cmd == "install-cert":   # run by the renewal timer after certbot renews
        import certs
        domain = config.load().get("cert_domain", "")
        if not domain:
            print("No Let's Encrypt certificate is configured.", file=sys.stderr)
            return 1
        certs.install_issued(domain)
        certs.restart_dashboard()
        print(f"Installed the renewed certificate for {domain}; the dashboard is restarting.")
        return 0
    if cmd == "show":
        cfg = config.load()
        print(f"dev-server bind: {cfg['bind_host']}:{cfg['bind_port']} "
              f"(the service's real address is set in gamedash.service)")
        print(f"admin password set: {'yes' if cfg['admin_password_hash'] else 'no'}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
