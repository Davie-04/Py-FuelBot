import requests
import json
import os
from datetime import datetime, timedelta, timezone
# Triggering GitHub Actions

# === Configuration ===
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
DISCORD_CHANNEL_ID = os.environ["DISCORD_CHANNEL_ID"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
ESI_BASE = "https://esi.evetech.net/latest"

# Load stored refresh token
def load_refresh_token():
    with open("eve_tokens.json", "r") as f:
        tokens = json.load(f)
    return tokens["refresh_token"]

# Refresh the access token
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

# Get character's corporation ID
def get_corp_id(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    whoami = requests.get("https://login.eveonline.com/oauth/verify", headers=headers).json()
    char_id = whoami["CharacterID"]
    char_info = requests.get(f"{ESI_BASE}/characters/{char_id}/", headers=headers).json()
    return char_info["corporation_id"]

# Get system name by system_id
def get_system_name(access_token, system_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/universe/systems/{system_id}/"
    res = requests.get(url, headers=headers)
    if res.ok:
        return res.json().get("name", "Unknown System")
    return "Unknown System"

# Get structures owned by the corporation
def get_structures(access_token, corp_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/corporations/{corp_id}/structures/?datasource=tranquility"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()

# Format and post to Discord
def post_to_discord(message):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"content": message}
    res = requests.post(url, headers=headers, json=data)
    res.raise_for_status()

# === Main Logic ===
def main():
    try:
        access_token = refresh_access_token()
        corp_id = get_corp_id(access_token)
        structures = get_structures(access_token, corp_id)

        now = datetime.now(timezone.utc)
        warning_threshold = now + timedelta(hours=24)
        low_fuel_structures = []

        for s in structures:
            fuel_expires = s.get("fuel_expires")
            if fuel_expires:
                expires_dt = datetime.fromisoformat(fuel_expires.replace("Z", "+00:00"))
                if expires_dt <= warning_threshold:
                    structure_id = s["structure_id"]
                    name = s.get("structure_name", f"Structure {structure_id}")
                    structure_type = s.get("structure_type_id", "Unknown Type")
                    system_name = get_system_name(access_token, s.get("solar_system_id"))
                    time_left = expires_dt - now
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes = int(remainder // 60)
                    alert_time = now.strftime("%Y-%m-%d %H:%M UTC")

                    msg = f"**{name}** ({structure_type})\nSystem: {system_name}\nFuel remaining: {int(hours)}h {minutes}m\nAlerted at: {alert_time}"
                    low_fuel_structures.append(msg)

        if low_fuel_structures:
            message = "\n\n".join(["⚠️ Low Fuel Warning"] + low_fuel_structures)
            post_to_discord(message)
            print("✅ Posted fuel alert to Discord.")
        else:
            print("✅ All structures have more than 24h of fuel.")

    except Exception as e:
        print("❌ Error:", str(e))

if __name__ == "__main__":
    main()
