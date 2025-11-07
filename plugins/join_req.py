from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNEL
import asyncio
import logging  # <-- Ise add karein

logger = logging.getLogger(__name__)  # <-- Ise add karein

@Client.on_chat_join_request(filters.chat(AUTH_CHANNEL))
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    """
    Component 1: Jab user join request bhejta hai,
    use database mein 'pending' list mein add kar do.
    """
    try:
        await db.add_join_request(message.from_user.id, message.chat.id)
    except Exception as e:
        logger.error(f"Error saving join request: {e}")  # <-- 'print' ko 'logger.error' se badlein


@Client.on_chat_member_updated(filters.chat(AUTH_CHANNEL))
async def chat_member_update_handler(client: Client, message: ChatMemberUpdated):
    """
    Component 2: Database cleanup.
    Jab user ka status badle (approve, decline, cancel),
    use 'pending' list se remove kar do.
    """
    if not message.new_chat_member:
        return

    user_id = message.new_chat_member.user.id
    chat_id = message.chat.id

    if message.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
        return

    try:
        await db.remove_join_request(user_id, chat_id)
    except Exception as e:
        logger.error(f"Error cleaning up join request: {e}")  # <-- 'print' ko 'logger.error' se badlein


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    """
    Admin command: Pending list ko poori tarah clear karne ke liye.
    """
    await db.del_join_req()    
    await message.reply("<b>⚙️ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇQᴜᴇꜱᴛ ʟᴏɢꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")
