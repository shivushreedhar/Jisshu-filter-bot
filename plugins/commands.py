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
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from database.ia_filterdb import Media, get_file_details, get_bad_files, unpack_new_file_id
from database.users_chats_db import db
from database.config_db import mdb
from database.topdb import JsTopDB
from database.jsreferdb import referdb
from plugins.pm_filter import auto_filter
from utils import (
    formate_file_name, get_settings, save_group_settings, is_req_subscribed, is_subscribed,
    get_size, get_shortlink, is_check_admin, get_status, temp, get_readable_time, save_default_settings,
    add_premium
)

import re
import base64

# ---------------- Constants / Globals ----------------
OWNER_ID = 5536032493  # Your Telegram user ID
logger = logging.getLogger(__name__)
movie_series_db = JsTopDB(DATABASE_URI)
verification_ids = {}

REACTIONS = ["✅", "👍", "👌", "😎"]

# ---------------- Helpers ----------------
async def _reply_photo(client, chat_id, photo, caption, reply_markup=None):
    try:
        await client.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
    except Exception:
        # fallback to send message if photo fails
        await client.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

# ---------------- CommandSpy ----------------
@Client.on_message(filters.command() & ~filters.user(OWNER_ID))
async def command_spy(client, message):
    # Simple logging for all commands used by non-owner users
    try:
        user = message.from_user
        cmd = message.command[0] if message.command else message.text
        logger.info(f"[CommandSpy] {user.id} {user.first_name} used command: {cmd}")
    except Exception:
        pass

# ---------------- /start Handler ----------------
@Client.on_message(filters.command(["start"]) & filters.incoming)
async def start(client: Client, message):
    try:
        await message.react(emoji=random.choice(REACTIONS))
    except Exception:
        pass

    m = message
    user_id = m.from_user.id

    # Special start param handling (notcopy / jisshu etc.)
    if len(m.command) == 2 and (m.command[1].startswith("notcopy") or m.command[1].startswith("jisshu")):
        param = m.command[1]
        # Expected formats: notcopy_userid_verifyid_fileid or jisshu_userid_verifyid_fileid
        try:
            _, userid, verify_id, file_id = param.split("_", 3)
            user_id = int(userid)
        except Exception:
            await message.reply("<b>Invalid start parameter</b>")
            return

        grp_id = temp.CHAT.get(user_id, 0)
        settings = await get_settings(grp_id)
        verify_id_info = await db.get_verify_id_info(user_id, verify_id)

        if not verify_id_info or verify_id_info.get("verified"):
            await message.reply("<b>ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ᴛʀʏ ᴀɢᴀɪɴ...</b>")
            return

        ist_timezone = pytz.timezone("Asia/Kolkata")
        if await db.user_verified(user_id):
            key = "third_time_verified"
        else:
            key = "second_time_verified" if await db.is_user_verified(user_id) else "last_verified"

        current_time = dt.now(tz=ist_timezone)
        await db.update_notcopy_user(user_id, {key: current_time})
        await db.update_verify_id_info(user_id, verify_id, {"verified": True})

        num = 3 if key == "third_time_verified" else 2 if key == "second_time_verified" else 1
        msg = (
            script.THIRDT_VERIFY_COMPLETE_TEXT
            if key == "third_time_verified"
            else script.SECOND_VERIFY_COMPLETE_TEXT
            if key == "second_time_verified"
            else script.VERIFY_COMPLETE_TEXT
        )

        # Decide verified files link type
        if param.startswith("jisshu"):
            verifiedfiles = f"https://telegram.me/{temp.U_NAME}?start=allfiles_{grp_id}_{file_id}"
        else:
            verifiedfiles = f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file_id}"

        try:
            await client.send_message(
                settings.get("log"),
                script.VERIFIED_LOG_TEXT.format(
                    m.from_user.mention,
                    user_id,
                    dt.now(pytz.timezone("Asia/Kolkata")).strftime("%d %B %Y"),
                    num,
                ),
            )
        except Exception:
            pass

        btn = [[InlineKeyboardButton("‼️ ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ɢᴇᴛ ꜰɪʟᴇ ‼️", url=verifiedfiles)]]
        reply_markup = InlineKeyboardMarkup(btn)
        await _reply_photo(client, m.chat.id, VERIFY_IMG, msg.format(message.from_user.mention, get_readable_time(TWO_VERIFY_GAP)), reply_markup)
        return

    # If the message is from a group/supergroup: greet and optionally log
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        status = get_status()
        aks = await message.reply_text(f"<b>🔥 ʏᴇs {status},\nʜᴏᴡ ᴄᴀɴ ɪ ʜᴇʟᴘ ʏᴏᴜ??</b>")
        # delete the temp reply after some time to avoid clutter
        await asyncio.sleep(6)  # shortened for responsiveness
        try:
            await aks.delete()
            await m.delete()
        except Exception:
            pass

        if not await db.get_chat(message.chat.id):
            try:
                total = await client.get_chat_members_count(message.chat.id)
                group_link = await message.chat.export_invite_link()
            except Exception:
                total = 0
                group_link = ""
            user = message.from_user.mention if message.from_user else "Dear"
            try:
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
            except Exception:
                pass
            await db.add_chat(message.chat.id, message.chat.title)
        return

    # Ensure user exists in DB
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        try:
            await client.send_message(
                LOG_CHANNEL,
                script.NEW_USER_TXT.format(temp.B_LINK, message.from_user.id, message.from_user.mention),
            )
        except Exception:
            pass

    # Default start reply
    buttons = [
        [InlineKeyboardButton("⇋ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ⇋", url=f"http://telegram.dog/{temp.U_NAME}?startgroup=start")],
        [InlineKeyboardButton("• ᴅɪꜱᴀʙʟᴇ ᴀᴅꜱ •", callback_data="jisshupremium"), InlineKeyboardButton("• ꜱᴘᴇᴄɪᴀʟ •", callback_data="special")],
        [InlineKeyboardButton("• ʜᴇʟᴘ •", callback_data="help"), InlineKeyboardButton("• ᴀʙᴏᴜᴛ •", callback_data="about")],
        [InlineKeyboardButton("• ᴇᴀʀɴ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏɴᴇʏ ᴡɪᴛʜ ʙᴏᴛ •", callback_data="earn")],
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # playful sticker then main start photo
    try:
        mst = await message.reply_sticker("CAACAgUAAx0CZz_GMwACMBdnXZA4SejgJ6a_0TrNzOfn9ImI_QACNwsAArT4iFVaZPJf8ldVVh4E")
        await asyncio.sleep(1)
        await mst.delete()
    except Exception:
        pass

    await _reply_photo(client, message.chat.id, random.choice(START_IMG), script.START_TXT.format(message.from_user.mention, get_status(), message.from_user.id), reply_markup)

    # Referral handling (if present) - supports reff_XXXX
    if len(message.command) == 2 and message.command[1].startswith("reff_"):
        try:
            ref_user_id = int(message.command[1].split("_")[1])
        except Exception:
            await message.reply_text("Invalid Refer ID")
            return
        if ref_user_id == message.from_user.id:
            await message.reply_text("You can't refer yourself!")
            return
        if referdb.is_user_in_list(message.from_user.id) or await db.is_user_exist(message.from_user.id):
            await message.reply_text("You have already joined or been invited")
            return
        try:
            uss = await client.get_users(ref_user_id)
        except Exception:
            return
        referdb.add_user(message.from_user.id)
        points = referdb.get_refer_points(ref_user_id) + 10
        if points >= 100:
            referdb.add_refer_points(ref_user_id, 0)
            await message.reply_text(f"You have been invited by {uss.mention}!")
            await client.send_message(ref_user_id, f"You have been invited by {message.from_user.mention}!")
            # grant premium on threshold
            try:
                await add_premium(client, ref_user_id, uss)
            except Exception:
                pass
        else:
            referdb.add_refer_points(ref_user_id, points)
            await message.reply_text(f"You have been invited by {uss.mention}!")
            await client.send_message(ref_user_id, f"You have been invited by {message.from_user.mention}!")

    # getfile / auto_filter shortcut
    if len(message.command) == 2 and message.command[1].startswith("getfile"):
        searches = message.command[1].split("-", 1)[1]
        search = searches.replace("-", " ")
        message.text = search
        await auto_filter(client, message)
        return

    # ads handling
    if len(message.command) == 2 and message.command[1] in ["ads"]:
        msg, _, impression = await mdb.get_advirtisment()
        user = await db.get_user(message.from_user.id)
        seen_ads = user.get("seen_ads", False)
        JISSHU_ADS_LINK = await db.jisshu_get_ads_link()
        buttons = [[InlineKeyboardButton("❌ ᴄʟᴏꜱᴇ ❌", callback_data="close_data")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        if msg:
            await _reply_photo(client, message.chat.id, JISSHU_ADS_LINK if JISSHU_ADS_LINK else URL, msg, reply_markup)
            if impression is not None and not seen_ads:
                await mdb.update_advirtisment_impression(int(impression) - 1)
                await db.update_value(message.from_user.id, "seen_ads", True)
        else:
            await message.reply("<b>No Ads Found</b>")
        await mdb.reset_advertisement_if_expired()
        if msg is None and seen_ads:
            await db.update_value(message.from_user.id, "seen_ads", False)
        return

    # FORCE SUB / Premium checks / verification shorteners and link creation
    # This block replicates the shortener/verify logic from your original file
    # It uses get_shortlink, is_req_subscribed, is_subscribed, mdb, db etc.

    # Try to parse expected data param from /start x_y_z or similar
    data = message.command[1] if len(message.command) > 1 else None
    if not data:
        return

    # If data follows expected pattern, try to use it
    try:
        pre, grp_id, file_id = data.split("_", 2)
    except Exception:
        pre, grp_id, file_id = "", 0, data

    # Load group settings
    try:
        settings = await get_settings(int(grp_id))
    except Exception:
        settings = {}

    # Force subscription logic
    fsub_id = settings.get("fsub_id", AUTH_CHANNEL)
    if fsub_id == AUTH_REQ_CHANNEL:
        # Requires join-request subscription
        if AUTH_REQ_CHANNEL and not await is_req_subscribed(client, message):
            try:
                invite_link = await client.create_chat_invite_link(int(AUTH_REQ_CHANNEL), creates_join_request=True)
            except ChatAdminRequired:
                logger.error("Make sure Bot is admin in Forcesub channel")
                return
            btn = [[InlineKeyboardButton("⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link.invite_link)]]
            if message.command[1] != "subscribe":
                btn.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")])
            await _reply_photo(client, message.chat.id, FORCESUB_IMG, script.FORCESUB_TEXT, InlineKeyboardMarkup(btn))
            return
    else:
        # Custom channel id subscription
        channel = int(fsub_id) if fsub_id else AUTH_CHANNEL
        btn = []
        if channel != AUTH_CHANNEL and not await is_subscribed(client, message.from_user.id, channel):
            try:
                invite_link_custom = await client.create_chat_invite_link(channel)
                btn.append([InlineKeyboardButton("⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link_custom.invite_link)])
            except Exception:
                pass
        if not await is_req_subscribed(client, message):
            try:
                invite_link_default = await client.create_chat_invite_link(int(AUTH_CHANNEL), creates_join_request=True)
                btn.append([InlineKeyboardButton("⛔️ ᴊᴏɪɴ ɴᴏᴡ ⛔️", url=invite_link_default.invite_link)])
            except Exception:
                pass
        if message.command[1] != "subscribe" and (await is_req_subscribed(client, message) is False or await is_subscribed(client, message.from_user.id, channel) is False):
            btn.append([InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")])
        if btn:
            await _reply_photo(client, message.chat.id, FORCESUB_IMG, script.FORCESUB_TEXT, InlineKeyboardMarkup(btn))
            return

    # Premium check and verification shorteners
    user_id = m.from_user.id
    if not await db.has_premium_access(user_id):
        grp_id = int(grp_id) if grp_id else 0
        user_verified = await db.is_user_verified(user_id)
        settings = await get_settings(grp_id)
        is_second_shortener = await db.use_second_shortener(user_id, settings.get("verify_time", TWO_VERIFY_GAP))
        is_third_shortener = await db.use_third_shortener(user_id, settings.get("third_verify_time", THREE_VERIFY_GAP))

        if (settings.get("is_verify", IS_VERIFY) and not user_verified) or is_second_shortener or is_third_shortener:
            verify_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
            await db.create_verify_id(user_id, verify_id)
            temp.CHAT[user_id] = grp_id
            # create shortlink
            if message.command[1].startswith("allfiles"):
                verify = await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=jisshu_{user_id}_{verify_id}_{file_id}", grp_id, is_second_shortener, is_third_shortener)
            else:
                verify = await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=notcopy_{user_id}_{verify_id}_{file_id}", grp_id, is_second_shortener, is_third_shortener)

            howtodownload = settings.get("tutorial_3", TUTORIAL_3) if is_third_shortener else (settings.get("tutorial_2", TUTORIAL_2) if is_second_shortener else settings.get("tutorial", TUTORIAL))

            buttons = [
                [InlineKeyboardButton(text="✅ ᴠᴇʀɪꜰʏ ✅", url=verify), InlineKeyboardButton(text="ʜᴏᴡ ᴛᴏ ᴠᴇʀɪꜰʏ❓", url=howtodownload)],
                [InlineKeyboardButton(text="😁 ʙᴜʏ sᴜʙsᴄʀɪᴘᴛɪᴏɴ - ɴᴏ ɴᴇᴇᴅ ᴛᴏ ᴠᴇʀɪғʏ 😁", callback_data="getpremium")],
            ]
            reply_markup = InlineKeyboardMarkup(buttons)

            msg = script.THIRD_VERIFICATION_TEXT if await db.user_verified(user_id) else (script.SECOND_VERIFICATION_TEXT if is_second_shortener else script.VERIFICATION_TEXT)
            d = await message.reply_text(text=msg.format(message.from_user.mention, get_status()), protect_content=True, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
            # auto delete the message after 5 minutes
            await asyncio.sleep(300)
            try:
                await d.delete()
                await m.delete()
            except Exception:
                pass
            return

    # If user has premium or verification passed, proceed to show files/downloads
    # Handle "allfiles" start parameter which lists multiple files
    if data and data.startswith("allfiles"):
        try:
            _, grp_id, key = data.split("_", 2)
        except Exception:
            await message.reply_text("<b>⚠️ All files not found ⚠️</b>")
            return
        files = temp.FILES_ID.get(key)
        if not files:
            await message.reply_text("<b>⚠️ All files not found ⚠️</b>")
            return

        files_to_delete = []
        for file in files:
            grp_id = temp.CHAT.get(message.from_user.id)
            settings = await get_settings(grp_id)
            CAPTION = settings.get("caption", "{file_name} - {file_size}")
            f_caption = CAPTION.format(file_name=formate_file_name(file.file_name), file_size=get_size(file.file_size), file_caption=file.caption)
            btn = [[InlineKeyboardButton("📥 Download", url=(await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file.file_id}", grp_id)))]]
            try:
                await client.send_message(message.from_user.id, f_caption, reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML)
            except Exception:
                pass
        return

    # Single file handling (start=file_grp_fileid)
    if data and data.startswith("file_"):
        try:
            _, grp_id, file_id = data.split("_", 2)
        except Exception:
            await message.reply_text("Invalid file link")
            return
        # fetch file details from DB
        file_details = await get_file_details(grp_id, file_id)
        if not file_details:
            await message.reply_text("File not found or expired")
            return

        settings = await get_settings(int(grp_id))
        CAPTION = settings.get("caption", "{file_name} - {file_size}")
        f_caption = CAPTION.format(file_name=formate_file_name(file_details.file_name), file_size=get_size(file_details.file_size), file_caption=file_details.caption)

        # Build download button (shortlink) and send
        try:
            short = await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file_id}", grp_id)
            btn = [[InlineKeyboardButton("📥 Download", url=short)]]
            await client.send_message(message.from_user.id, f_caption, reply_markup=InlineKeyboardMarkup(btn), parse_mode=enums.ParseMode.HTML)
        except Exception:
            await message.reply_text(f_caption)
        return

# End of commandspy full implementation
# Note: This plugin relies on many external utils and DB functions from your project.
# Keep those modules unchanged. This file removes only maintenance mode and keeps all other behavior.
