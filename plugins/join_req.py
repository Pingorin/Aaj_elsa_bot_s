from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNEL
import asyncio
import logging  # --- FIX: logging को इम्पोर्ट किया गया ---

# --- FIX: logger को सेट अप किया गया ---
logger = logging.getLogger(__name__)


@Client.on_chat_join_request(filters.chat(AUTH_CHANNEL))
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    """
    Component 1: जब यूज़र रिक्वेस्ट भेजता है,
    उसे 'pending' लिस्ट में ऐड कर दो।
    """
    try:
        await db.add_join_request(message.from_user.id, message.chat.id)
    except Exception as e:
        # --- FIX: print की जगह logger का इस्तेमाल ---
        logger.error(f"Join request add karte hue error: {e}")


@Client.on_chat_member_updated(filters.chat(AUTH_CHANNEL))
async def chat_member_update_handler(client: Client, message: ChatMemberUpdated):
    """
    Database cleanup:
    Jab user ka status badle (approve, decline, cancel),
    use 'pending' list se remove kar do.
    """
    if not message.new_chat_member:
        return  # Koi naya status nahi hai, kuch mat karo

    user_id = message.new_chat_member.user.id
    chat_id = message.chat.id

    # --- लॉजिक सही है ---
    if message.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
        # यूज़र अभी 'pending' state mein hai.
        # Use database se *nahi* hatana hai.
        return

    # अगर स्टेटस 'RESTRICTED' नहीं है (MEMBER या LEFT है),
    # तो उसे 'pending' लिस्ट से हटा दो।
    try:
        await db.remove_join_request(user_id, chat_id)
    except Exception as e:
        # --- FIX: print की जगह logger का इस्तेमाल ---
        logger.error(f"Pending list se user {user_id} ko remove karne me error: {e}")


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    """
    Admin command: Pending list ko poori tarah clear karne ke liye.
    """
    await db.del_join_req()    
    await message.reply("<b>⚙️ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇQᴜᴇꜱᴛ ʟᴏɢꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")
