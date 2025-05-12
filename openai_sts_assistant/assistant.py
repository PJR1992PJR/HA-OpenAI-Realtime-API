import asyncio, base64, json, os, sys, aiohttp, websockets, numpy as np
import sounddevice as sd
from pvporcupine import Porcupine
from rapidfuzz import process

API_KEY   = os.getenv("OPENAI_API_KEY")
MODEL     = os.getenv("MODEL", "gpt-4o-realtime-preview")
VOICE     = os.getenv("ASSISTANT_VOICE", "alloy")
RATE      = int(os.getenv("SAMPLE_RATE", "24000"))
WAKE_WORD = os.getenv("WAKE_WORD", "jarvis")
HASS      = os.getenv("HASS_URL")
TOKEN     = os.getenv("HASS_TOKEN")
HEADERS   = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

### ─────────────────────────── Home Assistant helpers ──────────────────────────
async def call_ha(service, data):
    domain, srv = service.split(".")
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        await s.post(f"{HASS}/api/services/{domain}/{srv}", json=data)

async def get_entity_map():
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        async with s.get(f"{HASS}/api/states") as r:
            states = await r.json()
    areas = {}
    for st in states:
        area = st.get("attributes", {}).get("area_id", "unknown")
        areas.setdefault(area, []).append(st["entity_id"])
    return areas

### ───────────────────────────── Audio plumbing ────────────────────────────────
def play(pcm):
    sd.play(np.frombuffer(pcm, np.int16), RATE)

async def mic_stream():
    """Async generator of 50 ms PCM chunks (little-endian S16)."""
    block = int(RATE * 0.05)
    with sd.InputStream(channels=1, samplerate=RATE, dtype="int16") as rec:
        while True:
            audio, _ = rec.read(block)
            yield audio.tobytes()

### ─────────────────────────── Realtime session logic ──────────────────────────
async def converse():
    uri = f"wss://api.openai.com/v1/realtime/audio?model={MODEL}"
    async with websockets.connect(uri,
            extra_headers={"Authorization": f"Bearer {API_KEY}"}) as ws:

        # 1️⃣  Send the "start" frame with system prompt & tool schema
        areas = await get_entity_map()
        start = {
            "type": "start",
            "audio_format": {"type": "wav", "sample_rate": RATE},
            "voice": {"name": VOICE},
            "messages": [{
                "role": "system",
                "content": (
                    "You are a Home Assistant voice butler. "
                    f"Areas and entities: {json.dumps(areas)}. "
                    "When you need to act, reply with a JSON tool call: "
                    '{"service":"domain.service","data":{...}}'
                )
            }],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "call_home_assistant",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service": {"type": "string"},
                            "data":    {"type": "object"}
                        },
                        "required": ["service"]
                    }
                }
            }]
        }
        await ws.send(json.dumps(start))

        # 2️⃣  Start sending and receiving in parallel
        async def sender():
            async for chunk in mic_stream():
                await ws.send(base64.b64encode(chunk))
            await ws.send(json.dumps({"type":"stop"}))

        async def receiver():
            async for msg in ws:
                if isinstance(msg, bytes):          # assistant audio
                    play(msg)
                else:                              # JSON control
                    payload = json.loads(msg)
                    if payload.get("type") == "tool_call":
                        svc = payload["id"]["service"]
                        data = payload["id"].get("data", {})
                        await call_ha(svc, data)

        await asyncio.gather(sender(), receiver())

### ─────────────────────────── Wake-word outer loop ────────────────────────────
async def main():
    detector = Porcupine(keyword_paths=[Porcupine.KEYWORD_PATHS[WAKE_WORD]])
    block = detector.frame_length
    with sd.InputStream(channels=1, samplerate=detector.sample_rate) as stream:
        while True:
            pcm, _ = stream.read(block)
            if detector.process(pcm.flatten()) >= 0:
                play(b"\x00"*RATE)     # beep (silence placeholder)
                await converse()       # one conversational turn

if __name__ == "__main__":
    asyncio.run(main())
