import os
import json
import requests
import base64  # Add this import for base64 encoding
from datetime import datetime, timedelta, timezone

# === Configuration ===
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TOKEN_FILE = "refresh_token.txt"  # This file will be used for refresh token
ESI_BASE = "https://esi.evetech.net/latest"

# === Load EVE token from file ===
def load_refresh_token():
    with open(TOKEN_FILE, "r") as f:
        tokens = json.load(f)
    return tokens["refresh_token"]

def generate_access_token(refresh_token):
    TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64_credentials = base64.b64encode(credentials.encode()).decode()  # This is where base64 is used
    
    headers = {
        "Authorization": f"Basic {b64_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(TOKEN_URL, headers=headers, data=data)

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Error refreshing token: {response.status_code} - {response.text}")

# === Corporation ID from token ===
def get_corp_id(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    whoami = requests.get("https://login.eveonline.com/oauth/verify", headers=headers).json()
    char_id = whoami["CharacterID"]
    char_info = requests.get(f"{ESI_BASE}/characters/{char_id}/", headers=headers).json()
    return char_info["corporation_id"]

# === Get system name from ID ===
def get_system_name(access_token, system_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/universe/systems/{system_id}/"
    res = requests.get(url, headers=headers)
    return res.json().get("name", "Unknown System") if res.ok else "Unknown System"

# === Get structures ===
def get_structures(access_token, corp_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/corporations/{corp_id}/structures/?datasource=tranquility"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()

# === Post message to Discord ===
def post_to_discord(message):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"content": message}
    res = requests.post(url, headers=headers, json=data)
    res.raise_for_status()

# === Compose alert messages ===
def compose_fuel_alerts(structures, access_token):
    now = datetime.now(timezone.utc)
    thresholds = [3*24, 48, 24]  # in hours
    alerts = {t: [] for t in thresholds}

    for s in structures:
        fuel_expires = s.get("fuel_expires")
        if not fuel_expires:
            continue

        expires_dt = datetime.fromisoformat(fuel_expires.replace("Z", "+00:00"))
        time_left = expires_dt - now
        hours_left = time_left.total_seconds() / 3600

        for threshold in thresholds:
            if 0 < hours_left <= threshold:
                name = s.get("structure_name", f"Structure {s['structure_id']}")
                structure_type = s.get("structure_type_id", "Unknown Type")
                system_name = get_system_name(access_token, s.get("solar_system_id"))
                hours, rem = divmod(time_left.total_seconds(), 3600)
                minutes = int(rem // 60)
                alert_time = now.strftime("%Y-%m-%d %H:%M UTC")

                msg = (
                    f"**{name}** ({structure_type})\n"
                    f"System: {system_name}\n"
                    f"Fuel remaining: {int(hours)}h {minutes}m\n"
                    f"Alerted at: {alert_time}"
                )
                alerts[threshold].append(msg)
                break

    return alerts

# === Main ===
def main():
    try:
        refresh_token = load_refresh_token()
        access_token = generate_access_token(refresh_token)
        corp_id = get_corp_id(access_token)
        structures = get_structures(access_token, corp_id)
        alerts = compose_fuel_alerts(structures, access_token)

        sent = False
        for threshold, msgs in sorted(alerts.items()):
            if msgs:
                label = f"⚠️ Fuel Alert: {threshold}h remaining"
                message = "\n\n".join([label] + msgs)
                post_to_discord(message)
                sent = True

        if sent:
            print("✅ Fuel alerts sent to Discord.")
        else:
            print("✅ No alerts needed. All structures have sufficient fuel.")

    except Exception as e:
        print("❌ Error:", str(e))

if __name__ == "__main__":
    main()
