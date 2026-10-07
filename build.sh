#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

cd ai_assignment
python manage.py collectstatic --no-input
python manage.py migrate
