#!/bin/bash

# Collect static files into the staticfiles/ folder
# (Tailwind CDN has nothing to collect, but your own images/JS files do)
python manage.py collectstatic --noinput

# Run database migrations automatically on every deploy
python manage.py migrate --noinput

# Start Gunicorn — replace 'myproject' with YOUR project folder name
# This is the folder that contains settings.py and wsgi.py
gunicorn --bind=0.0.0.0 --timeout=600 backend.wsgi