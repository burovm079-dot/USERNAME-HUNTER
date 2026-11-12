import asyncio
import logging
import os
import random
import string
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from supabase import create_client
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("username-hunter-action")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = os.environ["ADMIN_ID"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
DELAY = max(5.0, float(os.getenv("CHECK_DELAY", "5")))
CHECKS_PER_RUN = max(1, min(40, int(os.getenv("CHECKS_PER_RUN", "20"))))
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
        return "".join((
            random.choice(CONSONANTS), random.choice(VOWELS),
            random.choice(CONSONANTS), random.choice(VOWELS),
            random.choice(CONSONANTS),
        ))
    if pattern == 2:
        a, b, c = random.choices(ABC, k=3)
        return a + b + c + b + a
    a, b = random.choices(ABC, k=2)
    return a + b + b + a + random.choice(ABC)


def candidate():
    # "both": alternate randomly between fully random and readable patterns.
    return readable_candidate() if random.random() < 0.5 else random_candidate()


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


def notify(username):
    body = urllib.parse.urlencode({
        "chat_id": ADMIN_ID,
        "text": (
            f"🎯 Telegram сообщил, что имя может быть свободно: @{username}\n"
            f"https://t.me/{username}\n\n"
            "Это моментальный результат, не бронь. Проверь и попробуй занять сразу."
        ),
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram Bot API returned HTTP {response.status}")


async def run_scan():
    checked_this_run = 0
    free_this_run = 0
    async with TelegramClient(StringSession(SESSION), API_ID, API_HASH) as client:
        log.info("Connected to Telegram. Checking up to %s candidates.", CHECKS_PER_RUN)
        attempts = 0
        max_attempts = CHECKS_PER_RUN * 5
        while checked_this_run < CHECKS_PER_RUN and attempts < max_attempts:
            attempts += 1
            username = candidate()
            try:
                if already_checked(username):
                    continue
                available = await client(
                    functions.account.CheckUsernameRequest(username=username)
                )
                status = "free" if available else "taken"
                save_result(username, status)
                checked_this_run += 1
                log.info("Checked @%s: %s", username, status)
                if available:
                    free_this_run += 1
                    await asyncio.to_thread(notify, username)
                if checked_this_run < CHECKS_PER_RUN:
                    await asyncio.sleep(DELAY)
            except errors.FloodWaitError as exc:
                log.warning("Telegram requested FloodWait of %s seconds; stopping this run.", exc.seconds)
                break
            except Exception:
                log.exception("Error while checking @%s; stopping this run to avoid repeated failures.", username)
                break

    log.info("Finished. New checks: %s; potentially available: %s.", checked_this_run, free_this_run)


if __name__ == "__main__":
    asyncio.run(run_scan())
