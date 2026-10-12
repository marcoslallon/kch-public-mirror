#!/usr/bin/env bash
# Install an iPad-independent primary collector on existing KCH VM.
set -Eeuo pipefail
HOME_DIR=/home/a28449084
ROOT="$HOME_DIR/kch_mirror"
PUBLIC="$HOME_DIR/kch_public"
USER_NAME=a28449084
SRC_URL="https://raw.githubusercontent.com/marcoslallon/kch-public-mirror/main/scripts/kch_direct_collect.py"
mkdir -p "$ROOT" "$PUBLIC"
curl --fail --silent --show-error --location --retry 3 --connect-timeout 12 --max-time 45 "$SRC_URL" -o "$ROOT/kch_direct_collect.py.new"
python3 -m py_compile "$ROOT/kch_direct_collect.py.new"
mv "$ROOT/kch_direct_collect.py.new" "$ROOT/kch_direct_collect.py"
if [[ ! -x "$ROOT/direct-venv/bin/python" ]]; then
  python3 -m venv "$ROOT/direct-venv"
fi
"$ROOT/direct-venv/bin/python" -m pip install --disable-pip-version-check --quiet requests beautifulsoup4
# Keep old upload + GitHub publisher services intact.
cat > "$ROOT/kch-direct-collect.service" <<EOF
[Unit]
Description=KCH hospital public notices direct collector (iPad-independent)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$ROOT
Environment=KCH_OUTPUT_DIR=$PUBLIC
Environment=KCH_COLLECTOR_NAME=gcp-vm-direct
ExecStart=$ROOT/direct-venv/bin/python $ROOT/kch_direct_collect.py
TimeoutStartSec=105
StandardOutput=journal
StandardError=journal
EOF
cat > "$ROOT/kch-direct-collect.timer" <<'EOF'
[Unit]
Description=KCH iPad-free collection on weekdays before daily briefing

[Timer]
OnCalendar=Mon..Fri *-*-* 12:02:00 Asia/Seoul
OnCalendar=Mon..Fri *-*-* 12:04:00 Asia/Seoul
AccuracySec=1s
RandomizedDelaySec=0
Persistent=false
Unit=kch-direct-collect.service

[Install]
WantedBy=timers.target
EOF
sudo -n install -m 0644 "$ROOT/kch-direct-collect.service" /etc/systemd/system/kch-direct-collect.service
sudo -n install -m 0644 "$ROOT/kch-direct-collect.timer" /etc/systemd/system/kch-direct-collect.timer
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now kch-direct-collect.timer
printf '\n=== TIMER ===\n'
systemctl list-timers --all --no-pager | grep kch-direct || true
printf '\n=== IMPORTANT ===\n'
printf 'No manual collection was performed. Existing iPad intake, GitHub publisher, and 12:05 ChatGPT remain unchanged.\n'
printf 'To test explicitly (may publish validated fresh public notices):\n'
printf 'sudo systemctl start kch-direct-collect.service && sudo journalctl -u kch-direct-collect.service -n 50 --no-pager\n'
