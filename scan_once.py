import logging
import os
import random
import string
import time
import urllib.error
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone

from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("username-hunter-action")

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = os.environ["ADMIN_ID"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
DELAY = max(5.0, float(os.getenv("CHECK_DELAY", "5")))
CHECKS_PER_RUN = max(1, min(20, int(os.getenv("CHECKS_PER_RUN", "20"))))
ABC = string.ascii_lowercase
VOWELS = "aeiou"
CONSONANTS = "bcdfghjklmnpqrstvwxyz"

db = create_client(SUPABASE_URL, SUPABASE_KEY)


def random_candidate():
    return "".join(random.choices(ABC, k=5))


def readable_candidate():
    pattern = random.randrange(4)
    if pattern == 0:
        return random.choice(ABC) * 2 + "".join(random.choices(ABC, k=3))
    if pattern == 1:
        return "".join((random.choice(CONSONANTS), random.choice(VOWELS),
                        random.choice(CONSONANTS), random.choice(VOWELS),
                        random.choice(CONSONANTS)))
    if pattern == 2:
        a, b, c = random.choices(ABC, k=3)
        return a + b + c + b + a
    a, b = random.choices(ABC, k=2)
    return a + b + b + a + random.choice(ABC)


def candidate():
    return readable_candidate() if random.random() < 0.5 else random_candidate()


def already_checked(username):
    result = db.table("checked_usernames").select("username").eq("username", username).limit(1).execute()
    return bool(result.data)


def save_result(username, status):
    db.table("checked_usernames").upsert({
        "username": username,
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def telegram_api(method, values):
    body = urllib.parse.urlencode(values).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            payload = {}
        if exc.code == 429:
            raise RuntimeError("Telegram rate limit (429); stopping this run.") from exc
        return payload


def notify(username):
    text = (
        f"🔎 Проверка @{username}: Bot API не нашёл публичный чат с таким именем.\n"
        "⚠️ Это НЕ означает, что username свободен: имя может принадлежать пользователю "
        "или быть недоступным для проверки через Bot API. Проверь вручную в Telegram."
    )
    result = telegram_api("sendMessage", {"chat_id": ADMIN_ID, "text": text})
    if not result.get("ok"):
        raise RuntimeError(f"Could not send Telegram notification: {result}")


def inspect_username(username):
    result = telegram_api("getChat", {"chat_id": f"@{username}"})
    if result.get("ok"):
        return "public_chat_found"
    description = str(result.get("description", "")).lower()
    if "chat not found" in description or "username not found" in description:
        return "not_found_unverified"
    raise RuntimeError(f"Telegram getChat failed: {result}")


def run_scan():
    checked = 0
    not_found = 0
    attempts = 0
    while checked < CHECKS_PER_RUN and attempts < CHECKS_PER_RUN * 5:
        attempts += 1
        username = candidate()
        if already_checked(username):
            continue
        try:
            status = inspect_username(username)
            save_result(username, status)
            checked += 1
            log.info("@%s: %s", username, status)
            if status == "not_found_unverified":
                not_found += 1
                notify(username)
            if checked < CHECKS_PER_RUN:
                time.sleep(DELAY)
        except Exception:
            log.exception("Check failed; stopping this run to avoid repeated requests.")
            break
    log.info("Finished. Checked: %s; not found but unverified: %s.", checked, not_found)


if __name__ == "__main__":
    run_scan()
