#!/bin/bash
cd "$(dirname "$0")"
python manage.py migrate
gunicorn --bind=0.0.0.0:8000 --timeout 600 backend.wsgi