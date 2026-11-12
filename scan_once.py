
import logging
import math
import os
import time
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from supabase import create_client
from telethon import TelegramClient, functions, errors
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("username-hunter")

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = os.environ["ADMIN_ID"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELETHON_SESSION = os.environ["TELETHON_SESSION"]

DELAY = max(5.0, float(os.getenv("CHECK_DELAY", "10")))
CHECKS_PER_RUN = max(1, min(5, int(os.getenv("CHECKS_PER_RUN", "5"))))
PROGRESS_ID = 1

CONSONANTS = "bcdfghjklmnprstvwyz"
VOWELS = "aeiou"
FIVE_LETTER_TOTAL = len(CONSONANTS) ** 3 * len(VOWELS) ** 2

SHUFFLE_MULTIPLIER = 104729
SHUFFLE_OFFSET = 731

assert math.gcd(SHUFFLE_MULTIPLIER, FIVE_LETTER_TOTAL) == 1

POPULAR_NAMES = """
gram wallet durov toncoin telegram crypto bitcoin ethereum notcoin
gifts stars premium username usernames fragment collectible collectibles
blockchain trading trader exchange market finance money coins token tokens
tonkeeper tonspace tonhub walletconnect airdrop launchpad minting digital
avatar profile channel community messages messenger
"""

POPULAR_CANDIDATES = list(dict.fromkeys(
    word.lower()
    for word in POPULAR_NAMES.split()
    if word.isalpha() and 5 <= len(word) <= 32
))

TOTAL_CANDIDATES = FIVE_LETTER_TOTAL + len(POPULAR_CANDIDATES)

db = create_client(SUPABASE_URL, SUPABASE_KEY)

client = TelegramClient(
    StringSession(TELETHON_SESSION),
    API_ID,
    API_HASH
)


def generated_name(index):
    value = (
        SHUFFLE_MULTIPLIER * index + SHUFFLE_OFFSET
    ) % FIVE_LETTER_TOTAL

    c1 = value % len(CONSONANTS)
    value //= len(CONSONANTS)

    v1 = value % len(VOWELS)
    value //= len(VOWELS)

    c2 = value % len(CONSONANTS)
    value //= len(CONSONANTS)

    v2 = value % len(VOWELS)
    value //= len(VOWELS)

    c3 = value % len(CONSONANTS)

    return (
        CONSONANTS[c1] + VOWELS[v1] + CONSONANTS[c2]
        + VOWELS[v2] + CONSONANTS[c3]
    )


def candidate_at(index):
    if index < FIVE_LETTER_TOTAL:
        return generated_name(index)

    return POPULAR_CANDIDATES[index - FIVE_LETTER_TOTAL]


def get_next_index():
    result = (
        db.table("scan_progress")
        .select("next_index")
        .eq("id", PROGRESS_ID)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise RuntimeError("Progress row is missing.")

    return int(result.data[0]["next_index"])


def save_next_index(index):
    db.table("scan_progress").update({
        "next_index": index,
        "updated_at": datetime.now(timezone.utc).isoformat()
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
        "checked_at": datetime.now(timezone.utc).isoformat()
    }).execute()


def bot_request(method, values):
    body = urllib.parse.urlencode(values).encode()

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=body,
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode())


def inspect_username(username):
    try:
        available = client(
            functions.account.CheckUsernameRequest(username=username)
        )

        if available:
            return "username_available"

        return "username_occupied"

    except errors.RPCError as exc:
        message = str(getattr(exc, "message", exc)).upper()

        if "USERNAME_OCCUPIED" in message:
            return "username_occupied"

        if "USERNAME_PURCHASE_AVAILABLE" in message:
            return "username_collectible_only"

        if "USERNAME_INVALID" in message:
            return "username_invalid"

        if "FLOOD_WAIT" in message:
            raise RuntimeError(
                "Telegram imposed a flood limit. Stopping safely."
            ) from exc

        raise


def notify_batch(available, checked, next_candidate):
    lines = [
        "🔎 USERNAME HUNTER — MTProto",
        f"Проверено: {checked}",
        f"Доступных имён: {len(available)}",
        ""
    ]

    if available:
        lines.append("🎉 Можно попробовать назначить:")
        lines.extend(f"@{name}" for name in available[:15])
    else:
        lines.append("В этой партии доступных имён не найдено.")

    lines.extend([
        "",
        "Проверка выполнена Telegram для авторизованного аккаунта.",
        "Доступность может измениться — найденное имя нужно назначить как можно скорее.",
        f"Следующий кандидат: @{next_candidate}"
        if next_candidate != "completed"
        else "Все кандидаты проверены."
    ])

    result = bot_request("sendMessage", {
        "chat_id": ADMIN_ID,
        "text": "\n".join(lines)
    })

    if not result.get("ok"):
        raise RuntimeError(f"Notification failed: {result}")


def run_scan():
    checked = 0
    available = []

    next_index = get_next_index()

    if next_index >= TOTAL_CANDIDATES:
        bot_request("sendMessage", {
            "chat_id": ADMIN_ID,
            "text": "🏁 Все кандидаты проверены."
        })
        return

    while checked < CHECKS_PER_RUN and next_index < TOTAL_CANDIDATES:
        username = candidate_at(next_index)

        if already_checked(username):
            next_index += 1
            save_next_index(next_index)
            continue

        status = inspect_username(username)

        save_result(username, status)

        next_index += 1
        save_next_index(next_index)
        checked += 1

        log.info("@%s: %s", username, status)

        if status == "username_available":
            available.append(username)

        if checked < CHECKS_PER_RUN:
            time.sleep(DELAY)

    next_candidate = (
        candidate_at(next_index)
        if next_index < TOTAL_CANDIDATES
        else "completed"
    )

    if checked:
        notify_batch(available, checked, next_candidate)


def main():
    client.connect()

    if not client.is_user_authorized():
        raise RuntimeError(
            "Telegram session is not authorized. Check TELETHON_SESSION."
        )

    try:
        run_scan()
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
