import aiohttp
import asyncio
import os
import re
import uvicorn
import yt_dlp

from typing import Union
from fastapi import FastAPI
from pyrogram import Client, idle
from motor.motor_asyncio import AsyncIOMotorClient
from youtubesearchpython.__future__ import VideosSearch

# ================= ENV =================
api_id = int(os.getenv("API_ID", "28492745"))
api_hash = os.getenv("API_HASH", "0241a9746f6e264fe7f75cf209177246")
bot_token = os.getenv("BOT_TOKEN", "8104460140:AAEnI5F2oBkRSKMPgHh6L5O3s6D_5-ap8XA")
mongo_url = os.getenv("MONGO_URL", "mongodb+srv://Mafia:Mafia@mafia.wvuzxgl.mongodb.net/?retryWrites=true&w=majority")

channel_id = int(os.getenv("CHANNEL_ID", "-1002362100657"))
sudo_users = list(map(int, os.getenv("SUDO_USERS", "6035523795").split(",")))

# ================= BOT =================
class Bot(Client):
    def __init__(self):
        super().__init__(
            "AdityaHalder",
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
        )

    async def start(self):
        await super().start()
        print("✅ Bot Started!")

    async def stop(self, *args):
        await super().stop()
        print("❌ Bot Stopped!")

bot = Bot()

# ================= API =================
app = FastAPI(title="Audio API")

# ================= DB =================
mongodb = AsyncIOMotorClient(mongo_url).adityahalderdb
audiodb = mongodb.audiodb

async def is_served_audio(id: str):
    return await audiodb.find_one({"id": id}) is not None

async def add_served_audio(id: str, link: str):
    if not await is_served_audio(id):
        await audiodb.insert_one({"id": id, "link": link})

async def get_served_audio(id: str):
    return await audiodb.find_one({"id": id})

# ================= DOWNLOAD =================
async def download_audio(link: str):
    loop = asyncio.get_running_loop()

    def run():
        os.makedirs("downloads", exist_ok=True)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            return ydl.prepare_filename(info)

    return await loop.run_in_executor(None, run)

# ================= UTILS =================
def convert_to_seconds(duration: str):
    parts = list(map(int, duration.split(":")))
    total = 0
    for p in parts:
        total = total * 60 + p
    return total

# ================= ROUTES =================
@app.get("/")
async def home():
    return {"status": "running"}

@app.get("/song")
async def get_audio_url(query: Union[str, None] = None):
    if not query:
        return {"error": "No query"}

    try:
        search = VideosSearch(query, limit=1)
        result = (await search.next())["result"]

        if not result:
            return {"error": "No results"}

        video = result[0]
        vid = video["id"]
        title = video["title"]
        duration = video.get("duration")
        link = video["link"]

        if not duration:
            return {"error": "Live not supported"}

        # cached
        if await is_served_audio(vid):
            data = await get_served_audio(vid)
            return {"link": data["link"]}

        # download
        file_path = await download_audio(link)

        # upload
        msg = await bot.send_audio(
            channel_id,
            audio=file_path,
            duration=convert_to_seconds(duration),
            title=title,
        )

        await add_served_audio(vid, msg.link)

        if os.path.exists(file_path):
            os.remove(file_path)

        return {"link": msg.link}

    except Exception as e:
        return {"error": str(e)}

# ================= MAIN =================
async def main():
    port = int(os.environ.get("PORT", 1470))  # fallback to 1470

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

    server = uvicorn.Server(config)

    api_task = asyncio.create_task(server.serve())

    await bot.start()
    await idle()
    await bot.stop()

    await api_task

if __name__ == "__main__":
    asyncio.run(main())
