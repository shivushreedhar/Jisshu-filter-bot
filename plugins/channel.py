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

MOVIE_UPDATE_CHANNEL = -1002762317286

LANGUAGE_KEYWORDS = {
    "Bhojpuri": ["bhojpuri"],
    "Hindi": ["hindi", "hin"],
    "Bengali": ["bengali", "bengoli", "ben"],
    "Tamil": ["tamil", "tam"],
    "English": ["english", "eng"],
    "Bangla": ["bangla"],
    "Telugu": ["telugu", "tel"],
    "Malayalam": ["malayalam", "mal"],
    "Kannada": ["kannada", "kan"],
    "Marathi": ["marathi", "mar"],
    "Punjabi": ["punjabi", "pun"],
    "Gujarati": ["gujarati", "gujrati", "guj"],
    "Korean": ["korean", "kor"],
    "Spanish": ["spanish", "spa"],
    "French": ["french", "fre"],
    "German": ["german", "ger"],
    "Chinese": ["chinese", "chi", "mandarin"],
    "Arabic": ["arabic", "ara"],
    "Portuguese": ["portuguese", "por"],
    "Russian": ["russian", "rus"],
    "Japanese": ["japanese", "jap"],
    "Odia": ["odia", "oriya"],
    "Assamese": ["assamese", "ass"],
    "Urdu": ["urdu"]
}

UPDATE_CAPTION = """<b>𝖭𝖤𝖶 {} 𝖠𝖣𝖣𝖤𝖣 ✅</b>

🎬 <b>{} {}</b>
🔰 <b>Quality:</b> {}
🎧 <b>Audio:</b> {}

<b>✨ Telegram Files ✨</b>

{}

<blockquote>〽️ Powered by @BSHEGDE5</b></blockquote>"""

notified_movies = set()
movie_files = defaultdict(list)
POST_DELAY = 25
processing_movies = set()
media_filter = filters.document | filters.video | filters.audio


def detect_languages(text):
    text = text.lower()
    detected = []
    for lang, keywords in LANGUAGE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                detected.append(lang)
                break
    return ", ".join(sorted(set(detected))) or "Not Idea"


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    bot_id = bot.me.id
    media = getattr(message, message.media.value, None)
    if media.mime_type in ["video/mp4", "video/x-matroska", "document/mp4"]:
        media.file_type = message.media.value
        media.caption = message.caption
        success_sts = await save_file(media)
        if success_sts == "suc" and await db.get_send_movie_update_status(bot_id):
            file_id, file_ref = unpack_new_file_id(media.file_id)
            await queue_movie_file(bot, media)


async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None

        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = detect_languages(caption) or "Not Idea"
        file_size_str = format_file_size(media.file_size)
        file_id, file_ref = unpack_new_file_id(media.file_id)

        movie_files[file_name].append({
            "quality": quality,
            "jisshuquality": jisshuquality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year
        })

        if file_name in processing_movies:
            return

        processing_movies.add(file_name)
        print(f"Waiting {POST_DELAY}s for grouping '{file_name}' files...")
        await asyncio.sleep(POST_DELAY)

        if file_name in movie_files:
            await send_movie_update(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

    finally:
        processing_movies.discard(file_name)


async def send_movie_update(bot, file_name, files):
    try:
        if file_name in notified_movies:
            print(f"[Skipped] '{file_name}' already posted.")
            return

        notified_movies.add(file_name)
        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        year = imdb_data.get("year", "")
        poster = await fetch_movie_poster(title, files[0]["year"])
        kind = imdb_data.get("kind", "Movie").upper().replace(" ", "_")
        if kind == "TV_SERIES":
            kind = "SERIES"

        languages = set()
        for file in files:
            if file["language"] != "Not Idea":
                languages.update(file["language"].split(", "))
        language = ", ".join(sorted(languages)) or "Not Idea"

        quality_text = ""
        for file in files:
            link = f"<a href='https://t.me/{temp.U_NAME}?start=file_0_{file['file_id']}'>{file['file_size']}</a>"
            quality = file.get("jisshuquality") or file.get("quality") or "Unknown"
            quality_text += f"📦 {quality} : {link}\n"

        image_url = poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        full_caption = UPDATE_CAPTION.format(kind, title, year, files[0]['quality'], language, quality_text)

        movie_update_channel = await db.movies_update_channel_id()
        if not movie_update_channel:
            print(f"[Warning] MUC not set in DB, using fallback {MOVIE_UPDATE_CHANNEL}")
        target_channel = movie_update_channel if movie_update_channel else MOVIE_UPDATE_CHANNEL

        print(f"[Posting] '{title}' ({language}) to channel {target_channel}")
        await bot.send_photo(
            chat_id=target_channel,
            photo=image_url,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML
        )

    except Exception as e:
        print(f"[Error] Failed posting movie update: {e}")
        await bot.send_message(LOG_CHANNEL, f"[Error] Failed to send movie update: {e}")


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
        except:
            return None


def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"
    
