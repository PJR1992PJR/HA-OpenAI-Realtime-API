import os
import asyncio
import json
import requests
import pvporcupine
import sounddevice as sd
from openai import OpenAI

# Load configuration from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HASS_TOKEN = os.getenv("HASS_TOKEN")
HASS_URL = os.getenv("HASS_URL")
WAKE_WORD = os.getenv("WAKE_WORD", "jarvis")

# Home Assistant headers
HEADERS = {"Authorization": f"Bearer {HASS_TOKEN}", "Content-Type": "application/json"}

# Initialize Porcupine wake‑word engine
porcupine = pvporcupine.create(keywords=[WAKE_WORD])

# Function definitions for Home Assistant service calls

def set_light_brightness(area: str, brightness_level: int) -> str:
    # Fetch all entities, filter lights by area
    resp = requests.get(f"{HASS_URL}/api/states", headers=HEADERS).json()
    lights = [s["entity_id"] for s in resp if s["entity_id"].startswith("light.")
              and s.get("attributes", {}).get("area_id") == area]
    for ent in lights:
        requests.post(
            f"{HASS_URL}/api/services/light/turn_on",
            headers=HEADERS,
            json={"entity_id": ent, "brightness": brightness_level}
        )
    return f"Set brightness to {brightness_level} in area {area}."


def create_automation(yaml: str) -> str:
    # Append to automations.yaml and reload
    with open("/config/automations.yaml", "a") as f:
        f.write("\n" + yaml + "\n")
    requests.post(f"{HASS_URL}/api/services/automation/reload", headers=HEADERS)
    return "Created and reloaded new automation."


async def listen_for_wake_and_audio() -> bytes:
    # Continuously read from microphone until wake word detected, then collect speech
    stream = sd.InputStream(samplerate=16000, channels=1, dtype="int16")
    buffer = []
    with stream:
        while True:
            frame, _ = stream.read(512)
            pcm = frame.flatten().tolist()
            result = porcupine.process(frame.flatten())
            if result >= 0:
                break  # wake word detected
        # After wake, capture until silence or timeout
        silence_count = 0
        while silence_count < 30:  # ~1 second of silence
            frame, _ = stream.read(512)
            buffer.extend(frame.flatten().tolist())
            if max(abs(x) for x in frame.flatten()) < 500:
                silence_count += 1
            else:
                silence_count = 0
    # Convert to bytes
    return (b"".join(int(v).to_bytes(2, "little", signed=True) for v in buffer))


async def main():
    # Initialize OpenAI client
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Prepare function schemas
    functions = [
        {
            "name": "set_light_brightness",
            "description": "Set brightness for all lights in an area",
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {"type": "string"},
                    "brightness_level": {"type": "integer"}
                },
                "required": ["area", "brightness_level"]
            }
        },
        {
            "name": "create_automation",
            "description": "Create a Home Assistant automation (YAML)",
            "parameters": {"type": "object", "properties": {"yaml": {"type": "string"}}, "required": ["yaml"]}
        }
    ]

    # Start realtime session
    async with client.realtime.connect(model="gpt-4o-realtime-preview", functions=functions) as sess:
        # Build a system prompt describing areas
        resp = requests.get(f"{HASS_URL}/api/areas", headers=HEADERS).json()
        area_map = [a["name"] for a in resp]
        sys_msg = f"You are a voice assistant for my home. Areas: {', '.join(area_map)}."
        await sess.send_system_message(sys_msg)

        # Main loop: listen, send, handle response
        while True:
            audio_bytes = await listen_for_wake_and_audio()
            await sess.send_audio(audio_bytes)
            async for msg in sess:
                if hasattr(msg, "function_call") and msg.function_call:
                    name = msg.function_call.name
                    args = msg.function_call.arguments
                    result = globals()[name](**args)
                    await sess.send_function_response(name, result)
                if hasattr(msg, "audio") and msg.audio:
                    sd.play(msg.audio, samplerate=24000)
                    sd.wait()

if __name__ == "__main__":
    asyncio.run(main())
