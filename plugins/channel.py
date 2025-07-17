# --| This code created by: Jisshu_bots & SilentXBotz |--#
import re
import hashlib
import asyncio
from info import *
from utils import *
from pyrogram import Client, filters, enums
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id
import aiohttp
from typing import Optional
from collections import defaultdict

# Language Keywords Extended
CAPTION_LANGUAGES = [
    "Bhojpuri", "bho", "bhojp", "Hindi", "hin", "hindi",
    "Bengali", "ben", "bengali", "Bangla", "bangla", "bang", "Tamil", "tam", "tamil",
    "English", "eng", "english", "Telugu", "tel", "telugu",
    "Malayalam", "mal", "malayalam", "Kannada", "kan", "kannada",
    "Marathi", "mar", "marathi", "Punjabi", "pun", "punjabi",
    "Bengoli", "beng", "bengoli", "Gujrati", "guj", "gujrati", "gujarati",
    "Korean", "kor", "korean", "Spanish", "spa", "spanish",
    "French", "fre", "french", "German", "ger", "german",
    "Chinese", "chi", "chinese", "Arabic", "ara", "arabic",
    "Portuguese", "por", "portuguese", "Russian", "rus", "russian",
    "Japanese", "jap", "japanese", "Odia", "ori", "odia",
    "Assamese", "ass", "assamese", "Urdu", "urd", "urdu"
]

UPDATE_CAPTION = """<b><blockquote>🎉 Streaming Now 🎉</b></blockquote>

<b>🎬 Title : {} {}</b>
<b>🛠️ Available in : {} </b>
<b>🔊 Audio : {}</b>

<b>📥 Download Now</b> 

<b>{}</b>

<b> Download Now & Dive In </b>

<blockquote><b>〽️ Powered by @BSHEGDE5</b></blockquote>"""

notified_movies = set()
movie_files = defaultdict(list)
POST_DELAY = 25  # Delay before posting
processing_movies = set()
media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    bot_id = bot.me.id
    media = getattr(message, message.media.value, None)
    if media and media.mime_type in ["video/mp4", "video/x-matroska", "document/mp4"]:
        media.file_type = message.media.value
        media.caption = message.caption
        save_status = await save_file(media)
        if save_status == "suc" and await db.get_send_movie_update_status(bot_id):
            await queue_movie_file(bot, media)


async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None
        season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption)

        if year:
            file_name = file_name[: file_name.find(year) + 4]
        elif season_match:
            season = season_match.group(1)
            file_name = file_name[: file_name.find(season) + 1]

        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Unknown"
        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        movie_files[file_name].append({
            "quality": quality,
            "jisshuquality": jisshuquality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year
        })

        print(f"[Koyeb Log] ➜ New file queued: {file_name}. Reset 25s timer.")

        if file_name in processing_movies:
            return
        processing_movies.add(file_name)

        await asyncio.sleep(POST_DELAY)

        if file_name in movie_files:
            await send_movie_update(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

        processing_movies.remove(file_name)

    except Exception as e:
        processing_movies.discard(file_name)
        await bot.send_message(LOG_CHANNEL, f"[Koyeb Log] ❌ Error in queue_movie_file: {e}")


async def send_movie_update(bot, file_name, files):
    try:
        if file_name in notified_movies:
            return
        notified_movies.add(file_name)

        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "").upper().replace(" ", "_")
        if kind == "TV_SERIES":
            kind = "SERIES"
        elif kind == "MOVIE":
            kind = "MOVIE"
        else:
            kind = "MOVIE"

        year = files[0].get("year", "")
        poster = await fetch_movie_poster(title, year)
        language = ", ".join({f["language"] for f in files if f["language"] != "Unknown"}) or "Unknown"

        quality_text = ""
        for f in files:
            quality = f["jisshuquality"] or f["quality"]
            fid = f["file_id"]
            quality_text += f"📦 {quality} ➔ <a href='https://t.me/{temp.U_NAME}?start=file_0_{fid}'>Download</a>\n"

        full_caption = UPDATE_CAPTION.format(kind, title, year or "", files[0]["quality"], language, quality_text)

        movie_update_channel = await db.movies_update_channel_id()
        await bot.send_photo(
            chat_id=movie_update_channel or MOVIE_UPDATE_CHANNEL,
            photo=poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg",
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML
        )

        print(f"[Koyeb Log] ✅ Posted: {file_name}")

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"[Koyeb Log] ❌ Error sending post for {file_name}: {e}")


# ---------- UTILITIES (Do not modify) -----------
async def get_imdb(file_name):
    try:
        formatted_name = await movie_name_format(file_name)
        imdb = await get_poster(formatted_name)
        if not imdb:
            return {}
        return {
            "title": imdb.get("title", formatted_name),
            "kind": imdb.get("kind", "Movie"),
            "year": imdb.get("year"),
            "url": imdb.get("url"),
        }
    except Exception:
        return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        query = title.strip().replace(" ", "+")
        url = f"https://jisshuapis.vercel.app/api.php?query={query}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
                return None
        except Exception:
            return None

async def get_qualities(text):
    qualities = [
        "480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p",
        "ORG", "org", "HDRip", "hdrip", "CAMRip", "camrip", "WEB-DL", "hdtc", "predvd", "dvdscr", "dvdrip", "HDTS", "hdts"
    ]
    found_qualities = [q for q in qualities if q.lower() in text.lower()]
    return ", ".join(found_qualities) or "HDRip"

async def Jisshu_qualities(text, file_name):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    combined_text = (text.lower() + " " + file_name.lower()).strip()
    for quality in qualities:
        if quality.lower() in combined_text:
            return quality
    return "720p"

async def movie_name_format(file_name):
    filename = re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", file_name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", "").replace("!", "")
    ).strip()
    return filename

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"
                      
