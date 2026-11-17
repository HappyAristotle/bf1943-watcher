import os
import json
import time
import requests

# אותו קובץ נתונים שהאתר עצמו טוען כל 15 שניות
SERVERS_URL = "https://bf1943.tekrantgaming.com/servers.json"
# שם הערוץ נלקח מ-GitHub Secret בשם NTFY_TOPIC
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
TARGET_MAP = "coral sea"
MIN_PLAYERS = 2          # התראה רק כשיש יותר מ-2 שחקנים (כלומר 3 ומעלה)
COOLDOWN_SECONDS = 420   # 7 דקות - לכל סוג התראה בנפרד
STATE_FILE = "last_alert.json"


def is_target(map_name):
    return TARGET_MAP in str(map_name or "").lower()


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        return {
            # "timestamp" - תאימות לקובץ הישן
            "now": float(data.get("now", data.get("timestamp", 0))),
            "next": float(data.get("next", 0)),
        }
    except (OSError, ValueError, AttributeError, TypeError):
        return {"now": 0.0, "next": 0.0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    # מסמן ל-workflow לשמור את הקובץ לריצה הבאה
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write("state_changed=true\n")


def send_notification(title, message, tags):
    resp = requests.post(
        "https://ntfy.sh/",
        json={
            "topic": NTFY_TOPIC,
            "title": title,
            "message": message,
            "priority": 4,  # high
            "tags": tags,
        },
        timeout=10,
    )
    resp.raise_for_status()


def fetch_servers():
    resp = requests.get(
        SERVERS_URL,
        params={"t": int(time.time() * 1000)},  # עוקף cache, כמו שהאתר עושה
        headers={"User-Agent": "Mozilla/5.0 (bf1943-watcher)"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("state") != "online":
        print(f"WARNING: server list state is '{data.get('state')}' (last ok: {data.get('last_ok_at')})")
    servers = []
    for s in data.get("servers", []):
        servers.append({
            "name": str(s.get("name") or "Server"),
            "map": str(s.get("map") or ""),
            "next_map": str(s.get("next_map") or ""),
            "players": int(s.get("players") or 0),
            "max_players": int(s.get("max_players") or 0),
        })
    return servers


def describe(servers):
    return "\n".join(f"• {s['name']}: {s['players']}/{s['max_players']} שחקנים" for s in servers)


def main():
    if not NTFY_TOPIC:
        raise SystemExit("NTFY_TOPIC secret is missing - add it in GitHub repo Settings > Secrets > Actions")

    servers = fetch_servers()
    print(f"Fetched {len(servers)} servers:")
    for s in servers:
        print(f"  {s['name']} | map={s['map']} | next={s['next_map']} | players={s['players']}/{s['max_players']}")

    busy = [s for s in servers if s["players"] > MIN_PLAYERS]
    # כלל 1: משחקים עכשיו על Coral Sea
    playing_now = [s for s in busy if is_target(s["map"])]
    # כלל 2: Coral Sea היא המפה הבאה (ולא המפה הנוכחית - את זה כלל 1 כבר מכסה)
    coming_next = [s for s in busy if is_target(s["next_map"]) and not is_target(s["map"])]

    now = time.time()
    state = load_state()
    changed = False

    if playing_now:
        if now - state["now"] > COOLDOWN_SECONDS:
            send_notification("Coral Sea פעילה עכשיו!", describe(playing_now), ["video_game", "rotating_light"])
            state["now"] = now
            changed = True
            print(f"Sent 'playing now' alert for {len(playing_now)} server(s)")
        else:
            print(f"Coral Sea active now, but within cooldown ({int(COOLDOWN_SECONDS - (now - state['now']))}s left).")
    else:
        print("Coral Sea not being played right now (with more than 2 players).")

    if coming_next:
        if now - state["next"] > COOLDOWN_SECONDS:
            send_notification("Coral Sea היא המפה הבאה!", describe(coming_next), ["video_game", "hourglass"])
            state["next"] = now
            changed = True
            print(f"Sent 'next map' alert for {len(coming_next)} server(s)")
        else:
            print(f"Coral Sea is next, but within cooldown ({int(COOLDOWN_SECONDS - (now - state['next']))}s left).")
    else:
        print("No busy server has Coral Sea as the next map.")

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
