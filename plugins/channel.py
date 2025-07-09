import re, asyncio, aiohttp
from typing import Optional
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from collections import defaultdict
from info import *
from utils import *
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id
from bs4 import BeautifulSoup

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

🔗 <b>TamilBlasters:</b> {}
<blockquote>〽️ Powered by @BSHEGDE5</blockquote>"""

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
        year = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year.group(0) if year else None
        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Not Idea"
        file_size_str = format_file_size(media.file_size)
        file_id, file_ref = unpack_new_file_id(media.file_id)

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
        OWNER_ID = 5536032493
        ask = await bot.ask(OWNER_ID, f"Do you want to schedule the post for '{file_name}'? (yes/no)", timeout=180)
        await asyncio.sleep(5)
        await ask.delete()
        if ask.text.strip().lower() == "yes":
            delay_msg = await bot.ask(OWNER_ID, "In how many minutes should the movie drop?", timeout=120)
            await asyncio.sleep(5)
            await delay_msg.delete()
            try:
                minutes = int(delay_msg.text.strip())
                muc_id = await db.movies_update_channel_id() or -1002762317286
                teaser = await bot.send_message(muc_id, f"🎬 <b>{file_name}</b>\n🚀 Dropping soon...", parse_mode=enums.ParseMode.HTML)
                await asyncio.sleep(minutes * 60)
                await teaser.delete()
            except Exception as e:
                await bot.send_message(LOG_CHANNEL, f"❌ Delay input error: {e}")
        else:
            await bot.send_message(OWNER_ID, "Post will be sent immediately.")
            await asyncio.sleep(5)

        image_msg = await bot.ask(OWNER_ID, f"Send custom image for '{file_name}' or type 'skip'", timeout=120)
        await asyncio.sleep(5)
        await image_msg.delete()

        if image_msg.photo:
            image = image_msg.photo.file_id
        else:
            image = None

        await send_movie_update(bot, file_name, files, image)
    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ schedule_movie_post error: {e}")

async def send_movie_update(bot, file_name, files, poster_override=None):
    try:
        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "Movie").upper().replace(" ", "_")
        year = imdb_data.get("year", files[0]["year"])
        poster = poster_override or await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

        language = ", ".join(sorted({file["language"] for file in files if file["language"] != "Not Idea"})) or "Not Idea"
        quality_text = ""
        for file in files:
            q = file.get("jisshuquality") or file.get("quality") or "Unknown"
            size = file["file_size"]
            file_id = file["file_id"]
            quality_text += f"📦 {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>{size}</a>\n"

        tbl_url = await get_tbl_link(title)
        caption = UPDATE_CAPTION.format(kind, title, year, files[0]["quality"], language, quality_text, tbl_url)

        muc_id = await db.movies_update_channel_id() or -1002762317286
        await bot.send_photo(muc_id, poster, caption=caption, parse_mode=enums.ParseMode.HTML)

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

async def get_tbl_link(query):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://www.1tamilblasters.how/search/{query.replace(' ', '%20')}"
            async with session.get(url) as res:
                soup = BeautifulSoup(await res.text(), "html.parser")
                first_link = soup.select_one("div.Title a")
                return first_link["href"] if first_link else "Not found"
    except Exception as e:
        return "Not found"

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
            url = f"https://jisshuapis.vercel.app/api.php?query={title.strip().replace(' ', '+')}"
            async with session.get(url) as res:
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list):
                        return posters[0]
    except Exception:
        pass
    return None

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

async def movie_name_format(file_name):
    return re.sub(r"http\S+", "", re.sub(r"[@#]\w+", "", file_name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", "").replace("!", "")).strip()

async def get_qualities(text):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", "HDCAM", "WEB-DL", "PreDVD"]
    return ", ".join([q for q in qualities if q.lower() in text.lower()]) or "HDRip"

async def Jisshu_qualities(text, file_name):
    text = (text + " " + file_name).lower()
    qualities = ["360p", "480p", "540p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    for q in qualities:
        if "hevc" in q and q.split()[0] in text and "hevc" in text:
            return q
    for q in qualities:
        if q in text:
            return q
    return "720p"
                
