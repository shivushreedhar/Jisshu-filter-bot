import re
import asyncio
import aiohttp
from typing import Optional
from collections import defaultdict
from pyrogram import Client, filters, enums
from info import *
from utils import *
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id

LANGUAGE_KEYWORDS = {
    "tam": "Tamil",
    "tamil": "Tamil",
    "tel": "Telugu",
    "telugu": "Telugu",
    "kan": "Kannada",
    "kannada": "Kannada",
    "mal": "Malayalam",
    "malayalam": "Malayalam",
    "hin": "Hindi",
    "hindi": "Hindi",
    "eng": "English",
    "english": "English",
    "ben": "Bengali",
    "bengali": "Bengali",
    "pun": "Punjabi",
    "punjabi": "Punjabi"
}

CAPTION_LANGUAGES = list(set(LANGUAGE_KEYWORDS.values()))

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


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    try:
        print(f"📥 File received in DB channel: {message.chat.id}")
        media = getattr(message, message.media.value, None)
        if media.mime_type in ["video/mp4", "video/x-matroska", "document/mp4"]:
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
        language = detect_languages(caption) or "Not Idea"
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
            await send_movie_update(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

        processing_movies.remove(file_name)

    except Exception as e:
        print(f"❌ queue_movie_file error: {e}")
        processing_movies.discard(file_name)
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")


async def send_movie_update(bot, file_name, files):
    try:
        muc_id = await db.movies_update_channel_id() or MOVIE_UPDATE_CHANNEL

        # Validate MUC id before posting
        if isinstance(muc_id, int):
            try:
                await bot.get_chat(muc_id)
            except Exception as e:
                print(f"⚠️ Invalid or inaccessible MUC channel: {e}")
                await bot.send_message(LOG_CHANNEL, f"⚠️ MUC Channel inaccessible: {e}")
                return

        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_")
        if kind == "TV_SERIES":
            kind = "SERIES"

        year = imdb_data.get("year", files[0]["year"])
        poster = await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

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

        print("📨 Sending update to MUC:", muc_id)

        await bot.send_photo(
            chat_id=muc_id,
            photo=poster,
            caption=caption,
            parse_mode=enums.ParseMode.HTML
        )

    except Exception as e:
        print(f"❌ send_movie_update error: {e}")
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
    except Exception as e:
        print(f"❌ IMDb fetch error: {e}")
        return {}


async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            query = title.strip().replace(" ", "+")
            url = f"https://jisshuapis.vercel.app/api.php?query={query}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    print(f"Poster API error: HTTP {res.status}")
                    return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
                print(f"No poster found for {title}")
                return None
    except Exception as e:
        print(f"❌ Poster fetch error: {e}")
        return None


def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


async def movie_name_format(file_name):
    return re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", file_name)
        .replace("_", " ")
        .replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "")
        .replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "")
        .replace(":", "").replace(";", "")
        .replace("'", "").replace("-", "")
        .replace("!", "")).strip()


async def get_qualities(text):
    qualities = [
        "480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p",
        "HDRip", "HDCAM", "WEB-DL", "PreDVD", "CAMRip", "DVDScr"
    ]
    found = [q for q in qualities if q.lower() in text.lower()]
    return ", ".join(found) or "HDRip"


def detect_languages(text):
    detected = set()
    lower_text = text.lower()
    for keyword, language in LANGUAGE_KEYWORDS.items():
        if keyword in lower_text:
            detected.add(language)
    return ", ".join(sorted(detected)) if detected else None


async def Jisshu_qualities(text, file_name):
    return await get_qualities(text + " " + file_name)
    
