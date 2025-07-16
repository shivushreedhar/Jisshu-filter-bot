import re, asyncio, aiohttp
from typing import Optional
from collections import defaultdict

from pyrogram import Client, filters, enums
from info import *
from utils import *
from database.ia_filterdb import save_file, unpack_new_file_id

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

media_filter = filters.document | filters.video | filters.audio
movie_files = defaultdict(list)
processing_timers = dict()  # key: asyncio.Task

GROUP_DELAY = 30  # seconds

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
        file_name = await clean_title(media.file_name)
        caption = await clean_title(media.caption or "")

        key = await detect_title_key(file_name, caption)
        year = await extract_year(caption) or await extract_year(file_name) or "N/A"
        quality = await get_quality(caption) or "HDRip"
        language = detect_language(f"{file_name} {caption}".lower())

        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        movie_files[key].append({
            "quality": quality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year
        })

        # Cancel existing timer and restart grouping delay
        if key in processing_timers:
            processing_timers[key].cancel()

        processing_timers[key] = asyncio.create_task(process_after_delay(bot, key))

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")

async def process_after_delay(bot, key):
    try:
        await asyncio.sleep(GROUP_DELAY)
        if key in movie_files:
            await send_movie_update(bot, key, movie_files[key])
            del movie_files[key]
            del processing_timers[key]
    except asyncio.CancelledError:
        pass
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ process_after_delay error: {e}")

async def send_movie_update(bot, title, files):
    try:
        poster = await fetch_movie_poster(title) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        language = files[0]["language"]
        year = files[0]["year"]
        quality = files[0]["quality"]

        is_combined = "combined" in title.lower()
        file_lines = ""
        if is_combined or len(files) == 1:
            file = files[0]
            file_id = file["file_id"]
            q = file["quality"]
            file_lines += f"<b>🎉 Complete Season :</b> <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"
        else:
            ep_num = 1
            for file in files:
                file_id = file["file_id"]
                file_lines += f"<b>🎉 EPISODE {str(ep_num).zfill(2)} :</b> <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"
                ep_num += 1

        caption = f"""<blockquote><b>🎉 NOW STREAMING! 🎉</b></blockquote>

<b>🎬 Title : {title} ({year})</b>
<b>🛠️ Available In : {quality}</b>
<b>🔊 Audio : {language}</b>

<b>📥 Download Links :</b>

<b>{file_lines}</b>

<blockquote><b>🚀 Download and Dive In!</b></blockquote>
<blockquote><b>〽️ Powered by @BSHEGDE5</b></blockquote>"""

        await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=caption, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

# Utility Functions

async def detect_title_key(file_name, caption):
    name = file_name or caption
    title = re.sub(r'(S\d{1,2}|Season\s?\d{1,2}|E\d{1,2}|Episode\s?\d{1,2}|\.|\-|_|#)', ' ', name, flags=re.I)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

async def clean_title(text):
    if not text:
        return ""
    text = re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", text))
    text = re.sub(r"[\[\]{}().:;'\-_!]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def detect_language(text):
    found_langs = set()
    for k, lang in LANGUAGE_KEYWORDS.items():
        if re.search(rf"\b{k}\b", text):
            found_langs.add(lang)
    return ", ".join(sorted(found_langs)) if found_langs else "English"

async def fetch_movie_poster(title: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            query = title.strip().replace(" ", "+")
            url = f"https://jisshuapis.vercel.app/api.php?query={query}"
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

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

async def get_quality(text):
    qualities = ["400MB", "450MB", "480p", "700MB", "720p", "800MB",
                 "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", 
                 "HDCAM", "WEB-DL", "WebRip", "PreDVD", "PRE-HD", "HDTS", 
                 "CAMRip", "DVDScr"]
    for q in qualities:
        if q.lower() in text.lower():
            return q
    return "HDRip"

async def extract_year(text):
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else None
    
