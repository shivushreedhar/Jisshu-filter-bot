import re, asyncio, aiohttp
from typing import Optional
from collections import defaultdict
from pyrogram import Client, filters, enums
from info import *
from utils import *
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id

CAPTION_LANGUAGES = [
    "Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam",
    "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish",
    "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia",
    "Assamese", "Urdu"
]

LANGUAGE_SHORTCODES = {
    "Hindi": "Hin", "Tamil": "Tam", "Telugu": "Tel", "Kannada": "Kan", "Malayalam": "Mal",
    "English": "Eng", "Bengali": "Ben", "Bhojpuri": "Bho", "Bangla": "Ban", "Marathi": "Mar",
    "Punjabi": "Pun", "Gujrati": "Guj", "Gujarati": "Guj", "Korean": "Kor", "Spanish": "Spa",
    "French": "Fre", "German": "Ger", "Chinese": "Chi", "Arabic": "Ara", "Portuguese": "Por",
    "Russian": "Rus", "Japanese": "Jap", "Odia": "Odi", "Assamese": "Asm", "Urdu": "Urd",
    "Bengoli": "Ben"
}

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

def extract_languages(text: str) -> str:
    text = text.lower()
    langs = {short for full, short in LANGUAGE_SHORTCODES.items()
             if full.lower() in text or short.lower() in text}
    return " + ".join(sorted(langs)) if langs else "No Idea"

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
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
        print(f"❌ Error in media: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ media error: {e}")

async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")

        year = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year.group(0) if year else None
        season = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption) or re.search(r"(?i)(?:s|season)0*(\d{1,2})", file_name)
        if year:
            file_name = file_name[:file_name.find(year)+4]
        elif season:
            s = season.group(1)
            file_name = file_name[:file_name.find(s)+1]

        quality = await get_qualities(caption) or "HDRip"
        jquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        language = extract_languages(caption)

        movie_files[file_name].append({
            "quality": quality, "jisshuquality": jquality,
            "file_id": file_id, "file_size": size_str,
            "caption": caption, "language": language, "year": year
        })

        if file_name in processing_movies:
            return
        processing_movies.add(file_name)

        await asyncio.sleep(POST_DELAY)

        if file_name in movie_files:
            await post_movie(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

        processing_movies.remove(file_name)
    except Exception as e:
        print(f"❌ queue_movie_file error: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")

async def post_movie(bot, file_name, files):
    try:
        OWNER_ID = 5536032493
        ask = await bot.send_message(OWNER_ID, f"Send custom image for '{file_name}' poster or skip...")
        reply = await bot.listen(OWNER_ID, timeout=180)
        await ask.delete(); await reply.delete()

        poster = reply.photo.file_id if reply.photo else None
        await send_movie_update(bot, file_name, files, poster)
    except Exception as e:
        print(f"❌ post_movie error: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ post_movie error: {e}")

async def send_movie_update(bot, file_name, files, custom_poster=None):
    try:
        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_")
        kind = "SERIES" if kind == "TV_SERIES" else kind
        year = imdb_data.get("year", files[0]["year"])
        poster = custom_poster or await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

        language = files[0]["language"]
        quality_text = ""
        for f in files:
            q = f.get("jisshuquality") or f.get("quality") or "Unknown"
            size = f["file_size"]
            fid = f["file_id"]
            quality_text += f"📦 {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{fid}'>{size}</a>\n"

        caption = UPDATE_CAPTION.format(kind, title, year, files[0]["quality"], language, quality_text)
        await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=caption, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        print(f"❌ send_movie_update error: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

# Utility functions (get_imdb, fetch_movie_poster, format_file_size, movie_name_format, get_qualities, Jisshu_qualities) remain unchanged.
