# fail2ban for GameDash — install

Bans IPs that repeatedly fail the dashboard login, at the firewall, on port 8443
only. Watches GameDash's `audit.log` (in the data root, default
`~/.config/gamedash/logs/audit.log`). Needs root. (`setup.sh --fail2ban` does all
of this for you, substituting the real log path.)

## Install
First set the log path in the jail file — replace `__GAMEDASH_LOGS__` with the
ABSOLUTE logs dir of the user running GameDash (fail2ban runs as root, so `~`
won't expand), e.g. `/home/youruser/.config/gamedash/logs`:
```
LOGS="$HOME/.config/gamedash/logs"      # adjust if you set $GAMEDASH_HOME
sed "s#__GAMEDASH_LOGS__#$LOGS#" deploy/fail2ban/gamedash-jail.conf | sudo tee /etc/fail2ban/jail.d/gamedash.conf
sudo cp deploy/fail2ban/gamedash-filter.conf /etc/fail2ban/filter.d/gamedash.conf
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
sudo systemctl restart fail2ban
```

## Verify
```
# filter matches the log (should report several matches if there have been failures):
sudo fail2ban-regex "$HOME/.config/gamedash/logs/audit.log" /etc/fail2ban/filter.d/gamedash.conf

# jail is up and reading the log:
sudo fail2ban-client status gamedash
```

## Manage
```
sudo fail2ban-client status gamedash          # see banned IPs / counts
sudo fail2ban-client set gamedash unbanip <IP> # unban (e.g. if you lock yourself out)
sudo fail2ban-client set gamedash banip <IP>   # manual ban
```

## Tuning (edit /etc/fail2ban/jail.d/gamedash.conf, then `sudo systemctl restart fail2ban`)
- `maxretry` (4) / `findtime` (600s) — failures-per-window before a ban.
- `bantime` (3600s) — ban length; set `-1` for permanent.
- `ignoreip` — add your home/VPN public IP so you can never lock yourself out.

Notes:
- Bans only port 8443, so a friend fumbling the dashboard password won't be cut
  off from the game servers.
- fail2ban runs as root and can read the 0600 audit.log fine.
- If banning doesn't take effect, the backend may need nftables: set
  `banaction = nftables-multiport` in the jail and restart.
