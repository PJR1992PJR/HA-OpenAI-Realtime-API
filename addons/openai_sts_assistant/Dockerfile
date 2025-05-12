ARG BUILD_FROM=ghcr.io/home-assistant/amd64-addon-base:14.0
FROM ${BUILD_FROM}

RUN apk add --no-cache alsa-utils libstdc++ pulseaudio-utils jq curl

RUN pip install --no-cache-dir \
      websockets==12.0 \
      sounddevice==0.4.6 \
      numpy==1.26.4 \
      rapidfuzz==3.7.0

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY run.sh /run.sh
COPY assistant.py /app/assistant.py
RUN chmod a+x /run.sh

ENTRYPOINT ["/run.sh"]
