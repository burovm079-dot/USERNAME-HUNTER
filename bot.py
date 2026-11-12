import asyncio, csv, io, logging, os, random, sqlite3, string
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telethon import TelegramClient, errors, functions, StringSession

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("username-hunter")
BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION = os.environ["TELETHON_SESSION"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
DB_PATH = os.getenv("DB_PATH", "usernames.db")
DELAY = max(3.0, float(os.getenv("CHECK_DELAY", "4")))
ABC = string.ascii_lowercase
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS checked (username TEXT PRIMARY KEY, status TEXT NOT NULL, checked_at TEXT NOT NULL)")
db.commit()
client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
scan_task = None
mode = "both"

def owner(update):
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

async def guard(update):
    if update.effective_message:
        await update.effective_message.reply_text("⛔ Доступ только владельцу.")

def seen(name):
    return db.execute("SELECT 1 FROM checked WHERE username=?", (name,)).fetchone() is not None

def save(name, status):
    db.execute("INSERT OR REPLACE INTO checked VALUES (?,?,?)", (name, status, datetime.now(timezone.utc).isoformat()))
    db.commit()

def random_name():
    return "".join(random.choices(ABC, k=5))

def pretty_name():
    v, c = "aeiou", "bcdfghjklmnpqrstvwxyz"
    patterns = [
        lambda: random.choice(ABC)*2 + "".join(random.choices(ABC,k=3)),
        lambda: random.choice(c)+random.choice(v)+random.choice(c)+random.choice(v)+random.choice(c),
        lambda: (lambda a,b,d:a+b+d+b+a)(random.choice(ABC),random.choice(ABC),random.choice(ABC)),
        lambda: random.choice(ABC)+random.choice(ABC)+random.choice(ABC)*2+random.choice(ABC),
    ]
    return random.choice(patterns)()

def candidate(which):
    return pretty_name() if which == "beautiful" or (which == "both" and random.random() < .5) else random_name()

async def notify(app, name):
    await app.bot.send_message(ADMIN_ID, f"🎯 Telegram сообщил, что имя может быть свободно: @{name}\nhttps://t.me/{name}\n\nПроверь и попробуй занять сразу: доступность может измениться.")

async def check(app, name):
    try:
        free = await client(functions.account.CheckUsernameRequest(username=name))
        save(name, "free" if free else "taken")
        if free:
            await notify(app, name)
    except errors.FloodWaitError as e:
        log.warning("FloodWait: %s seconds", e.seconds)
        await asyncio.sleep(e.seconds + 2)
    except Exception:
        log.exception("Check failed for %s", name)
        save(name, "error")

async def loop(app):
    global scan_task
    await app.bot.send_message(ADMIN_ID, f"🔎 Поиск запущен: {mode}; пауза {DELAY:g} сек.")
    try:
        while True:
            name = candidate(mode)
            if not seen(name):
                await check(app, name)
                await asyncio.sleep(DELAY)
            else:
                await asyncio.sleep(.2)
    except asyncio.CancelledError:
        raise
    finally:
        scan_task = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner(update): return await guard(update)
    await update.message.reply_text("USERNAME HUNTER\n/scan — оба режима\n/scan_random — случайные\n/scan_beautiful — красивые\n/stop — остановить\n/status — статистика\n/list — найденные\n/export — CSV")

async def begin(update, context, selected):
    global scan_task, mode
    if not owner(update): return await guard(update)
    if scan_task and not scan_task.done():
        return await update.message.reply_text("Поиск уже запущен. /stop")
    mode = selected
    scan_task = asyncio.create_task(loop(context.application))
    await update.message.reply_text("✅ Запускаю.")

async def scan(update, context): await begin(update, context, "both")
async def scan_random(update, context): await begin(update, context, "random")
async def scan_beautiful(update, context): await begin(update, context, "beautiful")

async def stop(update, context):
    global scan_task
    if not owner(update): return await guard(update)
    if scan_task and not scan_task.done():
        scan_task.cancel()
        await update.message.reply_text("🛑 Останавливаю поиск.")
    else: await update.message.reply_text("Поиск не запущен.")

async def status(update, context):
    if not owner(update): return await guard(update)
    total = db.execute("SELECT COUNT(*) FROM checked").fetchone()[0]
    free = db.execute("SELECT COUNT(*) FROM checked WHERE status='free'").fetchone()[0]
    running = bool(scan_task and not scan_task.done())
    await update.message.reply_text(f"Состояние: {'работает' if running else 'остановлен'}\nПроверено: {total}\nСвободно при проверке: {free}\nПауза: {DELAY:g} сек.")

async def listing(update, context):
    if not owner(update): return await guard(update)
    rows = db.execute("SELECT username,checked_at FROM checked WHERE status='free' ORDER BY checked_at DESC LIMIT 30").fetchall()
    if not rows: return await update.message.reply_text("Пока находок нет.")
    await update.message.reply_text("🎯 Последние находки:\n" + "\n".join("@" + n + " — " + t[:16] for n,t in rows))

async def export_csv(update, context):
    if not owner(update): return await guard(update)
    rows = db.execute("SELECT username,status,checked_at FROM checked ORDER BY checked_at DESC").fetchall()
    out = io.StringIO()
    w = csv.writer(out); w.writerow(["username","status_at_check","checked_at_utc"]); w.writerows(rows)
    f = io.BytesIO(out.getvalue().encode("utf-8-sig")); f.name = "username-hunter.csv"
    await update.message.reply_document(f, caption=f"Всего записей: {len(rows)}")

async def post_init(app):
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Telethon session is not authorized; create a StringSession and add it as TELETHON_SESSION.")
    log.info("MTProto session connected")

async def post_shutdown(app):
    global scan_task
    if scan_task and not scan_task.done(): scan_task.cancel()
    await client.disconnect()
    db.close()

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    for command, handler in [("start",start),("scan",scan),("scan_random",scan_random),("scan_beautiful",scan_beautiful),("stop",stop),("status",status),("list",listing),("export",export_csv)]:
        app.add_handler(CommandHandler(command, handler))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__": main()
