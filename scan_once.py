import logging
import os
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

# Keyboard order, matching the requested sequence: qqqqq, qqqqw, qqqqe...
ALPHABET = "qwertyuiopasdfghjklzxcvbnm"
BASE = len(ALPHABET)
TOTAL_COMBINATIONS = BASE ** 5
PROGRESS_ID = 1

db = create_client(SUPABASE_URL, SUPABASE_KEY)


def username_at(index):
    """Convert a zero-based counter to a 5-letter username in keyboard order."""
    chars = ["q"] * 5
    value = index
    for position in range(4, -1, -1):
        chars[position] = ALPHABET[value % BASE]
        value //= BASE
    return "".join(chars)


def get_next_index():
    result = (
        db.table("scan_progress")
        .select("next_index")
        .eq("id", PROGRESS_ID)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise RuntimeError(
            "Progress row is missing. Run supabase/scan_progress.sql in Supabase SQL Editor."
        )
    return int(result.data[0]["next_index"])


def save_next_index(index):
    db.table("scan_progress").update({
        "next_index": index,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", PROGRESS_ID).execute()


def already_checked(username):
    result = (
        db.table("checked_usernames")
        .select("username")
        .eq("username", username)
        .limit(1)
        .execute()
    )
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
    message = (
        f"🔎 Кандидат @{username}: Bot API не нашёл публичный чат.\\n"
        "⚠️ Это НЕ подтверждает, что имя свободно: личный username может быть занят. "
        "Результат требует отдельной проверки."
    )
    result = telegram_api("sendMessage", {"chat_id": ADMIN_ID, "text": message})
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
    next_index = get_next_index()

    if next_index >= TOTAL_COMBINATIONS:
        telegram_api("sendMessage", {
            "chat_id": ADMIN_ID,
            "text": "🏁 Последовательность всех 5-буквенных комбинаций завершена."
        })
        log.info("All 5-letter combinations have been scanned.")
        return

    while checked < CHECKS_PER_RUN and next_index < TOTAL_COMBINATIONS:
        username = username_at(next_index)

        try:
            if already_checked(username):
                next_index += 1
                save_next_index(next_index)
                continue

            status = inspect_username(username)
            save_result(username, status)

            # Persist the cursor only after the result has been stored.
            next_index += 1
            save_next_index(next_index)
            checked += 1

            log.info("@%s: %s (next index: %s)", username, status, next_index)

            if status == "not_found_unverified":
                not_found += 1
                notify(username)

            if checked < CHECKS_PER_RUN and next_index < TOTAL_COMBINATIONS:
                time.sleep(DELAY)

        except Exception:
            log.exception("Check failed; stopping this run. The current candidate will be retried.")
            break

    log.info(
        "Finished. Checked this run: %s; not found but unverified: %s; next candidate: %s",
        checked,
        not_found,
        username_at(next_index) if next_index < TOTAL_COMBINATIONS else "completed",
    )


if __name__ == "__main__":
    run_scan()
