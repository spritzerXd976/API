import aiohttp
import asyncio
import os
import yt_dlp

from typing import Union
from fastapi import FastAPI
from pyrogram import Client, idle
from motor.motor_asyncio import AsyncIOMotorClient
from youtubesearchpython.__future__ import VideosSearch
from pytubefix import YouTube
from pytubefix.innertube import _default_clients

# ================= ENV (SAFE FALLBACK) =================
api_id = int(os.getenv("API_ID", "28492745"))
api_hash = os.getenv("API_HASH", "0241a9746f6e264fe7f75cf209177246")
bot_token = os.getenv("BOT_TOKEN", "8104460140:AAEnI5F2oBkRSKMPgHh6L5O3s6D_5-ap8XA")
mongo_url = os.getenv("MONGO_URL", "mongodb+srv://Mafia:Mafia@mafia.wvuzxgl.mongodb.net/?retryWrites=true&w=majority")

channel_id = int(os.getenv("CHANNEL_ID", "-1002362100657"))
sudo_users = list(map(int, os.getenv("SUDO_USERS", "6035523795").split(",")))

po_token = os.getenv("PO_TOKEN", "MniJ8-uPxkMu94nPi_sy6PTkQaTX01vR_Q-oD qrPJK2PxvorDEQQMRAFzxekrSWaQu82sZ-RqcN _-kfUI34Xmh1GteltmE0m39nBV3sHGRiuU6Zws QCnugsspcW8tY3gSi9fVNiqHQGWhvFTEpDQZ8U fU3x151LSgNE=")
visitor_data = os.getenv("VISITOR_DATA", "CgtjNW5HUmRVd1RZbyi_-Y HPBjIKCgJVUxIEGgAgUw%3D%3D")

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

        # ---- METHOD 1: yt-dlp ----
        try:
            common_opts = {
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "quiet": True,
                "nocheckcertificate": True,
                "geo_bypass": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

            formats_to_try = [
                "bestaudio[ext=m4a]",
                "bestaudio[ext=webm]",
                "bestaudio",
                "worstaudio",
                "best[ext=mp4]",
                "best",
            ]

            for fmt in formats_to_try:
                try:
                    ydl_opts = {**common_opts, "format": fmt}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(link, download=True)
                        base = os.path.splitext(ydl.prepare_filename(info))[0]
                        path = base + ".mp3"
                        if os.path.exists(path):
                            return path
                except Exception:
                    continue
        except Exception:
            pass

        # ---- METHOD 2: pytubefix with PO Token ----
        try:
            # Patch client to use ANDROID which bypasses bot detection
            _default_clients["ANDROID"]["context"]["client"]["clientVersion"] = "19.09.3"
            _default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID"]

            token_kwargs = {}
            if po_token and visitor_data:
                token_kwargs = {
                    "use_po_token": True,
                    "po_token_verifier": lambda: (visitor_data, po_token),
                }

            yt = YouTube(link, client="ANDROID_MUSIC", **token_kwargs)
            stream = yt.streams.filter(only_audio=True).order_by("abr").last()
            if not stream:
                stream = yt.streams.filter(progressive=True).order_by("resolution").last()

            out_path = stream.download(output_path="downloads")
            base = os.path.splitext(out_path)[0]
            mp3_path = base + ".mp3"
            os.rename(out_path, mp3_path)
            return mp3_path
        except Exception as e2:
            raise Exception(f"All methods failed: {e2}")

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
