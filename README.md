# USERNAME HUNTER

Owner-only Telegram bot for checking five-letter lowercase Latin usernames (a-z).

## Commands
- /myid — show your numeric Telegram ID
- /scan — mix random and readable-pattern candidates
- /scan_random — random candidates
- /scan_beautiful — repeated-letter, vowel/consonant and palindrome-like patterns
- /stop — stop scanning
- /status — totals and current state
- /list — latest names Telegram reported as available
- /export — download CSV history

## Supabase setup
1. Open the Supabase project SQL Editor.
2. Run the SQL in supabase/schema.sql.
3. In Project Settings -> API Keys, copy the Secret key (sb_secret_...). Keep it only in the hosting provider's private environment variables.
4. Set SUPABASE_URL and SUPABASE_SECRET_KEY in the worker environment.

The bot writes scan history to the checked_usernames table. The secret key bypasses Row Level Security and must never be put in GitHub, a browser, or this chat.

## Required private environment variables
BOT_TOKEN, API_ID, API_HASH, TELETHON_SESSION, ADMIN_ID, SUPABASE_URL, SUPABASE_SECRET_KEY.
CHECK_DELAY is optional (minimum 4 seconds; default 5).

Never put tokens, API hashes, login codes, 2FA passwords, or session strings in GitHub files or chat. Add them only to your hosting provider's secret settings.

## Create a Telethon session
On a trusted device with Python and Telethon installed, run:
from telethon import TelegramClient
from telethon.sessions import StringSession
api_id = int(input("API_ID: "))
api_hash = input("API_HASH: ").strip()
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print(client.session.save())

Keep the printed session string secret. Never share it.

## Run
Install requirements, set all environment variables, then run: python bot.py

## Hosting
Deploy as an always-on Docker/background worker and attach persistent storage only if needed for local cache. Supabase stores scan history; GitHub stores source code. Free hosting providers may sleep, limit hours, or change terms, so verify current limits before relying on 24/7 operation.

## Important
Availability is a point-in-time result, not a reservation. Another user may claim the username immediately. The bot does not claim or automatically assign names. Telegram may impose FloodWait; the scanner waits when Telegram asks it to. Keep checks conservative and stop if Telegram reports rate limits.


## GitHub Actions scheduled scanning
The repository includes `.github/workflows/scan.yml` and `scan_once.py`. The workflow can be started manually from the Actions tab and is scheduled every five minutes. Each run checks up to 20 new candidates with a minimum five-second delay. GitHub may delay scheduled starts; this is not a continuously running 24/7 process.

### Add GitHub Actions secrets
In the repository, open Settings -> Secrets and variables -> Actions -> New repository secret. Add these names exactly:
- `API_ID`
- `API_HASH`
- `TELETHON_SESSION`
- `BOT_TOKEN`
- `ADMIN_ID`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

Use the values from your own Telegram and Supabase accounts. Never commit them to files or paste them into chat. The Supabase secret key must remain server-side. The Telegram user session string is highly sensitive: anyone who obtains it may access the associated Telegram account.

After adding all secrets, open Actions -> USERNAME HUNTER scan -> Run workflow. Check the run log for success. Do not share logs if they contain secret values.
