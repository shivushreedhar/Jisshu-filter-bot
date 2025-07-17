import re, asyncio, aiohttp
from collections import defaultdict
from typing import Optional

from pyrogram import Client, filters, enums
from info import MOVIE_UPDATE_CHANNEL, CHANNELS
from utils import temp
from database.ia_filterdb import save_file, unpack_new_file_id

media_filter = filters.document | filters.video | filters.audio
movie_files = defaultdict(list)
waiting_tasks = dict()
POST_DELAY = 25

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


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    media_obj = getattr(message, message.media.value, None)
    if not media_obj or media_obj.mime_type not in ["video/mp4", "video/x-matroska", "document/mp4"]:
        return

    await save_file(media_obj)

    file_name = await movie_name_format(media_obj.file_name or "")
    title_key = await simplify_title(file_name)

    file_size = format_file_size(media_obj.file_size)
    file_id, _ = unpack_new_file_id(media_obj.file_id)
    caption_text = await movie_name_format(message.caption or "")

    language = detect_language(f"{file_name} {caption_text}".lower())
    quality = await get_qualities(f"{file_name} {caption_text}")
    year = await extract_year(f"{file_name} {caption_text}") or "N/A"

    movie_files[title_key].append({
        "file_id": file_id,
        "file_size": file_size,
        "quality": quality,
        "language": language,
        "year": year
    })

    print(f"[{title_key}] ➕ File added to DB ({quality}, {file_size})")

    if title_key in waiting_tasks:
        waiting_tasks[title_key].cancel()

    waiting_tasks[title_key] = asyncio.create_task(wait_and_post(bot, title_key))


async def wait_and_post(bot, key):
    try:
        remaining = POST_DELAY
        print(f"[{key}] New file detected. Timer reset.")
        while remaining > 0:
            print(f"[{key}] Waiting for file {remaining} sec...")
            await asyncio.sleep(1)
            remaining -= 1

        print(f"[{key}] No file came. Sending post to MUC...")

        await send_movie_update(bot, key, movie_files[key])
        print(f"[{key}] ✅ Post sent to MUC.")

        del movie_files[key]
        del waiting_tasks[key]

    except asyncio.CancelledError:
        print(f"[{key}] New file detected during wait. Countdown reset.")
    except Exception as e:
        print(f"[{key}] ❌ Error in wait_and_post: {e}")


async def send_movie_update(bot, title_key, files):
    poster = await fetch_movie_poster(title_key) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

    file_lines = ""
    qualities_present = []

    year = files[0].get("year", "N/A")
    language = files[0].get("language", "Unknown")

    for file in files:
        q = file.get("quality", "HDRip")
        if q not in qualities_present:
            qualities_present.append(q)
        link = f"https://t.me/{temp.U_NAME}?start=file_0_{file['file_id']}"
        file_lines += f"🎉 <b>{q}</b> : <a href='{link}'>Download Link</a>\n"

    caption = f"""
<blockquote><b>🎉 NOW STREAMING! 🎉</b></blockquote>

<b>🎬 Title : {title_key} ({year})</b>
<b>🛠️ Available In : {', '.join(sorted(set(qualities_present)))}</b>
<b>🔊 Audio : {language}</b>

<b>📥 Download Links :</b>

{file_lines}

<blockquote><b>🚀 Download and Dive In!</b></blockquote>
<blockquote><b>〽️ Powered by @BSHEGDE5</b></blockquote>
"""

    await bot.send_photo(
        chat_id=MOVIE_UPDATE_CHANNEL,
        photo=poster,
        caption=caption,
        parse_mode=enums.ParseMode.HTML
    )


async def simplify_title(text):
    name = await movie_name_format(text)
    return name.strip()


def detect_language(text):
    found_langs = {lang for k, lang in LANGUAGE_KEYWORDS.items() if re.search(rf"\b{k}\b", text)}
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
    cleaned = re.sub(r"http\S+", "", file_name)
    cleaned = re.sub(r"@\w+|#\w+", "", cleaned)
    cleaned = cleaned.replace("_", " ").replace("[", "").replace("]", "")
    cleaned = cleaned.replace("(", "").replace(")", "").replace("{", "").replace("}", "")
    cleaned = cleaned.replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
    cleaned = cleaned.replace("'", "").replace("-", " ").replace("!", "").strip()
    return cleaned


async def get_qualities(text):
    qualities = [
        "400MB", "450MB", "480p", "700MB", "720p", "800MB",
        "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip",
        "HDCAM", "WEB-DL", "WebRip", "PreDVD", "PRE-HD", "HDTS",
        "CAMRip", "DVDScr", "TRUE WEB-DL"
    ]
    for q in qualities:
        if q.lower() in text.lower():
            return q
    return "HDRip"


async def extract_year(text):
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else None
    
