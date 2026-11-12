# USERNAME HUNTER

Owner-only Telegram bot for checking five-letter lowercase Latin usernames (a-z).

## Commands
- /scan — random and readable-pattern candidates
- /scan_random — random candidates
- /scan_beautiful — repeated-letter, vowel/consonant and palindrome-like patterns
- /stop — stop scanning
- /status — totals and current state
- /list — latest names Telegram reported as available
- /export — download CSV history

## Required private environment variables
- BOT_TOKEN — token from BotFather
- API_ID and API_HASH — credentials from my.telegram.org
- TELETHON_SESSION — authorized Telethon StringSession
- ADMIN_ID — your numeric Telegram user ID
- CHECK_DELAY — optional seconds between checks (minimum 3; default 4)
- DB_PATH — optional SQLite path

Never put tokens, API hashes, login codes, 2FA passwords, or session strings in GitHub files or chat. Add them only to your hosting provider's secret settings.

## Create a Telethon session
On a trusted computer or phone with Python and Telethon installed, run this one-time script and complete Telegram's login prompt:

    from telethon import TelegramClient
    from telethon.sessions import StringSession
    api_id = int(input("API_ID: "))
    api_hash = input("API_HASH: ").strip()
    with TelegramClient(StringSession(), api_id, api_hash) as client:
        print(client.session.save())

Keep the printed session string secret. Do not share it.

## Run
Install requirements, set the environment variables, then run: python bot.py

## Cloud
Deploy as an always-on Docker/background service and attach persistent storage for the SQLite database. A sleeping free web service will not scan continuously. GitHub stores the source code; GitHub Pages cannot run this Python bot. Check your host's current pricing and limits before deploying.

## Important
Availability is a point-in-time result, not a reservation. Another user may claim the username immediately. The bot does not claim or automatically assign names. Telegram may impose FloodWait; the scanner waits when Telegram asks it to.
