from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, LOG_CHANNEL
import logging

logger = logging.getLogger(__name__)

# Note: Humne specific channel filter hata diya hai taaki 
# yeh "Custom FSub Channels" (jo /settings me set kiye gaye hain) ke liye bhi kaam kare.

@Client.on_chat_join_request()
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    """
    Handles Join Requests for ANY channel where the bot is Admin.
    Logic:
    1. User requests to join.
    2. We log this in Database (user_id, chat_id).
    3. We DO NOT approve. The user remains 'Pending'.
    4. When user clicks 'Try Again' in bot, utils.py checks this DB entry.
    """
    try:
        # Request aate hi DB me entry karo
        await db.add_join_request(message.from_user.id, message.chat.id)
        # logger.info(f"Join Request logged: User {message.from_user.id} -> Chat {message.chat.id}")
    except Exception as e:
        logger.error(f"Join Request DB Error: {e}")

@Client.on_chat_member_updated()
async def chat_member_update_handler(client: Client, update: ChatMemberUpdated):
    """
    Clean up Database if user status changes (Approved, Left, Banned).
    """
    if not update.new_chat_member:
        return

    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id
    
    try:
        # Agar status ABHI BHI Restricted/Pending hai, to DB se mat hatao
        if update.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            return 

        # Agar status MEMBER (Approved), LEFT (Cancel/Left), ya BANNED ho gaya
        # To iska matlab ab wo "Pending Request" state me nahi hai.
        # DB se hata do taaki agar wo dubara aaye to naye सिरे se check ho.
        await db.remove_join_request(user_id, chat_id)

        # --- Logging Logic (Optional: Sirf Log Channel ke liye) ---
        # Agar aap chahte hain ki logs aayein jab request approve/cancel ho:
        if LOG_CHANNEL and update.old_chat_member and update.old_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            
            admin = update.from_user 
            user = update.new_chat_member.user 
            chat_title = update.chat.title
            
            log_msg = ""

            if update.new_chat_member.status == enums.ChatMemberStatus.LEFT:
                if admin and user and admin.id == user.id:
                    log_msg = f"**User {user.mention} cancelled their join request for {chat_title}.**"
                elif user:
                    log_msg = f"**Join request for {user.mention} in {chat_title} was declined.**"

            elif update.new_chat_member.status == enums.ChatMemberStatus.MEMBER:
                 if user:
                    log_msg = f"**User {user.mention} was approved in {chat_title}.**"
            
            if log_msg:
                try:
                    await client.send_message(LOG_CHANNEL, log_msg)
                except:
                    pass

    except Exception as e:
        logger.error(f"Chat Member Update Error: {e}")

@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    """
    Clears the Join Request database cache.
    Use this if DB gets too big or buggy.
    """
    await db.del_join_req()    
    await message.reply("<b>⚙️ Successfully cleared Join Request Cache.</b>")
