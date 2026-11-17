import os
import json
import time
import requests
import yaml

# אותו קובץ נתונים שהאתר עצמו טוען כל 15 שניות
SERVERS_URL = "https://bf1943.tekrantgaming.com/servers.json"
# שם הערוץ נלקח מ-GitHub Secret בשם NTFY_TOPIC
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
CONFIG_FILE = "alerts.yml"
STATE_FILE = "last_alert.json"
FORGET_AFTER_SECONDS = 24 * 3600  # ניקוי רשומות ישנות מקובץ המצב

TYPE_TEXT = {
    "now": ("{map} פעילה עכשיו!", ["video_game", "rotating_light"]),
    "next": ("{map} היא המפה הבאה!", ["video_game", "hourglass"]),
}


def norm(name):
    return " ".join(str(name or "").lower().split())


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    rules = []
    for i, r in enumerate(cfg.get("rules") or [], 1):
        if not isinstance(r, dict) or not r.get("map"):
            raise SystemExit(f"alerts.yml: rule #{i} is missing 'map'")
        when = str(r.get("when", "both")).strip().lower()
        if when not in ("now", "next", "both"):
            raise SystemExit(f"alerts.yml: rule #{i} has when='{when}' - use now / next / both")
        rules.append({
            "map": str(r["map"]).strip(),
            "types": ["now", "next"] if when == "both" else [when],
            "min_players": int(r.get("min_players", 3)),
        })
    settings = cfg.get("settings") or {}
    rearm = float(settings.get("rearm_minutes", 5)) * 60
    return rules, rearm


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        alerts = data.get("alerts", {})
        return {k: float(v) for k, v in alerts.items()} if isinstance(alerts, dict) else {}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump({"alerts": state}, f, ensure_ascii=False)
    # מסמן ל-workflow לשמור את הקובץ לריצה הבאה
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write("state_changed=true\n")


def send_notification(title, message, tags):
    resp = requests.post(
        "https://ntfy.sh/",
        json={"topic": NTFY_TOPIC, "title": title, "message": message, "priority": 4, "tags": tags},
        timeout=10,
    )
    resp.raise_for_status()


def fetch_servers():
    resp = requests.get(
        SERVERS_URL,
        params={"t": int(time.time() * 1000)},
        headers={"User-Agent": "Mozilla/5.0 (bf1943-watcher)"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("state") != "online":
        print(f"WARNING: server list state is '{data.get('state')}' (last ok: {data.get('last_ok_at')})")
    return [{
        "name": str(s.get("name") or "Server"),
        "map": str(s.get("map") or ""),
        "next_map": str(s.get("next_map") or ""),
        "players": int(s.get("players") or 0),
        "max_players": int(s.get("max_players") or 0),
    } for s in data.get("servers", [])]


def find_matches(servers, rules):
    """מחזיר {(type, map): [servers]} לכל התנאים שמתקיימים כרגע."""
    matches = {}
    for rule in rules:
        target = norm(rule["map"])
        for s in servers:
            if s["players"] < rule["min_players"]:
                continue
            is_now = norm(s["map"]) == target
            # "הבאה" רק אם היא לא גם הנוכחית (שרת שמשחק תמיד אותה מפה)
            is_next = norm(s["next_map"]) == target and not is_now
            for t in rule["types"]:
                if (t == "now" and is_now) or (t == "next" and is_next):
                    lst = matches.setdefault((t, rule["map"]), [])
                    if s not in lst:
                        lst.append(s)
    return matches


def main():
    if not NTFY_TOPIC:
        raise SystemExit("NTFY_TOPIC secret is missing - add it in GitHub repo Settings > Secrets > Actions")

    rules, rearm_seconds = load_config()
    print("Rules: " + "; ".join(f"{r['map']} {'+'.join(r['types'])} >= {r['min_players']} players" for r in rules))

    servers = fetch_servers()
    print(f"Fetched {len(servers)} servers:")
    for s in servers:
        print(f"  {s['name']} | map={s['map']} | next={s['next_map']} | players={s['players']}/{s['max_players']}")

    now = time.time()
    state = load_state()
    changed = False

    for (t, map_name), matched in find_matches(servers, rules).items():
        fresh = []
        for s in matched:
            key = f"{t}|{norm(map_name)}|{s['name']}"
            last_seen = state.get(key)
            if last_seen is None or now - last_seen > rearm_seconds:
                fresh.append(s)      # התנאי הופיע עכשיו (או חזר אחרי שהתבטל) -> התראה
            else:
                print(f"  already alerted, condition still on: {key}")
            state[key] = now         # מעדכן "נראה לאחרונה" כל עוד התנאי מתקיים
            changed = True
        if fresh:
            title_tpl, tags = TYPE_TEXT[t]
            body = "\n".join(f"• {s['name']}: {s['players']}/{s['max_players']} שחקנים" for s in fresh)
            send_notification(title_tpl.format(map=map_name), body, tags)
            print(f"Sent '{t}' alert for {map_name}: {[s['name'] for s in fresh]}")

    # ניקוי רשומות שלא נראו הרבה זמן
    for key in [k for k, v in state.items() if now - v > FORGET_AFTER_SECONDS]:
        del state[key]
        changed = True

    if changed:
        save_state(state)
    print("Done.")


if __name__ == "__main__":
    main()
