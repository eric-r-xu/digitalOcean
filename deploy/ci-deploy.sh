#!/usr/bin/env bash
# Deploy origin/main on the Droplet. Run as the `deploy` user via the forced
# command on the GitHub Actions SSH key. Install outside the checkout:
#   sudo install -o root -g root -m 0755 deploy/ci-deploy.sh /usr/local/bin/myproject-ci-deploy
set -euo pipefail

APP_DIR=/srv/digitalOcean
SOCKET=/run/myproject/myproject.sock

expected_sha="${SSH_ORIGINAL_COMMAND:-}"
if [[ -n "$expected_sha" && ! "$expected_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "error: argument must be a 40-character commit SHA" >&2
    exit 2
fi

cd "$APP_DIR"

if [[ -n "$(git status --short)" ]]; then
    echo "error: working tree is not clean; refusing to deploy" >&2
    git status --short >&2
    exit 1
fi

echo "previous HEAD: $(git rev-parse HEAD)"
git fetch origin main
git merge --ff-only origin/main
head_sha="$(git rev-parse HEAD)"
echo "deployed HEAD: $head_sha"
if [[ -n "$expected_sha" && "$expected_sha" != "$head_sha" ]]; then
    echo "warning: expected $expected_sha; origin/main has moved on to $head_sha"
fi

.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q myproject.py wsgi.py initialize_mysql_rain.py local_settings.py

sudo /usr/bin/systemctl restart myproject

for _ in $(seq 1 20); do
    if curl -fsS -o /dev/null --unix-socket "$SOCKET" http://localhost/; then
        echo "health check passed"
        exit 0
    fi
    sleep 1
done

echo "error: health check failed" >&2
sudo /usr/bin/systemctl --no-pager --full status myproject >&2 || true
exit 1
