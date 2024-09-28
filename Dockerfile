# syntax=docker/dockerfile:1.4
FROM python:3.11-bookworm

LABEL stdout-format="python-json"
LABEL project="google_indexer"

WORKDIR /app

RUN useradd -d /app/ -Ms /bin/sh service
RUN --mount=type=cache,sharing=locked,target=/var/cache/apt apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        netcat-traditional \
        netbase \
        wget \
        python3-pip \
        python3-dev \
        libgdal32 \
        build-essential\
        python3-setuptools\
        python3-wheel\
        python3-cffi\
        libcairo2\
        libpango-1.0-0\
        libpangocairo-1.0-0\
        libgdk-pixbuf2.0-0\
        libffi-dev \
        shared-mime-info \
 && rm -rf /var/lib/apt/lists/*


# setup healthcheck
COPY ./check_http.sh /app/
HEALTHCHECK --interval=4s --timeout=6s --retries=2 CMD ["/app/check_http.sh",  "8000"]


RUN --mount=type=cache,target=/root/.cache pip install pipenv

# install dep
COPY Pipfile* .

RUN --mount=type=cache,target=/root/.cache pipenv sync --dev --system


# copy app
COPY ./app /app
RUN mkdir -p /app/media && /app/manage.py collectstatic --settings=google_indexer.settings.base --noinput

CMD ["/app/start.sh"]
