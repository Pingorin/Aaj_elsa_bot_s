import os
# import requests # Replaced with aiohttp
import logging
import random
import asyncio
import string
import pytz
import urllib.parse
from datetime import datetime, timedelta
from Script import script
from pyrogram import Client, filters, enums
from pyrogram.errors import ChatAdminRequired, FloodWait, UserIsBlocked, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
from database.ia_filterdb import Media, get_file_details, get_bad_files, unpack_new_file_id
from database.users_chats_db import db
from info import (
    ADMINS, LOG_CHANNEL, USERNAME, VERIFY_IMG, IS_VERIFY, FILE_CAPTION, 
    AUTH_CHANNEL, AUTH_CHANNEL_2, 
    AUTH_CHANNEL_3, 
    AUTH_CHANNEL_4, AUTH_CHANNEL_4_TEXT, # <-- YEH FIX HAI
    SHORTENER_WEBSITE, SHORTENER_API, SHORTENER_WEBSITE2, 
    SHORTENER_API2, LOG_API_CHANNEL, TWO_VERIFY_GAP, QR_CODE, DELETE_TIME, 
    REQUEST_CHANNEL, REFERRAL_TARGET, PREMIUM_MONTH_DURATION
)
from utils import (
    get_settings, save_group_settings, get_size, get_shortlink, 
    is_check_admin, get_status, temp, get_readable_time, 
    check_fsub_status, check_fsub_4_status, get_seconds  # <-- YAHAN 'get_seconds' ADD KIYA GAYA
)
import re
import json
import base64
import aiohttp  # Added for non-blocking requests
from html import escape 

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client:Client, message): 
    m = message
    user_id = m.from_user.id

    # --- NAYA REFERRAL CODE BLOCK --
    if len(m.command) == 2 and m.command[1].startswith("get_referral_"):
        try:
            chat_id_str = m.command[1].replace("get_referral_", "")
            
            if not chat_id_str.lstrip('-').isdigit():
                await m.reply_text("<b>Invalid referral link format.</b>")
                return
            
            chat_id = int(chat_id_str)
            user_id = m.from_user.id
            user_mention = m.from_user.mention

            user_data = await db.get_user_data(user_id)
            if not user_data:
                await db.add_user(user_id, m.from_user.first_name)
                user_data = await db.get_user_data(user_id)

            link_data = await db.get_referral_link(user_id, chat_id)
            referral_link = link_data.get('_id') if link_data else None
            
            if not referral_link:
                link = await client.create_chat_invite_link(
                    chat_id=chat_id,
                    name=f"ref_{user_id}_{chat_id}",
                    creates_join_request=False
                )
                referral_link = link.invite_link
                await db.update_referral_link(user_id, referral_link, chat_id)
            
            current_count = user_data.get('referral_count', 0)
            
            share_text = f"Join this awesome Telegram group! {referral_link}"
            encoded_share_text = urllib.parse.quote(share_text)
            
            await m.reply_text(
                text=script.REFERRAL_TXT.format(
                    user_mention=user_mention,
                    referral_link=referral_link,
                    target=REFERRAL_TARGET,
                    current_count=current_count
                ),
                disable_web_page_preview=False, 
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Share Link 🔗", url=f"https://t.me/share/url?url={encoded_share_text}")],
                    [InlineKeyboardButton("Close ❌", callback_data="close_data")]
                ])
            )
            return 

        except ChatAdminRequired:
            await m.reply_text(
                "<b>Main invite link nahi bana pa raha hoon! 😢\n\n"
                "Kripya group admin ko batayein ki bot ko 'Invite users' ki permission dein.</b>"
            )
        except Exception as e:
            await m.reply_text(f"<b>Ek error aa gaya:</b> <code>{e}</code>")
            logger.error(f"Error in get_referral start: {e}")
        return
    # --- NAYA REFERRAL CODE BLOCK YAHAN KHATAM HOTA HAI ---
            
    # --- YEH HAI 'NOTCOPY' (VERIFICATION) WALA FIX (UPDATED) ---
    if len(m.command) == 2 and m.command[1].startswith('notcopy'):
        _, userid, verify_id, file_id = m.command[1].split("_", 3)
        user_id = int(userid)
        grp_id = temp.CHAT.get(user_id, 0)
        settings = await get_settings(grp_id)
        
        # Admin dwara set time (in seconds) ko fetch karein
        verify_time_seconds = settings.get('verify_time', TWO_VERIFY_GAP)
        
        verify_id_info = await db.get_verify_id_info(user_id, verify_id)
        
        if not verify_id_info or verify_id_info["verified"]:
            await message.reply("<b>ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ᴛʀʏ ᴀɢᴀɪN...</b>")
            return
            
        # User ko verify karein
        ist_timezone = pytz.timezone('Asia/Kolkata')
        
        # --- YEH HAI ASLI FIX: Decide karein kaunsa timestamp update karna hai ---
        user_data = await db.get_notcopy_user(user_id)
        
        # Check karein kaunsa link dikhaya gaya tha (kaunsa purana hai)
        try:
            if user_data["last_verified"] > user_data["second_time_verified"]:
                # Link 1 aakhri baar use hua tha, iska matlab Link 2 dikhaya gaya tha.
                # Isliye, 'second_time_verified' ko update karein.
                key = "second_time_verified"
                num = 2
                msg = script.SECOND_VERIFY_COMPLETE_TEXT
            else:
                # Link 2 aakhri baar use hua tha, iska matlab Link 1 dikhaya gaya tha.
                # Isliye, 'last_verified' ko update karein.
                key = "last_verified"
                num = 1
                msg = script.VERIFY_COMPLETE_TEXT
        except Exception:
             # Agar koi timestamp missing hai, toh default Link 1 (last_verified) ko update karein
             key = "last_verified"
             num = 1
             msg = script.VERIFY_COMPLETE_TEXT
        # --- FIX KHATAM ---

        current_time = datetime.now(tz=ist_timezone)  
        await db.update_notcopy_user(user_id, {key:current_time}) # Sahi key (timestamp) ko update karein
        await db.update_verify_id_info(user_id, verify_id, {"verified":True})
        
        await client.send_message(settings['log'], script.VERIFIED_LOG_TEXT.format(m.from_user.mention, user_id, datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d %B %Y'), num))
        
        # User ko file lene ke liye "Try Again" link bhejein
        btn = [[
            InlineKeyboardButton("✅ ᴄʟɪᴄᴋ ʜᴇʀᴇ ᴛᴏ ɢᴇᴛ ꜰɪʟᴇ ✅", url=f"https://telegram.me/{temp.U_NAME}?start=file_{grp_id}_{file_id}"),
        ]]
        reply_markup=InlineKeyboardMarkup(btn)
        
        # --- YEH HAI AAPKA NAYA SUCCESS MESSAGE ---
        
        # Seconds ko readable string (jaise '1 day' ya '6 hours') mein convert karein
        readable_access_time = get_readable_time(verify_time_seconds)
        
        # Agar time 0 hai, toh alag message dikhayein
        if verify_time_seconds == 0:
            access_msg = "Ab aap <b>sirf iss file</b> ko access kar sakte hain."
        else:
            access_msg = f"Aapko <b>{readable_access_time}</b> ke liye free access mil gaya hai."

        # --- YEH HAI ASLI FIX (INDEXERROR KE LIYE) ---
        # 'msg.format' ko dono arguments (user mention aur time) pass karein
        caption = msg.format(message.from_user.mention, readable_access_time) 
        caption += f"\n\n{access_msg}" # Naya message add kiya
        # --- FIX KHATAM ---
        
        await m.reply_photo(
            photo=(VERIFY_IMG),
            caption=caption, # <-- Yahan badlaav kiya gaya hai
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return 
    # --- 'NOTCOPY' FIX KHATAM ---
        
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        status = get_status()
        aks=await message.reply_text(f"<b>🔥 ʏᴇs {status},\nʜᴏᴡ ᴄᴀɴ ɪ ʜᴇʟᴘ ʏᴏᴜ??</b>")
        await asyncio.sleep(600)
        await aks.delete()
        await m.delete()
        if (str(message.chat.id)).startswith("-100") and not await db.get_chat(message.chat.id):
            total=await client.get_chat_members_count(message.chat.id)
            try:
                group_link = await message.chat.export_invite_link()
            except ChatAdminRequired:
                group_link = "N/A (Bot is not admin)"
            user = message.from_user.mention if message.from_user else "Dear" 
            await client.send_message(LOG_CHANNEL, script.NEW_GROUP_TXT.format(temp.B_LINK, message.chat.title, message.chat.id, message.chat.username, group_link, total, user))       
            await db.add_chat(message.chat.id, message.chat.title)
        return 
        
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.NEW_USER_TXT.format(temp.B_LINK, message.from_user.id, message.from_user.mention))
        
    if len(message.command) != 2:
        buttons = [[
            InlineKeyboardButton('⇆ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘs ⇆', url=f'http://t.me/{temp.U_NAME}?startgroup=start')
        ],[
            InlineKeyboardButton('⚙ ꜰᴇᴀᴛᴜʀᴇs', callback_data='features'),
            InlineKeyboardButton('💸 ᴘʀᴇᴍɪᴜᴍ', callback_data='buy_premium')
        ],[
            InlineKeyboardButton('🚫 ᴇᴀʀɴ ᴍᴏɴᴇʏ ᴡɪᴛH ʙᴏᴛ 🚫', callback_data='earn')
        ]]   
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_text(script.START_TXT.format(message.from_user.mention, get_status(), message.from_user.id),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    # --- YEH HAI AAPKA 3-CHANNEL FSUB LOGIC (LAYOUT FIX KE SAATH) ---
    if AUTH_CHANNEL or AUTH_CHANNEL_2 or AUTH_CHANNEL_3:
        
        status_1, status_2, status_3 = await check_fsub_status(client, message.from_user.id)
        
        all_joined = (status_1 in ["MEMBER", "PENDING"] and
                      status_2 in ["MEMBER", "PENDING"] and
                      status_3 == "MEMBER")
        
        if all_joined:
            pass 
        
        else:
            btn = []
            fsub_row_1 = []
            
            if status_1 == "NOT_JOINED":
                try:
                    link_1 = await client.create_chat_invite_link(int(AUTH_CHANNEL), creates_join_request=True)
                    fsub_row_1.append(
                        InlineKeyboardButton("Request Channel 1 🔗", url=link_1.invite_link)
                    )
                except Exception as e:
                    logger.error(f"Channel 1 link error: {e}")
                    
            if status_2 == "NOT_JOINED":
                try:
                    link_2 = await client.create_chat_invite_link(int(AUTH_CHANNEL_2), creates_join_request=True)
                    fsub_row_1.append(
                        InlineKeyboardButton("Request Channel 2 🔗", url=link_2.invite_link)
                    )
                except Exception as e:
                    logger.error(f"Channel 2 link error: {e}")
            
            if fsub_row_1:
                btn.append(fsub_row_1)

            fsub_row_2 = []
            
            if status_3 == "NOT_JOINED":
                try:
                    # FIX: Invite link ab 'export_chat_invite_link' se banega
                    invite_link_3 = await client.export_chat_invite_link(AUTH_CHANNEL_3)
                    fsub_row_2.append(
                        InlineKeyboardButton("Join Channel 3 🔗", url=invite_link_3)
                    )
                except Exception as e:
                    logger.error(f"Channel 3 link error (exporting link): {e}")
                    if isinstance(AUTH_CHANNEL_3, str) and AUTH_CHANNEL_3.startswith("@"):
                         fsub_row_2.append(
                            InlineKeyboardButton("Join Channel 3 🔗", url=f"https://t.me/{AUTH_CHANNEL_3.replace('@', '')}")
                        )
            
            if fsub_row_2:
                btn.append(fsub_row_2)

            if len(message.command) > 1 and message.command[1] != "subscribe":
                btn.append(
                    [InlineKeyboardButton("Try Again ♻️", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")]
                )

            if not btn:
                await message.reply_text("**Kuch error aa gaya hai.**\nBot admin nahi hai Fsub channel(s) mein, ya invite links galat hain.")
                return

            await message.reply_text(
                "**File lene ke liye, pehle upar diye gaye sabhi channel(s) ko join karein (ya request karein).**\n\n"
                "Sabhi steps poore karke **Try Again** button dabayein.",
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return
    # --- NAYA FSUB LOGIC YAHAN KHATAM HOTA HAI ---


    if len(message.command) == 2 and message.command[1] in ["subscribe", "error", "okay", "help", "buy_premium"]:
        if message.command[1] == "buy_premium":
            btn = [[
                InlineKeyboardButton('📸 sᴇɴᴅ sᴄʀᴇᴇɴsʜᴏᴛ 📸', url=USERNAME)
            ],[
                InlineKeyboardButton('🗑 ᴄʟᴏsᴇ 🗑', callback_data='close_data')
            ]]            
            await message.reply_photo(
                photo=(QR_CODE),
                caption=script.PREMIUM_TEXT.format(message.from_user.mention),
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return
        buttons = [[
            InlineKeyboardButton('⇆ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘs ⇆', url=f'http://t.me/{temp.U_NAME}?startgroup=start')
        ],[
            InlineKeyboardButton('⚙ ꜰᴇᴀᴛᴜʀᴇs', callback_data='features'),
            InlineKeyboardButton('💸 ᴘʀᴇᴍɪᴜᴍ', callback_data='buy_premium')
        ],[
            InlineKeyboardButton('🚫 ᴇᴀʀɴ ᴍᴏɴᴇʏ ᴡɪᴛʜ ʙᴏᴛ 🚫', callback_data='earn')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_text(
            text=script.START_TXT.format(message.from_user.mention, get_status(), message.from_user.id),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    data = message.command[1]
    try:
        pre, grp_id, file_id = data.split('_', 2)
    except:
        pre, grp_id, file_id = "", 0, data
             
    user_id = m.from_user.id
    if not await db.has_premium_access(user_id):
        grp_id = int(grp_id)
        
        # --- YEH HAI NAYA VERIFICATION FIX ---
        settings = await get_settings(grp_id)
        verify_gap_seconds = settings.get('verify_time', TWO_VERIFY_GAP) 
        
        # Pehli verification (Link 1) check karein
        is_link_1_valid = await db.is_user_verified(user_id, verify_gap_seconds) 
        
        # Doosri verification (Link 2) check karein
        is_link_2_valid = await db.is_user_verified_second(user_id, verify_gap_seconds)
        
        # Decide karein kaunsa link dikhana hai (True = Link 2, False = Link 1)
        # Yeh 'True' tabhi hoga jab dono link expired honge aur Link 1 aakhri baar use hua tha.
        is_second_shortener = await db.use_second_shortener(user_id, verify_gap_seconds)
        
        # Naya Logic: Verification link tabhi dikhayein jab DONO link invalid hon
        if settings.get("is_verify", IS_VERIFY) and not is_link_1_valid and not is_link_2_valid:
        # --- FIX KHATAM ---
        
            verify_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
            await db.create_verify_id(user_id, verify_id)
            temp.CHAT[user_id] = grp_id
            verify = await get_shortlink(f"https://telegram.me/{temp.U_NAME}?start=notcopy_{user_id}_{verify_id}_{file_id}", grp_id, is_second_shortener)
            buttons = [[
                InlineKeyboardButton(text="✅️ ᴠᴇʀɪғʏ ✅️", url=verify),
                InlineKeyboardButton(text="⁉️ ʜᴏᴡ ᴛᴏ ᴠᴇʀɪғʏ ⁉️", url=settings['tutorial'])
            ],[
                InlineKeyboardButton("😁 ʙᴜʏ ꜱᴜʙꜱᴄʀɪᴘᴛɪᴏN - ɴᴏ ɴᴇᴇᴅ ᴛᴏ ᴠᴇʀɪғʏ 😁", callback_data='buy_premium')
            ]]
            reply_markup=InlineKeyboardMarkup(buttons)            
            msg = script.SECOND_VERIFICATION_TEXT if is_second_shortener else script.VERIFICATION_TEXT
            d = await m.reply_text(
                text=msg.format(message.from_user.mention, get_status()),
                protect_content = False,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML
            )
            await asyncio.sleep(300) 
            await d.delete()
            return
            
    # --- YEH HAI AAPKA NAYA FSUB 4 (POST-VERIFY) CHECK ---
    if not await db.has_premium_access(user_id) and AUTH_CHANNEL_4:
        fsub_4_status = await check_fsub_4_status(client, user_id)
        
        if fsub_4_status == "NOT_JOINED":
            try:
                invite_link = await client.create_chat_invite_link(int(AUTH_CHANNEL_4), creates_join_request=True)
                btn = [
                    [InlineKeyboardButton(f"{AUTH_CHANNEL_4_TEXT}", url=invite_link.invite_link)],
                    [InlineKeyboardButton("Try Again ♻️", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")]
                ]
                
                await message.reply_photo(
                    photo=(VERIFY_IMG),
                    caption=f"**Aakhri Step!**\n\nFile lene ke liye, kripya neeche diye gaye channel ko join karein. Phir 'Try Again' button dabayein.",
                    reply_markup=InlineKeyboardMarkup(btn),
                    parse_mode=enums.ParseMode.HTML
                )
                return # File mat bhejho
            
            except Exception as e:
                logger.error(f"FSub 4 link generation error: {e}")
                pass # Error aaye toh file bhej do (fail-safe)
    # --- FSUB 4 CHECK KHATAM ---
            
    if data and data.startswith("allfiles"):
        _, key = data.split("_", 1)
        files = temp.FILES_ID.get(key)
        if not files:
            await message.reply_text("<b>⚠️ ᴀʟʟ ꜰɪʟᴇs ɴᴏᴛ ꜰᴏᴜɴᴅ ⚠️</b>")
            return
        for file in files:
            user_id= message.from_user.id 
            grp_id = temp.CHAT.get(user_id)
            settings = await get_settings(int(grp_id))
            CAPTION = settings['caption']
            f_caption = CAPTION.format(
                file_name = file.file_name,
                file_size = get_size(file.file_size),
                file_caption=file.caption
            )
            btn=[[
                InlineKeyboardButton("✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f'stream#{file.file_id}')
            ]]
            await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file.file_id,
                caption=f_caption,
                protect_content=settings['file_secure'],
                reply_markup=InlineKeyboardMarkup(btn)
            )
        return

    files_ = await get_file_details(file_id)           
    if not files_:
        try:
            pre, file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")).split("_", 1)
            files_ = await get_file_details(file_id)
            if not files_:
                return await message.reply('<b>⚠️ ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ ⚠️</b>')
        except:
            return await message.reply('<b>⚠️ ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ / ʟɪɴᴋ ᴇxᴘɪʀᴇᴅ ⚠️</b>')
            
    files = files_[0]
    settings = await get_settings(int(grp_id))
    CAPTION = settings['caption']
    f_caption = CAPTION.format(
        file_name = files.file_name,
        file_size = get_size(files.file_size),
        file_caption=files.caption
    )
    
    btn = [[
        InlineKeyboardButton("✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f'stream#{file_id}')
    ]]

    d=await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=settings['file_secure'],
        reply_markup=InlineKeyboardMarkup(btn)
    )
    await asyncio.sleep(3600)
    await d.delete()
    
    await client.send_message(
        chat_id=message.from_user.id,
        text="<b>⚠️ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛᴇᴅ ᴍᴏᴠɪᴇ ꜰɪʟᴇ ɪs ᴅᴇʟᴇᴛᴇᴅ, ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪɴ ʙᴏᴛ, ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴀɢᴀɪɴ ᴛʜᴇɴ sᴇᴀʀᴄʜ ᴀɢᴀɪɴ ☺️</b>"
    )

@Client.on_message(filters.command('delete'))
async def delete(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply('ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ... 😑')
        return
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("ᴘʀᴏᴄᴇssɪɴɢ...⏳", quote=True)
    else:
        await message.reply('Reply to file with /delete which you want to delete', quote=True)
        return
    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit('<b>ᴛʜɪs ɪs ɴᴏᴛ sᴜᴘᴘᴏʀᴛᴇᴅ ꜰɪʟᴇ ꜰᴏʀᴍᴀᴛ</b>')
        return
    
    file_id, file_ref = unpack_new_file_id(media.file_id)
    result = await Media.collection.delete_one({
        '_id': file_id,
    })
    if result.deleted_count:
        await msg.edit('<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>')
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
            })
        if result.deleted_count:
            await msg.edit('<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>')
        else:
            result = await Media.collection.delete_many({
                'file_name': media.file_name,
                'file_size': media.file_size,
                'mime_type': media.mime_type
            })
            if result.deleted_count:
                await msg.edit('<b>ꜰɪʟᴇ ɪs sᴜᴄᴄᴇssꜰᴜʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ꜰʀᴏᴍ ᴅᴀᴛᴀʙᴀsᴇ 💥</b>')
            else:
                await msg.edit('<b>ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ</b>')

@Client.on_message(filters.command('deleteall'))
async def delete_all_index(bot, message):
    files = await Media.count_documents()
    if int(files) == 0:
        return await message.reply_text('Not have files to delete')
    btn = [[
            InlineKeyboardButton(text="ʏᴇs", callback_data="all_files_delete")
        ],[
            InlineKeyboardButton(text="ᴄᴀɴᴄᴇʟ", callback_data="close_data")
        ]]
    if message.from_user.id not in ADMINS:
        await message.reply('ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴḍ... 😑')
        return
    await message.reply_text('<b>ᴛʜɪs ᴡɪʟʟ ᴅᴇʟᴇᴛᴇ ᴀʟʟ ɪɴᴅᴇxᴇᴅ ꜰɪʟᴇs.\nᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ??</b>', reply_markup=InlineKeyboardMarkup(btn))

@Client.on_message(filters.command('settings'))
async def settings(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply("<b>💔 ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪN ʏᴏᴜ ᴄᴀɴ'ᴛ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ...</b>")
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<code>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ.</code>")
    grp_id = message.chat.id
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    settings = await get_settings(grp_id)
    title = message.chat.title
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
                InlineKeyboardButton('ʟɪɴᴋ' if settings["link"] else 'ʙᴜᴛᴛᴏɴ', callback_data=f'setgs#link#{settings["link"]}#{str(grp_id)}')
            ],[
                InlineKeyboardButton('ᴠᴇʀɪғʏ', callback_data=f'setgs#is_verify#{settings["is_verify"]}#{grp_id}'),
                InlineKeyboardButton('ᴏɴ ✔️' if settings["is_verify"] else 'ᴏғғ ✗', callback_data=f'setgs#is_verify#{settings["is_verify"]}#{grp_id}')
            ],[
                InlineKeyboardButton('☕️ ᴄʟᴏsᴇ ☕️', callback_data='close_data')
            ]]
            await message.reply_text(
                text=f"ᴄʜᴀɴɢᴇ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ <b>'{title}'</b> ᴀs ʏᴏᴜʀ ᴡɪsʜ ✨",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML
            )
    else:
        await message.reply_text('<b>ꜱᴏᴍᴇᴛʜɪɴɢ ᴡᴇɴᴛ ᴡʀᴏɴɢ</b>')

@Client.on_message(filters.command('set_template'))
async def save_template(client, message):
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    try:
        template = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("Command Incomplete!")    
    await save_group_settings(grp_id, 'template', template)
    await message.reply_text(f"Successfully changed template for {title} to\n\n{template}", disable_web_page_preview=True)
    
@Client.on_message(filters.command("send"))
async def send_msg(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply('<b>ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ...</b>')
        return
    if message.reply_to_message:
        target_ids = message.text.split(" ")[1:]
        if not target_ids:
            await message.reply_text("<b>ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴠɪᴅᴇ ᴏɴᴇ ᴏʀ ᴍᴏʀᴇ ᴜꜱᴇʀ ɪᴅꜱ ᴀꜱ ᴀ ꜱᴘᴀᴄᴇ...</b>")
            return
        out = "\n\n"
        success_count = 0
        try:
            users = await db.get_all_users()
            for target_id in target_ids:
                try:
                    user = await bot.get_users(target_id)
                    out += f"{user.id}\n"
                    await message.reply_to_message.copy(int(user.id))
                    success_count += 1
                except Exception as e:
                    out += f"‼️ ᴇʀʀᴏʀ ɪɴ ᴛʜɪꜱ ɪᴅ - <code>{target_id}</code> <code>{str(e)}</code>\n"
            await message.reply_text(f"<b>✅️ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴍᴇꜱꜱᴀɢᴇ ꜱᴇɴᴛ ɪɴ `{success_count}` ɪᴅ\n<code>{out}</code></b>")
        except Exception as e:
            await message.reply_text(f"<b>‼️ ᴇʀʀᴏʀ - <code>{e}</code></b>")
    else:
        await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴀꜱ ᴀ ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇꜱꜱᴀɢᴇ, ꜰᴏʀ ᴇɢ - <code>/send userid1 userid2</code></b>")

@Client.on_message(filters.regex("#request"))
async def send_request(bot, message):
    try:
        request = message.text.split(" ", 1)[1]
    except:
        await message.reply_text("<b>‼️ ʏᴏᴜʀ ʀᴇǫᴜᴇsᴛ ɪs ɪɴᴄᴏᴍᴘʟᴇᴛᴇ</b>")
        return
    buttons = [[
        InlineKeyboardButton('👀 ᴠɪᴇᴡ ʀᴇǫᴜᴇꜱᴛ 👀', url=f"{message.link}")
    ],[
        InlineKeyboardButton('⚙ sʜᴏᴡ ᴏᴘᴛɪᴏɴ ⚙', callback_data=f'show_options#{message.from_user.id}#{message.id}')
    ]]
    sent_request = await bot.send_message(REQUEST_CHANNEL, script.REQUEST_TXT.format(message.from_user.mention, message.from_user.id, request), reply_markup=InlineKeyboardMarkup(buttons))
    btn = [[
         InlineKeyboardButton('✨ ᴠɪᴇᴡ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ✨', url=f"{sent_request.link}")
    ]]
    await message.reply_text("<b>✅ sᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ʏᴏᴜʀ ʀᴇǫᴜᴇꜱᴛ ʜᴀꜱ ʙᴇᴇN ᴀᴅᴅᴇᴅ, ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ ꜱᴏᴍᴇᴛɪᴍᴇ...</b>", reply_markup=InlineKeyboardMarkup(btn))

@Client.on_message(filters.command("search"))
async def search_files(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply('Only the bot owner can use this command... 😑')
        return
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, this command won't work in groups. It only works in my PM!</b>")  
    try:
        keyword = message.text.split(" ", 1)[1]
    except IndexError:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, give me a keyword along with the command to delete files.</b>")
    files, total = await get_bad_files(keyword)
    if int(total) == 0:
        await message.reply_text('<i>I could not find any files with this keyword 😐</i>')
        return 
    file_names = "\n\n".join(f"{index + 1}. {item['file_name']}" for index, item in enumerate(files))
    file_data = f"🚫 Your search - '{keyword}':\n\n{file_names}"    
    with open("file_names.txt", "w") as file:
        file.write(file_data)
    await message.reply_document(
        document="file_names.txt",
        caption=f"<b>♻️ ʙʏ ʏᴏᴜʀ ꜱᴇᴀʀᴄʜ, ɪ ꜰᴏᴜɴᴅ - <code>{total}</code> ꜰɪʟᴇs</b>",
        parse_mode=enums.ParseMode.HTML
    )
    os.remove("file_names.txt")

@Client.on_message(filters.command("deletefiles"))
async def deletemultiplefiles(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply('ᴏɴʟʏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ... 😑')
        return
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>ʜᴇʏ {message.from_user.mention}, ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴡᴏɴ'ᴛ ᴡᴏʀᴋ ɪɴ ɢʀᴏᴜᴘs. ɪᴛ ᴏɴʟʏ ᴡᴏʀᴋs ᴏɴ ᴍʏ ᴘᴍ !!</b>")
    else:
        pass
    try:
        keyword = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(f"<b>ʜᴇʏ {message.from_user.mention}, ɢɪᴠᴇ ᴍᴇ ᴀ ᴋᴇʏᴡᴏʀᴅ ᴀʟᴏɴɢ ᴡɪᴛʜ ᴛʜᴇ ᴄᴏᴍᴍᴀɴᴅ ᴛᴏ ᴅᴇʟᴇᴛᴇ ꜰɪʟᴇs.</b>")
    files, total = await get_bad_files(keyword)
    if int(total) == 0:
        await message.reply_text('<i>ɪ ᴄᴏᴜʟᴅ ɴᴏᴛ ꜰɪɴᴅ ᴀɴʏ ꜰɪʟᴇs ᴡɪᴛʜ ᴛʜɪs ᴋᴇʏᴡᴏʀᴅ 😐</i>')
        return 
    btn = [[
       InlineKeyboardButton("ʏᴇs, ᴄᴏɴᴛɪɴᴜᴇ ✅", callback_data=f"killfilesak#{keyword}")
       ],[
       InlineKeyboardButton("ɴᴏ, ᴀʙᴏʀᴛ ᴏᴘᴇʀᴀᴛɪᴏɴ 😢", callback_data="close_data")
    ]]
    await message.reply_text(
        text=f"<b>ᴛᴏᴛᴀʟ ꜰɪʟᴇs ꜰᴏᴜɴᴅ - <code>{total}</code>\n\nᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ?\n\nɴᴏᴛᴇ:- ᴛʜɪs ᴄᴏᴜʟᴅ ʙᴇ ᴀ ᴅᴇsᴛʀᴜᴄᴛɪᴠᴇ ᴀᴄᴛɪᴏN!!</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.command("del_file"))
async def delete_files(bot, message):
    if message.from_user.id not in ADMINS:
        await message.reply('Only the bot owner can use this command... 😑')
        return
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, this command won't work in groups. It only works on my PM!</b>")    
    try:
        keywords = message.text.split(" ", 1)[1].split(",")
    except IndexError:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, give me keywords separated by commas along with the command to delete files.</b>")   
    deleted_files_count = 0
    not_found_files = []
    for keyword in keywords:
        result = await Media.collection.delete_many({'file_name': keyword.strip()})
        if result.deleted_count:
            deleted_files_count += 1
        else:
            not_found_files.append(keyword.strip())
    if deleted_files_count > 0:
        await message.reply_text(f'<b>{deleted_files_count} file successfully deleted from the database 💥</b>')
    if not_found_files:
        await message.reply_text(f'<b>Files not found in the database - <code>{", ".join(not_found_files)}</code></b>')

@Client.on_message(filters.command('set_caption'))
async def save_caption(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        caption = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("Command Incomplete!")
    await save_group_settings(grp_id, 'caption', caption)
    await message.reply_text(f"Successfully changed caption for {title} to\n\n{caption}", disable_web_page_preview=True) 
    
@Client.on_message(filters.command('set_tutorial'))
async def save_tutorial(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        tutorial = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text("<b>Command Incomplete!!\n\nuse like this -</b>\n\n<code>/set_caption https://t.me/Aksbackup</code>")    
    await save_group_settings(grp_id, 'tutorial', tutorial)
    await message.reply_text(f"<b>Successfully changed tutorial for {title} to</b>\n\n{tutorial}", disable_web_page_preview=True)
    
@Client.on_message(filters.command('set_shortner'))
async def set_shortner(c, m):
    grp_id = m.chat.id
    title = m.chat.title
    if not await is_check_admin(c, grp_id, m.from_user.id):
        return await m.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')        
    if len(m.text.split()) < 3:
        await m.reply("<b>Use this command like this - \n\n`/set_shortner tnshort.net 06b24eb6bbb025713cd522fb3f696b6d5de11354`</b>")
        return        
    sts = await m.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    chat_type = m.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await m.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        URL = m.command[1]
        API = m.command[2]
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://{URL}/api?api={API}&url=https://telegram.dog/Aksbackup') as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP Error {resp.status}")
                data = await resp.json()
        
        if data.get('status') == 'success':
            SHORT_LINK = data['shortenedUrl']
        else:
            raise Exception(f"API Error: {data.get('message', 'Unknown error')}")
            
        await save_group_settings(grp_id, 'shortner', URL)
        await save_group_settings(grp_id, 'api', API)
        await m.reply_text(f"<b><u>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ ʏᴏᴜʀ sʜᴏʀᴛɴᴇʀ ɪs ᴀᴅᴅᴇᴅ</u>\n\nᴅᴇᴍᴏ - {SHORT_LINK}\n\nsɪᴛᴇ - `{URL}`\n\nᴀᴘɪ - `{API}`</b>", quote=True)
        user_id = m.from_user.id
        user_info = f"@{m.from_user.username}" if m.from_user.username else f"{m.from_user.mention}"
        link = (await c.get_chat(m.chat.id)).invite_link
        grp_link = f"[{m.chat.title}]({link})"
        log_message = f"#New_Shortner_Set_For_1st_Verify\n\nName - {user_info}\nId - `{user_id}`\n\nDomain name - {URL}\nApi - `{API}`\nGroup link - {grp_link}"
        await c.send_message(LOG_API_CHANNEL, log_message, disable_web_page_preview=True)
    except Exception as e:
        await save_group_settings(grp_id, 'shortner', SHORTENER_WEBSITE)
        await save_group_settings(grp_id, 'api', SHORTENER_API)
        await m.reply_text(f"<b><u>💢 ᴇʀʀᴏʀ ᴏᴄᴄᴏᴜʀᴇᴅ!!</u>\n\nᴀᴜᴛᴏ ᴀᴅᴅᴇᴅ ʙᴏᴛ ᴏᴡɴᴇʀ ᴅᴇꜰᴜʟᴛ sʜᴏʀᴛɴᴇʀ\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴄᴏʀʀᴇᴄᴛ ꜰᴏʀᴍᴀᴛ ᴏʀ ᴀᴅᴅ ᴠᴀʟɪᴅ sʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ ɴᴀᴍᴇ & ᴀᴘɪ\n\nʏᴏᴜ ᴄᴀɴ ᴀʟsᴏ ᴄᴏɴᴛᴀᴄᴛ ᴏᴜʀ <a href=https://t.me/aks_bot_support>sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ</a> ꜰᴏʀ sᴏʟᴠᴇ ᴛʜɪs ɪssᴜᴇ...\n\nʟɪᴋᴇ -\n\n`/set_shortner mdiskshortner.link e7beb3c8f756dfa15d0bec495abc65f58c0dfa95`\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>", quote=True)

@Client.on_message(filters.command('set_shortner_2'))
async def set_shortner_2(c, m):
    grp_id = m.chat.id
    title = m.chat.title
    if not await is_check_admin(c, grp_id, m.from_user.id):
        return await m.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    if len(m.text.split()) < 3:
        await m.reply("<b>Use this command like this - \n\n`/set_shortner_2 tnshort.net 06b24eb6bbb025713cd522fb3f696b6d5de11354`</b>")
        return
    sts = await m.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    chat_type = m.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await m.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        URL = m.command[1]
        API = m.command[2]
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://{URL}/api?api={API}&url=https://telegram.dog/Aksbackup') as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP Error {resp.status}")
                data = await resp.json()
        
        if data.get('status') == 'success':
            SHORT_LINK = data['shortenedUrl']
        else:
            raise Exception(f"API Error: {data.get('message', 'Unknown error')}")
            
        await save_group_settings(grp_id, 'shortner_two', URL)
        await save_group_settings(grp_id, 'api_two', API)
        await m.reply_text(f"<b><u>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ ʏᴏᴜʀ sʜᴏʀᴛɴᴇʀ ɪs ᴀᴅᴅᴇᴅ</u>\n\nᴅᴇᴍᴏ - {SHORT_LINK}\n\nsɪᴛᴇ - `{URL}`\n\nᴀᴘɪ - `{API}`</b>", quote=True)
        user_id = m.from_user.id
        user_info = f"@{m.from_user.username}" if m.from_user.username else f"{m.from_user.mention}"
        link = (await c.get_chat(m.chat.id)).invite_link
        grp_link = f"[{m.chat.title}]({link})"
        log_message = f"#New_Shortner_Set_For_2nd_Verify\n\nName - {user_info}\nId - `{user_id}`\n\nDomain name - {URL}\nApi - `{API}`\nGroup link - {grp_link}"
        await c.send_message(LOG_API_CHANNEL, log_message, disable_web_page_preview=True)
    except Exception as e:
        await save_group_settings(grp_id, 'shortner_two', SHORTENER_WEBSITE2)
        await save_group_settings(grp_id, 'api_two', SHORTENER_API2)
        await m.reply_text(f"<b><u>💢 ᴇʀʀᴏʀ ᴏᴄᴄᴏᴜʀᴇᴅ!!</u>\n\nᴀᴜᴛᴏ ᴀᴅᴅᴇᴅ ʙᴏᴛ ᴏᴡɴᴇʀ ᴅᴇꜰᴜʟᴛ sʜᴏʀᴛɴᴇʀ\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇɴ ᴜsᴇ ᴄᴏʀʀᴇᴄᴛ ꜰᴏʀᴍᴀᴛ ᴏʀ ᴀᴅᴅ ᴠᴀʟɪᴅ sʜᴏʀᴛʟɪɴᴋ ᴅᴏᴍᴀɪɴ ɴᴀᴍᴇ & ᴀᴘɪ\n\nʏᴏᴜ ᴄᴀɴ ᴀʟsᴏ ᴄᴏɴᴛᴀᴄᴛ ᴏᴜʀ <a href=https://t.me/aks_bot_support>sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ</a> ꜰᴏʀ sᴏʟᴠᴇ ᴛʜɪs ɪssᴜᴇ...\n\nʟɪᴋᴇ -\n\n`/set_shortner_2 mdiskshortner.link e7beb3c8f756dfa15d0bec495abc65f58c0dfa95`\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>", quote=True)

@Client.on_message(filters.command('set_log_channel'))
async def set_log(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    if len(message.text.split()) == 1:
        await message.reply("<b>Use this command like this - \n\n`/set_log_channel -100******`</b>")
        return
    sts = await message.reply("<b>♻️ ᴄʜᴇᴄᴋɪɴɢ...</b>")
    await asyncio.sleep(1.2)
    await sts.delete()
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    try:
        log = int(message.text.split(" ", 1)[1])
    except IndexError:
        return await message.reply_text("<b><u>ɪɴᴠᴀɪʟᴅ ꜰᴏʀᴍᴀᴛ!!</u>\n\nᴜsᴇ ʟɪᴋᴇ ᴛʜɪs - `/set_log_channel -100xxxxxxxx`</b>")
    except ValueError:
        return await message.reply_text('<b>ᴍᴀᴋᴇ sᴜʀᴇ ɪᴅ ɪs ɪɴᴛᴇɢᴇʀ...</b>')
    try:
        t = await client.send_message(chat_id=log, text="<b>ʜᴇʏ ᴡʜᴀᴛ's ᴜᴘ!!</b>")
        await asyncio.sleep(3)
        await t.delete()
    except Exception as e:
        return await message.reply_text(f'<b><u>😐 ᴍᴀᴋᴇ sᴜʀᴇ ᴛʜɪs ʙᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ...</u>\n\n💔 ᴇʀʀᴏʀ - <code>{e}</code></b>')
    await save_group_settings(grp_id, 'log', log)
    await message.reply_text(f"<b>✅ sᴜᴄᴄᴇssꜰᴜʟʟʏ sᴇᴛ ʏᴏᴜʀ ʟᴏɢ ᴄʜᴀɴɴᴇʟ ꜰᴏʀ {title}\n\nɪᴅ - `{log}`</b>", disable_web_page_preview=True)
    
    user_id = message.from_user.id
    user_info = f"@{message.from_user.username}" if message.from_user.username else f"{message.from_user.mention}"
    link = (await client.get_chat(message.chat.id)).invite_link
    grp_link = f"[{message.chat.title}]({link})"
    log_message = f"#New_Log_Channel_Set\n\nName - {user_info}\nId - `{user_id}`\n\nLog channel id - `{log}`\nGroup link - {grp_link}"
    await client.send_message(LOG_API_CHANNEL, log_message, disable_web_page_preview=True)  

@Client.on_message(filters.command('details'))
async def all_settings(client, message):
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")
    settings = await get_settings(grp_id)
    text = f"""<b><u>⚙️ ʏᴏᴜʀ sᴇᴛᴛɪɴɢs ꜰᴏʀ -</u> {title}

<u>✅️ 1sᴛ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇʀ ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings["shortner"]}`
ᴀᴘɪ - `{settings["api"]}`

<u>✅️ 2ɴᴅ ᴠᴇʀɪꜰʏ sʜᴏʀᴛɴᴇR ɴᴀᴍᴇ/ᴀᴘɪ</u>
ɴᴀᴍᴇ - `{settings["shortner_two"]}`
ᴀᴘɪ - `{settings["api_two"]}`

📝 ʟᴏɢ ᴄʜᴀɴɴᴇʟ ɪᴅ - `{settings['log']}`

📍 ᴛᴜᴛᴏʀɪᴀʟ ʟɪɴᴋ - {settings['tutorial']}

🎯 ɪᴍᴅʙ ᴛᴇᴍᴘʟᴀᴛᴇ - `{settings['template']}`

📂 ꜰɪʟᴇ ᴄᴀᴘᴛɪᴏN - `{settings['caption']}`</b>"""
    
    btn = [[
        InlineKeyboardButton("ʀᴇꜱᴇᴛ ᴅᴀᴛᴀ", callback_data="reset_grp_data")
    ],[
        InlineKeyboardButton("ᴄʟᴏsᴇ", callback_data="close_data")
    ]]
    reply_markup=InlineKeyboardMarkup(btn)
    dlt=await message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    await asyncio.sleep(300)
    await dlt.delete()

# --- YEH HAI AAPKA NAYA '/set_verify_time' COMMAND ---
@Client.on_message(filters.command('set_verify_time'))
async def set_verify_time(client, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("<b>ʏᴏᴜ ᴀʀᴇ ᴀɴᴏɴʏᴍᴏᴜꜱ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ...</b>")
    
    chat_type = message.chat.type
    if chat_type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return await message.reply_text("<b>ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ɢʀᴏᴜᴘ...</b>")       
    
    grp_id = message.chat.id
    title = message.chat.title
    if not await is_check_admin(client, grp_id, message.from_user.id):
        return await message.reply_text('<b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪN ɪɴ ᴛʜɪꜱ ɢʀᴏᴜᴘ</b>')
    
    try:
        # Command se time string extract karein (jaise "12 hours" ya "7 days")
        time_string = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(
            "<b>Command poora nahi hai!</b>\n\n"
            "Example:\n"
            "<code>/set_verify_time 6 hours</code>\n"
            "<code>/set_verify_time 1 day</code>\n"
            "<code>/set_verify_time 30 mins</code>\n"
            "<code>/set_verify_time 0</code> (Hamesha verify karne ke liye)"
        )
    
    # Time string ko seconds mein convert karein
    seconds = await get_seconds(time_string)
    
    if seconds == 0 and time_string != "0" and not time_string.startswith("0"): # Agar 'get_seconds' invalid input ko 0 return karta hai
         return await message.reply_text(
            "<b>Galat time format!</b>\n\n"
            "Use karein: m>min</code>, <code>hour</code>, <code>day</code>, <code>month</code>\n"
            "Example: <code>/set_verify_time 12 hours</code>"
        )

    # Database mein naya time (seconds mein) save karein
    await save_group_settings(grp_id, 'verify_time', seconds)
    
    reply_text = (
        f"<b>✅ Verification time {title} ke liye set ho gaya hai.</b>\n\n"
        f"<b>Naya Time:</b> <code>{time_string}</code> ({seconds} seconds)\n\n"
    )
    
    if seconds == 0:
        reply_text += "<i>Note: Aapne <code>0</code> set kiya hai. Ab users ko har file ke liye verify karna padega.</i>"
    
    await message.reply_text(reply_text)
# --- COMMAND KHATAM ---


# --- YEH HAI AAPKA 'COMBINED HANDLER' KA FIX ---
@Client.on_chat_member_updated()
async def combined_chat_member_handler(client: Client, member: ChatMemberUpdated):
    
    # --- Logic 1: FSUB Cleanup (AUTH_CHANNEL 1, 2, aur 4 ke liye) ---
    try:
        # --- FIX: AUTH_CHANNEL_4 ko bhi check karein ---
        if str(member.chat.id) in [str(AUTH_CHANNEL), str(AUTH_CHANNEL_2), str(AUTH_CHANNEL_4)]: 
            if member.new_chat_member and member.new_chat_member.user:
                user_id = member.new_chat_member.user.id
                channel_id = member.chat.id
                new_status = member.new_chat_member.status

                if new_status not in [enums.ChatMemberStatus.RESTRICTED]:
                    # --- FIX: Sahi DB function names ka istemaal karein ---
                    if await db.is_join_request_pending(user_id, channel_id):
                        await db.remove_join_request(user_id, channel_id)
                        logger.info(f"[ADV-FSUB] User {user_id} (New Status: {new_status}) ko pending list se remove kar diya.")

    except Exception as e:
        logger.error(f"FSUB Cleanup error: {e}")
    
    # --- Logic 2: Referral Handler ---
    try:
        if (
            member.invite_link
            and member.new_chat_member
            and member.new_chat_member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.RESTRICTED]
            and (not member.old_chat_member or member.old_chat_member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED])
        ):
            new_user_id = member.new_chat_member.user.id
            chat_id = member.chat.id
            
            invite_link_str = member.invite_link.invite_link
            referrer = await db.get_user_by_referral_link(invite_link_str)
            
            if not referrer:
                return  # Normal invite link

            referrer_id = referrer['referrer_id']
            
            if new_user_id == referrer_id:
                return # Self-referral
                
            if await db.has_been_referred_in_group(new_user_id, chat_id):
                return  # This user has already been referred in this group
                
            await db.log_referral(new_user_id, referrer_id, chat_id)
            await db.increment_referral_count(referrer_id)
            new_count = await db.get_referral_count(referrer_id)
            
            referrer_mention = ""
            try:
                referrer_user = await client.get_users(referrer_id)
                referrer_mention = referrer_user.mention
            except Exception:
                # --- FIX: 'await' add karein ---
                referrer_data = await db.get_user_data(referrer_id) 
                if referrer_data and 'name' in referrer_data:
                    referrer_name = escape(referrer_data['name'])
                    referrer_mention = f"<a href='tg://user?id={referrer_id}'>{referrer_name}</a>"
                else:
                    referrer_mention = f"<a href='tg://user?id={referrer_id}'>Referrer</a>"
            
            if new_count >= REFERRAL_TARGET:
                expiry_time = datetime.now() + timedelta(days=PREMIUM_MONTH_DURATION)
                # --- FIX: Sahi DB function ka istemaal karein ---
                await db.update_one(
                    {"id": referrer_id},
                    {"$set": {"expiry_time": expiry_time, "referral_count": 0}}
                )
                try:
                    await client.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 <b>Congratulations, {referrer_mention}!</b> 🎉\n\nYou have successfully invited {new_count} users and earned <b>1 Month of Free Premium Access</b>! Your referral count has been reset."
                    )
                except (UserIsBlocked, PeerIdInvalid):
                    pass
            else:
                try:
                    await client.send_message(
                        chat_id=referrer_id,
                        text=f"👍 <b>Referral Success!</b>\n\nUser {member.new_chat_member.user.mention} joined the group.\n\nYour new referral count is <b>{new_count} / {REFERRAL_TARGET}</b>."
                    )
                except (UserIsBlocked, PeerIdInvalid):
                    pass
    except Exception as e:
        logger.error(f"Referral (welcome_handler) error: {e}")
