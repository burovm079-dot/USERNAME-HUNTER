# USERNAME HUNTER

Owner-only Telegram bot that generates five-letter lowercase Latin username candidates (a-z).

## Important limitation

This version uses only the Telegram Bot API. The Bot API can look up public chats/channels by username, but it cannot verify whether an arbitrary username is available for a Telegram user account. Therefore:

- `public_chat_found` means a public chat/channel was found.
- `not_found_unverified` means Bot API did not find a public chat. It does **not** mean the username is free.
- The bot never labels an unverified name as available and never claims usernames.

For a reliable user-account availability check, Telegram's MTProto user authorization is required. This project intentionally no longer asks for that session.

## Commands

- /myid — show your numeric Telegram ID
- /scan — mix random and readable-pattern candidates
- /scan_random — random candidates
- /scan_beautiful — repeated-letter, vowel/consonant and palindrome-like patterns
- /stop — stop scanning
- /status — totals and current state
- /list — latest unverified results
- /export — download CSV history

## Supabase setup

1. Open the Supabase project SQL Editor.
2. Run the updated SQL in `supabase/schema.sql`.
3. In Project Settings -> API Keys, copy the Secret key (`sb_secret_...`).
4. Set `SUPABASE_URL` and `SUPABASE_SECRET_KEY` as private GitHub Actions secrets.

The Supabase secret key bypasses Row Level Security and must never be placed in a browser, committed to Git, or pasted into chat.

## Required private environment variables

- `BOT_TOKEN`
- `ADMIN_ID`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

Optional: `CHECK_DELAY` (minimum 5 seconds; default 5).

## Run locally

Install requirements and set the environment variables above, then run:

```bash
python bot.py
```

## GitHub Actions

The repository includes `.github/workflows/scan.yml` and `scan_once.py`. The workflow can be started manually from Actions and is scheduled every five minutes. Each run checks up to 20 new candidates with at least five seconds between checks. GitHub may delay scheduled starts; this is not a continuously running 24/7 process.

Add these repository secrets under Settings -> Secrets and variables -> Actions:

- `BOT_TOKEN`
- `ADMIN_ID`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

The old `API_ID`, `API_HASH`, and `TELETHON_SESSION` secrets are no longer used and can be deleted.

## Safety and limitations

The scan is exploratory only. A Bot API "chat not found" response does not prove that a username is available: it may belong to a user, be reserved, or otherwise be unavailable. Verify any candidate manually in Telegram. Telegram may rate-limit requests; the workflow stops when the API returns an error instead of trying to bypass limits.
