import re, asyncio, aiohttp
from typing import Optional
from collections import defaultdict

from pyrogram import Client, filters, enums
from info import *
from utils import *
from database.users_chats_db import db
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

        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None

        season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption) or re.search(r"(?i)(?:s|season)0*(\d{1,2})", file_name)

        if year and year in file_name:
            key = file_name[: file_name.find(year) + 4]
        elif season_match:
            season = season_match.group(1)
            key = file_name[: file_name.find(season) + len(season)]
        else:
            key = file_name.split()[0]

        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"

        text = f"{file_name} {caption}".lower()
        found_langs = set()
        for k, lang in LANGUAGE_KEYWORDS.items():
            if re.search(rf"\b{k}\b", text):
                found_langs.add(lang)
        language = ", ".join(sorted(found_langs)) if found_langs else "English"

        file_size_str = format_file_size(media.file_size)
        file_id, file_ref = unpack_new_file_id(media.file_id)

        movie_files[key].append({
            "quality": quality,
            "jisshuquality": jisshuquality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year
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
        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_")
        kind = "SERIES" if kind == "TV_SERIES" else "MOVIE"
        year = imdb_data.get("year", files[0]["year"])
        poster = await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

        language = files[0]["language"]
        qualities = sorted(set(file["jisshuquality"] or file["quality"] for file in files))
        quality_text = ", ".join(qualities)

        file_lines = ""
        if kind == "SERIES":
            ep_num = 1
            if len(files) == 1:
                file = files[0]
                q = file.get("jisshuquality") or file.get("quality")
                file_id = file["file_id"]
                file_lines += f"▶️ Complete Season [{q}] : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"
            else:
                for file in files:
                    q = file.get("jisshuquality") or file.get("quality")
                    file_id = file["file_id"]
                    file_lines += f"▶️ Episode {str(ep_num).zfill(2)} [{q}] : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"
                    ep_num += 1
        else:
            for file in files:
                q = file.get("jisshuquality") or file.get("quality")
                file_id = file["file_id"]
                file_lines += f"▶️ {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>Download Link</a>\n"

        caption = f"""<blockquote><b>🎉 NOW STREAMING! 🎉</b></blockquote>

<b>🎬 {title} ({year})</b>
<b>🛠️ Available In :</b> {quality_text}
<b>🔊 Audio :</b> {language}

<b>📥 {"Episodes" if kind == "SERIES" else "Download Links"} :</b>

{file_lines}

<blockquote><b>🚀 Download and Dive In!</b></blockquote>
<blockquote><b>〽️ Powered by @BSHEGDE5</b></blockquote>"""

        await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=caption, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

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
    except Exception:
        return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
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
    return re.sub(r"http\\S+", "", re.sub(r"@\\w+|#\\w+", "", file_name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", " ").replace("!", "")).strip()

async def get_qualities(text):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", "HDCAM", "WEB-DL", "WebRip", "PreDVD", "PRE-HD", "HDTS", "CAMRip", "DVDScr"]
    found = [q for q in qualities if q.lower() in text.lower()]
    return ", ".join(found) or "HDRip"

async def Jisshu_qualities(text, file_name):
    qualities = ["360p", "400MB", "480p", "540p", "576p", "700MB", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    text = (text + " " + file_name).lower()
    if "hevc" in text:
        for q in qualities:
            if "hevc" in q.lower() and q.split()[0].lower() in text:
                return q
    for q in qualities:
        if "hevc" not in q.lower() and q.lower() in text:
            return q
    return "720p"
    
