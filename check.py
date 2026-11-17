import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://bf1943.tekrantgaming.com/servers"
NTFY_TOPIC = "bf1943_coralsea_XXXX"  # <-- ודא שזה שם הערוץ שלך!
TARGET_MAP = "coral sea"
MIN_PLAYERS = 2
COOLDOWN_SECONDS = 420  # בדיוק 7 דקות (7 * 60)
STATE_FILE = "last_alert.json"

def load_last_alert_time():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("timestamp", 0)
        except:
            pass
    return 0

def save_last_alert_time(timestamp):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"timestamp": timestamp}, f)
    except:
        pass

def send_phone_notification(server_name, players):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=f"בשרת {server_name} יש כרגע {players} שחקנים!".encode("utf-8"),
        headers={
            "Title": "Coral Sea פעילה עכשיו!".encode("utf-8"),
            "Priority": "high",
            "Tags": "video_game,rotating_light"
        },
        timeout=10
    )

def main():
    resp = requests.get(TARGET_URL, timeout=15)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")

    servers = []
    if "application/json" in content_type:
        data = resp.json()
        items = data if isinstance(data, list) else data.get("servers", [])
        for s in items:
            name = str(s.get("name") or s.get("server_name") or "Server")
            map_name = str(s.get("map") or s.get("current_map") or "")
            players = int(s.get("players") or s.get("num_players") or 0)
            servers.append((name, map_name, players))
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("tr, .server-row, .server-card, li"):
            text = " ".join(row.stripped_strings)
            if TARGET_MAP in text.lower():
                match = re.search(r"(\d+)\s*/\s*\d+", text)
                if match:
                    servers.append((text[:40], "Coral Sea", int(match.group(1))))

    active_server_found = False
    now = time.time()
    last_alert = load_last_alert_time()

    for name, map_name, players in servers:
        if TARGET_MAP in map_name.lower() and players > MIN_PLAYERS:
            active_server_found = True
            if now - last_alert > COOLDOWN_SECONDS:
                send_phone_notification(name, players)
                save_last_alert_time(now)
                print(f"Sent alert for {name} ({players} players)")
            else:
                print(f"Server is active, but within 7-minute cooldown.")
            break

    # איפוס הזיכרון כשהשרת מתרוקן, כדי שברגע שיאוכלס שוב תקבל התראה מיידית
    if not active_server_found and (now - last_alert > COOLDOWN_SECONDS * 2):
        save_last_alert_time(0)

if __name__ == "__main__":
    main()
