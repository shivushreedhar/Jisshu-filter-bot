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
POST_DELAY = 25
processing_movies = set()

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
        key = await simplify_title(file_name)

        quality = await get_qualities(caption) or "HDRip"
        language = detect_language(f"{file_name} {caption}".lower())
        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        movie_files[key].append({
            "quality": quality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language
        })

        if key in processing_movies:
            return

        processing_movies.add(key)
        await asyncio.sleep(POST_DELAY)

        if key in movie_files:
            await send_movie_update(bot, key, movie_files[key])
            del movie_files[key]

        processing_movies.remove(key)

    except Exception as e:
        processing_movies.discard(key)
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")

async def send_movie_update(bot, file_name, files):
    try:
        poster = await fetch_movie_poster(file_name) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        language = files[0]["language"]
        quality_text = files[0]["quality"]

        is_series = "S" in file_name.upper() and any(char.isdigit() for char in file_name)
        file_lines = ""

        if is_series:
            ep_num = 1
            for file in files:
                q = file.get("quality", "HDRip")
                file_id = file["file_id"]
                file_lines += f"▶️ EPISODE {str(ep_num).zfill(2)} [{q}] : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"
                ep_num += 1
        else:
            for file in files:
                q = file.get("quality", "HDRip")
                file_id = file["file_id"]
                file_lines += f"▶️ {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"

        caption = f"""<blockquote><b>🎉 NOW STREAMING! 🎉</b></blockquote>

<b>🎬 Title : {file_name} (N/A)</b>
<b>🛠️ Available In : {quality_text}</b>
<b>🔊 Audio : {language}</b>

<b>📥 {"Episodes" if is_series else "Download Links"} :</b>

{file_lines}

<blockquote><b>🚀 Download and Dive In!</b></blockquote>
<blockquote><b>〽️ Powered by @BSHEGDE5</b></blockquote>"""

        await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=caption, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

async def simplify_title(file_name):
    name = await movie_name_format(file_name)
    season_match = re.search(r"(?i)(S(\d{1,2})|Season\s?(\d{1,2}))", file_name)
    if season_match:
        season_number = season_match.group(2) or season_match.group(3)
        base_title = re.split(r"S\d{1,2}|Season\s?\d{1,2}", name, maxsplit=1)[0].strip()
        return f"{base_title} S{season_number}"
    else:
        return name.strip()

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

async def movie_name_format(file_name):
    return re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", file_name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", " ").replace("!", "")).strip()

async def get_qualities(text):
    qualities = ["400MB", "450MB", "480p", "700MB", "720p", "800MB",
                 "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip",
                 "HDCAM", "WEB-DL", "WebRip", "PreDVD", "PRE-HD", "HDTS", "CAMRip", "DVDScr"]
    found = [q for q in qualities if q.lower() in text.lower()]
    return found[0] if found else "HDRip"
    
