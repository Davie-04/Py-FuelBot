import requests
import json
from datetime import datetime, timedelta, timezone

# === Configuration ===
DISCORD_CHANNEL_ID = "1353643987822706721"
DISCORD_BOT_TOKEN = "${{ secrets.DISCORD_BOT_TOKEN }}"
CLIENT_ID = "${{ secrets.CLIENT_ID }}"
CLIENT_SECRET = "${{ secrets.CLIENT_SECRET }}"
ESI_BASE = "https://esi.evetech.net/latest"

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
    if res.ok:
        return res.json().get("name", "Unknown System")
    return "Unknown System"

def get_structures(access_token, corp_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/corporations/{corp_id}/structures/?datasource=tranquility"
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    return res.json()

def post_to_discord(message):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {"content": message}
    res = requests.post(url, headers=headers, json=data)
    res.raise_for_status()

def main():
    try:
        access_token = refresh_access_token()
        corp_id = get_corp_id(access_token)
        structures = get_structures(access_token, corp_id)

        now = datetime.now(timezone.utc)
        fake_fuel_time = now + timedelta(days=60)  # Force structure to be below threshold
        low_fuel_structures = []

        for s in structures:
            structure_id = s["structure_id"]
            name = s.get("structure_name", f"Structure {structure_id}")
            structure_type = s.get("structure_type_id", "Unknown Type")
            system_name = get_system_name(access_token, s.get("solar_system_id"))
            time_left = fake_fuel_time - now
            hours, remainder = divmod(time_left.total_seconds(), 3600)
            minutes = int(remainder // 60)
            alert_time = now.strftime("%Y-%m-%d %H:%M UTC")

            msg = f"**{name}** ({structure_type})\nSystem: {system_name}\nFuel remaining: {int(hours)}h {minutes}m\nAlerted at: {alert_time}"
            low_fuel_structures.append(msg)

        if low_fuel_structures:
            message = "\n\n".join(["🚨 **Test Fuel Alert** 🚨"] + low_fuel_structures)
            post_to_discord(message)
            print("✅ Test fuel alert posted to Discord.")
        else:
            print("✅ All structures are above threshold.")

    except Exception as e:
        print("❌ Error:", str(e))

if __name__ == "__main__":
    main()
