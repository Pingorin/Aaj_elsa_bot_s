from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from info import ADMINS, LOG_CHANNEL, USERNAME
from database.users_chats_db import db
# --- YEH HAIN NAYE IMPORTS ---
from database.ia_filterdb import (
    Media, get_db_size_primary, get_db_size_secondary, get_db_size_third,
    get_files_count_primary, get_files_count_secondary, get_files_count_third
)
from utils import get_size, temp
from Script import script
from datetime import datetime
import psutil
import time

@Client.on_message(filters.new_chat_members & filters.group)
async def save_group(bot, message):
    check = [u.id for u in message.new_chat_members]
    if temp.ME in check:
        if (str(message.chat.id)).startswith("-100") and not await db.get_chat(message.chat.id):
            total=await bot.get_chat_members_count(message.chat.id)
            user = message.from_user.mention if message.from_user else "Dear" 
            try:
                group_link = await message.chat.export_invite_link()
            except Exception:
                group_link = "N/A (Bot not admin)"
            await bot.send_message(LOG_CHANNEL, script.NEW_GROUP_TXT.format(temp.B_LINK, message.chat.title, message.chat.id, message.chat.username, group_link, total, user), disable_web_page_preview=True)  
            await db.add_chat(message.chat.id, message.chat.title)
            btn = [[
                InlineKeyboardButton('⚡️ sᴜᴘᴘᴏʀᴛ ⚡️', url=USERNAME)
            ]]
            reply_markup=InlineKeyboardMarkup(btn)
            await bot.send_message(
                chat_id=message.chat.id,
                text=f"<b>☤ ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ ɪɴ {message.chat.title}\n\n🤖 ᴅᴏɴ’ᴛ ꜰᴏʀɢᴇᴛ ᴛᴏ ᴍᴀᴋᴇ ᴍᴇ ᴀᴅᴍɪɴ 🤖\n\n㊝ ɪꜰ ʏᴏᴜ ʜᴀᴠᴇ ᴀɴʏ ᴅᴏᴜʙᴛ ʏᴏᴜ ᴄʟᴇᴀʀ ɪᴛ ᴜsɪɴɢ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴs ㊜</b>",
                reply_markup=reply_markup
            )

@Client.on_message(filters.command('leave') & filters.user(ADMINS))
async def leave_a_chat(bot, message):
    r = message.text.split(None)
    if len(message.command) == 1:
        return await message.reply('<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ʟɪᴋᴇ ᴛʜɪꜱ `/leave -100******`</b>')
    if len(r) > 2:
        reason = message.text.split(None, 2)[2]
        chat = message.text.split(None, 2)[1]
    else:
        chat = message.command[1]
        reason = "ɴᴏ ʀᴇᴀꜱᴏɴ ᴘʀᴏᴠɪᴅᴇᴅ..."
    try:
        chat = int(chat)
    except:
        chat = chat
    try:
        btn = [[
            InlineKeyboardButton('⚡️ ᴏᴡɴᴇʀ ⚡️', url=USERNAME)
        ]]
        reply_markup=InlineKeyboardMarkup(btn)
        await bot.send_message(
            chat_id=chat,
            text=f'😞 ʜᴇʟʟᴏ ᴅᴇᴀʀ,\nᴍʏ ᴏᴡɴᴇʀ ʜᴀꜱ ᴛᴏʟᴅ ᴍᴇ ᴛᴏ ʟᴇᴀᴠᴇ ꜰʀᴏᴍ ɢʀᴏᴜᴘ ꜱᴏ ɪ ɢᴏ 😔\n\n🚫 ʀᴇᴀꜱᴏɴ ɪꜱ - <code>{reason}</code>\n\nɪꜰ ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ᴀᴅᴅ ᴍᴇ ᴀɢᴀɪɴ ᴛʜᴇɴ ᴄᴏɴᴛᴀᴄᴛ ᴍʏ ᴏᴡɴᴇʀ 👇',
            reply_markup=reply_markup,
        )
        await bot.leave_chat(chat)
        await db.delete_chat(chat)
        await message.reply(f"<b>ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʟᴇꜰᴛ ꜰʀᴏᴍ ɢʀᴏᴜᴘ - `{chat}`</b>")
    except Exception as e:
        await message.reply(f'<b>🚫 ᴇʀʀᴏʀ - `{e}`</b>')

@Client.on_message(filters.command('groups') & filters.user(ADMINS))
async def groups_list(bot, message):
    msg = await message.reply('<b>Searching...</b>')
    chats = await db.get_all_chats()
    out = "Groups saved in the database:\n\n"
    count = 1
    async for chat in chats:
        try:
            chat_info = await bot.get_chat(chat['id'])
            members_count = chat_info.members_count if chat_info.members_count else "Unknown"
            out += f"<b>{count}. Title - `{chat['title']}`\nID - `{chat['id']}`\nMembers - `{members_count}`</b>"
            out += '\n\n'
            count += 1
        except Exception:
            # Agar bot group mein nahi hai, toh skip kar do
            pass
    try:
        if count > 1:
            await msg.edit_text(out)
        else:
            await msg.edit_text("<b>No groups found</b>")
    except MessageTooLong:
        with open('chats.txt', 'w+') as outfile:
            outfile.write(out)
        await message.reply_document('chats.txt', caption="<b>List of all groups</b>")

# --- YEH HAI AAPKA NAYA /stats COMMAND ---
@Client.on_message(filters.command('stats') & filters.user(ADMINS) & filters.incoming)
async def get_ststs(bot, message):
    
    msg = await message.reply("`Processing...`")

    # Users DB (DATABASE_URI)
    users_count = await db.total_users_count()
    groups_count = await db.total_chat_count()
    users_db_size = get_size(await db.get_db_size())

    # Media DB 1 (Primary)
    files_db1_count = await get_files_count_primary()
    files_db1_size = get_size(await get_db_size_primary())

    # Media DB 2 (Secondary)
    files_db2_count = await get_files_count_secondary()
    files_db2_size = get_size(await get_db_size_secondary())

    # Media DB 3 (Third)
    files_db3_count = await get_files_count_third()
    files_db3_size = get_size(await get_db_size_third())

    # Total Files
    total_files = files_db1_count + files_db2_count + files_db3_count
    
    # System Stats
    try:
        total_time = time.time() - temp.START_TIME
        uptime = time.strftime("%Hh %Mm %Ss", time.gmtime(total_time))
    except AttributeError:
        uptime = "N/A (Bot Restarting)"
    ram = psutil.virtual_memory().percent
    cpu = psutil.cpu_percent()

    # Naya stats text yahan banayein
    stats_text = f"""
**Bot Statistics** 🤖

**Users & Groups:**
* **Total Users:** `{users_count}`
* **Total Groups:** `{groups_count}`
* **Users DB Size:** `{users_db_size}`

---

**File Databases Stats:**

**🗃️ Primary DB 1 (URI):**
* **Total Files:** `{files_db1_count}`
* **DB Size:** `{files_db1_size}`

**💾 Secondary DB 2 (URI 2):**
* **Total Files:** `{files_db2_count}`
* **DB Size:** `{files_db2_size}`

**🗄️ Third DB 3 (URI 3):**
* **Total Files:** `{files_db3_count}`
* **DB Size:** `{files_db3_size}`

* **✨ Total Indexed Files (All DBs):** `{total_files}`

---

**Server Stats:**
* **Bot Uptime:** `{uptime}`
* **RAM Usage:** `{ram}%`
* **CPU Usage:** `{cpu}%`
"""
    
    await msg.edit_text(stats_text)
