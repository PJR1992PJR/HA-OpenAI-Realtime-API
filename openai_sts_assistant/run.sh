#!/usr/bin/with-contenv bash
set -e
export HOMEASSISTANT_URL=${HASS_URL:-http://supervisor/core}
export HOMEASSISTANT_TOKEN=${HASS_TOKEN}
/usr/bin/python /app/assistant.py
