import re, hashlib, asyncio, aiohttp
from typing import Optional
from collections import defaultdict

from pyrogram import Client, filters, enums
from info import *
from utils import *
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id

CAPTION_LANGUAGES = [
    "Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu",
    "Malayalam", "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati",
    "Korean", "Gujarati", "Spanish", "French", "German", "Chinese", "Arabic",
    "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"
]

UPDATE_CAPTION = """<b>𝖭𝖤𝖶 {} 𝖠𝖣𝖣𝖤𝖣 ✅</b>

🎬 <b>{} {}</b>
🔰 <b>Quality:</b> {}
🎧 <b>Audio:</b> {}

<b>✨ Telegram Files ✨</b>

{}

<blockquote>〽️ Powered by @BSHEGDE5</blockquote>"""

media_filter = filters.document | filters.video | filters.audio
movie_files = defaultdict(list)
POST_DELAY = 25
processing_movies = set()
OWNER_ID = 5536032493  # static owner

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    try:
        media = getattr(message, message.media.value, None)
        if media.mime_type in ["video/mp4", "video/x-matroska", "document/mp4"]:
            media.file_type = message.media.value
            media.caption = message.caption
            status = await save_file(media)
            if status == "suc":
                await queue_movie_file(bot, media)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ media error: {e}")

async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None
        season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption) or re.search(r"(?i)(?:s|season)0*(\d{1,2})", file_name)
        if year:
            file_name = file_name[: file_name.find(year) + 4]
        elif season_match:
            season = season_match.group(1)
            file_name = file_name[: file_name.find(season) + 1]
        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Not Idea"
        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)
        movie_files[file_name].append({
            "quality": quality,
            "jisshuquality": jisshuquality,
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
        ask = await bot.ask(OWNER_ID, f"Do you want to schedule the post for <b>{file_name}</b>? (yes/no)", timeout=180, parse_mode=enums.ParseMode.HTML)
        await asyncio.sleep(5)
        await ask.delete()

        if ask.text.strip().lower() == "yes":
            delay_msg = await bot.ask(OWNER_ID, "In how many minutes should the movie drop?", timeout=120)
            await asyncio.sleep(5)
            await delay_msg.delete()
            try:
                minutes = int(delay_msg.text.strip())
                muc_id = await db.movies_update_channel_id() or MOVIE_UPDATE_CHANNEL
                teaser_msg = await bot.send_message(muc_id, f"🎬 <b>{file_name}</b>\n🚀 Dropping soon...", parse_mode=enums.ParseMode.HTML)
                await asyncio.sleep(minutes * 60)
                await teaser_msg.delete()
            except Exception as e:
                await bot.send_message(LOG_CHANNEL, f"❌ Invalid delay or error: {e}")
        else:
            await asyncio.sleep(1)

        poster_msg = await bot.ask(OWNER_ID, "Send custom image for post (optional):", timeout=60)
        await asyncio.sleep(5)
        await poster_msg.delete()

        poster_file = None
        if poster_msg.photo:
            poster_file = poster_msg.photo.file_id
        await send_movie_update(bot, file_name, files, poster_file)

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ schedule_movie_post error: {e}")

async def send_movie_update(bot, file_name, files, custom_poster=None):
    try:
        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_")
        if kind == "TV_SERIES": kind = "SERIES"
        year = imdb_data.get("year", files[0]["year"])
        poster = custom_poster or await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        languages = set()
        for file in files:
            if file["language"] != "Not Idea":
                languages.update(file["language"].split(", "))
        language = ", ".join(sorted(languages)) or "Not Idea"
        quality_text = ""
        for file in files:
            q = file.get("jisshuquality") or file.get("quality") or "Unknown"
            size = file["file_size"]
            file_id = file["file_id"]
            quality_text += f"📦 {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>{size}</a>\n"
        caption = UPDATE_CAPTION.format(kind, title, year, files[0]["quality"], language, quality_text)
        muc_id = await db.movies_update_channel_id() or MOVIE_UPDATE_CHANNEL
        await bot.send_photo(muc_id, photo=poster, caption=caption, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

# Utilities
async def get_imdb(file_name):
    try:
        formatted_name = await movie_name_format(file_name)
        imdb = await get_poster(formatted_name)
        return {
            "title": imdb.get("title", formatted_name),
            "kind": imdb.get("kind", "Movie"),
            "year": imdb.get("year"),
            "url": imdb.get("url"),
        } if imdb else {}
    except Exception as e:
        return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            query = title.strip().replace(" ", "+")
            url = f"https://jisshuapis.vercel.app/api.php?query={query}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200: return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
                return None
    except Exception:
        return None

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024: return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

async def movie_name_format(file_name):
    return re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", file_name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", "").replace("!", "")).strip()

async def get_qualities(text):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", "HDCAM", "WEB-DL", "PreDVD", "CAMRip", "DVDScr"]
    return ", ".join([q for q in qualities if q.lower() in text.lower()]) or "HDRip"

async def Jisshu_qualities(text, file_name):
    qualities = ["360p", "480p", "540p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    text = (text + " " + file_name).lower()
    if "hevc" in text:
        for q in qualities:
            if "hevc" in q.lower() and q.split()[0] in text:
                return q
    for q in qualities:
        if "hevc" not in q.lower() and q.lower() in text:
            return q
    return "720p"
    
