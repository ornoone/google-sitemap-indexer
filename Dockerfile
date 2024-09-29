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

# install chromedriver
RUN apt-get update -qq -y && \
    apt-get install -y \
        libasound2 \
        libatk-bridge2.0-0 \
        libgtk-4-1 \
        libnss3 \
        xdg-utils \
        wget && \
    wget -q -O chrome-linux64.zip https://bit.ly/chrome-linux64-121-0-6167-85 && \
    unzip chrome-linux64.zip && \
    rm chrome-linux64.zip && \
    mv chrome-linux64 /opt/chrome/ && \
    ln -s /opt/chrome/chrome /usr/local/bin/ && \
    wget -q -O chromedriver-linux64.zip https://bit.ly/chromedriver-linux64-121-0-6167-85 && \
    unzip -j chromedriver-linux64.zip chromedriver-linux64/chromedriver && \
    rm chromedriver-linux64.zip && \
    mv chromedriver /usr/local/bin/

RUN --mount=type=cache,target=/root/.cache pip install pipenv

# install dep
COPY Pipfile* .

RUN --mount=type=cache,target=/root/.cache pipenv sync --dev --system


# copy app
COPY ./app /app
RUN mkdir -p /app/media && /app/manage.py collectstatic --settings=google_indexer.settings.base --noinput

USER service

CMD ["/app/start.sh"]
