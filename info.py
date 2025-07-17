import re
from os import environ
from Script import script

id_pattern = re.compile(r"^-?\d+$")


def is_enabled(value, default):
    if value.lower() in ["true", "yes", "1", "enable", "y"]:
        return True
    elif value.lower() in ["false", "no", "0", "disable", "n"]:
        return False
    else:
        return default


# Main Config
SESSION = environ.get("SESSION", "Media_search")
API_ID = int(environ.get("API_ID", "16073849"))
API_HASH = environ.get("API_HASH", "e84dd69cd0504b8b45b2fd6a4e19068d")
BOT_TOKEN = environ.get("BOT_TOKEN", "replace_with_your_token")
PORT = environ.get("PORT", "8082")

# Admins and Owners
ADMINS = [
    int(admin) if id_pattern.search(admin) else admin
    for admin in environ.get("ADMINS", "5536032493").split()
]
OWNER_USERNAME = environ.get("OWNER_USERNAME", "SHREESHIVA323")
USERNAME = environ.get("USERNAME", "SHREESHIVA323")

# Channels
CHANNELS = [
    int(ch) for ch in environ.get(
        "CHANNELS", "-1001714589113 -1002035953699 -1002888911184"
    ).split()
]

print(f"CHANNELS Loaded: {CHANNELS}")
print(f"Types: {[type(ch) for ch in CHANNELS]}")

AUTH_CHANNEL = int(environ.get("AUTH_CHANNEL", "-1002088921495"))
AUTH_REQ_CHANNEL = int(environ.get("AUTH_REQ_CHANNEL", "-1002668203148"))
LOG_CHANNEL = int(environ.get("LOG_CHANNEL", "-1002668203148"))
LOG_API_CHANNEL = int(environ.get("LOG_API_CHANNEL", "-1002668203148"))
LOG_VR_CHANNEL = int(environ.get("LOG_VR_CHANNEL", "-1002668203148"))

# MongoDB
DATABASE_URI = environ.get("DATABASE_URI", "mongodb+srv://replace_with_credentials")
DATABASE_NAME = environ.get("DATABASE_NAME", "Cluster0")
FILES_DATABASE = environ.get("FILES_DATABASE", DATABASE_URI)
COLLECTION_NAME = environ.get("COLLECTION_NAME", "jisshu")

# Other Channels
SUPPORT_GROUP = int(environ.get("SUPPORT_GROUP", "-1002295837366"))
DELETE_CHANNELS = int(environ.get("DELETE_CHANNELS", "0"))
request_channel = environ.get("REQUEST_CHANNEL", "")
REQUEST_CHANNEL = (
    int(request_channel)
    if request_channel and id_pattern.search(request_channel)
    else None
)
MOVIE_UPDATE_CHANNEL = int(environ.get("MOVIE_UPDATE_CHANNEL", "-1002762317286"))

SUPPORT_CHAT = environ.get("SUPPORT_CHAT", "BSHEGDE5")
MOVIE_GROUP_LINK = environ.get("MOVIE_GROUP_LINK", "BSHEGDEMOVIE")

# Verification
IS_VERIFY = is_enabled(environ.get("IS_VERIFY", "True"), True)

# Shortener APIs
SHORTENER_API = environ.get("SHORTENER_API", "")
SHORTENER_WEBSITE = environ.get("SHORTENER_WEBSITE", "")
SHORTENER_API2 = environ.get("SHORTENER_API2", SHORTENER_API)
SHORTENER_WEBSITE2 = environ.get("SHORTENER_WEBSITE2", SHORTENER_WEBSITE)
SHORTENER_API3 = environ.get("SHORTENER_API3", SHORTENER_API)
SHORTENER_WEBSITE3 = environ.get("SHORTENER_WEBSITE3", SHORTENER_WEBSITE)

# Verification Gaps
TWO_VERIFY_GAP = int(environ.get("TWO_VERIFY_GAP", "14400"))
THREE_VERIFY_GAP = int(environ.get("THREE_VERIFY_GAP", "14400"))

# Auto Delete & File Control
FILE_AUTO_DEL_TIMER = int(environ.get("FILE_AUTO_DEL_TIMER", "600"))
AUTO_FILTER = is_enabled(environ.get("AUTO_FILTER", "True"), True)
IS_PM_SEARCH = is_enabled(environ.get("IS_PM_SEARCH", "False"), False)
IS_SEND_MOVIE_UPDATE = is_enabled(environ.get("IS_SEND_MOVIE_UPDATE", "False"), False)
MAX_BTN = int(environ.get("MAX_BTN", "8"))
AUTO_DELETE = is_enabled(environ.get("AUTO_DELETE", "True"), True)
DELETE_TIME = int(environ.get("DELETE_TIME", 1200))

# IMDB/Caption Settings
IMDB = is_enabled(environ.get("IMDB", "False"), False)
FILE_CAPTION = environ.get("FILE_CAPTION", f"{script.FILE_CAPTION}")
IMDB_TEMPLATE = environ.get("IMDB_TEMPLATE", f"{script.IMDB_TEMPLATE_TXT}")
LONG_IMDB_DESCRIPTION = is_enabled(environ.get("LONG_IMDB_DESCRIPTION", "False"), False)
PROTECT_CONTENT = is_enabled(environ.get("PROTECT_CONTENT", "False"), False)
SPELL_CHECK = is_enabled(environ.get("SPELL_CHECK", "True"), True)
LINK_MODE = is_enabled(environ.get("LINK_MODE", "True"), True)
TMDB_API_KEY = environ.get("TMDB_API_KEY", "")

# Stream & Client
STREAM_MODE = bool(environ.get("STREAM_MODE", True))
MULTI_CLIENT = False
SLEEP_THRESHOLD = int(environ.get("SLEEP_THRESHOLD", "60"))
PING_INTERVAL = int(environ.get("PING_INTERVAL", "1200"))
ON_HEROKU = "DYNO" in environ
URL = environ.get("FQDN", "")

# Static Assets
START_IMG = environ.get("START_IMG", "https://telegra.ph/file/054c51d89929c773caeb3.jpg").split()
FORCESUB_IMG = environ.get("FORCESUB_IMG", "https://telegra.ph/file/054c51d89929c773caeb3.jpg")
REFER_PICS = environ.get("REFER_PICS", "https://telegra.ph/file/054c51d89929c773caeb3.jpg").split()
PAYPICS = environ.get("PAYPICS", "https://telegra.ph/file/054c51d89929c773caeb3.jpg").split()
SUBSCRIPTION = environ.get("SUBSCRIPTION", "https://telegra.ph/file/054c51d89929c773caeb3.jpg")
REACTIONS = ["👀", "😱", "🔥", "😍", "🎉", "🥰", "😇", "⚡"]
VERIFY_IMG = environ.get("VERIFY_IMG", "https://graph.org/file/1669ab9af68eaa62c3ca4.jpg")

# Languages, Qualities, Years, Seasons
LANGUAGES = [
    "hindi", "english", "telugu", "tamil", "kannada",
    "malayalam", "bengali", "marathi", "gujarati", "punjabi"
]
QUALITIES = [
    "HdRip", "web-dl", "bluray", "hdr", "fhd", "240p", "360p", "480p", "540p",
    "720p", "960p", "1080p", "1440p", "2K", "2160p", "4k", "5K", "8K"
]
YEARS = [f"{i}" for i in range(2025, 2002, -1)]
SEASONS = [f"season {i}" for i in range(1, 23)]
TUTORIAL = environ.get("TUTORIAL", "https://t.me/bshowtodownload/22")
TUTORIAL_2 = environ.get("TUTORIAL_2", "https://t.me/bshowtodownload/22")
TUTORIAL_3 = environ.get("TUTORIAL_3", "https://t.me/bshowtodownload/22")

# Commands
admin_cmds = [
    "/add_premium - Add A User To Premium",
    "/premium_users - View All Premium Users",
    "/remove_premium - Remove A User's Premium Status",
    "/add_redeem - Generate A Redeem Code",
    "/refresh - Refresh Free Trail",
    "/set_muc - Set Movie Update Channel",
    "/pm_search_on - Enable PM Search",
    "/pm_search_off - Disable PM Search",
    "/set_ads - Set Advertisements",
    "/del_ads - Delete Advertisements",
    "/setlist - Set Top Trending List",
    "/clearlist - Clear Top Trending List",
    "/verify_id - Verification Off ID",
    "/index - Index Files",
    "/send - Send Message To A User",
    "/leave - Leave A Group Or Channel",
    "/ban - Ban A User",
    "/unban - Unban A User",
    "/broadcast - Broadcast Message",
    "/grp_broadcast - Broadcast Messages To Groups",
    "/delreq - Delete Join Request",
    "/channel - List Of Database Channels",
    "/del_file - Delete A Specific File",
    "/delete - Delete A File(By Reply)",
    "/deletefiles - Delete Multiple Files",
    "/deleteall - Delete All Files",
]

cmds = [
    {"start": "Start The Bot"},
    {"most": "Get Most Searches Button List"},
    {"trend": "Get Top Trending Button List"},
    {"mostlist": "Show Most Searches List"},
    {"trendlist": "𝖦𝖾𝗍 𝖳𝗈𝗉 𝖳𝗋𝖾𝗇𝖽𝗂𝗇𝗀 𝖡𝗎𝗍𝗍𝗈𝗇 𝖫𝗂𝗌𝗍"},
    {"plan": "Check Available Premium Membership Plans"},
    {"myplan": "Check Your Current Plan"},
    {"refer": "To Refer Your Friend And Get Premium"},
    {"stats": "Check My Database"},
    {"id": "Get Telegram Id"},
    {"font": "To Generate Cool Fonts"},
    {"details": "Check Group Details"},
    {"settings": "Change Bot Setting"},
    {"grp_cmds": "Check Group Commands"},
    {"admin_cmds": "Bot Admin Commands"},
]
