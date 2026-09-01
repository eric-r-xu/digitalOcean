# digitalOcean Flask Site

Flask portfolio and weather applications deployed on one Ubuntu DigitalOcean
Droplet. The production stack deliberately stays small:

- Nginx terminates HTTP/HTTPS and serves `/static/*`.
- Gunicorn runs the Flask WSGI application behind a Unix socket.
- Redis stores rate-limit counters shared by all Gunicorn workers.
- MySQL stores rain history and email subscriptions.
- systemd starts, supervises, and logs the application and Redis services.

This deployment does not need Docker, Kubernetes, Node.js, or a separate process
manager. Ubuntu packages manage Nginx and Redis; a Python virtual environment
isolates application dependencies.

## Application behavior

- `/`, `/old`, and `/research` render portfolio content.
- `GET /rain` and `GET /klaviyo` render forms.
- `POST /rain` reads rainfall history from MySQL.
- `POST /klaviyo` validates and stores a subscription in MySQL.

Only the two POST routes are rate limited. Each allows 50 requests per client IP
per hour and 500 per day. Nginx is the single trusted proxy, and Redis makes the
counters consistent across the three Gunicorn workers. Public GET routes are not
subject to these application-level limits.

## Important files

- `myproject.py`: Flask routes, database clients, and Redis-backed rate limiting.
- `wsgi.py`: Gunicorn entrypoint.
- `local_settings.example.py`: tracked template for the required, ignored
  `local_settings.py` city mappings.
- `requirements.txt`: Python runtime dependencies.
- `deploy/myproject.env.example`: production environment template.
- `deploy/myproject.service`: systemd unit for Gunicorn.
- `deploy/nginx-site.conf`: initial Nginx server block.

## Local development

MySQL and Redis must be reachable before importing the application. By default,
Redis is expected at `redis://127.0.0.1:6379/0`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
cp local_settings.example.py local_settings.py
gunicorn --bind 127.0.0.1:5000 wsgi:app
```

Edit `local_settings.py` with the real city mappings. Supply `MYSQL_HOST`,
`MYSQL_USER`, and `MYSQL_PASSWORD` through the shell environment; do not commit
credentials.

## Production layout

The checked-in service and Nginx files use these paths:

| Purpose | Path or identity |
| --- | --- |
| Application user | `deploy` |
| Repository | `/srv/digitalOcean` |
| Virtual environment | `/srv/digitalOcean/.venv` |
| Runtime configuration | `/etc/myproject/myproject.env` |
| Gunicorn socket | `/run/myproject/myproject.sock` |
| Application log | `/srv/digitalOcean/logs/myproject.log` |

Do not run Gunicorn as root or point the service at a checkout under `/root`.
If an administrative checkout already exists at `/root/digitalOcean`, leave it
as a temporary staging copy and create the production checkout under `/srv`.

## One-time Droplet provisioning

These steps assume Ubuntu, working DNS, an existing MySQL service, and a sudo-capable
administrator. Commands that own application files run as `deploy`.

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y nginx redis-server git python3-venv python3-dev build-essential default-libmysqlclient-dev pkg-config python3-certbot-nginx
```

### 2. Create the service account and application directory

Skip `adduser` if the account already exists.

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo install -d -o deploy -g www-data -m 0750 /srv/digitalOcean
```

### 3. Give the service account read-only GitHub access

For a private repository, create a dedicated SSH deploy key as `deploy`:

```bash
sudo -u deploy install -d -m 0700 /home/deploy/.ssh
sudo -u deploy ssh-keygen -t ed25519 -C "digitalOcean production deploy key" -f /home/deploy/.ssh/github_digitalocean_deploy -N ""
sudo cat /home/deploy/.ssh/github_digitalocean_deploy.pub
```

Add the public key in GitHub under **Repository settings → Deploy keys** and leave
write access disabled. Create `/home/deploy/.ssh/config` with:

```sshconfig
Host github-digitalocean
    HostName github.com
    User git
    IdentityFile /home/deploy/.ssh/github_digitalocean_deploy
    IdentitiesOnly yes
```

Then secure and test it:

```bash
sudo chown deploy:deploy /home/deploy/.ssh/config
sudo chmod 0600 /home/deploy/.ssh/config
sudo -u deploy ssh -T git@github-digitalocean
```

The successful GitHub message says shell access is unavailable; that is expected.
Clone the production branch:

```bash
sudo -u deploy git clone --branch main git@github-digitalocean:eric-r-xu/digitalOcean.git /srv/digitalOcean
```

### 4. Configure application secrets and mappings

Keep database credentials outside the checkout:

```bash
cd /srv/digitalOcean
sudo install -d -o root -g root -m 0755 /etc/myproject
sudo install -o root -g root -m 0600 deploy/myproject.env.example /etc/myproject/myproject.env
sudoedit /etc/myproject/myproject.env
sudo -u deploy cp local_settings.example.py local_settings.py
sudo -u deploy chmod 0600 local_settings.py
sudo -u deploy nano local_settings.py
```

Set the real MySQL credentials in `/etc/myproject/myproject.env` and the real city
mappings in `local_settings.py`. The MySQL user must be able to use the `rain` and
`klaviyo` databases. Importing the application creates `rain.tblFactLatLon` if it
does not exist; the Klaviyo city and subscription tables must already exist.

### 5. Install Python dependencies

```bash
cd /srv/digitalOcean
sudo -u deploy python3 -m venv .venv
sudo -u deploy .venv/bin/python -m pip install --upgrade pip wheel
sudo -u deploy .venv/bin/python -m pip install -r requirements.txt
sudo -u deploy .venv/bin/python -m pip check
```

### 6. Start and secure Redis

```bash
sudo systemctl enable --now redis-server
redis-cli ping
sudo redis-cli CONFIG GET bind
sudo redis-cli CONFIG GET protected-mode
sudo ss -ltnp | grep ':6379'
```

Required results:

- `redis-cli ping` returns `PONG`.
- Protected mode is `yes`.
- Redis listens only on `127.0.0.1` and optionally `::1`.
- Port 6379 is not allowed through UFW or a DigitalOcean Cloud Firewall.

### 7. Install the application service

```bash
cd /srv/digitalOcean
sudo install -m 0644 deploy/myproject.service /etc/systemd/system/myproject.service
sudo systemd-analyze verify /etc/systemd/system/myproject.service
sudo systemctl daemon-reload
sudo systemctl enable --now myproject
sudo systemctl --no-pager --full status myproject
```

The service requires Redis and intentionally has no in-memory production fallback.
If Redis is unavailable, limited POST requests fail instead of bypassing protection
or using inconsistent per-worker counters.

### 8. Configure Nginx and HTTPS

```bash
cd /srv/digitalOcean
sudo install -m 0644 deploy/nginx-site.conf /etc/nginx/sites-available/digitalOcean
sudoedit /etc/nginx/sites-available/digitalOcean
sudo ln -s /etc/nginx/sites-available/digitalOcean /etc/nginx/sites-enabled/digitalOcean
sudo nginx -t
sudo systemctl reload nginx
sudo ufw allow 'Nginx Full'
sudo certbot --nginx -d app.ericrxu.com
```

Set the Nginx `server_name` before testing or running Certbot. The included Ubuntu
`proxy_params` must forward `X-Forwarded-For` and `X-Forwarded-Proto`; `ProxyFix`
trusts exactly this one Nginx hop.

## Routine deployment

Commit, review, and merge changes into `main` before deploying. On the Droplet,
run Git and Python commands as `deploy` so the checkout never gains root-owned
files:

```bash
cd /srv/digitalOcean
sudo -u deploy git status --short
sudo -u deploy git rev-parse HEAD
sudo -u deploy git fetch origin main
sudo -u deploy git merge --ff-only origin/main
sudo -u deploy .venv/bin/python -m pip install -r requirements.txt
sudo -u deploy .venv/bin/python -m pip check
sudo -u deploy .venv/bin/python -m compileall -q myproject.py wsgi.py initialize_mysql_rain.py local_settings.py
sudo install -m 0644 deploy/myproject.service /etc/systemd/system/myproject.service
sudo systemd-analyze verify /etc/systemd/system/myproject.service
sudo systemctl daemon-reload
sudo systemctl restart myproject
sudo systemctl --no-pager --full status myproject
```

Record the commit printed by `git rev-parse HEAD` before updating. An empty
`git status --short` is required before the merge. Redis and Nginx do not need to
restart during a normal application deployment.

Do not overwrite `/etc/nginx/sites-available/digitalOcean` during routine releases:
Certbot may have added the active TLS configuration there. Review and apply Nginx
changes separately, followed by `sudo nginx -t` and a reload.

## Production verification

The public page should return 200 without rate-limit headers:

```bash
curl -sS -D - -o /dev/null https://app.ericrxu.com/
```

A harmless invalid POST exercises the limiter without querying rain history:

```bash
curl -sS -D - -o /dev/null -X POST --data-urlencode 'i_location_name=__rate_limit_smoke_test__' https://app.ericrxu.com/rain
redis-cli --scan --pattern 'LIMITS:*digitalocean*'
```

The POST response should include `X-RateLimit-Limit`,
`X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After`. Do not generate
51 production requests merely to test the 429 response.

## Operations and recovery

Useful checks:

```bash
sudo journalctl -u myproject -n 100 --no-pager
sudo journalctl -u redis-server -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/digitalOcean.error.log
redis-cli ping
sudo nginx -t
```

If Nginx returns 502, verify that `myproject` is active and that
`/run/myproject/myproject.sock` exists. If limited POST requests fail, check Redis
before restarting the application:

```bash
sudo systemctl restart redis-server
redis-cli ping
sudo systemctl restart myproject
```

For application rollback, revert the release commit through the normal Git review
workflow, merge the revert into `main`, and run the routine deployment again. This
preserves an auditable history and avoids destructive resets on the Droplet. Redis
can remain installed during rollback.
