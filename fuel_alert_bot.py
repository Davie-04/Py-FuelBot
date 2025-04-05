import requests
import json
import os
import asyncio
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify
from threading import Thread

# === Configuration ===
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ESI_BASE = "https://esi.evetech.net/latest"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
HEADERS = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type": "application/json"
}

def load_refresh_token():
    with open("eve_tokens.json", "r") as f:
        return json.load(f)["refresh_token"]

def refresh_access_token():
    refresh_token = load_refresh_token()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    headers = {
        "Authorization": f"Basic {requests.auth._basic_auth_str(CLIENT_ID, CLIENT_SECRET).split(' ')[1]}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    res = requests.post(TOKEN_URL, data=data, headers=headers)
    res.raise_for_status()
    return res.json()["access_token"]

def get_corp_id(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    whoami = requests.get("https://login.eveonline.com/oauth/verify", headers=headers).json()
    char_id = whoami["CharacterID"]
    char_info = requests.get(f"{ESI_BASE}/characters/{char_id}/", headers=headers).json()
    return char_info["corporation_id"]

def get_system_name(access_token, system_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/universe/systems/{system_id}/"
    res = requests.get(url, headers=headers)
    return res.json().get("name", "Unknown System") if res.ok else "Unknown System"

def get_structures(access_token, corp_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/corporations/{corp_id}/structures/?datasource=tranquility"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()

def post_to_discord(message):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    res = requests.post(url, headers=HEADERS, json={"content": message})
    res.raise_for_status()

def format_fuel_status(structures, access_token):
    now = datetime.now(timezone.utc)
    messages = []

    for s in structures:
        fuel_expires = s.get("fuel_expires")
        if fuel_expires:
            expires_dt = datetime.fromisoformat(fuel_expires.replace("Z", "+00:00"))
            structure_id = s["structure_id"]
            name = s.get("structure_name", f"Structure {structure_id}")
            structure_type = s.get("structure_type_id", "Unknown Type")
            system_name = get_system_name(access_token, s.get("solar_system_id"))
            time_left = expires_dt - now
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes = int(remainder // 60)
            alert_time = now.strftime("%Y-%m-%d %H:%M UTC")

            messages.append(
                f"**{name}** ({structure_type})\nSystem: {system_name}\nFuel remaining: {int(hours)}h {minutes}m\nChecked at: {alert_time}"
            )
    return messages

def check_fuel():
    access_token = refresh_access_token()
    corp_id = get_corp_id(access_token)
    structures = get_structures(access_token, corp_id)

    now = datetime.now(timezone.utc)
    alerts = []

    for s in structures:
        fuel_expires = s.get("fuel_expires")
        if not fuel_expires:
            continue

        expires_dt = datetime.fromisoformat(fuel_expires.replace("Z", "+00:00"))
        structure_id = s["structure_id"]
        name = s.get("structure_name", f"Structure {structure_id}")
        structure_type = s.get("structure_type_id", "Unknown Type")
        system_name = get_system_name(access_token, s.get("solar_system_id"))
        time_left = expires_dt - now
        hours_left = time_left.total_seconds() / 3600
        alert_time = now.strftime("%Y-%m-%d %H:%M UTC")

        for threshold in [72, 48, 24]:
            if threshold - 1 < hours_left <= threshold:
                hours, remainder = divmod(time_left.total_seconds(), 3600)
                minutes = int(remainder // 60)
                alerts.append(
                    f"⚠️ Fuel Alert: **{name}** ({structure_type})\nSystem: {system_name}\nFuel remaining: {int(hours)}h {minutes}m\nThreshold: {threshold}h\nAlerted at: {alert_time}"
                )

    if alerts:
        post_to_discord("\n\n".join(alerts))
        print("✅ Posted alerts")
    else:
        print("✅ No structures under threshold.")

# === Flask App for Slash Command ===
app = Flask(__name__)

@app.route("/interactions", methods=["POST"])
def interactions():
    data = request.json
    if data.get("type") == 1:
        return jsonify({"type": 1})  # Ping

    if data.get("type") == 2:  # Slash command
        command = data["data"]["name"]
        if command == "fuelstatus":
            access_token = refresh_access_token()
            corp_id = get_corp_id(access_token)
            structures = get_structures(access_token, corp_id)
            status_msgs = format_fuel_status(structures, access_token)
            content = "\n\n".join(status_msgs[:3]) if status_msgs else "✅ All structures have sufficient fuel."
            return jsonify({"type": 4, "data": {"content": content}})

    return "", 400

def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "fuelstatus":
        access_token = refresh_access_token()
        corp_id = get_corp_id(access_token)
        structures = get_structures(access_token, corp_id)
        status_msgs = format_fuel_status(structures, access_token)
        print("\n".join(status_msgs))
    else:
        Thread(target=run_flask).start()
        check_fuel()
