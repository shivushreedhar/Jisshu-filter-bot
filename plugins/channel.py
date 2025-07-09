# channel.py

import re, hashlib, asyncio, aiohttp
from typing import Optional
from pyrogram import Client, filters, enums
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from info import *
from utils import *
from database.ia_filterdb import save_file, unpack_new_file_id
from database.users_chats_db import db
from collections import defaultdict
from bs4 import BeautifulSoup

CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam",
    "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish",
    "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia",
    "Assamese", "Urdu"]

UPDATE_CAPTION = """<b>𝖭𝖤𝖶 {} 𝖠𝖣𝖣𝖤𝖣 ✅</b>

🎬 <b>{} {}</b>
🔰 <b>Quality:</b> {}
🎧 <b>Audio:</b> {}

<b>✨ Telegram Files ✨</b>

{}

<blockquote>〽️ Powered by @BSHEGDE5</blockquote>"""

media_filter = filters.document | filters.video | filters.audio
movie_files = defaultdict(list)
processing_movies = set()
POST_DELAY = 25

OWNER_ID = 5536032493
MUC = -1002762317286

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media_handler(bot, message):
    try:
        media = getattr(message, message.media.value, None)
        if media.mime_type in ["video/mp4", "video/x-matroska", "document/mp4"]:
            media.caption = message.caption
            save_status = await save_file(media)
            if save_status == "suc":
                await queue_movie_file(bot, media)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ media error: {e}")

async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        year = re.search(r"\b(19|20)\d{2}\b", caption)
        season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption)
        year = year.group(0) if year else None

        if year:
            file_name = file_name[:file_name.find(year)+4]
        elif season_match:
            season = season_match.group(1)
            file_name = file_name[:file_name.find(season)+1]

        quality = await get_qualities(caption) or "HDRip"
        j_quality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Not Idea"
        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        movie_files[file_name].append({
            "quality": quality,
            "jisshuquality": j_quality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year,
        })

        if file_name in processing_movies:
            return
        processing_movies.add(file_name)
        await asyncio.sleep(POST_DELAY)

        if file_name in movie_files:
            await schedule_movie_post(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

        processing_movies.remove(file_name)
    except Exception as e:
        processing_movies.discard(file_name)
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")

async def schedule_movie_post(bot, file_name, files):
    try:
        ask = await bot.ask(OWNER_ID, f"Do you want to schedule the post for '{file_name}'? (yes/no)", timeout=120)
        await asyncio.sleep(5); await ask.delete()

        if ask.text.lower().strip() == "yes":
            delay = await bot.ask(OWNER_ID, "In how many minutes should the movie drop?", timeout=60)
            await asyncio.sleep(5); await delay.delete()
            try:
                mins = int(delay.text.strip())
                await bot.send_message(MUC, f"🎬 <b>{file_name}</b>\n🚀 Dropping soon...", parse_mode=ParseMode.HTML)
                await asyncio.sleep(mins * 60)
            except Exception as e:
                await bot.send_message(LOG_CHANNEL, f"❌ Invalid delay: {e}")
        
        img_ask = await bot.ask(OWNER_ID, "Send custom image for post or skip", timeout=30)
        await asyncio.sleep(5); await img_ask.delete()

        poster = None
        if img_ask.photo:
            photo = await bot.download_media(img_ask.photo.file_id)
            poster = photo
        else:
            imdb = await get_imdb(file_name)
            poster = await fetch_movie_poster(imdb.get("title", file_name), imdb.get("year")) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

        await send_movie_update(bot, file_name, files, poster)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ schedule_movie_post error: {e}")

async def send_movie_update(bot, file_name, files, poster):
    try:
        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_")
        if kind == "TV_SERIES":
            kind = "SERIES"

        year = imdb_data.get("year", files[0]["year"])
        languages = set()
        for f in files:
            if f["language"] != "Not Idea":
                languages.update(f["language"].split(", "))
        language = ", ".join(sorted(languages)) or "Not Idea"

        quality_text = ""
        for f in files:
            q = f.get("jisshuquality") or f.get("quality") or "Unknown"
            size = f["file_size"]
            file_id = f["file_id"]
            quality_text += f"📦 {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>{size}</a>\n"

        caption = UPDATE_CAPTION.format(kind, title, year, files[0]["quality"], language, quality_text)
        await bot.send_photo(chat_id=MUC, photo=poster, caption=caption, parse_mode=ParseMode.HTML)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

async def get_imdb(file_name):
    try:
        name = await movie_name_format(file_name)
        imdb = await get_poster(name)
        return {"title": imdb.get("title", name), "kind": imdb.get("kind", "Movie"), "year": imdb.get("year")} if imdb else {}
    except: return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://jisshuapis.vercel.app/api.php?query={title.replace(' ', '+')}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
    except: pass
    return None

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

async def movie_name_format(name):
    return re.sub(r"http\S+", "", re.sub(r"[@#]\w+", "", name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "")
        .replace(";", "").replace("'", "").replace("-", "").replace("!", "")).strip()

async def get_qualities(text):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", "HDCAM", "WEB-DL", "PreDVD", "CAMRip", "DVDScr"]
    return ", ".join(q for q in qualities if q.lower() in text.lower()) or "HDRip"

async def Jisshu_qualities(text, file_name):
    text = (text + " " + file_name).lower()
    for q in ["360p", "480p", "540p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]:
        if "hevc" in q.lower() and "hevc" in text and q.split()[0] in text:
            return q
        elif "hevc" not in q.lower() and q.lower() in text:
            return q
    return "720p"

# TamilBlasters scraper (every 5 sec)
async def tbl_scraper_loop(bot: Client):
    posted = set()
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.1tamilblasters.how/") as res:
                    html = await res.text()
                    soup = BeautifulSoup(html, "html.parser")
                    articles = soup.select(".post-box-title a")
                    for a in articles:
                        title = a.get_text(strip=True)
                        link = a["href"]
                        if link not in posted:
                            posted.add(link)
                            await bot.send_message(MUC, f"🔥 <b>{title}</b>\n🔗 <a href='{link}'>Read More</a>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await bot.send_message(LOG_CHANNEL, f"TBL scraper error: {e}")
        await asyncio.sleep(5)

# Add this in your __main__.py or start.py
# asyncio.create_task(tbl_scraper_loop(app))
