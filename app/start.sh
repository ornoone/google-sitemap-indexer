#!/bin/bash

set -euo pipefail

ENV=${ENV:-dev}

NAME="google_indexer"                                # Name of the application
DJANGODIR=/app                                     # Django project directory
USER=root                                          # the user to run as
GROUP=root                                         # the group to run as
NUM_WORKERS=${NUM_WORKERS:-4}                      # how many worker processes should Gunicorn spaw
TIMEOUT=120
export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-google_indexer.settings.$ENV}     # which settings file should Django use
DJANGO_WSGI_MODULE=google_indexer.wsgi                  # WSGI module name
DJANGO_ASGI_MODULE=google_indexer.asgi               # WSGI module name
PORT=8000
LOGLEVEL=${LOGLEVEL:-error}
export PYTHONUNBUFFERED=1

migrate() {
  ./manage.py migrate --noinput --settings=$DJANGO_SETTINGS_MODULE
}

start_huey() {
  ./manage.py run_huey  --settings=$DJANGO_SETTINGS_MODULE
}

start_gunicorn() {


  echo "starting gunicorn with settings ${DJANGO_SETTINGS_MODULE}"
  # Start your Django Unicorn
  # Programs meant to be run under supervisor should not daemonize themselves (do not use --daemon)
  exec gunicorn ${DJANGO_WSGI_MODULE}:application \
      --name $NAME \
      --workers $NUM_WORKERS \
      --timeout $TIMEOUT \
      --log-level=$LOGLEVEL \
      --bind=0:8000 \
      --worker-class gevent \
      --limit-request-line=9999
}


start_runserver() {


  echo "starting django dev server with settings ${DJANGO_SETTINGS_MODULE}"
  exec python manage.py runserver 0.0.0.0:8000
}

start_daphne() {
  echo "starting daphne with settings ${DJANGO_SETTINGS_MODULE}"

  exec daphne ${DJANGO_ASGI_MODULE}:application \
      --bind 0.0.0.0 \
      --port 9000 \
      --verbosity 1
}

task=${1:-${START}}
echo "doing task ${task}"
WAITFOR="${WAITFOR:-${DB_HOST:-database}}:5432"
echo "waitfor: ${WAITFOR}"
test -z "${WAITFOR+x}" || ./wait-for ${WAITFOR} -t 25

case "${task}" in
  "daphne")
    start_daphne
  ;;
  "gunicorn")
    start_gunicorn
  ;;
  "migrate")
    migrate
  ;;
  "runserver")
    start_runserver
  ;;
  "huey")
    start_huey
  ;;
  *)
    echo "shoudl call me with daphne|gunicorn|migrate|runserver|huey"

esac
