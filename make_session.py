from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH (private): ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTELETHON_SESSION — keep this secret:")
    print(client.session.save())
