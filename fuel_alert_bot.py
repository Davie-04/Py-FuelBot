import os
import json
import requests
from datetime import datetime, timezone

# === Configuration ===
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

EVE_REFRESH_TOKEN = os.getenv("EVE_REFRESH_TOKEN")  # Access refresh token from environment

ESI_BASE = "https://esi.evetech.net/latest"

# === Refresh the access token using the refresh token ===
def refresh_access_token():
    url = "https://login.eveonline.com/v2/oauth/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": EVE_REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(url, headers=headers, data=data)
    if response.ok:
        tokens = response.json()
        print("✅ Access token refreshed successfully.")  # Debugging line
        return tokens['access_token']  # Return the new access token
    else:
        raise Exception(f"Failed to refresh access token. Status: {response.status_code}, Response: {response.text}")

# === Load EVE token from file (updated to use the refreshed token directly) ===
def load_access_token():
    access_token = refresh_access_token()  # Get new access token from refresh token
    return access_token

# === Corporation ID from token ===
def get_corp_id(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    whoami = requests.get("https://login.eveonline.com/oauth/verify", headers=headers).json()
    char_id = whoami["CharacterID"]
    char_info = requests.get(f"{ESI_BASE}/characters/{char_id}/", headers=headers).json()
    print(f"✅ Corporation ID: {char_info['corporation_id']}")  # Debugging line
    return char_info["corporation_id"]

# === Get system name from ID ===
def get_system_name(access_token, system_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/universe/systems/{system_id}/"
    res = requests.get(url, headers=headers)
    
    # Debugging response details
    print(f"Response status: {res.status_code}")  # Log status code
    print(f"Response content: {res.text}")  # Log full response content for debugging

    if res.ok:
        system_name = res.json().get("name", "Unknown System")
        print(f"✅ System found: {system_name}")  # Debugging line
        return system_name
    else:
        print(f"❌ Failed to fetch system name for ID: {system_id}, Error: {res.text}")  # Debugging line
        return "Unknown System"

# === Get structure type name from type_id ===
def get_structure_type_name(access_token, type_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/universe/types/{type_id}/"
    res = requests.get(url, headers=headers)
    if res.ok:
        structure_type = res.json().get("name", "Unknown Type")
        print(f"✅ Structure type found: {structure_type}")  # Debugging line
        return structure_type
    else:
        print(f"❌ Failed to fetch structure type for ID: {type_id}")  # Debugging line
        return "Unknown Type"

# === Get structures ===
def get_structures(access_token, corp_id):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE}/corporations/{corp_id}/structures/?datasource=tranquility"
    res = requests.get(url, headers=headers)
    res.raise_for_status()  # If the request failed, an exception will be raised
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
    thresholds = [5000, 48, 24]  # in hours
    alerts = {t: [] for t in thresholds}

    for s in structures:
        print(f"✅ Structure Data: {s}")  # Debugging line to check structure data
        fuel_expires = s.get("fuel_expires")
        if not fuel_expires:
            continue

        expires_dt = datetime.fromisoformat(fuel_expires.replace("Z", "+00:00"))
        time_left = expires_dt - now
        hours_left = time_left.total_seconds() / 3600

        for threshold in thresholds:
            if 0 < hours_left <= threshold:
                # Ensure we are fetching the correct structure name
                name = s.get("name", f"Structure {s['structure_id']}")
                structure_type_id = s.get("type_id", "Unknown Type")
                system_id = s.get("solar_system_id")  # Get the system ID
                system_name = get_system_name(access_token, system_id) if system_id else "Unknown System"
                structure_type = get_structure_type_name(access_token, structure_type_id)
                
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
        access_token = load_access_token()  # Use refreshed token
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
