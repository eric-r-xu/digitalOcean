# digitalOcean Flask Site

This repository is a Flask website intended to run behind Nginx on a DigitalOcean Droplet.

## What Serves What

- Nginx receives public HTTP/HTTPS traffic and serves `/static/*` files directly.
- Gunicorn runs the Flask app through `wsgi.py`.
- Flask renders the Jinja templates in `templates/` and handles the database-backed routes.
- MySQL stores the rain history and Klaviyo weather-email subscription data.

## Routes

- `/` renders the portfolio homepage from `templates/index.html`.
- `/old` renders the older portfolio page from `templates/index_old.html`.
- `/research` renders `templates/research.html`, which links to PDFs under `static/research/`.
- `/rain` reads locations from `initialize_mysql_rain.py` and rainfall data from `rain.tblFactLatLon`.
- `/klaviyo` validates an email address and inserts a subscription into `klaviyo.tblDimEmailCity`.

## Important Files

- `myproject.py`: Flask app, route handlers, database connections, and rate limiting.
- `wsgi.py`: WSGI entrypoint used by Gunicorn.
- `initialize_mysql_rain.py`: Rain location list plus schema setup for `rain.tblFactLatLon`.
- `local_settings.py`: Local secrets and city mappings. This file is required at runtime and intentionally ignored by git.
- `local_settings.example.py`: Copy this to `local_settings.py` and replace the placeholder values.
- `requirements.txt`: Python packages needed by the app.
- `deploy/myproject.service`: Example systemd service for Gunicorn.
- `deploy/nginx-site.conf`: Example Nginx server block.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
cp local_settings.example.py local_settings.py
```

Edit `local_settings.py` with the MySQL host, user, password, and real Klaviyo city mappings. The app imports this file on startup.

To run the app locally after MySQL is reachable:

```bash
gunicorn --bind 127.0.0.1:5000 wsgi:app
```

## DigitalOcean Droplet Deployment

These commands assume Ubuntu on a Droplet, a deploy user named `deploy`, and an install path of `/srv/digitalOcean`.

1. Install system packages:

```bash
sudo apt update
sudo apt install -y nginx git python3-venv python3-dev build-essential default-libmysqlclient-dev pkg-config
```

2. Create the deploy location:

```bash
sudo adduser deploy
sudo mkdir -p /srv/digitalOcean
sudo chown deploy:www-data /srv/digitalOcean
sudo chmod 775 /srv/digitalOcean
```

3. Put this repository at `/srv/digitalOcean`, then install Python dependencies:

```bash
cd /srv/digitalOcean
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
cp local_settings.example.py local_settings.py
```

4. Edit `local_settings.py`. Confirm the MySQL user can access the `rain` and `klaviyo` databases. `initialize_mysql_rain.py` creates `rain.tblFactLatLon` when the app imports, but the Klaviyo city/subscription tables must already exist.

5. Install and start the Gunicorn systemd service:

```bash
sudo cp deploy/myproject.service /etc/systemd/system/myproject.service
sudo systemctl daemon-reload
sudo systemctl enable --now myproject
sudo systemctl status myproject
```

6. Install the Nginx site:

```bash
sudo cp deploy/nginx-site.conf /etc/nginx/sites-available/digitalOcean
sudo sed -i 's/app.example.com/YOUR_DOMAIN/g' /etc/nginx/sites-available/digitalOcean
sudo ln -s /etc/nginx/sites-available/digitalOcean /etc/nginx/sites-enabled/digitalOcean
sudo nginx -t
sudo systemctl reload nginx
```

7. Open the firewall for Nginx:

```bash
sudo ufw allow 'Nginx Full'
```

8. Add HTTPS after DNS points at the Droplet:

```bash
sudo apt install -y python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN
```

DigitalOcean's Flask deployment guide also uses Gunicorn behind Nginx, with systemd managing the app and Nginx proxying to a Unix socket: https://www.digitalocean.com/community/tutorials/how-to-serve-flask-applications-with-gunicorn-and-nginx-on-ubuntu-22-04

## Troubleshooting

- App logs: `sudo journalctl -u myproject -f`
- Flask file log: `/srv/digitalOcean/logs/myproject.log`
- Nginx errors: `sudo tail -f /var/log/nginx/digitalOcean.error.log`
- Nginx config check: `sudo nginx -t`
- Restart after code changes: `sudo systemctl restart myproject`

If Nginx returns `502 Bad Gateway`, check that `myproject` is running and that `/run/myproject/myproject.sock` exists.
