#!/usr/bin/env bash
# Build do Render: instala dependências, coleta estáticos e aplica migrações.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
