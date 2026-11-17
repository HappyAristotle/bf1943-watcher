import re
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://bf1943.tekrantgaming.com/servers"
NTFY_TOPIC = "bf1943_coralsea_6644557"  # <-- החלף לשם הערוץ המדויק שבחרת באפליקציה!
TARGET_MAP = "coral sea"
MIN_PLAYERS = 2

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

    for name, map_name, players in servers:
        if TARGET_MAP in map_name.lower() and players > MIN_PLAYERS:
            send_phone_notification(name, players)
            print(f"Sent alert: {name} ({players})")
            break

if __name__ == "__main__":
    main()
