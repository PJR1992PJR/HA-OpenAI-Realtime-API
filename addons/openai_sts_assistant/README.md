# OpenAI STS Voice Assistant Add-on

A Home Assistant add-on for a streaming speech-to-speech voice assistant using OpenAI's `gpt-4o-realtime-preview` API.

## Features
- Custom wake-word support via Porcupine
- True streaming STT→GPT→TTS with sub-second latency
- Function-calling to control Home Assistant entities by area
- Dynamic automation authoring in YAML

## Installation
1. Create a new GitHub repo with this structure.
2. In Home Assistant UI: Supervisor → Add-on Store → Repositories → Add your repo URL.
3. Install **OpenAI STS Voice Assistant**.
4. Under Configuration, set secrets:
   ```yaml
   OPENAI_API_KEY: !secret openai_key
   HASS_TOKEN: !secret hass_token
   HASS_URL: http://supervisor/core/api
   WAKE_WORD: jarvis

### Quick test
1. Plug in a microphone & speaker on the host.
2. Add your OpenAI key and Home Assistant token in the add-on *Configuration*.
3. Start the add-on, watch the logs for:  💤 waiting for “jarvis” …
4. Say:  “Jarvis, the living room is too bright.” 
5. Lights dim within 0.3 s and the assistant responds while acting.
