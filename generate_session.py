"""
Génère une session Telethon en ligne de commande.
Usage : python generate_session.py
"""
import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

API_ID   = int(os.environ.get("TELEGRAM_API_ID",  "0") or input("API_ID   : "))
API_HASH = os.environ.get("TELEGRAM_API_HASH") or input("API_HASH : ")
PHONE    = "+22995501564"

async def main():
    print("=" * 60)
    print("  Connexion Telethon — Sossou Kouamé Apollinaire")
    print(f"  Numéro : {PHONE}")
    print("=" * 60)

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    result = await client.send_code_request(PHONE)
    print("\n✅ Code envoyé sur Telegram !")
    print("👉 Tapez le code reçu (ex: 12345) :")
    code = input(">>> ").strip()

    try:
        await client.sign_in(PHONE, code=code, phone_code_hash=result.phone_code_hash)
    except SessionPasswordNeededError:
        print("\n🔐 Compte 2FA. Entrez votre mot de passe :")
        await client.sign_in(password=input("Mot de passe : ").strip())

    session_string = client.session.save()
    await client.disconnect()

    with open("session.txt", "w") as f:
        f.write(session_string)

    print("\n" + "=" * 60)
    print("✅ SESSION TELETHON GÉNÉRÉE !")
    print("Ajoutez dans TELEGRAM_SESSION :\n")
    print(session_string)
    print("\n💾 Aussi sauvegardée dans session.txt")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
