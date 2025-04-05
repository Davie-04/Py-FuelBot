import requests
import json
from datetime import datetime, timedelta, timezone
import os
import sys

# === Configuration (from GitHub Actions secrets or environment variables) ===
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
DISCORD_CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

ESI_BASE = "https://esi.evetech.net/latest"

# === Token Management ===
def load_refresh_token():
    with open("eve_tokens.json", "r") as f:
        tokens = json.load(f)
    return tokens["refresh_token"]

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
    res = requests.post("https://login.eveonline.com/v2/oauth/token", data=data, headers=headers)
    res.raise_for_status()
    return res.json()["access_token"]

# === ESI Helpers ===
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

# === Discord Messaging ===
def post_to_discord(message):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"content": message}
    res = requests.post(url, headers=headers, json=data)
    res.raise_for_status()

# === Fuel Check and Alerts ===
def generate_alerts(structures, access_token):
    now = datetime.now(timezone.utc)
    thresholds = {
        "⚠️ 3 Days Warning": timedelta(days=3),
        "⚠️ 48 Hours Warning": timedelta(hours=48),
        "⚠️ 24 Hours Warning": timedelta(hours=24),
    }
    
    alerts = {label: [] for label in thresholds.keys()}

    for s in structures:
        fuel_expires = s.get("fuel_expires")
        if fuel_expires:
            expires_dt = datetime.fromisoformat(fuel_expires.replace("Z", "+00:00"))
            time_left = expires_dt - now
            
            structure_id = s["structure_id"]
            name = s.get("structure_name", f"Structure {structure_id}")
            structure_type = s.get("structure_type_id", "Unknown Type")
            system_name = get_system_name(access_token, s.get("solar_system_id"))
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes = int(remainder // 60)
            alert_time = now.strftime("%Y-%m-%d %H:%M UTC")

            msg = f"**{name}** ({structure_type})\nSystem: {system_name}\nFuel remaining: {int(hours)}h {minutes}m\nAlerted at: {alert_time}"

            for label, delta in thresholds.items():
                if delta - timedelta(minutes=15) < time_left <= delta + timedelta(minutes=15):
                    alerts[label].append(msg)

    return alerts

# === Main ===
def main():
    try:
        access_token = refresh_access_token()
        corp_id = get_corp_id(access_token)
        structures = get_structures(access_token, corp_id)

        alerts = generate_alerts(structures, access_token)

        for label, messages in alerts.items():
            if messages:
                content = "\n\n".join([label] + messages)
                post_to_discord(content)

    except Exception as e:
        print("❌ Error:", str(e))

# === /fuelstatus Command Response ===
def fuel_status():
    try:
        access_token = refresh_access_token()
        corp_id = get_corp_id(access_token)
        structures = get_structures(access_token, corp_id)

        now = datetime.now(timezone.utc)
        status_lines = []

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

                msg = f"**{name}** ({structure_type}) - {system_name}: {int(hours)}h {minutes}m"
                status_lines.append(msg)

        if status_lines:
            post_to_discord("📊 **Fuel Status Report**\n\n" + "\n".join(status_lines))
        else:
            post_to_discord("📊 No structures with fuel timers found.")

    except Exception as e:
        print("❌ /fuelstatus error:", str(e))

if __name__ == "__main__":
    # Determine if this is a command or regular run
    if len(sys.argv) > 1 and sys.argv[1] == "fuelstatus":
        fuel_status()
    else:
        main()
