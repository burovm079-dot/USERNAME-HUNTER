import asyncio, csv, io, logging, os, random, string
from datetime import datetime, timezone

from supabase import create_client
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("username-hunter")
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
DELAY = max(4.0, float(os.getenv("CHECK_DELAY", "5")))
ABC = string.ascii_lowercase
db = create_client(SUPABASE_URL, SUPABASE_KEY)
client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
scan_task = None
mode = "both"
seen_cache = set()

def owner(update):
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

async def guard(update):
    if update.effective_message:
        await update.effective_message.reply_text("⛔ Доступ только владельцу.")

def seen(name):
    if name in seen_cache:
        return True
    result = db.table("checked_usernames").select("username").eq("username", name).limit(1).execute()
    exists = bool(result.data)
    if exists:
        seen_cache.add(name)
    return exists

def save(name, status):
    db.table("checked_usernames").upsert({
        "username": name,
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    seen_cache.add(name)

def random_name():
    return "".join(random.choices(ABC, k=5))

def pretty_name():
    vowels, consonants = "aeiou", "bcdfghjklmnpqrstvwxyz"
    patterns = [
        lambda: random.choice(ABC) * 2 + "".join(random.choices(ABC, k=3)),
        lambda: random.choice(consonants) + random.choice(vowels) + random.choice(consonants) + random.choice(vowels) + random.choice(consonants),
        lambda: (lambda a,b,c: a+b+c+b+a)(random.choice(ABC), random.choice(ABC), random.choice(ABC)),
        lambda: random.choice(ABC) + random.choice(ABC) + random.choice(ABC) * 2 + random.choice(ABC),
    ]
    return random.choice(patterns)()

def candidate(which):
    if which == "beautiful":
        return pretty_name()
    if which == "both" and random.random() < .5:
        return pretty_name()
    return random_name()

async def notify(app, name):
    await app.bot.send_message(ADMIN_ID, f"🎯 Telegram сообщил, что имя может быть свободно: @{name}\nhttps://t.me/{name}\n\nЭто моментальный результат, не бронь. Проверь и попробуй занять сразу.")

async def check(app, name):
    try:
        available = await client(functions.account.CheckUsernameRequest(username=name))
        save(name, "free" if available else "taken")
        if available:
            await notify(app, name)
    except errors.FloodWaitError as exc:
        log.warning("Telegram FloodWait: %s seconds", exc.seconds)
        await asyncio.sleep(exc.seconds + 2)
    except Exception:
        log.exception("Check failed for %s", name)
        try:
            save(name, "error")
        except Exception:
            log.exception("Could not save error status to Supabase")

async def scan_loop(app):
    global scan_task
    await app.bot.send_message(ADMIN_ID, f"🔎 Поиск запущен: {mode}; интервал не менее {DELAY:g} сек.")
    try:
        while True:
            name = candidate(mode)
            try:
                already_checked = seen(name)
            except Exception:
                log.exception("Supabase lookup failed")
                await asyncio.sleep(15)
                continue
            if not already_checked:
                await check(app, name)
                await asyncio.sleep(DELAY)
            else:
                await asyncio.sleep(.25)
    except asyncio.CancelledError:
        raise
    finally:
        scan_task = None

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой Telegram ID: {update.effective_user.id}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner(update):
        return await guard(update)
    await update.message.reply_text("USERNAME HUNTER\n/scan — оба режима\n/scan_random — случайные\n/scan_beautiful — красивые\n/stop — остановить\n/status — статистика\n/list — последние находки\n/export — CSV")

async def begin(update, context, selected):
    global scan_task, mode
    if not owner(update):
        return await guard(update)
    if scan_task and not scan_task.done():
        return await update.message.reply_text("Поиск уже запущен. Используй /stop.")
    mode = selected
    scan_task = asyncio.create_task(scan_loop(context.application))
    await update.message.reply_text("✅ Запускаю поиск.")

async def scan(update, context): await begin(update, context, "both")
async def scan_random(update, context): await begin(update, context, "random")
async def scan_beautiful(update, context): await begin(update, context, "beautiful")

async def stop(update, context):
    global scan_task
    if not owner(update):
        return await guard(update)
    if scan_task and not scan_task.done():
        scan_task.cancel()
        await update.message.reply_text("🛑 Останавливаю поиск.")
    else:
        await update.message.reply_text("Поиск не запущен.")

async def status(update, context):
    if not owner(update):
        return await guard(update)
    total = db.table("checked_usernames").select("username", count="exact").execute().count or 0
    free = db.table("checked_usernames").select("username", count="exact").eq("status", "free").execute().count or 0
    running = bool(scan_task and not scan_task.done())
    await update.message.reply_text(f"Состояние: {'работает' if running else 'остановлен'}\nПроверено: {total}\nСвободно при проверке: {free}\nИнтервал: {DELAY:g} сек.")

async def listing(update, context):
    if not owner(update):
        return await guard(update)
    result = db.table("checked_usernames").select("username,checked_at").eq("status", "free").order("checked_at", desc=True).limit(30).execute()
    if not result.data:
        return await update.message.reply_text("Пока находок нет.")
    lines = [f"@{row['username']} — {row['checked_at'][:16]}" for row in result.data]
    await update.message.reply_text("🎯 Последние находки:\n" + "\n".join(lines))

async def export_csv(update, context):
    if not owner(update):
        return await guard(update)
    rows, offset = [], 0
    while True:
        result = db.table("checked_usernames").select("username,status,checked_at").order("checked_at", desc=True).range(offset, offset + 999).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["username", "status_at_check", "checked_at"])
    for row in rows:
        writer.writerow([row["username"], row["status"], row["checked_at"]])
    file = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    file.name = "username-hunter.csv"
    await update.message.reply_document(file, caption=f"Всего записей: {len(rows)}")

async def post_init(app):
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session is not authorized. Create a StringSession and add TELETHON_SESSION.")
    log.info("MTProto session connected; Supabase configured")

async def post_shutdown(app):
    global scan_task
    if scan_task and not scan_task.done():
        scan_task.cancel()
    await client.disconnect()

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    handlers = [("myid",myid),("start",start),("scan",scan),("scan_random",scan_random),("scan_beautiful",scan_beautiful),("stop",stop),("status",status),("list",listing),("export",export_csv)]
    for command, handler in handlers:
        app.add_handler(CommandHandler(command, handler))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
