import logging
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone

from supabase import create_client
from telethon import TelegramClient, functions, errors
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("username-hunter-action")

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = os.environ["ADMIN_ID"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELETHON_SESSION = os.environ["TELETHON_SESSION"]
DELAY = max(5.0, float(os.getenv("CHECK_DELAY", "5")))
CHECKS_PER_RUN = max(1, min(20, int(os.getenv("CHECKS_PER_RUN", "20"))))
PROGRESS_ID = 1

# Generate a large deterministic stream of pronounceable five-letter names.
# Pattern: consonant-vowel-consonant-vowel-consonant (CVCVC).
CONSONANTS = "bcdfghjklmnprstvwyz"
VOWELS = "aeiou"
FIVE_LETTER_TOTAL = len(CONSONANTS) ** 3 * len(VOWELS) ** 2

# An affine permutation visits every CVCVC combination once, in a shuffled order.
# The multiplier must be coprime with FIVE_LETTER_TOTAL.
SHUFFLE_MULTIPLIER = 104729
SHUFFLE_OFFSET = 731
assert math.gcd(SHUFFLE_MULTIPLIER, FIVE_LETTER_TOTAL) == 1

# Recognizable/popular names are checked after the generated five-letter names.
# Keep only valid-length alphabetic candidates; never append random digits.
POPULAR_NAMES = """
gram wallet durov toncoin telegram crypto bitcoin ethereum notcoin
gifts stars premium username usernames fragment collectible collectibles
blockchain trading trader exchange market finance money coins token tokens
tonkeeper tonspace tonhub walletconnect airdrop launchpad minting digital
avatar profile channel community messages messenger usernamehunter usernamehunt
telegrambot telegramgift telegramstars telegramwallet
"""
POPULAR_CANDIDATES = list(dict.fromkeys(
    word.lower() for word in POPULAR_NAMES.split()
    if word.isalpha() and 5 <= len(word) <= 32
))
TOTAL_CANDIDATES = FIVE_LETTER_TOTAL + len(POPULAR_CANDIDATES)

db = create_client(SUPABASE_URL, SUPABASE_KEY)

mtproto_client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)
mtproto_client.connect()
if not mtproto_client.is_user_authorized():
    mtproto_client.disconnect()
    raise RuntimeError("TELETHON_SESSION is not authorized. Re-create the session in Termux.")


def generated_name(index):
    """Return one unique CVCVC name for a zero-based generated-name index."""
    shuffled = (SHUFFLE_MULTIPLIER * index + SHUFFLE_OFFSET) % FIVE_LETTER_TOTAL

    # Mixed-radix decode: C, V, C, V, C.
    c1 = shuffled % len(CONSONANTS)
    shuffled //= len(CONSONANTS)
    v1 = shuffled % len(VOWELS)
    shuffled //= len(VOWELS)
    c2 = shuffled % len(CONSONANTS)
    shuffled //= len(CONSONANTS)
    v2 = shuffled % len(VOWELS)
    shuffled //= len(VOWELS)
    c3 = shuffled % len(CONSONANTS)

    return (
        CONSONANTS[c1] + VOWELS[v1] + CONSONANTS[c2]
        + VOWELS[v2] + CONSONANTS[c3]
    )


def candidate_at(index):
    if index < FIVE_LETTER_TOTAL:
        return generated_name(index)
    popular_index = index - FIVE_LETTER_TOTAL
    return POPULAR_CANDIDATES[popular_index]


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
            retry_after = int((payload.get("parameters") or {}).get("retry_after", 60))
            log.warning("Telegram rate limit; waiting %s seconds.", retry_after)
            time.sleep(min(max(retry_after, 5), 180))
            raise RuntimeError("Telegram rate limit (429); stopping this run.") from exc
        if exc.code >= 500:
            raise RuntimeError(f"Telegram server error ({exc.code}); candidate will be retried.") from exc
        return payload


def notify_batch(usernames, checked, next_candidate):
    shown = usernames[:15]
    lines = [
        "🔎 Результаты проверки Telegram MTProto",
        f"Проверено кандидатов: {checked}",
    ]
    if shown:
        lines.extend([
            "🎉 Доступны для назначения на аккаунт на момент проверки:",
            *[f"@{name}" for name in shown],
        ])
        if len(usernames) > len(shown):
            lines.append(f"И ещё {len(usernames) - len(shown)} доступных кандидатов.")
    else:
        lines.append("Пока свободных для назначения имён не найдено.")
    lines.extend([
        "",
        "Проверка выполнена Telegram для авторизованного аккаунта. Доступность может измениться, поэтому найденное имя нужно сразу попробовать установить.",
        f"Следующий кандидат: @{next_candidate}" if next_candidate != "completed" else "Список кандидатов завершён.",
    ])
    result = telegram_api("sendMessage", {"chat_id": ADMIN_ID, "text": "\\n".join(lines)})
    if not result.get("ok"):
        raise RuntimeError(f"Could not send batch notification: {result}")


def inspect_username(username):
    try:
        available = mtproto_client(functions.account.CheckUsernameRequest(username=username))
        return "username_available" if available else "username_occupied"
    except errors.RPCError as exc:
        message = str(getattr(exc, "message", exc)).upper()
        if "USERNAME_PURCHASE_AVAILABLE" in message:
            return "username_collectible_only"
        if "USERNAME_OCCUPIED" in message:
            return "username_occupied"
        if "USERNAME_INVALID" in message:
            return "username_invalid"
        raise RuntimeError(f"Telegram MTProto check failed: {message}") from exc


def run_scan():
    checked = 0
    available = []
    next_index = get_next_index()

    if next_index >= TOTAL_CANDIDATES:
        telegram_api("sendMessage", {
            "chat_id": ADMIN_ID,
            "text": "🏁 Все сгенерированные пятибуквенные варианты и популярные слова проверены."
        })
        log.info("All generated and curated candidates have been scanned.")
        return

    while checked < CHECKS_PER_RUN and next_index < TOTAL_CANDIDATES:
        username = candidate_at(next_index)

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

            log.info("@%s: %s (next index: %s/%s)", username, status, next_index, TOTAL_CANDIDATES)

            if status == "username_available":
                available.append(username)

            if checked < CHECKS_PER_RUN and next_index < TOTAL_CANDIDATES:
                time.sleep(DELAY)

        except Exception:
            log.exception("Check failed; stopping this run. The current candidate will be retried.")
            break

    next_candidate = candidate_at(next_index) if next_index < TOTAL_CANDIDATES else "completed"
    log.info(
        "Finished. Checked this run: %s; available: %s; next candidate: %s",
        checked, len(available), next_candidate,
    )
    if checked:
        try:
            notify_batch(available, checked, next_candidate)
        except Exception:
            log.exception("Could not send scan summary notification.")


if __name__ == "__main__":
    try:
        run_scan()
    finally:
        mtproto_client.disconnect()
