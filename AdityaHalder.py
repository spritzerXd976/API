import aiohttp, asyncio, os, re, uvicorn, yt_dlp

from typing import Union
from fastapi import FastAPI
from urllib.parse import urlparse
from pyrogram import Client, enums, filters, idle
from motor.motor_asyncio import AsyncIOMotorClient
from youtubesearchpython.__future__ import VideosSearch


api_id = 12380656
api_hash = "d927c13beaaf5110f25c505b7c071273"
bot_token = "your_bot_token"
mongo_url = "your_mongo_db_url"
channel_id = -1003015175237
sudo_users = [7615306685]


sudoers = filters.user()
for user in sudo_users:
    if user not in sudoers:
        sudoers.add(user)



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
        print("✅ Bot Started❗")

    async def stop(self, *args):
        await super().stop()
        print("✅ Bot Stopped❗")


bot = Bot()
app = FastAPI(title="AdityaAPI")
mongodb = AsyncIOMotorClient(mongo_url).adityahalderdb


audiodb = mongodb.audiodb



async def is_served_audio(id: str) -> bool:
    doc = await audiodb.find_one({"id": id})
    return doc is not None


async def add_served_audio(id: str, link: str) -> bool:
    if await is_served_audio(id):
        return False

    await audiodb.insert_one({"id": id, "link": link})
    return True


async def get_served_audio(id: str) -> dict | None:
    return await audiodb.find_one({"id": id})


async def delete_served_audio(id: str) -> bool:
    result = await audiodb.delete_one({"id": id})
    return result.deleted_count > 0




async def download_audio(link: str):
    loop = asyncio.get_running_loop()
    
    def audio_dl():
        ydl_opts = {
            "cookiefile": "Cookies.txt",
            "format": "bestaudio/best",
            "outtmpl": "downloads/%(id)s.mp3",
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
        }
        x = yt_dlp.YoutubeDL(ydl_opts)
        info = x.extract_info(link, False)
        xyz = os.path.join(
            "downloads", f"{info['id']}.mp3"
        )
        if os.path.exists(xyz):
            return xyz
        x.download([link])
        return xyz
        
    return await loop.run_in_executor(None, audio_dl)


async def get_cdn_url(message_link: str):
    parsed = urlparse(message_link)
    parts = parsed.path.strip("/").split("/")
    channel = parts[0]
    msg_id = int(parts[1])

    msg = await bot.get_messages(channel, int(msg_id))
    media = msg.audio or msg.document or msg.voice
    if not media:
        return None

    file_id = media.file_id
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        ) as resp:
            data = await resp.json()
            try:
                file_path = data["result"]["file_path"]
            except Exception:
                return None
                
            return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"



def parse_query(query: str) -> str:
    if bool(re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/(?:watch\?v=|embed/|v/|shorts/|live/)?([A-Za-z0-9_-]{11})(?:[?&].*)?$', query)):
        match = re.search(r'(?:v=|\/(?:embed|v|shorts|live)\/|youtu\.be\/)([A-Za-z0-9_-]{11})', query)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
        
    return query



def convert_to_seconds(duration: str) -> int:
    parts = list(map(int, duration.split(":")))
    total = 0
    multiplier = 1

    for value in reversed(parts):
        total += value * multiplier
        multiplier *= 60

    return total


def format_duration(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    sec = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if sec > 0 or not parts:
        parts.append(f"{sec}s")

    return " ".join(parts)



@app.get("/")
async def home():
    return {"status": "running", "bot": str(bot.me.username) if bot.me else None}


@app.get("/song")
async def get_audio_url(query: Union[str, bool] = False):
    if not query:
        return {}

    search_query = parse_query(query)
    search = VideosSearch(search_query, limit=1)
    result = (await search.next())["result"]
    if not result:
        return {}

    video = result[0]
    title = video["title"]
    id = video["id"]
    duration = video["duration"]
    link = video["link"]

    if not duration:
        return {}
    
    is_audio = await is_served_audio(id)
    if not is_audio:
        try:
            audio_file = await download_audio(link)
        except Exception:
            return {}

        try:
            sent_audio = await bot.send_audio(
                channel_id,
                audio=audio_file,
                duration=convert_to_seconds(duration),
                performer="@ErixterNetwork",
                title=title,
            )
        except Exception as e:
            return {}
            
        audio_link = sent_audio.link
        await add_served_audio(id, audio_link)

        if os.path.exists(audio_file):
            os.remove(audio_file)

    served_audio = await get_served_audio(id)
    return {"link": served_audio["link"]}


async def main():
    config = uvicorn.Config(
        app, host="0.0.0.0", port=1470, log_level="info"
    )
    server = uvicorn.Server(config)
    api_task = asyncio.create_task(server.serve())
    await bot.start()
    await idle()
    await bot.stop()
    api_task.cancel


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    
