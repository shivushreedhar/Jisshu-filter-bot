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

# ---------------- Constants -----------------
LANGUAGE_KEYWORDS = {
    "tam": "Tamil", "tamil": "Tamil",
    "tel": "Telugu", "telugu": "Telugu",
    "kan": "Kannada", "kannada": "Kannada",
    "mal": "Malayalam", "malayalam": "Malayalam",
    "hin": "Hindi", "hindi": "Hindi",
    "eng": "English", "english": "English",
    "ben": "Bengali", "bengali": "Bengali",
    "pun": "Punjabi", "punjabi": "Punjabi"
}

PRINT_TYPES = ["HDRip", "WEB-DL", "PreDVD", "HDCAM", "CAMRip", "DVDScr"]

UPDATE_CAPTION = """<b><blockquote>🎉 NEW {} STREAMING NOW 🎉</b></blockquote>

🎬 <b>Title : {} {}</b>
🛠️ <b>Available in : {}</b>
🔊 <b>Audio : {}</b>

<b>📥 Download Now</b>

<b>{}</b>

<blockquote><b>🚀 Download And Dive In !</b></blockquote>
<blockquote><b>〽️ Powered by @BSHEGDE5</b></blockquote>"""

media_filter = filters.document | filters.video | filters.audio
movie_files = defaultdict(list)
POST_DELAY = 25
processing_movies = set()
OWNER_ID = 5536032493  # Owner for PM confirmation

# ---------------- Helper Functions -----------------
async def movie_name_format(file_name):
    return re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", file_name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", " ").replace("!", "")).strip()

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

def detect_languages(text):
    detected = set()
    lower_text = text.lower()
    for keyword, language in LANGUAGE_KEYWORDS.items():
        if keyword in lower_text:
            detected.add(language)
    return ", ".join(sorted(detected)) if detected else None

async def get_qualities(text):
    text_lower = text.lower()
    patterns = [
        (r"\b2160p\b", "2160p"),
        (r"\b1080p\b", "1080p"),
        (r"\b720p\b", "720p"),
        (r"\b480p\b", "480p"),
        (r"\b400mb\b", "400MB"),
        (r"\b700mb\b", "700MB"),
        (r"\b1080p\s*hevc\b", "1080p HEVC"),
        (r"\b720p\s*hevc\b", "720p HEVC"),
    ]
    found = []
    for pattern, label in patterns:
        if re.search(pattern, text_lower):
            found.append(label)
    return ", ".join(found) if found else "720p"

async def Jisshu_qualities(text, file_name):
    return await get_qualities(text + " " + file_name)

def extract_episode_number(text: str) -> Optional[int]:
    m = re.search(r"(?:EP|Ep|Episode|E)[\s\-_]?0*(\d{1,3})", text, re.IGNORECASE)
    return int(m.group(1)) if m else None

# ---------------- File Detection -----------------
def parse_file_name(filename: str):
    """
    Detect title, type, year, season, episode from filename
    """
    clean_name = filename.replace(".", " ").replace("_", " ").strip()
    # Detect year
    year_match = re.search(r"\b(19|20)\d{2}\b", clean_name)
    year = year_match.group(0) if year_match else ""
    # Detect season/episode
    s_match = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", clean_name)
    season = s_match.group(1) if s_match else None
    episode = s_match.group(2) if s_match else extract_episode_number(clean_name)
    # Detect type
    is_series = bool(s_match or re.search(r"(Season|Episode)", clean_name, re.IGNORECASE))
    # Title cleanup
    title = clean_name
    if year:
        title = title.replace(year, "")
    if season:
        title = re.sub(r"[Ss]" + season + r"[Ee]\d{1,2}", "", title)
    title = re.sub(r"\b(Season|Episode)\b", "", title, flags=re.IGNORECASE).strip()
    return title, "Series" if is_series else "Movie", year, season, episode

# ---------------- Media Handling -----------------
@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    try:
        print(f"📥 File received in DB channel: {message.chat.id}")
        media_obj = getattr(message, message.media.value, None)
        if media_obj and media_obj.mime_type in ["video/mp4", "video/x-matroska", "document/mp4"]:
            media_obj.file_type = message.media.value
            media_obj.caption = message.caption
            status = await save_file(media_obj)
            print(f"✅ File saved status: {status}")
            if status == "suc":
                await queue_movie_file(bot, media_obj)
    except Exception as e:
        print(f"❌ Error in media: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ media error: {e}")

async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        # Detect title/type/year/season/episode
        title, kind, year, season, episode = parse_file_name(file_name + " " + caption)
        season_tag = f" Season {season}" if season else ""
        group_key = (title + season_tag).strip()
        print(f"🔗 Grouping under: {group_key} | File: {file_name}")

        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = detect_languages(caption) or "Unknown"
        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        movie_files[group_key].append({
            "quality": quality,
            "jisshuquality": jisshuquality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year,
            "episode": int(episode) if episode else None
        })

        if group_key in processing_movies:
            return
        processing_movies.add(group_key)
        await asyncio.sleep(POST_DELAY)

        # ---------------- Owner Confirmation -----------------
        owner_msg = f"New upload detected:\n\nTitle: {title}\nType: {kind}\nYear: {year}\nSeason: {season}\nEpisode: {episode}\n\nDo you want to edit the title or type? Reply with 'title:new title' or 'type:Movie/Series' or 'skip'."
        sent_msg = await bot.send_message(OWNER_ID, owner_msg)

        # Wait for owner's reply (max 60s)
        try:
            response = await bot.listen(OWNER_ID, timeout=60)
            text = response.text.strip()
            if text.lower().startswith("title:"):
                title = text[6:].strip()
            elif text.lower().startswith("type:"):
                kind = text[5:].strip().title()
        except asyncio.TimeoutError:
            pass
        finally:
            await sent_msg.delete()

        if group_key in movie_files:
            await send_movie_update(bot, title, kind, movie_files[group_key])
            del movie_files[group_key]
        processing_movies.remove(group_key)

    except Exception as e:
        print(f"❌ queue_movie_file error: {e}")
        processing_movies.discard(file_name)
        await bot.send_message(LOG_CHANNEL, f"❌ queue_movie_file error: {e}")

# ---------------- Send Updates -----------------
async def send_movie_update(bot, title, kind, files):
    try:
        is_series = kind.lower() == "series"
        year = files[0]["year"]
        languages = set()
        print_types = set()
        for file in files:
            if file["language"] != "Unknown":
                languages.update(file["language"].split(", "))
            for p in PRINT_TYPES:
                if p.lower() in (file["quality"] or "").lower():
                    print_types.add(p)
        language = ", ".join(sorted(languages)) or "Unknown"
        available_in = ", ".join(sorted(print_types)) or "HDRip"

        files.sort(key=lambda x: x.get("episode") or 0)
        quality_text = ""
        if is_series:
            episode_map = defaultdict(list)
            for file in files:
                ep = file.get("episode") or 0
                q = file.get("jisshuquality") or "Unknown"
                episode_map[ep].append(q)
            for ep in sorted(episode_map.keys()):
                qualities = " | ".join(sorted(set(episode_map[ep])))
                quality_text += f"✴️ Episode {ep} : {qualities}\n"
        else:
            for file in files:
                q = file.get("jisshuquality") or "Unknown"
                size = file["file_size"]
                file_id = file["file_id"]
                quality_text += f"✴️ {q} : <a href='https://t.me/{temp.U_NAME}?start=file_0_{file_id}'>{size}</a>\n"

        poster = await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        caption = UPDATE_CAPTION.format(kind.upper(), title, year, available_in, language, quality_text)

        muc_id = await db.movies_update_channel_id() or MOVIE_UPDATE_CHANNEL
        try:
            chat = await bot.get_chat(muc_id)
            print(f"✅ Bot can access MUC: {chat.title} ({muc_id})")
        except Exception as e:
            print(f"❌ Cannot access MUC {muc_id}: {e}")
            await bot.send_message(LOG_CHANNEL, f"❌ Cannot access MUC {muc_id}: {e}")
            return

        print(f"📨 Sending update to MUC: {muc_id} | {kind}: {title} ({year}) | Files: {len(files)})")
        await bot.send_photo(
            chat_id=muc_id,
            photo=poster,
            caption=caption,
            parse_mode=enums.ParseMode.HTML
        )

    except Exception as e:
        print(f"❌ send_movie_update error: {e}")
        await bot.send_message(LOG_CHANNEL, f"❌ send_movie_update error: {e}")

# ---------------- Fetch Poster -----------------
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
    except Exception as e:
        print(f"❌ Poster fetch error: {e}")
        return None
