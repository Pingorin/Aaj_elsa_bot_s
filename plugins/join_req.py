import logging
from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import AUTH_CHANNEL

logger = logging.getLogger(__name__)

# Component 1: Jab user "Request to Join" button dabata hai
# (Yeh function sahi hai)
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


# Component 2: Database Cleanup (FIXED)
@Client.on_chat_member_updated(filters.chat(AUTH_CHANNEL))
async def handle_status_change(client: Client, member: ChatMemberUpdated):
    """
    Trigger: Jab bhi user ka status channel mein badalta hai.
    Action: User ko 'pending' database se remove karein.
    """
    if not member.new_chat_member or not member.new_chat_member.user:
        return

    user_id = member.new_chat_member.user.id
    channel_id = member.chat.id
    
    # --- FIX: 'if member.old_chat_member:' wala check hata diya hai ---
    # Ab yeh har status change par check karega (Approve, Dismiss, Cancel, Leave)
    
    try:
        # Agar user 'pending' DB mein tha, toh use remove karein
        if await db.is_request_pending(user_id, channel_id):
            await db.remove_pending_request(user_id, channel_id)
            logger.info(f"[ADV-FSUB] User {user_id} ko pending list se remove kar diya gaya hai (Status change).")
    except Exception as e:
        logger.error(f"Pending request cleanup mein error: {e}")
