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
