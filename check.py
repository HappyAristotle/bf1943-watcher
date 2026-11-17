import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://bf1943.tekrantgaming.com/servers"
# שם הערוץ נלקח מ-GitHub Secret בשם NTFY_TOPIC (לא נשמר בקוד הציבורי)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
TARGET_MAP = "coral sea"
MIN_PLAYERS = 2          # התראה רק כשיש יותר מ-2 שחקנים (כלומר 3 ומעלה)
COOLDOWN_SECONDS = 420   # 7 דקות
STATE_FILE = "last_alert.json"


def load_last_alert_time():
    try:
        with open(STATE_FILE, "r") as f:
            return float(json.load(f).get("timestamp", 0))
    except (OSError, ValueError, AttributeError):
        return 0.0


def save_last_alert_time(timestamp):
    with open(STATE_FILE, "w") as f:
        json.dump({"timestamp": timestamp}, f)
    # מסמן ל-workflow לשמור את הקובץ ב-cache לריצה הבאה
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write("state_changed=true\n")


def send_phone_notification(server_name, players):
    # פרסום בפורמט JSON - בטוח לעברית (כותרות HTTP לא תומכות היטב בתווים שאינם ASCII)
    resp = requests.post(
        "https://ntfy.sh/",
        json={
            "topic": NTFY_TOPIC,
            "title": "Coral Sea פעילה עכשיו!",
            "message": f"בשרת {server_name} יש כרגע {players} שחקנים!",
            "priority": 4,  # high
            "tags": ["video_game", "rotating_light"],
        },
        timeout=10,
    )
    resp.raise_for_status()


def fetch_servers():
    resp = requests.get(
        TARGET_URL,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (bf1943-watcher)"},
    )
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
    return servers


def main():
    if not NTFY_TOPIC:
        raise SystemExit("NTFY_TOPIC secret is missing - add it in GitHub repo Settings > Secrets > Actions")

    servers = fetch_servers()
    print(f"Parsed {len(servers)} server entries: {servers}")
    if not servers:
        print("WARNING: no servers parsed - the page layout may have changed or is rendered by JavaScript.")

    now = time.time()
    last_alert = load_last_alert_time()

    for name, map_name, players in servers:
        if TARGET_MAP in map_name.lower() and players > MIN_PLAYERS:
            if now - last_alert > COOLDOWN_SECONDS:
                send_phone_notification(name, players)
                save_last_alert_time(now)
                print(f"Sent alert for {name} ({players} players)")
            else:
                left = int(COOLDOWN_SECONDS - (now - last_alert))
                print(f"Server is active, but within cooldown ({left}s left).")
            return

    print("Coral Sea not active right now.")


if __name__ == "__main__":
    main()
