FROM python:3.11-slim

# install system libs for audio (ALSA/PulseAudio)
RUN apt-get update \
  && apt-get install -y --no-install-recommends libsndfile1 ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# bring in your Python deps
RUN pip install --no-cache-dir openai sounddevice requests pvporcupine

# copy your entrypoint and code
COPY run.sh /run.sh
COPY assistant.py /assistant.py
RUN chmod +x /run.sh

ENTRYPOINT [ "/run.sh" ]
