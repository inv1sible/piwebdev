#!/bin/sh
set -e

git config --global --add safe.directory '*'

python manage.py migrate --run-syncdb
python manage.py collectstatic --noinput -v 0
python manage.py bootstrap_superuser
exec daphne -b 0.0.0.0 -p 3142 piwebdev.asgi:application
