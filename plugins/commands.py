import os
import requests
import logging
import random
import asyncio
import string
import pytz
from datetime import datetime as dt
from Script import script
from pyrogram import Client, filters, enums
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from database.ia_filterdb import (
    Media,
    get_file_details,
    get_bad_files,
    unpack_new_file_id,
)
from database.users_chats_db import db
from database.config_db import mdb
from database.topdb import JsTopDB
from database.jsreferdb import referdb
from plugins.pm_filter import auto_filter
from utils import (
    formate_file_name,
    get_settings,
    save_group_settings,
    is_req_subscribed,
    is_subscribed,
    get_size,
    get_shortlink,
    is_check_admin,
    get_status,
    temp,
    get_readable_time,
    save_default_settings,
)
import re
import base64
from info import *

logger = logging.getLogger(__name__)
movie_series_db = JsTopDB(DATABASE_URI)
verification_ids = {}


def _parse_start_data(data: str, user_id: int):
    """Safely parse the /start payload.

    Returns (pre, grp_id:int or 0, file_id)
    """
    if not data:
        return "", 0, ""
    # Prefer explicit underscore-separated format: pre_grp_file
    if "_" in data:
        parts = data.split("_", 2)
        if len(parts) == 3:
            pre, grp_raw, file_id = parts
            try:
                grp_id = int(grp_raw)
            except Exception:
                # fallback to known chat mapping or 0
                grp_id = temp.CHAT.get(user_id, 0)
            return pre, grp_id, file_id
    # fallback: treat whole data as file_id and try to get group from temp.CHAT
    grp_id = temp.CHAT.get(user_id, 0)
    return "", grp_id, data


@Client.on_message(filters.command("start") & filters.incoming)
async def start(client: Client, message):
    await message.react(emoji=random.choice(REACTIONS))
    m = message
    user_id = m.from_user.id

    # handle /start with notcopy/jisshu verification tokens
    if len(m.command) == 2 and m.command[1].startswith("notcopy"):
        _, userid, verify_id, file_id = m.command[1].split("_", 3)
        user_id = int(userid)
        grp_id = temp.CHAT.get(user_id, 0)
        settings = await get_settings(grp_id)
        verify_id_info = await db.get_verify_id_info(user_id, verify_id)
        if not verify_id_info or verify_id_info["verified"]:
            await message.reply("<b>ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ᴛʀʏ ᴀɢᴀɪɴ...</b>")
            return
        ist_timezone = pytz.timezone("Asia/Kolkata")
        if await db.user_verified(user_id):
            key = "third_time_verified"
        else:
            key = (
                "second_time_verified"
                if await db.is_user_verified(user_id)
                else "last_verified"
            )
        current_time = dt.now(tz=ist_timezone)
        result = await db.update_notcopy_user(user_id, {key: current_time})
        await db.update_verify_id_info(user_id, verify_id, {"verified": True})
        if key == "third_time_verified":
            num = 3
        else:
            num = 2 if key == "second_time_verified" else 1
        if key == "third_time_verified":
            msg = script.THIRDT_VERIFY_COMPLETE_TEXT
        else:
            msg = (
                script.SECOND_VERIFY_COMPLETE_TEXT
                if key == "second_time_verified"
                else script.VERIFY_COMPLETE_TEXT
            )
        if message.command[1].startswith("jisshu"):
            verifiedfiles = (
                f"https://telegram.me/{temp.U_NAME}?start=allfiles_{grp_id}_{file_id}"
            )
        else:
            verifiedfiles = (
                f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file_id}"
            )
        await client.send_message(
            settings["log"],
            script.VERIFIED_LOG_TEXT.format(
                m.from_user.mention,
                user_id,
                dt.now(pytz.timezone("Asia/Kolkata")).strftime("%d %B %Y"),
                num,
            ),
        )
        btn = [
            [
                InlineKeyboardButton("‼️ ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ɢᴇᴛ ꜰɪʟᴇ ‼️", url=verifiedfiles),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(btn)
        await m.reply_photo(
            photo=(VERIFY_IMG),
            caption=msg.format(
                message.from_user.mention, get_readable_time(TWO_VERIFY_GAP)
            ),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
        return

    # If invoked in groups, show a short reply and auto-delete (keeps original behavior)
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        status = get_status()
        aks = await message.reply_text(f"<b>🔥 ʏᴇs {status},\nʜᴏᴡ ᴄᴀɴ ɪ ʜᴇʟᴘ ʏᴏᴜ??</b>")
        await asyncio.sleep(600)
        try:
            await aks.delete()
            await m.delete()
        except Exception:
            pass
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            try:
                group_link = await message.chat.export_invite_link()
            except Exception:
                group_link = ""
            user = message.from_user.mention if message.from_user else "Dear"
            await client.send_message(
                LOG_CHANNEL,
                script.NEW_GROUP_TXT.format(
                    temp.B_LINK,
                    message.chat.title,
                    message.chat.id,
                    message.chat.username,
                    group_link,
                    total,
                    user,
                ),
            )
            await db.add_chat(message.chat.id, message.chat.title)
        return

    # New user handling
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(
            LOG_CHANNEL,
            script.NEW_USER_TXT.format(
                temp.B_LINK, message.from_user.id, message.from_user.mention
            ),
        )

    # Normal /start with no payload - show main menu
    if len(message.command) != 2:
        buttons = [
            [
                InlineKeyboardButton(
                    "⇋ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ⇋",
                    url=f"http://telegram.dog/{temp.U_NAME}?startgroup=start",
                )
            ],
            [
                InlineKeyboardButton("• ᴅɪꜱᴀʙʟᴇ ᴀᴅꜱ •", callback_data="jisshupremium"),
                InlineKeyboardButton("• ꜱᴘᴇᴄɪᴀʟ •", callback_data="special"),
            ],
            [
                InlineKeyboardButton("• ʜᴇʟᴘ •", callback_data="help"),
                InlineKeyboardButton("• ᴀʙᴏᴜᴛ •", callback_data="about"),
            ],
            [
                InlineKeyboardButton(
                    "• ᴇᴀʀɴ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏɴᴇʏ ᴡɪᴛʜ ʙᴏᴛ •", callback_data="earn"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        m = await message.reply_sticker(
            "CAACAgUAAx0CZz_GMwACMBdnXZA4SejgJ6a_0TrNzOfn9ImI_QACNwsAArT4iFVaZPJf8ldVVh4E"
        )
        await asyncio.sleep(1)
        await m.delete()
        await message.reply_photo(
            photo=random.choice(START_IMG),
            caption=script.START_TXT.format(
                message.from_user.mention, get_status(), message.from_user.id
            ),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )
        return

    # Quick simple payload responses
    if len(message.command) == 2 and message.command[1] in [
        "subscribe",
        "error",
        "okay",
        "help",
    ]:
        buttons = [
            [
                InlineKeyboardButton(
                    "⇋ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ⇋",
                    url=f"http://telegram.dog/{temp.U_NAME}?startgroup=start",
                )
            ],
            [
                InlineKeyboardButton("• ᴅɪꜱᴀʙʟᴇ ᴀᴅꜱ •", callback_data="jisshupremium"),
                InlineKeyboardButton("• ꜱᴘᴇᴄɪᴀʟ •", callback_data="special"),
            ],
            [
                InlineKeyboardButton("• ʜᴇʟᴘ •", callback_data="help"),
                InlineKeyboardButton("• ᴀʙᴏᴜᴛ •", callback_data="about"),
            ],
            [
                InlineKeyboardButton(
                    "• ᴇᴀʀɴ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏɴᴇʏ ᴡɪᴛʜ ʙᴏᴛ •", callback_data="earn"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        return await message.reply_photo(
            photo=START_IMG,
            caption=script.START_TXT.format(
                message.from_user.mention, get_status(), message.from_user.id
            ),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
        )

    if len(message.command) == 2 and message.command[1].startswith("reff_"):
        try:
            user_id = int(message.command[1].split("_")[1])
        except ValueError:
            await message.reply_text("𝖨𝗇𝗏𝖺𝗅𝗂𝖽 𝖱𝖾𝖿𝖾𝗋⁉️")
            return
        if user_id == message.from_user.id:
            await message.reply_text("𝖧𝖾𝗒 𝖣𝗎𝖽𝖾 𝖸𝗈𝗎 𝖢𝖺𝗇'𝗍 𝖱𝖾𝖿𝖾𝗋 𝖸𝗈𝗎𝗋𝗌𝖾𝗅𝖿⁉️")
            return
        if referdb.is_user_in_list(message.from_user.id):
            await message.reply_text("‼️ 𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖠𝗅𝗅𝗋𝖾𝖺𝖽𝗒 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝗈𝗋 𝖩𝗈𝗂𝗇𝖾𝗱")
            return
        if await db.is_user_exist(message.from_user.id):
            await message.reply_text("‼️ 𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖠𝗅𝗅𝗋𝖾𝖺𝖽𝗒 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝗈𝗋 𝖩𝗈𝗂𝗇𝖾𝗱")
            return
        try:
            uss = await client.get_users(user_id)
        except Exception:
            return
        referdb.add_user(message.from_user.id)
        fromuse = referdb.get_refer_points(user_id) + 10
        if fromuse == 100:
            referdb.add_refer_points(user_id, 0)
            await message.reply_text(f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝖡𝗒 {uss.mention}!")
            await client.send_message(
                user_id, text=f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝖡𝗒 {message.from_user.mention}!"
            )
            await add_premium(client, user_id, uss)
        else:
            referdb.add_refer_points(user_id, fromuse)
            await message.reply_text(f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖡𝖾𝖾𝗇 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 𝖡𝗒 {uss.mention}!")
            await client.send_message(
                user_id, f"𝖸𝗈𝗎 𝖧𝖺𝗏𝖾 𝖨𝗇𝗏𝗂𝗍𝖾𝖽 {message.from_user.mention}!"
            )
        return

    if len(message.command) == 2 and message.command[1].startswith("getfile"):
        searches = message.command[1].split("-", 1)[1]
        search = searches.replace("-", " ")
        message.text = search
        await auto_filter(client, message)
        return

    if len(message.command) == 2 and message.command[1] in ["ads"]:
        msg, _, impression = await mdb.get_advirtisment()
        user = await db.get_user(message.from_user.id)
        seen_ads = user.get("seen_ads", False)
        JISSHU_ADS_LINK = await db.jisshu_get_ads_link()
        buttons = [[InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ ❌", callback_data="close_data")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        if msg:
            await message.reply_photo(
                photo=JISSHU_ADS_LINK if JISSHU_ADS_LINK else URL,
                caption=msg,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            if impression is not None and not seen_ads:
                await mdb.update_advirtisment_impression(int(impression) - 1)
                await db.update_value(message.from_user.id, "seen_ads", True)
        else:
            await message.reply("<b>No Ads Found</b>")
        await mdb.reset_advertisement_if_expired()
        if msg is None and seen_ads:
            await db.update_value(message.from_user.id, "seen_ads", False)
        return

    # --- SAFE parsing of start payload ---
    data = message.command[1]
    pre, grp_id, file_id = _parse_start_data(data, user_id)
    logger.debug(f"Start payload parsed: pre={pre} grp_id={grp_id} file_id={file_id}")

    settings = await get_settings(int(grp_id))

    # Force-subscribe checks (unchanged logic)
    if settings.get("fsub_id", AUTH_CHANNEL) == AUTH_REQ_CHANNEL:
        if AUTH_REQ_CHANNEL and not await is_req_subscribed(client, message):
            try:
                invite_link = await client.create_chat_invite_link(
                    int(AUTH_REQ_CHANNEL), creates_join_request=True
                )
            except ChatAdminRequired:
                logger.error("Make sure Bot is admin in Forcesub channel")
                return
            btn = [
                [InlineKeyboardButton("⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link.invite_link)]
            ]
            if message.command[1] != "subscribe":
                btn.append(
                    [
                        InlineKeyboardButton(
                            "♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️",
                            url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}",
                        )
                    ]
                )
            await client.send_photo(
                chat_id=message.from_user.id,
                photo=FORCESUB_IMG,
                caption=script.FORCESUB_TEXT,
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML,
            )
            return
    else:
        id = settings.get("fsub_id", AUTH_CHANNEL)
        channel = int(id)
        btn = []
        if channel != AUTH_CHANNEL and not await is_subscribed(
            client, message.from_user.id, channel
        ):
            invite_link_custom = await client.create_chat_invite_link(channel)
            btn.append(
                [
                    InlineKeyboardButton(
                        "⛔️ ᴊᴏɴ ɴᴏᴡ ⛔️", url=invite_link_custom.invite_link
                    )
                ]
            )
        if not await is_req_subscribed(client, message):
            invite_link_default = await client.create_chat_invite_link(
                int(AUTH_CHANNEL), creates_join_request=True
            )
            btn.append(
                [
                    InlineKeyboardButton(
                        "⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link_default.invite_link
                    )
                ]
            )
        if message.command[1] != "subscribe" and (
            await is_req_subscribed(client, message) is False
            or await is_subscribed(client, message.from_user.id, channel) is False
        ):
            btn.append(
                [
                    InlineKeyboardButton(
                        "♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️",
                        url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}",
                    )
                ]
            )
        if btn:
            await client.send_photo(
                chat_id=message.from_user.id,
                photo=FORCESUB_IMG,
                caption=script.FORCESUB_TEXT,
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML,
            )
            return

    user_id = m.from_user.id
    if not await db.has_premium_access(user_id):
        grp_id = int(grp_id)
        logger.debug(f"Group Id resolved: {grp_id}")
        user_verified = await db.is_user_verified(user_id)
        settings = await get_settings(grp_id)
        logger.debug(f"Id Settings - {settings}")
        is_second_shortener = await db.use_second_shortener(
            user_id, settings.get("verify_time", TWO_VERIFY_GAP)
        )
        is_third_shortener = await db.use_third_shortener(
            user_id, settings.get("third_verify_time", THREE_VERIFY_GAP)
        )
        if (
            settings.get("is_verify", IS_VERIFY)
            and not user_verified
            or is_second_shortener
            or is_third_shortener
        ):
            verify_id = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=7)
            )
            await db.create_verify_id(user_id, verify_id)
            temp.CHAT[user_id] = grp_id
            if message.command[1].startswith("allfiles"):
                verify = await get_shortlink(
                    f"https://telegram.me/{temp.U_NAME}?start=jisshu_{user_id}_{verify_id}_{file_id}",
                    grp_id,
                    is_second_shortener,
                    is_third_shortener,
                )
            else:
                verify = await get_shortlink(
                    f"https://telegram.me/{temp.U_NAME}?start=notcopy_{user_id}_{verify_id}_{file_id}",
                    grp_id,
                    is_second_shortener,
                    is_third_shortener,
                )
            if is_third_shortener:
                howtodownload = settings.get("tutorial_3", TUTORIAL_3)
            else:
                howtodownload = (
                    settings.get("tutorial_2", TUTORIAL_2)
                    if is_second_shortener
                    else settings.get("tutorial", TUTORIAL)
                )
            buttons = [
                [
                    InlineKeyboardButton(text="✅ ᴠᴇʀɪꜰʏ ✅", url=verify),
                    InlineKeyboardButton(text="ʜᴏᴡ ᴛᴏ ᴠᴇʀɪꜰʏ❓", url=howtodownload),
                ],
                [
                    InlineKeyboardButton(
                        text="😁 ʙᴜʏ sᴜʙsᴄʀɪᴘᴛɪᴏɴ - ɴᴏ ɴᴇᴇᴅ ᴛᴏ ᴠᴇʀɪғʏ 😁",
                        callback_data="getpremium",
                    ),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            if await db.user_verified(user_id):
                msg = script.THIRDT_VERIFICATION_TEXT
            else:
                msg = (
                    script.SECOND_VERIFICATION_TEXT
                    if is_second_shortener
                    else script.VERIFICATION_TEXT
                )
            d = await m.reply_text(
                text=msg.format(message.from_user.mention, get_status()),
                protect_content=True,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
            )
            await asyncio.sleep(300)
            await d.delete()
            await m.delete()
            return

    # handling allfiles payload
    if data and data.startswith("allfiles"):
        _, grp_id, key = data.split("_", 2)
        files = temp.FILES_ID.get(key)
        if not files:
            await message.reply_text("<b>⚠️ ᴀʟʟ ꜰɪʟᴇs ɴᴏᴛ ꜰᴏᴜɴᴅ ⚠️</b>")
            return
        files_to_delete = []
        for file in files:
            user_id = message.from_user.id
            grp_id = temp.CHAT.get(user_id)
            settings = await get_settings(grp_id)
            CAPTION = settings["caption"]
            f_caption = CAPTION.format(
                file_name=formate_file_name(file.file_name),
                file_size=get_size(file.file_size),
                file_caption=file.caption,
            )
            btn = [
                [
                    InlineKeyboardButton(
                        "✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f"stream#{file.file_id}"
                    )
                ]
            ]
            toDel = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file.file_id,
                caption=f_caption,
                reply_markup=InlineKeyboardMarkup(btn),
            )
            files_to_delete.append(toDel)

        delCap = "<i>ᴀʟʟ {} ꜰɪʟᴇs ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀꜰᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
            len(files_to_delete),
            (
                f"{FILE_AUTO_DEL_TIMER / 60} ᴍɪɴᴜᴛᴇs"
                if FILE_AUTO_DEL_TIMER >= 60
                else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
            ),
        )
        afterDelCap = "<i>ᴀʟʟ {} ꜰɪʟᴇs ᴀʀᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀꜰᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
            len(files_to_delete),
            (
                f"{FILE_AUTO_DEL_TIMER / 60} ᴍɪɴᴜᴛᴇs"
                if FILE_AUTO_DEL_TIMER >= 60
                else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
            ),
        )
        replyed = await message.reply(delCap)
        await asyncio.sleep(FILE_AUTO_DEL_TIMER)
        for file in files_to_delete:
            try:
                await file.delete()
            except:
                pass
        return await replyed.edit(
            afterDelCap,
        )

    if not data:
        return

    files_ = await get_file_details(file_id)
    if not files_:
        pre, file_id = (
            (base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")
        ).split("_", 1)
        return await message.reply("<b>⚠️ ᴀʟʟ ꜰɪʟᴇs ɴᴏᴛ ꜰᴏᴜɴᴅ ⚠️</b>")
    files = files_[0]
    settings = await get_settings(grp_id)
    CAPTION = settings["caption"]
    f_caption = CAPTION.format(
        file_name=formate_file_name(files.file_name),
        file_size=get_size(files.file_size),
        file_caption=files.caption,
    )
    btn = [
        [
            InlineKeyboardButton(
                "✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f"stream#{file_id}"
            )
        ]
    ]
    toDel = await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        reply_markup=InlineKeyboardMarkup(btn),
    )
    delCap = "<i>ʏᴏᴜʀ ꜰɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀғᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
        f"{FILE_AUTO_DEL_TIMER / 60} ᴍɪɴᴜᴛᴇs"
        if FILE_AUTO_DEL_TIMER >= 60
        else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
    )
    afterDelCap = (
        "<i>ʏᴏᴜʀ ꜰɪʟᴇ ɪs ᴅᴇʟᴇᴛᴇᴅ ᴀғᴛᴇʀ {} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ᴠɪᴏʟᴀᴛɪᴏɴs!</i>".format(
            f"{FILE_AUTO_DEL_TIMER / 60} ᴍɪɴᴜᴛᴇs"
            if FILE_AUTO_DEL_TIMER >= 60
            else f"{FILE_AUTO_DEL_TIMER} sᴇᴄᴏɴᴅs"
        )
    )
    replyed = await message.reply(delCap, reply_to_message_id=toDel.id)
    await asyncio.sleep(FILE_AUTO_DEL_TIMER)
    await toDel.delete()
    return await replyed.edit(afterDelCap)


@Client.on_message(filters.command("delete"))
async def delete(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply("ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ... 😑")
        return
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("ᴘʀᴏᴄᴇssɪɴɢ...⏳", quote=True)
    else:
        await message.reply(
            "Reply to file with /delete which you want to delete", quote=True
        )
        return
    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit("<b>ᴛʜɪs ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ꜰɪʟᴇ ꜰᴏʀᴍᴀᴛ</b>")
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)
    result = await Media.collection.delete_one(
        {
            "_id": file_id,
        }
    )
    if result.deleted_count:
        await msg.edit("<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>")
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many(
            {
                "file_name": file_name,
                "file_size": media.file_size,
                "mime_type": media.mime_type,
            }
        )
        if result.deleted_count:
            await msg.edit("<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>")
        else:
            result = await Media.collection.delete_many(
                {
                    "file_name": media.file_name,
                    "file_size": media.file_size,
                    "mime_type": media.mime_type,
                }
            )
            if result.deleted_count:
                await msg.edit("<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>")
            else:
                await msg.edit("<b>ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ</b>")

# ... remaining handlers unchanged ...
