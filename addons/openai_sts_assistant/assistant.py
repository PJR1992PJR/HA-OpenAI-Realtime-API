#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import logging
from pathlib import Path

import requests
import sounddevice as sd
import pvporcupine
import websockets

# ─── Load add-on options ──────────────────────────────────────────────────────
try:
    with open("/data/options.json", "r") as f:
        opts = json.load(f)
except FileNotFoundError:
    print("ERROR: /data/options.json not found", file=sys.stderr)
    sys.exit(1)

OPENAI_API_KEY = opts.get("openai_api_key")
WAKE_WORD       = opts.get("wake_word")
MODEL           = opts.get("model")
SAMPLE_RATE     = int(opts.get("sample_rate", 24000))
LANGUAGE        = opts.get("language", "en")
LOG_LEVEL       = opts.get("log_level", "INFO").upper()

# ─── Validate required options ────────────────────────────────────────────────
for name in ("openai_api_key", "wake_word", "model", "sample_rate"):
    if not opts.get(name):
        print(f"ERROR: Missing option '{name}' in /data/options.json", file=sys.stderr)
        sys.exit(1)

# ─── Configure logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("openai_sts_assistant")

# ─── Home Assistant API setup ─────────────────────────────────────────────────
HASS_URL        = os.getenv("HASS_URL", "http://supervisor/core/api")
SUPERVISOR_TOKEN= os.getenv("SUPERVISOR_TOKEN")
if not SUPERVISOR_TOKEN:
    logger.critical("SUPERVISOR_TOKEN not provided by Supervisor")
    sys.exit(1)
HEADERS = {
    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
    "Content-Type": "application/json"
}

# ─── Porcupine wake-word init ──────────────────────────────────────────────────
porcupine = pvporcupine.create(keywords=[WAKE_WORD])
logger.info(f"Porcupine initialized for wake word: '{WAKE_WORD}'")

# ─── Home Assistant helpers ───────────────────────────────────────────────────
async def call_ha(service: str, data: dict):
    """Invoke a Home Assistant service call via REST API."""
    domain, svc = service.split(".", 1)
    url = f"{HASS_URL}/services/{domain}/{svc}"
    resp = requests.post(url, headers=HEADERS, json=data)
    if not resp.ok:
        logger.error(f"HA service call {service} failed: {resp.status_code} {resp.text}")

async def get_area_map() -> dict:
    """Fetch all states and group entity_ids by area_id."""
    url = f"{HASS_URL}/states"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    states = resp.json()
    areas = {}
    for s in states:
        area = s.get("attributes", {}).get("area_id", "unknown")
        areas.setdefault(area, []).append(s["entity_id"])
    return areas

# ─── Audio utility functions ──────────────────────────────────────────────────
def play_audio(pcm_bytes: bytes):
    """Play raw 16-bit PCM at SAMPLE_RATE."""
    sd.play(pcm_bytes, samplerate=SAMPLE_RATE)
    sd.wait()

async def mic_audio_generator():
    """Async generator yielding raw PCM chunks (~100 ms each)."""
    chunk_size = int(SAMPLE_RATE * 0.1)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while True:
            data, _ = stream.read(chunk_size)
            yield data.tobytes()

# ─── OpenAI Realtime STS session ──────────────────────────────────────────────
async def converse_once():
    uri = f"wss://api.openai.com/v1/realtime/audio?model={MODEL}"
    async with websockets.connect(uri, extra_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}) as ws:

        # Build system prompt with your area map
        areas = await get_area_map()
        start_msg = {
            "type": "start",
            "audio_format": {"type": "wav", "sample_rate": SAMPLE_RATE},
            "voice": {"name": LANGUAGE},
            "messages": [
                {
                    "role": "system",
                    "content": "You are my Home Assistant voice assistant. "
                               f"Areas: {json.dumps(areas)}."
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "call_home_assistant",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "service": {"type": "string"},
                                "data": {"type": "object"}
                            },
                            "required": ["service"]
                        }
                    }
                }
            ]
        }
        await ws.send(json.dumps(start_msg))
        logger.info("Sent start frame to OpenAI Realtime API")

        # Send mic audio & receive assistant audio / function calls
        async def sender():
            async for chunk in mic_audio_generator():
                await ws.send(chunk)
            await ws.send(json.dumps({"type": "stop"}))

        async def receiver():
            async for msg in ws:
                if isinstance(msg, bytes):
                    play_audio(msg)
                else:
                    payload = json.loads(msg)
                    if payload.get("type") == "tool_call":
                        svc  = payload["id"]["service"]
                        data = payload["id"].get("data", {})
                        await call_ha(svc, data)

        await asyncio.gather(sender(), receiver())

# ─── Wake-word loop ───────────────────────────────────────────────────────────
async def main():
    frame_len = porcupine.frame_length
    with sd.InputStream(samplerate=porcupine.sample_rate, channels=1, dtype="int16") as stream:
        while True:
            pcm, _ = stream.read(frame_len)
            if porcupine.process(pcm.flatten()) >= 0:
                logger.info("Wake word detected, starting conversation")
                try:
                    await converse_once()
                except Exception as e:
                    logger.error(f"Error during Realtime conversation: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Assistant stopped by user")
