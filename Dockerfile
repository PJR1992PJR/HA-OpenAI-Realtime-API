FROM python:3.11-slim

# Install dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatlas3-base \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir openai sounddevice requests pvporcupine

# Copy the assistant script
COPY assistant.py /app/assistant.py

# Run the assistant
CMD ["python", "/app/assistant.py"]
