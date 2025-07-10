import re, asyncio, aiohttp
from typing import Optional
from collections import defaultdict
from pyrogram import Client, filters, enums
from info import *
from utils import *
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id

OWNER_ID = 5536032493
POST_DELAY = 25
MOVIE_UPDATE_CHANNEL = -1002762317286
media_filter = filters.document | filters.video | filters.audio
movie_files = defaultdict(list)
processing_movies = set()

LANGUAGE_KEYWORDS = {
    "kannada": "Kannada", "kan": "Kannada",
    "telugu": "Telugu", "tel": "Telugu",
    "tamil": "Tamil", "tam": "Tamil",
    "hindi": "Hindi", "hin": "Hindi",
    "malayalam": "Malayalam", "mal": "Malayalam",
    "english": "English", "eng": "English",
    "bengali": "Bengali", "ben": "Bengali",
    "marathi": "Marathi", "punjabi": "Punjabi",
    "gujarati": "Gujarati", "urdu": "Urdu"
}

UPDATE_CAPTION = """
<blockquote>🔥 <b>Trending Files</b></blockquote>

🎬 <b>{}</b>
🗓️ <b>Year:</b> {}
💬 <b>Languages:</b> {}
📦 <b>Quality:</b> {}

<b>✨ Telegram Files ✨</b>
{}

<blockquote>〽️ Powered by @BSHEGDE5</blockquote>
"""

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media_handler(bot, message):
    try:
        print(f"📥 File received in DB channel: {message.chat.id}")
        media = getattr(message, message.media.value, None)
        if media.mime_type in ["video/mp4", "video/x-matroska", "application/octet-stream"]:
            media.file_type = message.media.value
            media.caption = message.caption
            status = await save_file(media)
            print(f"✅ File saved status: {status}")
            if status == "suc":
                await queue_movie_file(bot, media)
    except Exception as e:
        print(f"❌ Error in media_handler: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ media_handler error: {e}")

async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None

        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = detect_languages(caption)
        file_size = format_file_size(media.file_size)
        file_id, file_ref = unpack_new_file_id(media.file_id)

        movie_files[file_name].append({
            "quality": quality, "jisshuquality": jisshuquality,
            "file_id": file_id, "file_size": file_size,
            "caption": caption, "language": language, "year": year
        })

        if file_name in processing_movies:
            return

        processing_movies.add(file_name)
        await asyncio.sleep(POST_DELAY)

        if file_name in movie_files:
            await send_movie_post(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

        processing_movies.remove(file_name)

    except Exception as e:
        print(f"❌ queue_movie_file error: {e}")
        processing_movies.discard(file_name)
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")

async def send_movie_post(bot, file_name, files):
    try:
        ask_img = await bot.send_message(OWNER_ID, f"Send custom image for <code>{file_name}</code> poster or skip.")
        reply_img = await bot.listen(OWNER_ID, timeout=180)
        await ask_img.delete()
        await reply_img.delete()
        custom_poster = None

        if reply_img.photo:
            custom_poster = reply_img.photo.file_id

        imdb = await get_imdb(file_name)
        title = imdb.get("title", file_name)
        year = imdb.get("year", files[0]["year"])
        poster = custom_poster or await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        language = merge_languages([f["language"] for f in files])
        quality_text = ""

        for f in files:
            q = f.get("jisshuquality") or f.get("quality")
            size = f["file_size"]
            fid = f["file_id"]
            quality_text += f"📥 <b>{q}</b>: <a href='https://t.me/{temp.U_NAME}?start=file_0_{fid}'>{size}</a>\n"

        caption = UPDATE_CAPTION.format(title, year, language, files[0]["quality"], quality_text)
        await bot.send_photo(MOVIE_UPDATE_CHANNEL, poster, caption=caption, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        print(f"❌ send_movie_post error: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_post error: {e}")

def detect_languages(text: str) -> str:
    text = text.lower()
    found = set()
    for key, lang in LANGUAGE_KEYWORDS.items():
        if key in text:
            found.add(lang)
    return ", ".join(sorted(found)) if found else "No Idea"

def merge_languages(lang_list):
    combined = set()
    for item in lang_list:
        for lang in item.split(", "):
            if lang and lang != "No Idea":
                combined.add(lang)
    return ", ".join(sorted(combined)) or "No Idea"

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

async def movie_name_format(text: str) -> str:
    return re.sub(r"http\S+|@\w+|#\w+", "", text).translate(
        str.maketrans("_[](){}.:;@!-'", "              ")
    ).strip()

async def get_qualities(text: str):
    qualities = ["480p", "720p", "1080p", "2160p", "HDRip", "WEB-DL", "PreDVD", "CAMRip"]
    return ", ".join([q for q in qualities if q.lower() in text.lower()])

async def Jisshu_qualities(text, file_name):
    all_text = (text + " " + file_name).lower()
    qualities = ["360p", "480p", "540p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    if "hevc" in all_text:
        for q in qualities:
            if "hevc" in q.lower() and q.split()[0] in all_text:
                return q
    for q in qualities:
        if q.lower() in all_text:
            return q
    return "720p"

async def fetch_movie_poster(title: str, year: Optional[int] = None):
    try:
        async with aiohttp.ClientSession() as session:
            query = title.strip().replace(" ", "+")
            url = f"https://jisshuapis.vercel.app/api.php?query={query}"
            async with session.get(url, timeout=5) as res:
                if res.status != 200:
                    return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list):
                        return posters[0]
    except Exception as e:
        print(f"❌ Poster fetch error: {e}")
    return None

async def get_imdb(name):
    try:
        formatted = await movie_name_format(name)
        imdb = await get_poster(formatted)
        return {
            "title": imdb.get("title", formatted),
            "year": imdb.get("year"),
            "url": imdb.get("url"),
        } if imdb else {}
    except Exception as e:
        print(f"❌ IMDb fetch error: {e}")
        return {}
        
