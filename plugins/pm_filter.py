import urllib.parse
import asyncio
import logging
import pytz
import re, time
import ast
import math
import string
import random
from datetime import datetime, timedelta
from pyrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from Script import script
import pyrogram
from info import (
    MAX_BTN, BIN_CHANNEL, USERNAME, URL, ADMINS, LANGUAGES, AUTH_CHANNEL, SUPPORT_GROUP, IMDB, 
    IMDB_TEMPLATE, LOG_CHANNEL, LOG_VR_CHANNEL, TUTORIAL, FILE_CAPTION, SHORTENER_WEBSITE, 
    SHORTENER_API, SHORTENER_WEBSITE2, SHORTENER_API2, IS_PM_SEARCH, QR_CODE, DELETE_TIME, 
    REFERRAL_TARGET
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, ChatPermissions
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified, PeerIdInvalid, ChatAdminRequired
from utils import temp, get_settings, is_check_admin, get_status, get_hash, get_name, get_size, save_group_settings, get_poster, get_readable_time
from database.users_chats_db import db
from database.ia_filterdb import Media, get_search_results, get_bad_files, get_file_details, get_available_qualities, get_available_years

lock = asyncio.Lock()
logger = logging.getLogger(__name__)

BUTTONS = {}
FILES_ID = {}
CAP = {}

# --- STATE MANAGEMENT ---
temp.FSUB_WAITING = {} 
temp.SHORTENER_WAITING = {}

# -------------------------------------------------------------------------------------
# 1. SHORTENER INPUT LISTENER (Handles Website & API Key Input)
# -------------------------------------------------------------------------------------
@Client.on_message(filters.private & filters.text & filters.incoming, group=-2)
async def shortener_input_handler(client, message):
    user_id = message.from_user.id
    if user_id in temp.SHORTENER_WAITING:
        data = temp.SHORTENER_WAITING[user_id]
        grp_id = data['grp_id']
        slot = data['slot'] # 'slot1', 'slot2', 'slot3'
        
        text = message.text.strip()
        
        # Validation (Domain API)
        if len(text.split()) < 2:
            await message.reply_text("⚠️ <b>Invalid Format!</b>\n\nSend format: `website.com API_KEY`\nExample: `tnshort.net 12345abcdef`\n\nTry again or click Cancel button above.")
            message.stop_propagation()
            return
            
        domain, api_key = text.split(" ", 1)
        
        # Save based on slot
        if slot == 'slot1':
            await save_group_settings(grp_id, 'shortner', domain)
            await save_group_settings(grp_id, 'api', api_key)
        elif slot == 'slot2':
            await save_group_settings(grp_id, 'shortner_two', domain)
            await save_group_settings(grp_id, 'api_two', api_key)
        elif slot == 'slot3':
            await save_group_settings(grp_id, 'shortner_three', domain)
            await save_group_settings(grp_id, 'api_three', api_key)
            
        await message.reply_text(
            f"✅ <b>{slot.title()} Configured Successfully!</b>\n\nDomain: `{domain}`\nAPI: `{api_key}`\n\n<i>Click below to return.</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Configuration", callback_data=f"conf_short#{grp_id}")]])
        )
        
        del temp.SHORTENER_WAITING[user_id]
        message.stop_propagation()

# -------------------------------------------------------------------------------------
# 2. FSUB INPUT LISTENER (Handles Channel ID Input)
# -------------------------------------------------------------------------------------
@Client.on_message(filters.private & filters.text & filters.incoming, group=-1)
async def fsub_input_handler(client, message):
    user_id = message.from_user.id
    if user_id in temp.FSUB_WAITING:
        # Data nikalo
        data = temp.FSUB_WAITING[user_id]
        grp_id = data['grp_id']
        slot_key = data['slot']
        
        chat_id_text = message.text
        
        # Validation
        if not (chat_id_text.startswith("-100") and chat_id_text[1:].isdigit()):
            await message.reply_text("⚠️ <b>Invalid Channel ID format!</b>\nId must start with `-100`.\nExample: `-1001234567890`\n\nTry again or click Cancel button above.")
            message.stop_propagation()
            return
        
        channel_id = int(chat_id_text)
        
        # Bot admin check
        try:
            chat_member = await client.get_chat_member(channel_id, "me")
            if chat_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
                await message.reply_text("⚠️ <b>I am not an Admin in that channel!</b>\nPlease make me admin and try again.")
                message.stop_propagation()
                return
        except Exception as e:
            await message.reply_text(f"⚠️ <b>Error:</b> I cannot access that channel.\nMake sure I am added there.\nError: `{e}`")
            message.stop_propagation()
            return

        # Save to DB
        await save_group_settings(grp_id, slot_key, channel_id)
        
        # Readable Name Logic
        if slot_key == "fsub_id_3":
             slot_name = "Normal Fsub Slot 3"
        elif slot_key == "fsub_id_1":
             slot_name = "Request Fsub Slot 1"
        elif slot_key == "fsub_id_2":
             slot_name = "Request Fsub Slot 2"
        elif slot_key == "fsub_id_4":
             slot_name = "Request Fsub Slot 4"
        else:
             slot_name = slot_key.replace("fsub_id_", "Slot ")

        # --- SUCCESS MESSAGE + MENU ---
        text = (
            f"✅ <b>{slot_name} has been set for chat {grp_id}.</b>\n\n"
            f"<b>Channel ID:</b> `{channel_id}`\n\n\n"
            "<b>📢 Force Subscribe Settings</b>\n\n"
            "Select which type of FSub you want to configure:"
        )
        
        btn = [
            [InlineKeyboardButton("Request Fsub (Auth 1, 2, 4)", callback_data=f"req_fsub_menu#{grp_id}")],
            [InlineKeyboardButton("Normal Fsub (Auth 3)", callback_data=f"norm_fsub_menu#{grp_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"open_settings#{grp_id}")]
        ]

        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(btn))
        
        # Clear state
        del temp.FSUB_WAITING[user_id]
        
        # Stop propagation
        message.stop_propagation()

# -------------------------------------------------------------------------------------
# MAIN SEARCH HANDLERS
# -------------------------------------------------------------------------------------

@Client.on_message(filters.private & filters.text & filters.incoming & ~filters.regex(r"^/"))
async def pm_search(client, message):
    if IS_PM_SEARCH:
        if 'hindi' in message.text.lower() or 'tamil' in message.text.lower() or 'telugu' in message.text.lower() or 'malayalam' in message.text.lower() or 'kannada' in message.text.lower() or 'english' in message.text.lower() or 'gujarati' in message.text.lower(): 
            return await auto_filter(client, message)
        await auto_filter(client, message)
    else:
        await message.reply_text("<b>⚠️ ꜱᴏʀʀʏ ɪ ᴄᴀɴ'ᴛ ᴡᴏʀᴋ ɪɴ ᴘᴍ</b>")
    
@Client.on_message(filters.group & filters.text & filters.incoming & ~filters.regex(r"^/"))
async def group_search(client, message):
    user_id = message.from_user.id if message.from_user else None
    chat_id = message.chat.id
    settings = await get_settings(chat_id)
    if settings["auto_filter"]:
        if not user_id:
            await message.reply("<b>🚨 ɪ'ᴍ ɴᴏᴛ ᴡᴏʀᴋɪɴɢ ғᴏʀ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪɴ!</b>")
            return
        
        if 'hindi' in message.text.lower() or 'tamil' in message.text.lower() or 'telugu' in message.text.lower() or 'malayalam' in message.text.lower() or 'kannada' in message.text.lower() or 'english' in message.text.lower() or 'gujarati' in message.text.lower(): 
            return await auto_filter(client, message)

        if message.text.startswith("/"):
            return
        
        elif re.findall(r'https?://\S+|www\.\S+|t\.me/\S+', message.text):
            if await is_check_admin(client, message.chat.id, message.from_user.id):
                return
            await message.delete()
            return await message.reply('<b>‼️ ᴡʜʏ ʏᴏᴜ ꜱᴇɴᴅ ʜᴇʀᴇ ʟɪɴᴋ\nʟɪɴᴋ ɴᴏᴛ ᴀʟʟᴏᴡᴇᴅ ʜᴇʀᴇ 🚫</b>')

        elif '@admin' in message.text.lower() or '@admins' in message.text.lower():
            if await is_check_admin(client, message.chat.id, message.from_user.id):
                return
            admins = []
            async for member in client.get_chat_members(chat_id=message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
                if not member.user.is_bot:
                    admins.append(member.user.id)
                    if member.status == enums.ChatMemberStatus.OWNER:
                        if message.reply_to_message:
                            try:
                                sent_msg = await message.reply_to_message.forward(member.user.id)
                                await sent_msg.reply_text(f"#Attention\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n★ <a href={message.reply_to_message.link}>Go to message</a>", disable_web_page_preview=True)
                            except:
                                pass
                        else:
                            try:
                                sent_msg = await message.forward(member.user.id)
                                await sent_msg.reply_text(f"#Attention\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n★ <a href={message.link}>Go to message</a>", disable_web_page_preview=True)
                            except:
                                pass
            hidden_mentions = (f'[\u2064](tg://user?id={user_id})' for user_id in admins)
            await message.reply_text('<code>Report sent</code>' + ''.join(hidden_mentions))
            return
        else:
            await auto_filter(client, message)   
    else:
        k=await message.reply_text('<b>⚠️ ᴀᴜᴛᴏ ғɪʟᴛᴇʀ ᴍᴏᴅᴇ ɪꜱ ᴏғғ...</b>')
        await asyncio.sleep(10)
        await k.delete()
        try:
            await message.delete()
        except:
            pass

# ... (Rest of the Search/Callback functions like next_page, languages, etc. remain same) ...
# ... COPY PASTING EXISTING SEARCH LOGIC HERE ...

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    ident, req, key, offset = query.data.split("_")
    if int(req) not in [query.from_user.id, 0]:
        return await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    try: offset = int(offset)
    except: offset = 0
    search = BUTTONS.get(key)
    cap = CAP.get(key)
    if not search:
        await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name),show_alert=True)
        return
    files, n_offset, total = await get_search_results(search, offset=offset)
    try: n_offset = int(n_offset)
    except: n_offset = 0
    if not files: return
    temp.FILES_ID[key] = files
    batch_ids = files
    temp.FILES_ID[f"{query.message.chat.id}-{query.id}"] = batch_ids
    batch_link = f"batchfiles#{query.message.chat.id}#{query.id}#{query.from_user.id}"
    settings = await get_settings(query.message.chat.id)
    reqnxt  = query.from_user.id if query.from_user else 0
    temp.CHAT[query.from_user.id] = query.message.chat.id
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code>...</b>" if settings["auto_delete"] else ''
    links = ""
    if settings["link"]:
        btn = []
        for file_num, file in enumerate(files, start=offset+1):
            links += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}>[{get_size(file.file_size)}] {' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@') and not x.startswith('www.'), file.file_name.split()))}</a></b>"""
    else:
        btn = [[InlineKeyboardButton(text=f"🔗 {get_size(file.file_size)}≽ {get_name(file.file_name)}", url=f'https://telegram.dog/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}'),]
                for file in files]
    btn.insert(0,[InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=batch_link),InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium"),InlineKeyboardButton("📰 ʟᴀɴɢᴜᴀɢᴇs", callback_data=f"languages#{key}#{offset}#{req}")])
    filter_buttons = []
    available_qualities = await get_available_qualities(search)
    if len(available_qualities) > 1: filter_buttons.append(InlineKeyboardButton("🎞️ Qᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}#{offset}#{req}"))
    available_years = await get_available_years(search)
    if len(available_years) > 1: filter_buttons.append(InlineKeyboardButton("📅 Yᴇᴀʀ", callback_data=f"years#{key}#{offset}#{req}"))
    if filter_buttons: btn.append(filter_buttons)
    btn.append([InlineKeyboardButton("💰 ʀᴇꜰᴇʀ & ᴇᴀʀɴ 💰", url=f"https://t.me/{temp.U_NAME}?start=get_referral_{query.message.chat.id}")])
    btn.append([InlineKeyboardButton("🤔 ʜᴏᴡ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ 🤔", url=settings['tutorial'])])

    if 0 < offset <= int(MAX_BTN): off_set = 0
    elif offset == 0: off_set = None
    else: off_set = offset - int(MAX_BTN)
    if n_offset == 0:
        btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"), InlineKeyboardButton(f"ᴘᴀɢᴇ {math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages")])
    elif off_set is None:
        btn.append([InlineKeyboardButton(f"{math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"next_{req}_{key}_{n_offset}")])
    else:
        btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"), InlineKeyboardButton(f"{math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"next_{req}_{key}_{n_offset}")])
    
    if settings["link"]:
        await query.message.edit_text(cap + links + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
        return        
    try: await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified: pass
    await query.answer()

@Client.on_callback_query(filters.regex(r"^languages#"))
async def languages_cb_handler(client: Client, query: CallbackQuery):
    _, key, offset, req = query.data.split("#")
    if int(req) != query.from_user.id: return await query.answer(script.ALRT_TXT, show_alert=True)
    if query.message.chat.type == enums.ChatType.PRIVATE: return await query.answer('ᴛʜɪs ʙᴜᴛᴛᴏɴ ᴏɴʟʏ ᴡᴏʀᴋ ɪɴ ɢʀᴏᴜᴘ', show_alert=True)
    btn = [[InlineKeyboardButton(text=lang.title(), callback_data=f"lang_search#{lang.lower()}#{key}#0#{offset}#{req}"),] for lang in LANGUAGES]
    btn.append([InlineKeyboardButton(text="⪻ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ", callback_data=f"next_{req}_{key}_{offset}")])
    d = await query.message.edit_text("<b>ɪɴ ᴡʜɪᴄʜ ʟᴀɴɢᴜᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ, ᴄʜᴏᴏsᴇ ʜᴇʀᴇ 👇</b>", reply_markup=InlineKeyboardMarkup(btn))
    await asyncio.sleep(600)
    try: await d.delete()
    except: pass

@Client.on_callback_query(filters.regex(r"^lang_search#"))
async def lang_search(client: Client, query: CallbackQuery):
    _, lang, key, offset, orginal_offset, req = query.data.split("#")
    if int(req) != query.from_user.id: return await query.answer(script.ALRT_TXT, show_alert=True)	
    offset = int(offset)
    search = BUTTONS.get(key)
    cap = CAP.get(key)
    if not search: return await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name),show_alert=True)
    search = search.replace("_", " ")
    files, n_offset, total = await get_search_results(f"{search} {lang}", max_results=int(MAX_BTN), offset=offset)
    try: n_offset = int(n_offset)
    except: n_offset = 0
    files = [file for file in files if re.search(lang, file.file_name, re.IGNORECASE)]
    if not files:
        await query.answer(f"sᴏʀʀʏ '{lang.title()}' ʟᴀɴɢᴜᴀɢᴇ ꜰɪʟᴇs ɴᴏᴛ ꜰᴏᴜɴᴅ 😕", show_alert=1)
        return
    batch_ids = files
    temp.FILES_ID[f"{query.message.chat.id}-{query.id}"] = batch_ids
    batch_link = f"batchfiles#{query.message.chat.id}#{query.id}#{query.from_user.id}"
    reqnxt = query.from_user.id if query.from_user else 0
    settings = await get_settings(query.message.chat.id)
    temp.CHAT[query.from_user.id] = query.message.chat.id
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code>...</b>" if settings["auto_delete"] else ''
    links = ""
    if settings["link"]:
        btn = []
        for file_num, file in enumerate(files, start=offset+1):
            links += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}>[{get_size(file.file_size)}] {' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@') and not x.startswith('www.'), file.file_name.split()))}</a></b>"""
    else:
        btn = [[InlineKeyboardButton(text=f"🔗 {get_size(file.file_size)}≽ {get_name(file.file_name)}", callback_data=f'files#{reqnxt}#{file.file_id}'),] for file in files]
    btn.insert(0, [InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ ♻️", callback_data=batch_link), InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium")])
    if n_offset== '':
        btn.append([InlineKeyboardButton(text="🚸 ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs 🚸", callback_data="buttons")])
    elif n_offset == 0:
        btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"lang_search#{lang}#{key}#{offset- int(MAX_BTN)}#{orginal_offset}#{req}"), InlineKeyboardButton(f"{math.ceil(offset / int(MAX_BTN)) + 1}/{math.ceil(total / int(MAX_BTN))}", callback_data="pages",)])
    elif offset==0:
        btn.append([InlineKeyboardButton(f"{math.ceil(offset / int(MAX_BTN)) + 1}/{math.ceil(total / int(MAX_BTN))}",callback_data="pages",), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"lang_search#{lang}#{key}#{n_offset}#{orginal_offset}#{req}"),])
    else:
        btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"lang_search#{lang}#{key}#{offset- int(MAX_BTN)}#{orginal_offset}#{req}"), InlineKeyboardButton(f"{math.ceil(offset / int(MAX_BTN)) + 1}/{math.ceil(total / int(MAX_BTN))}", callback_data="pages",), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"lang_search#{lang}#{key}#{n_offset}#{orginal_offset}#{req}"),])
    btn.append([InlineKeyboardButton(text="⪻ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ", callback_data=f"next_{req}_{key}_{orginal_offset}"),])
    await query.message.edit_text(cap + links + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))

@Client.on_callback_query(filters.regex(r"^qualities#"))
async def quality_filter_cb_handler(client: Client, query: CallbackQuery):
    try: _, key, offset, req = query.data.split("#")
    except: return await query.answer("Error processing quality filter.", show_alert=True)
    if int(req) != query.from_user.id: return await query.answer(script.ALRT_TXT, show_alert=True)
    search = BUTTONS.get(key)
    if not search: return await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    available_qualities = await get_available_qualities(search)
    if not available_qualities or len(available_qualities) < 2: return await query.answer("No other qualities found.", show_alert=True)
    buttons = []
    for quality in available_qualities:
        buttons.append([InlineKeyboardButton(text=quality, callback_data=f"quality_set#{quality}#{key}#0#{offset}#{req}")])
    buttons.append([InlineKeyboardButton(text="⪻ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ", callback_data=f"next_{req}_{key}_{offset}")])
    await query.message.edit_text("<b>Select a quality to filter results:</b>", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^quality_set#"))
async def set_quality_cb_handler(client: Client, query: CallbackQuery):
    try: _, quality, key, offset, original_offset, req = query.data.split("#")
    except: return await query.answer("Error processing quality selection.", show_alert=True)
    if int(req) != query.from_user.id: return await query.answer(script.ALRT_TXT, show_alert=True)
    offset = int(offset)
    search = BUTTONS.get(key)
    if not search: return await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    files, n_offset, total = await get_search_results(search, offset=offset, quality=quality)
    try: n_offset = int(n_offset)
    except: n_offset = 0
    if not files:
        await query.answer(f"Sorry, no files found for '{quality}'!", show_alert=True)
        return
    temp.FILES_ID[key] = files
    batch_ids = files
    temp.FILES_ID[f"{query.message.chat.id}-{query.id}"] = batch_ids
    batch_link = f"batchfiles#{query.message.chat.id}#{query.id}#{query.from_user.id}"
    settings = await get_settings(query.message.chat.id)
    reqnxt  = query.from_user.id if query.from_user else 0
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code>...</b>" if settings["auto_delete"] else ''
    links = ""
    if settings["link"]:
        btn = []
        for file_num, file in enumerate(files, start=offset+1):
            links += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}>[{get_size(file.file_size)}] {' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@') and not x.startswith('www.'), file.file_name.split()))}</a></b>"""
    else:
        btn = [[InlineKeyboardButton(text=f"🔗 {get_size(file.file_size)}≽ {get_name(file.file_name)}", url=f'https://telegram.dog/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}'),] for file in files]
    btn.insert(0,[InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=batch_link),InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium"),])
    btn.append([InlineKeyboardButton("🤔 ʜᴏᴡ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ 🤔", url=settings['tutorial'])])
    if 0 < offset <= int(MAX_BTN): off_set = 0
    elif offset == 0: off_set = None
    else: off_set = offset - int(MAX_BTN)
    if n_offset == 0:
        if total > int(MAX_BTN): btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"quality_set#{quality}#{key}#{off_set}#{original_offset}#{req}"), InlineKeyboardButton(f"ᴘᴀɢᴇ {math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages")])
    elif off_set is None: btn.append([InlineKeyboardButton(f"{math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"quality_set#{quality}#{key}#{n_offset}#{original_offset}#{req}")])
    else: btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"quality_set#{quality}#{key}#{off_set}#{original_offset}#{req}"), InlineKeyboardButton(f"{math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"quality_set#{quality}#{key}#{n_offset}#{original_offset}#{req}")])
    btn.append([InlineKeyboardButton(text="⪻ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ", callback_data=f"next_{req}_{key}_{original_offset}")])
    quality_cap = f"<b>📂 Results for {search} (Filtered by: {quality})</b>"
    CAP[key] = quality_cap 
    if settings["link"]: await query.message.edit_text(quality_cap + links + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
    else: await query.message.edit_text(quality_cap + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
    await query.answer()

@Client.on_callback_query(filters.regex(r"^years#"))
async def years_cb_handler(client: Client, query: CallbackQuery):
    try: _, key, offset, req = query.data.split("#")
    except: return await query.answer("Error processing year filter.", show_alert=True)
    if int(req) != query.from_user.id: return await query.answer(script.ALRT_TXT, show_alert=True)
    search = BUTTONS.get(key)
    if not search: return await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    available_years = await get_available_years(search)
    if not available_years or len(available_years) < 2: return await query.answer("No other years found.", show_alert=True)
    buttons = []
    for year in available_years:
        buttons.append([InlineKeyboardButton(text=year, callback_data=f"year_set#{year}#{key}#0#{offset}#{req}")])
    buttons.append([InlineKeyboardButton(text="⪻ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ", callback_data=f"next_{req}_{key}_{offset}")])
    await query.message.edit_text("<b>Select a year to filter results:</b>", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^year_set#"))
async def set_year_cb_handler(client: Client, query: CallbackQuery):
    try: _, year, key, offset, original_offset, req = query.data.split("#")
    except: return await query.answer("Error processing year selection.", show_alert=True)
    if int(req) != query.from_user.id: return await query.answer(script.ALRT_TXT, show_alert=True)
    offset = int(offset)
    search = BUTTONS.get(key)
    if not search: return await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name), show_alert=True)
    files, n_offset, total = await get_search_results(search, offset=offset, year=year)
    try: n_offset = int(n_offset)
    except: n_offset = 0
    if not files:
        await query.answer(f"Sorry, no files found for '{year}'!", show_alert=True)
        return
    temp.FILES_ID[key] = files
    batch_ids = files
    temp.FILES_ID[f"{query.message.chat.id}-{query.id}"] = batch_ids
    batch_link = f"batchfiles#{query.message.chat.id}#{query.id}#{query.from_user.id}"
    settings = await get_settings(query.message.chat.id)
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code>...</b>" if settings["auto_delete"] else ''
    links = ""
    if settings["link"]:
        btn = []
        for file_num, file in enumerate(files, start=offset+1):
            links += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}>[{get_size(file.file_size)}] {' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@') and not x.startswith('www.'), file.file_name.split()))}</a></b>"""
    else:
        btn = [[InlineKeyboardButton(text=f"🔗 {get_size(file.file_size)}≽ {get_name(file.file_name)}", url=f'https://telegram.dog/{temp.U_NAME}?start=file_{query.message.chat.id}_{file.file_id}'),] for file in files]
    btn.insert(0,[InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=batch_link),InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium"),])
    btn.append([InlineKeyboardButton("🤔 ʜᴏᴡ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ 🤔", url=settings['tutorial'])])
    if 0 < offset <= int(MAX_BTN): off_set = 0
    elif offset == 0: off_set = None
    else: off_set = offset - int(MAX_BTN)
    if n_offset == 0:
        if total > int(MAX_BTN): btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"year_set#{year}#{key}#{off_set}#{original_offset}#{req}"), InlineKeyboardButton(f"ᴘᴀɢᴇ {math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages")])
    elif off_set is None: btn.append([InlineKeyboardButton(f"{math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"year_set#{year}#{key}#{n_offset}#{original_offset}#{req}")])
    else: btn.append([InlineKeyboardButton("⪻ ʙᴀᴄᴋ", callback_data=f"year_set#{year}#{key}#{off_set}#{original_offset}#{req}"), InlineKeyboardButton(f"{math.ceil(int(offset) / int(MAX_BTN)) + 1} / {math.ceil(total / int(MAX_BTN))}", callback_data="pages"), InlineKeyboardButton("ɴᴇxᴛ ⪼", callback_data=f"year_set#{year}#{key}#{n_offset}#{original_offset}#{req}")])
    btn.append([InlineKeyboardButton(text="⪻ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ", callback_data=f"next_{req}_{key}_{original_offset}")])
    year_cap = f"<b>📂 Results for {search} (Filtered by: {year})</b>"
    CAP[key] = year_cap 
    if settings["link"]: await query.message.edit_text(year_cap + links + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
    else: await query.message.edit_text(year_cap + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
    await query.answer()

@Client.on_callback_query(filters.regex(r"^spol"))
async def advantage_spoll_choker(bot, query):
    _, id, user = query.data.split('#')
    if int(user) != 0 and query.from_user.id != int(user): return await query.answer(script.ALRT_TXT, show_alert=True)
    movie = await get_poster(id, id=True)
    search = movie.get('title')
    await query.answer('ᴄʜᴇᴄᴋɪɴɢ ɪɴ ᴍʏ ᴅᴀᴛᴀʙᴀꜱᴇ 🌚')
    files, offset, total_results = await get_search_results(search)
    if files:
        k = (search, files, offset, total_results)
        await auto_filter(bot, query, k)
    else:
        k = await query.message.edit(script.NO_RESULT_TXT)
        await asyncio.sleep(60)
        await k.delete()
        try: await query.message.reply_to_message.delete()
        except: pass

# -------------------------------------------------------------------------------------
# CALLBACK HANDLERS (SETTINGS & MORE)
# -------------------------------------------------------------------------------------

async def filter_non_index_callbacks(_, __, query):
    return not query.data.startswith("index")            

@Client.on_callback_query(filters.create(filter_non_index_callbacks))
async def cb_handler(client: Client, query: CallbackQuery):
    if query.data == "close_data":
        try: user = query.message.reply_to_message.from_user.id
        except: user = query.from_user.id
        if int(user) != 0 and query.from_user.id != int(user): return await query.answer(script.ALRT_TXT, show_alert=True)
        await query.answer("ᴛʜᴀɴᴋs ꜰᴏʀ ᴄʟᴏsᴇ 🙈")
        await query.message.delete()
        try: await query.message.reply_to_message.delete()
        except: pass
          
    elif query.data == "delallcancel":
        userid = query.from_user.id
        chat_type = query.message.chat.type
        if chat_type == enums.ChatType.PRIVATE:
            await query.message.reply_to_message.delete()
            await query.message.delete()
        elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            grp_id = query.message.chat.id
            st = await client.get_chat_member(grp_id, userid)
            if (st.status == enums.ChatMemberStatus.OWNER) or (str(userid) in ADMINS):
                await query.message.delete()
                try: await query.message.reply_to_message.delete()
                except: pass
            else:
                await query.answer(script.ALRT_TXT.format(query.from_user.first_name), show_alert=True)    
            
    elif query.data.startswith("stream"):
        user_id = query.from_user.id
        if not await db.has_premium_access(user_id):
            d=await query.message.reply("<b>💔 ᴛʜɪꜱ ғᴇᴀᴛᴜʀᴇ ɪꜱ ᴏɴʟʏ ғᴏʀ ʙᴏᴛ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ.\n\nɪғ ʏᴏᴜ ᴡᴀɴᴛ ʙᴏᴛ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏɴ ᴛʜᴇɴ ꜱᴇɴᴅ /plan</b>")
            await asyncio.sleep(10)
            await d.delete()
            return
        file_id = query.data.split('#', 1)[1]
        AKS = await client.send_cached_media(
            chat_id=BIN_CHANNEL,
            file_id=file_id)
        online = f"https://{URL}/watch/{AKS.id}?hash={get_hash(AKS)}"
        download = f"https://{URL}/{AKS.id}?hash={get_hash(AKS)}"
        btn= [[
            InlineKeyboardButton("ᴡᴀᴛᴄʜ ᴏɴʟɪɴᴇ", url=online),
            InlineKeyboardButton("ꜰᴀsᴛ ᴅᴏᴡɴʟᴏᴀᴅ", url=download)
        ],[
            InlineKeyboardButton('❌ ᴄʟᴏsᴇ ❌', callback_data='close_data')
        ]]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(btn)
        )

    elif query.data == "buttons":
        await query.answer("ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs 😊", show_alert=True)

    elif query.data == "pages":
        await query.answer("ᴛʜɪs ɪs ᴘᴀɢᴇs ʙᴜᴛᴛᴏɴ 😅")

    elif query.data.startswith("lang_art"):
        _, lang = query.data.split("#")
        await query.answer(f"ʏᴏᴜ sᴇʟᴇᴄᴛᴇᴅ {lang.title()} ʟᴀɴɢᴜᴀɢᴇ ⚡️", show_alert=True)
  
    elif query.data == "start":
        buttons = [[
            InlineKeyboardButton('⇆ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘs ⇆', url=f'http://t.me/{temp.U_NAME}?startgroup=start')
        ],[
            InlineKeyboardButton('⚙ ꜰᴇᴀᴛᴜʀᴇs', callback_data='features'),
            InlineKeyboardButton('💸 ᴘʀᴇᴍɪᴜᴍ', callback_data='buy_premium')
        ],[
            InlineKeyboardButton('🚫 ᴇᴀʀɴ ᴍᴏɴᴇʏ ᴡɪᴛʜ ʙᴏᴛ 🚫', callback_data='earn')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
            text=script.START_TXT.format(query.from_user.mention, get_status(), query.from_user.id),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )      
    elif query.data == "features":
        buttons = [[
            InlineKeyboardButton('📸 ᴛ-ɢʀᴀᴘʜ', callback_data='telegraph'),
            InlineKeyboardButton('🆎️ ғᴏɴᴛ', callback_data='font')    
        ], [ 
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='start')
        ]] 
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(                     
            text=script.HELP_TXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    elif query.data == "earn":
        buttons = [[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='start'),
            InlineKeyboardButton('sᴜᴘᴘᴏʀᴛ', url=USERNAME)
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.message.edit_text(
             text=script.EARN_TEXT.format(temp.B_LINK),
             reply_markup=reply_markup,
             parse_mode=enums.ParseMode.HTML
         )
    elif query.data == "telegraph":
        buttons = [[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='features')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)  
        await query.message.edit_text(
            text=script.TELE_TXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    elif query.data == "font":
        buttons = [[
            InlineKeyboardButton('⋞ ʙᴀᴄᴋ', callback_data='features')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons) 
        await query.message.edit_text(
            text=script.FONT_TXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
    elif query.data == "buy_premium":
        btn = [[
            InlineKeyboardButton('📸 sᴇɴᴅ sᴄʀᴇᴇɴsʜᴏᴛ 📸', url=USERNAME)
        ],[
            InlineKeyboardButton('🗑 ᴄʟᴏsᴇ 🗑', callback_data='close_data')
        ]]
        reply_markup = InlineKeyboardMarkup(btn)
        await query.message.reply_photo(
            photo=(QR_CODE),
            caption=script.PREMIUM_TEXT,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )

    elif query.data == "all_files_delete":
        files = await Media.count_documents({})
        await query.answer('Deleting...')
        await Media.collection.drop()
        await query.message.edit_text(f"Successfully deleted {files} files")
        
    elif query.data.startswith("killfilesak"):
        ident, keyword = query.data.split("#")
        await query.message.edit_text(f"<b>ꜰᴇᴛᴄʜɪɴɢ ꜰɪʟᴇs ꜰᴏʀ ʏᴏᴜʀ ǫᴜᴇʀʏ {keyword} ᴏɴ ᴅʙ...\n\nᴘʟᴇᴀsᴇ ᴡᴀɪᴛ...</b>")
        files, total = await get_bad_files(keyword)
        await query.message.edit_text(f"<b>ꜰᴏᴜɴᴅ {total} ꜰɪʟᴇs ꜰᴏʀ ʏᴏᴜʀ ǫᴜᴇʀʏ {keyword}!!</b>")
        deleted = 0
        async with lock:
            try:
                for file in files:
                    file_ids = file.file_id
                    file_name = file.file_name
                    result = await Media.collection.delete_one({
                        '_id': file_ids,
                    })
                    if result.deleted_count:
                        print(f'Successfully deleted {file_name} from database.')
                    deleted += 1
                    if deleted % 20 == 0:
                        await query.message.edit_text(f"<b>Process started for deleting files from DB. Successfully deleted {str(deleted)} files from DB for your query {keyword} !\n\nPlease wait...</b>")
            except Exception as e:
                print(e)
                await query.message.edit_text(f'Error: {e}')
            else:
                await query.message.edit_text(f"<b>Process Completed for file deletion !\n\nSuccessfully deleted {str(deleted)} files from database for your query {keyword}.</b>")
          
    elif query.data.startswith("reset_grp_data"):
        grp_id = query.message.chat.id
        btn = [[
            InlineKeyboardButton('☕️ ᴄʟᴏsᴇ ☕️', callback_data='close_data')
        ]]
        reply_markup=InlineKeyboardMarkup(btn)
        await save_group_settings(grp_id, 'shortner', SHORTENER_WEBSITE)
        await save_group_settings(grp_id, 'api', SHORTENER_API)
        await save_group_settings(grp_id, 'shortner_two', SHORTENER_WEBSITE2)
        await save_group_settings(grp_id, 'api_two', SHORTENER_API2)
        await save_group_settings(grp_id, 'template', IMDB_TEMPLATE)
        await save_group_settings(grp_id, 'tutorial', TUTORIAL)
        await save_group_settings(grp_id, 'caption', FILE_CAPTION)
        await save_group_settings(grp_id, 'log', LOG_VR_CHANNEL)
        await query.answer('ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇꜱᴇᴛ...')
        await query.message.edit_text("<b>ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʀᴇꜱᴇᴛ ɢʀᴏᴜᴘ ꜱᴇᴛᴛɪɴɢꜱ...\n\nɴᴏᴡ ꜱᴇɴᴅ /details ᴀɢᴀɪɴ</b>", reply_markup=reply_markup)

    # --- NEW HANDLER FOR PM SETTINGS ---
    elif query.data.startswith("open_settings"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        if not await is_check_admin(client, grp_id, query.from_user.id):
            await query.answer("You are not an admin in this group anymore!", show_alert=True)
            return

        settings = await get_settings(grp_id)
        try:
            chat = await client.get_chat(grp_id)
            title = chat.title
        except:
            title = "Group"

        if settings is not None:
            buttons = [
                [InlineKeyboardButton('ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ', callback_data=f'setgs#auto_filter#{settings["auto_filter"]}#{grp_id}'), InlineKeyboardButton('ᴏɴ ✔️' if settings["auto_filter"] else 'ᴏғғ ✗', callback_data=f'setgs#auto_filter#{settings["auto_filter"]}#{grp_id}')],
                [InlineKeyboardButton('ꜰɪʟᴇ sᴇᴄᴜʀᴇ', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}'), InlineKeyboardButton('ᴏɴ ✔️' if settings["file_secure"] else 'ᴏғғ ✗', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}')],
                [InlineKeyboardButton('ɪᴍᴅʙ', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'), InlineKeyboardButton('ᴏɴ ✔️' if settings["imdb"] else 'ᴏғғ ✗', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}')],
                [InlineKeyboardButton('sᴘᴇʟʟ ᴄʜᴇᴄᴋ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'), InlineKeyboardButton('ᴏɴ ✔️' if settings["spell_check"] else 'ᴏғғ ✗', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}')],
                [InlineKeyboardButton('ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'), InlineKeyboardButton(f'{get_readable_time(DELETE_TIME)}' if settings["auto_delete"] else 'ᴏғғ ✗', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}')],
                [InlineKeyboardButton('ʀᴇsᴜʟᴛ ᴍᴏᴅᴇ', callback_data=f'setgs#link#{settings["link"]}#{str(grp_id)}'), InlineKeyboardButton('ʟɪɴᴋ' if settings["link"] else 'ʙᴜᴛᴛᴏN', callback_data=f'setgs#link#{settings["link"]}#{str(grp_id)}')],
                [InlineKeyboardButton('ᴠᴇʀɪғʏ', callback_data=f'setgs#is_verify#{settings["is_verify"]}#{grp_id}'), InlineKeyboardButton('ᴏɴ ✔️' if settings["is_verify"] else 'ᴏғғ ✗', callback_data=f'setgs#is_verify#{settings["is_verify"]}#{grp_id}')],
                [InlineKeyboardButton('💰 Earning Method', callback_data=f'earning_menu#{grp_id}')], 
                [InlineKeyboardButton('📢 Force Subscribe', callback_data=f'fsub_menu#{grp_id}')], 
                [InlineKeyboardButton('🔙 Back to Groups', callback_data='settings_back')],
                [InlineKeyboardButton('☕️ ᴄʟᴏsᴇ ☕️', callback_data='close_data')]
            ]
            await query.message.edit_text(
                text=f"ᴄʜᴀɴɢᴇ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ <b>'{title}'</b> ᴀs ʏᴏᴜʀ ᴡɪsʜ ✨",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML
            )
    
    # --- MAIN FSUB MENU ---
    elif query.data.startswith("fsub_menu"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        btn = [
            [InlineKeyboardButton("Request Fsub (Auth 1, 2, 4)", callback_data=f"req_fsub_menu#{grp_id}")],
            [InlineKeyboardButton("Normal Fsub (Auth 3)", callback_data=f"norm_fsub_menu#{grp_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"open_settings#{grp_id}")]
        ]
        await query.message.edit(
            "<b>📢 Force Subscribe Settings</b>\n\nSelect which type of FSub you want to configure:",
            reply_markup=InlineKeyboardMarkup(btn)
        )

    # --- 1. REQUEST FSUB MENU (DYNAMIC BUTTONS) ---
    elif query.data.startswith("req_fsub_menu"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        settings = await get_settings(grp_id)
        id_1 = int(settings.get('fsub_id_1', 0))
        id_2 = int(settings.get('fsub_id_2', 0))
        id_4 = int(settings.get('fsub_id_4', 0))

        async def get_name(cid):
            try:
                if not cid: return "Not Set ❌"
                chat = await client.get_chat(cid)
                return f"{chat.title}"
            except:
                return f"Unknown ({cid})"

        name_1 = await get_name(id_1)
        name_2 = await get_name(id_2)
        name_4 = await get_name(id_4)

        text = (
            f"<b>⚙️ Configure Request F-Sub Channels for:</b> `{grp_id}`\n\n"
            f"1️⃣ <b>Slot 1:</b> {name_1}\n"
            f"2️⃣ <b>Slot 2:</b> {name_2}\n"
            f"4️⃣ <b>Slot 4:</b> {name_4}\n\n"
            f"<i>👇 Select an option below:</i>"
        )
        
        btn = []

        # --- SLOT 1 LOGIC ---
        if id_1 == 0:
            btn.append([InlineKeyboardButton("➕ Set Slot 1", callback_data=f"set_fsub#{grp_id}#fsub_id_1")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 1", callback_data=f"set_fsub#{grp_id}#fsub_id_1"),
                InlineKeyboardButton("🗑️ Clear Slot 1", callback_data=f"clear_fsub#{grp_id}#fsub_id_1")
            ])

        # --- SLOT 2 LOGIC ---
        if id_2 == 0:
            btn.append([InlineKeyboardButton("➕ Set Slot 2", callback_data=f"set_fsub#{grp_id}#fsub_id_2")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 2", callback_data=f"set_fsub#{grp_id}#fsub_id_2"),
                InlineKeyboardButton("🗑️ Clear Slot 2", callback_data=f"clear_fsub#{grp_id}#fsub_id_2")
            ])

        # --- SLOT 4 LOGIC ---
        if id_4 == 0:
            btn.append([InlineKeyboardButton("➕ Set Slot 4 (Post-Verify)", callback_data=f"set_fsub#{grp_id}#fsub_id_4")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 4", callback_data=f"set_fsub#{grp_id}#fsub_id_4"),
                InlineKeyboardButton("🗑️ Clear Slot 4", callback_data=f"clear_fsub#{grp_id}#fsub_id_4")
            ])
            
        # Common Buttons
        if id_1 or id_2 or id_4:
             btn.append([InlineKeyboardButton("🚫 Remove All Request Fsub", callback_data=f"remove_all_fsub#{grp_id}#req")])
             
        btn.append([InlineKeyboardButton("🔙 Back", callback_data=f"fsub_menu#{grp_id}")])
        
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))


    # --- 2. NORMAL FSUB MENU (DYNAMIC BUTTONS) ---
    elif query.data.startswith("norm_fsub_menu"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        settings = await get_settings(grp_id)
        id_3 = settings.get('fsub_id_3', 0) 
        
        chat_name = "Not Set ❌"
        if id_3:
            try:
                chat = await client.get_chat(id_3)
                chat_name = f"{chat.title}"
            except:
                chat_name = f"Unknown ({id_3})"
        
        text = (
            f"<b>⚙️ Configure Normal F-Sub (Auth 3) for:</b> `{grp_id}`\n\n"
            f"3️⃣ <b>Slot 3:</b> {chat_name}\n\n"
            f"<i>👇 Select an option below:</i>"
        )
        
        btn = []
        
        # --- SLOT 3 LOGIC ---
        if not id_3:
            btn.append([InlineKeyboardButton("➕ Set Slot 3 (Normal)", callback_data=f"set_fsub#{grp_id}#fsub_id_3")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 3", callback_data=f"set_fsub#{grp_id}#fsub_id_3"),
                InlineKeyboardButton("🗑️ Clear Slot 3", callback_data=f"clear_fsub#{grp_id}#fsub_id_3")
            ])
            btn.append([InlineKeyboardButton("🚫 Remove All Normal Fsub", callback_data=f"remove_all_fsub#{grp_id}#norm")])

        btn.append([InlineKeyboardButton("🔙 Back", callback_data=f"fsub_menu#{grp_id}")])
        
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))

    # --- 3. CLEAR SLOT HANDLER (NEW) ---
    elif query.data.startswith("clear_fsub"):
        ident, grp_id, slot_key = query.data.split("#")
        grp_id = int(grp_id)
        
        # Reset that specific slot to 0
        await save_group_settings(grp_id, slot_key, 0)
        
        await query.answer("✅ Slot Cleared!", show_alert=False)
        
        if slot_key == "fsub_id_3":
             btn = [[InlineKeyboardButton("🔙 Back to Menu", callback_data=f"norm_fsub_menu#{grp_id}")]]
             await query.message.edit("<b>🗑️ Slot 3 Cleared Successfully!</b>", reply_markup=InlineKeyboardMarkup(btn))
        else:
             btn = [[InlineKeyboardButton("🔙 Back to Menu", callback_data=f"req_fsub_menu#{grp_id}")]]
             await query.message.edit(f"<b>🗑️ {slot_key} Cleared Successfully!</b>", reply_markup=InlineKeyboardMarkup(btn))

    # --- 4. REMOVE ALL HANDLER (NEW) ---
    elif query.data.startswith("remove_all_fsub"):
        ident, grp_id, type_fsub = query.data.split("#")
        grp_id = int(grp_id)
        
        if type_fsub == "req":
            await save_group_settings(grp_id, 'fsub_id_1', 0)
            await save_group_settings(grp_id, 'fsub_id_2', 0)
            await save_group_settings(grp_id, 'fsub_id_4', 0)
            back_data = f"req_fsub_menu#{grp_id}"
        else:
            await save_group_settings(grp_id, 'fsub_id_3', 0)
            back_data = f"norm_fsub_menu#{grp_id}"
            
        await query.answer("🚫 All Channels Removed!", show_alert=True)
        
        btn = [[InlineKeyboardButton("🔙 Back to Menu", callback_data=back_data)]]
        await query.message.edit("<b>🚫 All Fsub Channels for this section have been removed!</b>", reply_markup=InlineKeyboardMarkup(btn))

    # --- SET FSUB ID HANDLER (ASK FOR ID) ---
    elif query.data.startswith("set_fsub"):
        ident, grp_id, slot_key = query.data.split("#")
        grp_id = int(grp_id)
        user_id = query.from_user.id
        
        # Set State
        temp.FSUB_WAITING[user_id] = {'grp_id': grp_id, 'slot': slot_key}
        
        slot_readable = slot_key.replace("fsub_id_", "Slot ")
        
        text = (
            f"<b>👇 Please send the Channel ID for {slot_readable}.</b>\n\n"
            "ℹ️ <b>Instructions:</b>\n"
            "1. Add this bot to that channel as Admin.\n"
            "2. Forward a message from that channel here OR send the ID directly (e.g., `-100xxxxxxx`).\n"
            "3. This must be a private/public channel based on the slot type."
        )
        
        btn = [[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_fsub_input#{grp_id}#{slot_key}")]]
        
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))
    
    # --- NEW CANCEL BUTTON HANDLER ---
    elif query.data.startswith("cancel_fsub_input"):
        ident, grp_id, slot_key = query.data.split("#")
        grp_id = int(grp_id)
        user_id = query.from_user.id
        
        # Remove user from waiting list
        if user_id in temp.FSUB_WAITING:
            del temp.FSUB_WAITING[user_id]
            
        # Decide where to go back (Normal or Request Menu)
        if slot_key == "fsub_id_3":
            back_data = f"norm_fsub_menu#{grp_id}"
        else:
            back_data = f"req_fsub_menu#{grp_id}"
            
        btn = [[InlineKeyboardButton("🔙 Back to Menu", callback_data=back_data)]]
        
        await query.message.edit("<b>❌ Process Cancelled.</b>", reply_markup=InlineKeyboardMarkup(btn))

    # --- EARNING METHOD MENU ---
    elif query.data.startswith("earning_menu"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        settings = await get_settings(grp_id)
        
        is_active = settings.get('is_verify', False)
        active_mode = "SHORTLINK ✅" if is_active else "DISABLED ❌"
        
        count = 0
        if settings.get('shortner') and settings.get('api'): count += 1
        if settings.get('shortner_two') and settings.get('api_two'): count += 1
        if settings.get('shortner_three') and settings.get('api_three'): count += 1
        
        text = (
            f"<b>💰 Earning Method Settings for:</b> `{grp_id}`\n\n"
            f"<b>Current Active Mode:</b> {active_mode}\n"
            f"<b>🔗 Shorteners Configured:</b> {count}\n\n"
            f"<i>Select a mode below to configure and activate it.</i>"
        )
        
        btn = [
            [InlineKeyboardButton("🔗 Shortlink Mode", callback_data=f"set_earn_mode#{grp_id}#shortlink")],
            [InlineKeyboardButton("🚫 Disable Shortlink", callback_data=f"set_earn_mode#{grp_id}#disable")],
            [InlineKeyboardButton("🔙 Back to Main Settings", callback_data=f"open_settings#{grp_id}")]
        ]
        
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))

    # --- UPDATED: SET EARNING MODE HANDLER (Redirects to Sub-menus) ---
    elif query.data.startswith("set_earn_mode"):
        ident, grp_id, mode = query.data.split("#")
        grp_id = int(grp_id)
        
        if mode == "shortlink":
            # Redirect to Shortlink Configuration Menu
            await shortlink_config_menu(client, query, grp_id)
        else:
            # Redirect to Disable Configuration Menu
            await disable_config_menu(client, query, grp_id)

    # --- NEW: SET SHORTENER TYPE (Dynamic/Together/Smart) ---
    elif query.data.startswith("set_short_type"):
        ident, grp_id, type_val = query.data.split("#")
        grp_id = int(grp_id)
        
        await save_group_settings(grp_id, 'shortener_type', type_val)
        await query.answer(f"✅ Mode set to: {type_val.title()}", show_alert=False)
        
        # Refresh Menu
        await shortlink_config_menu(client, query, grp_id)

    # --- NEW: DEACTIVATE SHORTLINK BUTTON ---
    elif query.data.startswith("deact_short"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        # Logic: Set is_verify = False
        await save_group_settings(grp_id, 'is_verify', False)
        await query.answer("🚫 Shortlink Mode Deactivated!", show_alert=True)
        
        # Refresh Menu
        await shortlink_config_menu(client, query, grp_id)

    # --- NEW: TOGGLE DISABLE/ENABLE (With Requirements Check) ---
    elif query.data.startswith("toggle_disable"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        settings = await get_settings(grp_id)
        is_shortlink_on = settings.get('is_verify', False) # True means Shortlink Active
        
        # Agar Shortlink ON hai, to hume use Disable karna hai (Status Active karna hai)
        if is_shortlink_on:
            # Check Fsubs
            fsub_set = False
            if settings.get('fsub_id_1') or settings.get('fsub_id_2') or settings.get('fsub_id_3') or settings.get('fsub_id_4'):
                fsub_set = True
            
            # Check Members
            try:
                count = await client.get_chat_members_count(grp_id)
            except:
                count = 0
                
            if not fsub_set:
                await query.answer("⚠️ Requirement Failed: Please configure at least one Fsub channel first!", show_alert=True)
                return
            
            if count < 100:
                await query.answer(f"⚠️ Requirement Failed: Group needs 100 members. Current: {count}", show_alert=True)
                return
            
            # Sab sahi hai -> Shortlink Disable (is_verify = False)
            await save_group_settings(grp_id, 'is_verify', False)
            await query.answer("✅ Shortlink Disabled! Users will use Fsub only.", show_alert=True)
            
        else:
            # Agar Shortlink OFF hai, to use Enable karna hai (Normal mode)
            await save_group_settings(grp_id, 'is_verify', True)
            await query.answer("✅ Shortlink Enabled!", show_alert=True)
            
        # Refresh Menu
        await disable_config_menu(client, query, grp_id)

    # --- CONFIGURE SHORTENERS MENU ---
    elif query.data.startswith("conf_short"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        settings = await get_settings(grp_id)
        short_type = settings.get('shortener_type', 'dynamic')
        
        # Get Current Details
        s1 = settings.get('shortner')
        s2 = settings.get('shortner_two')
        s3 = settings.get('shortner_three')
        
        # Helper to display
        def get_slot_text(domain):
            return domain if domain else "Not Set ❌"
            
        text = (
            f"<b>⚙️ Configure Shorteners for:</b> `{grp_id}`\n"
            f"<b>Current Mode:</b> {short_type.title()}\n\n"
            f"1️⃣ <b>Slot 1:</b> `{get_slot_text(s1)}`\n"
            f"2️⃣ <b>Slot 2:</b> `{get_slot_text(s2)}`\n"
            f"3️⃣ <b>Slot 3:</b> `{get_slot_text(s3)}`\n\n"
            f"<i>👇 Use buttons to setup slots or test connections.</i>"
        )
        
        btn = []
        
        # --- SLOT 1 BUTTONS ---
        if not s1:
            btn.append([InlineKeyboardButton("➕ Set Slot 1", callback_data=f"set_short_slot#{grp_id}#slot1")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 1", callback_data=f"set_short_slot#{grp_id}#slot1"),
                InlineKeyboardButton("🗑️ Clear Slot 1", callback_data=f"clear_short_slot#{grp_id}#slot1")
            ])
            
        # --- SLOT 2 BUTTONS ---
        if not s2:
            btn.append([InlineKeyboardButton("➕ Set Slot 2", callback_data=f"set_short_slot#{grp_id}#slot2")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 2", callback_data=f"set_short_slot#{grp_id}#slot2"),
                InlineKeyboardButton("🗑️ Clear Slot 2", callback_data=f"clear_short_slot#{grp_id}#slot2")
            ])

        # --- SLOT 3 BUTTONS ---
        if not s3:
            btn.append([InlineKeyboardButton("➕ Set Slot 3", callback_data=f"set_short_slot#{grp_id}#slot3")])
        else:
            btn.append([
                InlineKeyboardButton("✏️ Edit Slot 3", callback_data=f"set_short_slot#{grp_id}#slot3"),
                InlineKeyboardButton("🗑️ Clear Slot 3", callback_data=f"clear_short_slot#{grp_id}#slot3")
            ])
            
        # --- EXTRA UTILITIES ---
        btn.append([InlineKeyboardButton("🧪 Test Connected Shorteners", callback_data=f"test_shorts#{grp_id}")])
        
        tut_link = settings.get('tutorial', 'https://t.me/Aksbackup')
        btn.append([InlineKeyboardButton("📺 How to Connect Shortener", url=tut_link)])
        
        help_text = f"How {short_type.title()} Mode Works"
        btn.append([InlineKeyboardButton(f"ℹ️ {help_text}", callback_data=f"mode_info#{short_type}")])
        
        btn.append([InlineKeyboardButton("🔙 Back to Shortener Settings", callback_data=f"set_earn_mode#{grp_id}#shortlink")])
        
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)

    # --- SET SLOT HANDLER (Ask Input) ---
    elif query.data.startswith("set_short_slot"):
        ident, grp_id, slot = query.data.split("#")
        grp_id = int(grp_id)
        user_id = query.from_user.id
        
        temp.SHORTENER_WAITING[user_id] = {'grp_id': grp_id, 'slot': slot}
        
        await query.message.edit(
            f"<b>👇 Send details for {slot.title()}</b>\n\n"
            "<b>Format:</b> `website.com API_KEY`\n"
            "<b>Example:</b> `tnshort.net 06b24eb6bbb025713cd522fb3f696`\n\n"
            "<i>Click Cancel to abort.</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"conf_short#{grp_id}")]])
        )

    # --- CLEAR SLOT HANDLER ---
    elif query.data.startswith("clear_short_slot"):
        ident, grp_id, slot = query.data.split("#")
        grp_id = int(grp_id)
        
        if slot == 'slot1':
            await save_group_settings(grp_id, 'shortner', "")
            await save_group_settings(grp_id, 'api', "")
        elif slot == 'slot2':
            await save_group_settings(grp_id, 'shortner_two', "")
            await save_group_settings(grp_id, 'api_two', "")
        elif slot == 'slot3':
            await save_group_settings(grp_id, 'shortner_three', "")
            await save_group_settings(grp_id, 'api_three', "")
            
        await query.answer("🗑️ Slot Cleared!", show_alert=False)
        btn = [[InlineKeyboardButton("🔙 Back", callback_data=f"conf_short#{grp_id}")]]
        await query.message.edit(f"<b>✅ {slot.title()} Cleared!</b>", reply_markup=InlineKeyboardMarkup(btn))

    # --- TEST SHORTENERS HANDLER ---
    elif query.data.startswith("test_shorts"):
        ident, grp_id = query.data.split("#")
        grp_id = int(grp_id)
        
        await query.answer("🧪 Testing connections... Please wait.", show_alert=False)
        
        settings = await get_settings(grp_id)
        from utils import check_shortener_status
        
        s1_res = await check_shortener_status(settings.get('shortner'), settings.get('api'))
        s2_res = await check_shortener_status(settings.get('shortner_two'), settings.get('api_two'))
        s3_res = await check_shortener_status(settings.get('shortner_three'), settings.get('api_three'))
        
        text = (
            f"<b>🧪 Connection Test Results</b>\n\n"
            f"1️⃣ <b>Slot 1:</b> {s1_res}\n"
            f"2️⃣ <b>Slot 2:</b> {s2_res}\n"
            f"3️⃣ <b>Slot 3:</b> {s3_res}\n\n"
            f"<i>✅ = Working | ❌ = Error</i>"
        )
        btn = [[InlineKeyboardButton("🔙 Back", callback_data=f"conf_short#{grp_id}")]]
        await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))

    # --- MODE INFO POPUP ---
    elif query.data.startswith("mode_info"):
        ident, mode = query.data.split("#")
        
        info_text = ""
        if mode == "dynamic":
            info_text = "<b>Dynamic Mode:</b>\nBot will randomly pick one shortener (Slot 1, 2, or 3) for every link. Best for distributing traffic."
        elif mode == "together":
            info_text = "<b>Together Mode:</b>\nUser must pass ALL configured shorteners one by one to verify. (High difficulty, High Earning)."
        elif mode == "smart":
            info_text = "<b>Smart Mode:</b>\nBot uses Slot 1 first. If API fails/limits reached, it auto-switches to Slot 2, then Slot 3."
        else:
            info_text = "Select a mode to see details."
            
        await query.answer(info_text, show_alert=True)

    # --- Handler to go back to group list ---
    elif query.data == "settings_back":
        user_id = query.from_user.id
        await query.message.edit("<b>♻️ ʟᴏᴀᴅɪɴɢ ɢʀᴏᴜᴘs...</b>")
        all_chats = await db.get_all_chats()
        my_groups = []
        async for chat in all_chats:
            try:
                member = await client.get_chat_member(chat['id'], user_id)
                if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                    my_groups.append(chat)
            except:
                pass
        
        if not my_groups:
            await query.message.edit("<b>☹️ ɴᴏ ɢʀᴏᴜᴘs ꜰᴏᴜɴᴅ.</b>")
            return

        btn = []
        for group in my_groups:
            btn.append([InlineKeyboardButton(f"{group['title']}", callback_data=f"open_settings#{group['id']}")])
        btn.append([InlineKeyboardButton('ᴄʟᴏsᴇ', callback_data='close_data')])
        
        await query.message.edit(
            "<b>⚙️ sᴇʟᴇᴄᴛ ᴛʜᴇ ɢʀᴏᴜᴘ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴғɪɢᴜʀᴇ:</b>",
            reply_markup=InlineKeyboardMarkup(btn)
        )

    elif query.data.startswith("setgs"):
        ident, set_type, status, grp_id = query.data.split("#")
        userid = query.from_user.id if query.from_user else None
        if not await is_check_admin(client, int(grp_id), userid):
            await query.answer(script.ALRT_TXT, show_alert=True)
            return
        if status == "True":
            await save_group_settings(int(grp_id), set_type, False)
            await query.answer("ᴏғғ ❌")
        else:
            await save_group_settings(int(grp_id), set_type, True)
            await query.answer("ᴏɴ ✅")
        settings = await get_settings(int(grp_id))      
        if settings is not None:
            buttons = [[
                InlineKeyboardButton('ᴀᴜᴛᴏ ꜰɪʟᴛᴇʀ', callback_data=f'setgs#auto_filter#{settings["auto_filter"]}#{grp_id}'),
                InlineKeyboardButton('ᴏɴ ✔️' if settings["auto_filter"] else 'ᴏғғ ✗', callback_data=f'setgs#auto_filter#{settings["auto_filter"]}#{grp_id}')
            ],[
                InlineKeyboardButton('ꜰɪʟᴇ sᴇᴄᴜʀᴇ', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}'),
                InlineKeyboardButton('ᴏɴ ✔️' if settings["file_secure"] else 'ᴏғғ ✗', callback_data=f'setgs#file_secure#{settings["file_secure"]}#{grp_id}')
            ],[
                InlineKeyboardButton('ɪᴍᴅʙ', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}'),
                InlineKeyboardButton('ᴏɴ ✔️' if settings["imdb"] else 'ᴏғғ ✗', callback_data=f'setgs#imdb#{settings["imdb"]}#{grp_id}')
            ],[
                InlineKeyboardButton('sᴘᴇʟʟ ᴄʜᴇᴄᴋ', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}'),
                InlineKeyboardButton('ᴏɴ ✔️' if settings["spell_check"] else 'ᴏғғ ✗', callback_data=f'setgs#spell_check#{settings["spell_check"]}#{grp_id}')
            ],[
                InlineKeyboardButton('ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}'),
                InlineKeyboardButton(f'{get_readable_time(DELETE_TIME)}' if settings["auto_delete"] else 'ᴏғғ ✗', callback_data=f'setgs#auto_delete#{settings["auto_delete"]}#{grp_id}')
            ],[
                InlineKeyboardButton('ʀᴇsᴜʟᴛ ᴍᴏᴅᴇ', callback_data=f'setgs#link#{settings["link"]}#{str(grp_id)}'),
                InlineKeyboardButton('ʟɪɴᴋ' if settings["link"] else 'ʙᴜᴛᴛᴏN', callback_data=f'setgs#link#{settings["link"]}#{str(grp_id)}')
            ],[
                InlineKeyboardButton('ᴠᴇʀɪғʏ', callback_data=f'setgs#is_verify#{settings["is_verify"]}#{grp_id}'),
                InlineKeyboardButton('ᴏɴ ✔️' if settings["is_verify"] else 'ᴏғғ ✗', callback_data=f'setgs#is_verify#{settings["is_verify"]}#{grp_id}')
            ],[
                InlineKeyboardButton('💰 Earning Method', callback_data=f'earning_menu#{grp_id}')
            ],[
                InlineKeyboardButton('📢 Force Subscribe', callback_data=f'fsub_menu#{grp_id}')
            ],[
                InlineKeyboardButton('🔙 Back to Groups', callback_data='settings_back'),
                InlineKeyboardButton('☕️ ᴄʟᴏsᴇ ☕️', callback_data='close_data')
            ]]
            reply_markup = InlineKeyboardMarkup(buttons)
            d = await query.message.edit_reply_markup(reply_markup)
            await asyncio.sleep(300)
            await d.delete()
        else:
            await query.message.edit_text("<b>ꜱᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ</b>")
            
    elif query.data.startswith("show_options"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("✅️ ᴀᴄᴄᴇᴘᴛ ᴛʜɪꜱ ʀᴇǫᴜᴇꜱᴛ ✅️", callback_data=f"accept#{user_id}#{msg_id}")
        ],[
            InlineKeyboardButton("🚫 ʀᴇᴊᴇᴄᴛ ᴛʜɪꜱ ʀᴇǫᴜᴇꜱᴛ 🚫", callback_data=f"reject#{user_id}#{msg_id}")
        ]]
        try:
            st = await client.get_chat_member(chnl_id, userid)
            if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
                await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            elif st.status == enums.ChatMemberStatus.MEMBER:
                await query.answer(script.ALRT_TXT, show_alert=True)
        except pyrogram.errors.exceptions.bad_request_400.UserNotParticipant:
            await query.answer("⚠️ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏꜰ ᴛʜɪꜱ ᴄʜᴀɴɴᴇʟ, ꜰɪʀꜱᴛ ᴊᴏɪɴ", show_alert=True)

    elif query.data.startswith("reject"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("✗ ʀᴇᴊᴇᴄᴛ ✗", callback_data=f"rj_alert#{user_id}")
        ]]
        btn = [[
            InlineKeyboardButton("♻️ ᴠɪᴇᴡ sᴛᴀᴛᴜs ♻️", url=f"{query.message.link}")
        ]]
        st = await client.get_chat_member(chnl_id, userid)
        if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
            user = await client.get_users(user_id)
            request = query.message.text
            await query.answer("Message sent to requester")
            await query.message.edit_text(f"<s>{request}</s>")
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            try:
                await client.send_message(chat_id=user_id, text="<b>sᴏʀʀʏ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ʀᴇᴊᴇᴄᴛᴇᴅ 😶</b>", reply_markup=InlineKeyboardMarkup(btn))
            except UserIsBlocked:
                await client.send_message(SUPPORT_GROUP, text=f"<b>💥 ʜᴇʟʟᴏ {user.mention},\n\nsᴏʀʀʏ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ʀᴇᴊᴇᴄᴛᴇᴅ 😶</b>", reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=int(msg_id))
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("accept"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("😊 ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ 😊", callback_data=f"already_available#{user_id}#{msg_id}")
        ],[
            InlineKeyboardButton("‼️ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ ‼️", callback_data=f"not_available#{user_id}#{msg_id}")
        ],[
            InlineKeyboardButton("🥵 ᴛᴇʟʟ ᴍᴇ ʏᴇᴀʀ/ʟᴀɴɢᴜᴀɢᴇ 🥵", callback_data=f"year#{user_id}#{msg_id}")
        ],[
            InlineKeyboardButton("🙃 ᴜᴘʟᴏᴀᴅᴇᴅ ɪɴ 1 ʜᴏᴜʀ 🙃", callback_data=f"upload_in#{user_id}#{msg_id}")
        ],[
            InlineKeyboardButton("☇ ᴜᴘʟᴏᴀᴅᴇᴅ ☇", callback_data=f"uploaded#{user_id}#{msg_id}")
        ]]
        try:
            st = await client.get_chat_member(chnl_id, userid)
            if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
                await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            elif st.status == enums.ChatMemberStatus.MEMBER:
                await query.answer(script.OLD_ALRT_TXT.format(query.from_user.first_name),show_alert=True)
        except pyrogram.errors.exceptions.bad_request_400.UserNotParticipant:
            await query.answer("⚠️ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀ ᴍᴇᴍʙᴇʀ ᴏꜰ ᴛʜɪꜱ ᴄʜᴀɴɴᴇʟ, ꜰɪʀꜱᴛ ᴊᴏɪɴ", show_alert=True)

    elif query.data.startswith("not_available"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("🚫 ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ 🚫", callback_data=f"na_alert#{user_id}")
        ]]
        btn = [[
            InlineKeyboardButton("♻️ ᴠɪᴇᴡ sᴛᴀᴛᴜs ♻️", url=f"{query.message.link}")
        ]]
        st = await client.get_chat_member(chnl_id, userid)
        if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
            user = await client.get_users(user_id)
            request = query.message.text
            await query.answer("Message sent to requester")
            await query.message.edit_text(f"<s>{request}</s>")
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            try:
                await client.send_message(chat_id=user_id, text="<b>sᴏʀʀʏ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ 😢</b>", reply_markup=InlineKeyboardMarkup(btn))
            except UserIsBlocked:
                await client.send_message(SUPPORT_GROUP, text=f"<b>💥 ʜᴇʟʟᴏ {user.mention},\n\nsᴏʀʀʏ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ 😢</b>", reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=int(msg_id))
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("uploaded"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("🙂 ᴜᴘʟᴏᴀᴅᴇᴅ 🙂", callback_data=f"ul_alert#{user_id}")
        ]]
        btn = [[
            InlineKeyboardButton("♻️ ᴠɪᴇᴡ sᴛᴀᴛᴜs ♻️", url=f"{query.message.link}")
        ]]
        st = await client.get_chat_member(chnl_id, userid)
        if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
            user = await client.get_users(user_id)
            request = query.message.text
            await query.answer("Message sent to requester")
            await query.message.edit_text(f"<s>{request}</s>")
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            try:
                await client.send_message(chat_id=user_id, text="<b>ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴜᴘʟᴏᴀᴅᴇᴅ ☺️</b>", reply_markup=InlineKeyboardMarkup(btn))
            except UserIsBlocked:
                await client.send_message(SUPPORT_GROUP, text=f"<b>💥 ʜᴇʟʟᴏ {user.mention},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴜᴘʟᴏᴀᴅᴇᴅ ☺️</b>", reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=int(msg_id))
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("already_available"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("🫤 ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ 🫤", callback_data=f"aa_alert#{user_id}")
        ]]
        btn = [[
            InlineKeyboardButton("♻️ ᴠɪᴇᴡ sᴛᴀᴛᴜs ♻️", url=f"{query.message.link}")
        ]]
        st = await client.get_chat_member(chnl_id, userid)
        if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
            user = await client.get_users(user_id)
            request = query.message.text
            await query.answer("Message sent to requester")
            await query.message.edit_text(f"<s>{request}</s>")
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            try:
                await client.send_message(chat_id=user_id, text="<b>ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ 😋</b>", reply_markup=InlineKeyboardMarkup(btn))
            except UserIsBlocked:
                await client.send_message(SUPPORT_GROUP, text=f"<b>💥 ʜᴇʟʟᴏ {user.mention},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ 😋</b>", reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=int(msg_id))
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("upload_in"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("😌 ᴜᴘʟᴏᴀᴅ ɪɴ 1 ʜᴏᴜʀꜱ 😌", callback_data=f"upload_alert#{user_id}")
        ]]
        btn = [[
            InlineKeyboardButton("♻️ ᴠɪᴇᴡ sᴛᴀᴛᴜs ♻️", url=f"{query.message.link}")
        ]]
        st = await client.get_chat_member(chnl_id, userid)
        if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
            user = await client.get_users(user_id)
            request = query.message.text
            await query.answer("Message sent to requester")
            await query.message.edit_text(f"<s>{request}</s>")
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            try:
                await client.send_message(chat_id=user_id, text="<b>ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ᴡɪʟʟ ʙᴇ ᴜᴘʟᴏᴀᴅᴇᴅ ᴡɪᴛʜɪɴ 1 ʜᴏᴜʀ 😁</b>", reply_markup=InlineKeyboardMarkup(btn))
            except UserIsBlocked:
                await client.send_message(SUPPORT_GROUP, text=f"<b>💥 ʜᴇʟʟᴏ {user.mention},\n\nʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ᴡɪʟʟ ʙᴇ ᴜᴘʟᴏᴀᴅᴇᴅ ᴡɪᴛʜɪɴ 1 ʜᴏᴜʀ 😁</b>", reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=int(msg_id))
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("year"):
        ident, user_id, msg_id = query.data.split("#")
        chnl_id = query.message.chat.id
        userid = query.from_user.id
        buttons = [[
            InlineKeyboardButton("⚠️ ᴛᴇʟʟ ᴍᴇ ʏᴇᴀʀꜱ & ʟᴀɴɢᴜᴀɢᴇ ⚠️", callback_data=f"yrs_alert#{user_id}")
        ]]
        btn = [[
            InlineKeyboardButton("♻️ ᴠɪᴇᴡ sᴛᴀᴛᴜs ♻️", url=f"{query.message.link}")
        ]]
        st = await client.get_chat_member(chnl_id, userid)
        if (st.status == enums.ChatMemberStatus.ADMINISTRATOR) or (st.status == enums.ChatMemberStatus.OWNER):
            user = await client.get_users(user_id)
            request = query.message.text
            await query.answer("Message sent to requester")
            await query.message.edit_text(f"<s>{request}</s>")
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
            try:
                await client.send_message(chat_id=user_id, text="<b>ʙʀᴏ ᴘʟᴇᴀꜱᴇ ᴛᴇʟʟ ᴍᴇ ʏᴇᴀʀꜱ ᴀɴᴅ ʟᴀɴɢᴜᴀɢᴇ, ᴛʜᴇɴ ɪ ᴡɪʟʟ ᴜᴘʟᴏᴀᴅ 😬</b>", reply_markup=InlineKeyboardMarkup(btn))
            except UserIsBlocked:
                await client.send_message(SUPPORT_GROUP, text=f"<b>💥 ʜᴇʟʟᴏ {user.mention},\n\nʙʀᴏ ᴘʟᴇᴀꜱᴇ ᴛᴇʟʟ ᴍᴇ ʏᴇᴀʀꜱ ᴀɴᴅ ʟᴀɴɢᴜᴀɢᴇ, ᴛʜᴇɴ ɪ ᴡɪʟʟ ᴜᴘʟᴏᴀᴅ 😬</b>", reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=int(msg_id))
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("rj_alert"):
        ident, user_id = query.data.split("#")
        userid = query.from_user.id
        if str(userid) in user_id:
            await query.answer("sᴏʀʀʏ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ʀᴇᴊᴇᴄᴛ", show_alert=True)
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("na_alert"):
        ident, user_id = query.data.split("#")
        userid = query.from_user.id
        if str(userid) in user_id:
            await query.answer("sᴏʀʀʏ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("ul_alert"):
        ident, user_id = query.data.split("#")
        userid = query.from_user.id
        if str(userid) in user_id:
            await query.answer("ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴜᴘʟᴏᴀᴅᴇᴅ", show_alert=True)
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("aa_alert"):
        ident, user_id = query.data.split("#")
        userid = query.from_user.id
        if str(userid) in user_id:
            await query.answer("ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("upload_alert"):
        ident, user_id = query.data.split("#")
        userid = query.from_user.id
        if str(userid) in user_id:
            await query.answer("ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ᴡɪʟʟ ʙᴇ ᴜᴘʟᴏᴀᴅᴇᴅ ᴡɪᴛʜɪɴ 1 ʜᴏᴜʀ 😁", show_alert=True)
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("yrs_alert"):
        ident, user_id = query.data.split("#")
        userid = query.from_user.id
        if str(userid) in user_id:
            await query.answer("ʙʀᴏ ᴘʟᴇᴀꜱᴇ ᴛᴇʟʟ ᴍᴇ ʏᴇᴀʀꜱ ᴀɴᴅ ʟᴀɴɢᴜᴀɢᴇ, ᴛʜᴇɴ ɪ ᴡɪLL ᴜᴘʟᴏᴀᴅ 😬", show_alert=True)
        else:
            await query.answer(script.ALRT_TXT, show_alert=True)

    elif query.data.startswith("batchfiles"):
        ident, group_id, message_id, user = query.data.split("#")
        group_id = int(group_id)
        message_id = int(message_id)
        user = int(user)
        if user != query.from_user.id:
            await query.answer(script.ALRT_TXT, show_alert=True)
            return
        link = f"https://telegram.me/{temp.U_NAME}?start=allfiles_{group_id}-{message_id}"
        await query.answer(url=link)
        return

# --- HELPER FUNCTIONS FOR MENUS ---

async def shortlink_config_menu(client, query, grp_id):
    settings = await get_settings(grp_id)
    short_type = settings.get('shortener_type', 'dynamic')
    is_active = settings.get('is_verify', False)
    
    def get_btn_text(val):
        return f"✅ {val.title()}" if short_type == val else val.title()

    text = (
        f"<b>🔗 Shortener Mode Configuration for:</b> `{grp_id}`\n\n"
        f"<b>Current Shortener Type:</b> {short_type.title()}\n"
        f"<b>Status:</b> {'✅ ACTIVE' if is_active else '❌ INACTIVE'}\n\n"
        f"<b><a href='https://t.me/Aksbackup'>Dynamic Mode Demo</a></b>" 
    )
    
    btn = [
        [
            InlineKeyboardButton(get_btn_text("dynamic"), callback_data=f"set_short_type#{grp_id}#dynamic"),
            InlineKeyboardButton(get_btn_text("together"), callback_data=f"set_short_type#{grp_id}#together"),
            InlineKeyboardButton(get_btn_text("smart"), callback_data=f"set_short_type#{grp_id}#smart")
        ],
        [InlineKeyboardButton("⚙️ Configure Shorteners", callback_data=f"conf_short#{grp_id}")],
        [InlineKeyboardButton("🚫 Deactivate Shortlink Mode", callback_data=f"deact_short#{grp_id}")],
        [InlineKeyboardButton("🔙 Back to Earning methods", callback_data=f"earning_menu#{grp_id}")]
    ]
    
    await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)

async def disable_config_menu(client, query, grp_id):
    settings = await get_settings(grp_id)
    
    fsub_set = False
    if settings.get('fsub_id_1') or settings.get('fsub_id_2') or settings.get('fsub_id_3') or settings.get('fsub_id_4'):
        fsub_set = True
    req_1_icon = "✅" if fsub_set else "❌"
    
    try:
        count = await client.get_chat_members_count(grp_id)
    except:
        count = "Error"
    
    req_2_icon = "✅" if isinstance(count, int) and count > 100 else "❌"
    
    is_shortlink_on = settings.get('is_verify', False)
    
    if not is_shortlink_on:
        status_text = "✅ ACTIVE (Shortlinks Disabled)"
        toggle_btn_text = "Enable Shortlinks"
    else:
        status_text = "❌ INACTIVE (Shortlinks Enabled)"
        toggle_btn_text = "Disable Shortlinks Now"

    text = (
        f"<b>🚫 Disable Shortlink for:</b> `{grp_id}`\n\n"
        f"<b>Status:</b> {status_text}\n\n"
        "This feature bypasses shorteners, requiring users to join your Fsub channel(s) instead.\n\n"
        "<b>Requirements to Activate:</b>\n"
        f"{req_1_icon} 1. Configure at least one Fsub channel.\n"
        f"{req_2_icon} 2. Group must have over 100 members (Currently: {count})."
    )
    
    btn = [
        [InlineKeyboardButton(toggle_btn_text, callback_data=f"toggle_disable#{grp_id}")],
        [InlineKeyboardButton("🔙 Back to Earning Method", callback_data=f"earning_menu#{grp_id}")]
    ]
    
    await query.message.edit(text, reply_markup=InlineKeyboardMarkup(btn))
async def auto_filter(client, msg, spoll=False):
    if not spoll:
        message = msg
        search = message.text
        chat_id = message.chat.id
        settings = await get_settings(chat_id)
        files, offset, total_results = await get_search_results(search)
        if not files:
            if settings["spell_check"]:
                return await advantage_spell_chok(msg)
            return
        # Get available filters
        available_qualities = await get_available_qualities(search)
        available_years = await get_available_years(search)
    else:
        settings = await get_settings(msg.message.chat.id)
        message = msg.message.reply_to_message  # msg will be callback query
        search, files, offset, total_results = spoll
        # Get available filters for spoll
        available_qualities = await get_available_qualities(search)
        available_years = await get_available_years(search)

    req = message.from_user.id if message.from_user else 0
    key = f"{message.chat.id}-{message.id}"
    batch_ids = files
    temp.FILES_ID[f"{message.chat.id}-{message.id}"] = batch_ids
    batch_link = f"batchfiles#{message.chat.id}#{message.id}#{message.from_user.id}"
    
    temp.CHAT[message.from_user.id] = message.chat.id
    settings = await get_settings(message.chat.id)
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code> ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs</b>" if settings["auto_delete"] else ''
    links = ""
    if settings["link"]:
        btn = []
        for file_num, file in enumerate(files, start=1):
            links += f"""<b>\n\n{file_num}. <a href=https://t.me/{temp.U_NAME}?start=file_{message.chat.id}_{file.file_id}>[{get_size(file.file_size)}] {' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@') and not x.startswith('www.'), file.file_name.split()))}</a></b>"""
    else:
        btn = [[InlineKeyboardButton(text=f"🔗 {get_size(file.file_size)}≽ {get_name(file.file_name)}", url=f'https://telegram.dog/{temp.U_NAME}?start=file_{message.chat.id}_{file.file_id}'),]
               for file in files
              ]
    if offset != "":
        if total_results >= 3:
            btn.insert(0,[
                InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=batch_link),
                InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium"),
                InlineKeyboardButton("📰 ʟᴀɴɢᴜᴀɢᴇs", callback_data=f"languages#{key}#0#{req}")
            ])
        else:
            btn.insert(0,[
                InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium"),
                InlineKeyboardButton("📰 ʟᴀɴɢᴜᴀɢᴇs", callback_data=f"languages#{key}#0#{req}")
            ])
    else:
        if total_results >= 3:
            btn.insert(0,[
                InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=batch_link),
                InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium")
            ])
        else:
            btn.insert(0,[
                InlineKeyboardButton("🥇ʙᴜʏ🥇", url=f"https://t.me/{temp.U_NAME}?start=buy_premium")
            ])
    
    # --- Add Filter Buttons (Quality & Year) ---
    filter_buttons = []
    if len(available_qualities) > 1:
        filter_buttons.append(
            InlineKeyboardButton("🎞️ Qᴜᴀʟɪᴛʏ", callback_data=f"qualities#{key}#0#{req}")
        )
    if len(available_years) > 1:
        filter_buttons.append(
            InlineKeyboardButton("📅 Yᴇᴀʀ", callback_data=f"years#{key}#0#{req}")
        )
    
    if filter_buttons:
        btn.append(filter_buttons)

    # Refer & Earn Button
    btn.append(
        [InlineKeyboardButton("💰 ʀᴇꜰᴇʀ & ᴇᴀʀɴ 💰", url=f"https://t.me/{temp.U_NAME}?start=get_referral_{message.chat.id}")]
    )

    # How to Download Button
    btn.append(
        [InlineKeyboardButton("🤔 ʜᴏᴡ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ 🤔", url=settings['tutorial'])]
    )
                         
    if spoll:
        m = await msg.message.edit(f"<b><code>{search}</code> ɪs ꜰᴏᴜɴᴅ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ꜰᴏʀ ꜰɪʟᴇs 📫</b>")
        await asyncio.sleep(1.2)
        await m.delete()

    if offset != "":
        BUTTONS[key] = search
        req = message.from_user.id if message.from_user else 0
        btn.append(
            [InlineKeyboardButton(text=f"1/{math.ceil(int(total_results) / int(MAX_BTN))}", callback_data="pages"),
             InlineKeyboardButton(text="ɴᴇxᴛ ⪼", callback_data=f"next_{req}_{key}_{offset}")]
        )
        key = f"{message.chat.id}-{message.id}"
        BUTTONS[key] = search
        req = message.from_user.id if message.from_user else 0
        try:
            offset = int(offset) 
        except:
            offset = int(MAX_BTN)
        
    imdb = await get_poster(search, file=(files[0]).file_name) if settings["imdb"] else None
    TEMPLATE = settings['template']
    if imdb:
        cap = TEMPLATE.format(
            query=search,
            title=imdb['title'],
            votes=imdb['votes'],
            aka=imdb["aka"],
            seasons=imdb["seasons"],
            box_office=imdb['box_office'],
            localized_title=imdb['localized_title'],
            kind=imdb['kind'],
            imdb_id=imdb["imdb_id"],
            cast=imdb["cast"],
            runtime=imdb["runtime"],
            countries=imdb["countries"],
            certificates=imdb["certificates"],
            languages=imdb["languages"],
            director=imdb["director"],
            writer=imdb["writer"],
            producer=imdb["producer"],
            composer=imdb["composer"],
            cinematographer=imdb["cinematographer"],
            music_team=imdb["music_team"],
            distributors=imdb["distributors"],
            release_date=imdb['release_date'],
            year=imdb['year'],
            genres=imdb['genres'],
            poster=imdb['poster'],
            plot=imdb['plot'],
            rating=imdb['rating'],
            url=imdb['url'],
            **locals()
        )
    else:
        cap = f"<b>📂 ʜᴇʀᴇ ɪ ꜰᴏᴜɴᴅ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ {search}</b>"
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code> ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs</b>" if settings["auto_delete"] else ''
    CAP[key] = cap
    if imdb and imdb.get('poster'):
        try:
            if settings['auto_delete']:
                k = await message.reply_photo(photo=imdb.get('poster'), caption=cap[:1024] + links + del_msg, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
                await asyncio.sleep(DELETE_TIME)
                await k.delete()
                try:
                    await message.delete()
                except:
                    pass
            else:
                await message.reply_photo(photo=imdb.get('poster'), caption=cap[:1024] + links + del_msg, reply_markup=InlineKeyboardMarkup(btn))                    
        except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
            pic = imdb.get('poster')
            poster = pic.replace('.jpg', "._V1_UX360.jpg")
            if settings["auto_delete"]:
                k = await message.reply_photo(photo=poster, caption=cap[:1024] + links + del_msg, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
                await asyncio.sleep(DELETE_TIME)
                await k.delete()
                try:
                    await message.delete()
                except:
                    pass
            else:
                await message.reply_photo(photo=poster, caption=cap[:1024] + links + del_msg, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
        except Exception as e:
            if settings["auto_delete"]:
                k = await message.reply_text(cap + links + del_msg, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)
                await asyncio.sleep(DELETE_TIME)
                await k.delete()
                try:
                    await message.delete()
                except:
                    pass
            else:
                await message.reply_text(cap + links + del_msg, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True)
    else:
        k=await message.reply_text(text=cap + links + del_msg, disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn), reply_to_message_id=message.id)
        if settings['auto_delete']:
            await asyncio.sleep(DELETE_TIME)
            await k.delete()
            try:
                await message.delete()
            except:
                pass

async def advantage_spell_chok(message):
    mv_id = message.id
    search = message.text
    chat_id = message.chat.id
    settings = await get_settings(chat_id)
    query = re.sub(
        r"\b(pl(i|e)*?(s|z+|ease|se|ese|(e+)s(e)?)|((send|snd|giv(e)?|gib)(\sme)?)|movie(s)?|new|latest|br((o|u)h?)*|^h(e|a)?(l)*(o)*|mal(ayalam)?|t(h)?amil|file|that|find|und(o)*|kit(t(i|y)?)?o(w)?|thar(u)?(o)*w?|kittum(o)*|aya(k)*(um(o)*)?|full\smovie|any(one)|with\ssubtitle(s)?)",
        "", message.text, flags=re.IGNORECASE)
    RQST = query.strip()
    query = query.strip() + " movie"
    try:
        movies = await get_poster(search, bulk=True)
    except:
        k = await message.reply(script.I_CUDNT.format(message.from_user.mention))
        await asyncio.sleep(60)
        await k.delete()
        try:
            await message.delete()
        except:
            pass
        return
    if not movies:
        google = search.replace(" ", "+")
        button = [[
            InlineKeyboardButton("🔍 ᴄʜᴇᴄᴋ sᴘᴇʟʟɪɴɢ ᴏɴ ɢᴏᴏɢʟᴇ 🔍", url=f"https://www.google.com/search?q={google}")
        ]]
        k = await message.reply_text(text=script.I_CUDNT.format(search), reply_markup=InlineKeyboardMarkup(button))
        await asyncio.sleep(120)
        await k.delete()
        try:
            await message.delete()
        except:
            pass
        return
    user = message.from_user.id if message.from_user else 0
    buttons = [[
        InlineKeyboardButton(text=movie.get('title'), callback_data=f"spol#{movie.movieID}#{user}")
    ]
        for movie in movies
    ]
    buttons.append(
        [InlineKeyboardButton(text="🚫 ᴄʟᴏsᴇ 🚫", callback_data='close_data')]
    )
    d = await message.reply_text(text=script.CUDNT_FND.format(message.from_user.mention), reply_markup=InlineKeyboardMarkup(buttons), reply_to_message_id=message.id)
    await asyncio.sleep(120)
    await d.delete()
    try:
        await message.delete()
    except:
        pass
