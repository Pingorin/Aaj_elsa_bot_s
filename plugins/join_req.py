import logging
from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated # ChatMemberUpdated is no longer used but safe to keep
from database.users_chats_db import db
from info import AUTH_CHANNEL

logger = logging.getLogger(__name__)

# Component 1: Jab user "Request to Join" button dabata hai
# (Yeh function sahi hai aur yahan rehna chahiye)
@Client.on_chat_join_request(filters.chat(AUTH_CHANNEL))
async def handle_join_request(client: Client, message: ChatJoinRequest):
    """
    Trigger: Jab user join request bhejta hai.
    Action: User ko 'pending' database mein add karein.
    """
    user_id = message.from_user.id
    channel_id = message.chat.id
    try:
        if not await db.is_request_pending(user_id, channel_id):
            await db.add_pending_request(user_id, channel_id)
            logger.info(f"[ADV-FSUB] User {user_id} ki request {channel_id} ke liye pending mein add ho gayi hai.")
    except Exception as e:
        logger.error(f"Join request handle karte waqt error: {e}")


# --- FIX: 'handle_status_change' (on_chat_member_updated) function ko yahan se poori tarah se DELETE kar diya gaya hai ---
# Iska logic ab 'commands.py' mein 'combined_chat_member_handler' ke andar hai.
