import aiohttp
import asyncio
import os
import yt_dlp

from typing import Union
from fastapi import FastAPI
from pyrogram import Client, idle
from motor.motor_asyncio import AsyncIOMotorClient
from youtubesearchpython.__future__ import VideosSearch

# ================= ENV (SAFE FALLBACK) =================
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

# ================= DOWNLOAD (UPDATED FIX) =================
async def download_audio(link: str):
    loop = asyncio.get_running_loop()

    def run():
        os.makedirs("downloads", exist_ok=True)

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "quiet": True,

            # ✅ FIX: bypass YouTube block
            "cookiefile": "Cookies.txt",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept-Language": "en-US,en;q=0.9",
            },

            "nocheckcertificate": True,
            "geo_bypass": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            base = os.path.splitext(ydl.prepare_filename(info))[0]
            return base + ".mp3"

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

        # cache
        if await is_served_audio(vid):
            data = await get_served_audio(vid)
            return {"link": data["link"]}

        file_path = await download_audio(link)

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

# ================= BOT BACKGROUND =================
@app.on_event("startup")
async def startup():
    asyncio.create_task(start_bot())

async def start_bot():
    await bot.start()
    print("✅ Bot Started!")
    await idle()
    await bot.stop()

# ================= MAIN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1470))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
