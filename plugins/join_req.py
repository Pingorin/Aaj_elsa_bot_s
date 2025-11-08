from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNEL, LOG_CHANNEL  # <-- Yahan LOG_CHANNEL import karein
import logging

# Logger set up karein
logger = logging.getLogger(__name__)


@Client.on_chat_join_request(filters.chat(AUTH_CHANNEL))
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    """
    Component 1: Jab user request bhejta hai,
    use 'pending' list mein add kar do.
    """
    try:
        await db.add_join_request(message.from_user.id, message.chat.id)
    except Exception as e:
        logger.error(f"Join request add karte hue error: {e}")


@Client.on_chat_member_updated(filters.chat(AUTH_CHANNEL))
async def chat_member_update_handler(client: Client, update: ChatMemberUpdated):
    """
    Handles Approve, Dismiss, and Cancel events.
    1. Logs the action.
    2. Removes user from the 'pending' DB.
    """
    if not update.new_chat_member:
        return

    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id
    
    try:
        # --- YEH HAI AAPKA GOAL 3 (Pending list se Remove karna) ---
        
        # Step 1: Agar user 'pending' ban raha hai, toh DB se remove *mat* karo.
        if update.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            return  # User abhi request kar raha hai, DB mein add ho chuka hai, bas.

        # Step 2: Agar user 'pending' nahi raha (MEMBER ya LEFT hua),
        # toh use 'pending' DB se remove kar do.
        await db.remove_join_request(user_id, chat_id)

        # --- YEH HAI AAPKA GOAL 1 & 2 (Log Message Bhejna) ---
        
        # Hum sirf tab log karenge jab status 'pending' (RESTRICTED) se badla ho.
        if update.old_chat_member and update.old_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            
            admin = update.from_user # Admin/User jisne action liya
            user = update.new_chat_member.user # User jispar action hua

            # Case A: Admin ne "Dismiss" kiya (ya user ne khud "Cancel" kiya)
            if update.new_chat_member.status == enums.ChatMemberStatus.LEFT:
                
                # Pata lagao ki admin ne kiya ya user ne khud
                if admin.id == user.id:
                    log_message = (
                        f"**Join Request Cancelled 🤷‍♂️**\n\n"
                        f"**User:** {user.mention} (ID: `{user.id}`)\n"
                        f"*(User ne khud cancel kiya)*"
                    )
                else:
                    log_message = (
                        f"**Join Request Dismissed 👎**\n\n"
                        f"**User:** {user.mention} (ID: `{user.id}`)\n"
                        f"**Admin:** {admin.mention} (ID: `{admin.id}`)"
                    )
                
                await client.send_message(LOG_CHANNEL, log_message)

            # Case B: Admin ne "Approve" kiya
            elif update.new_chat_member.status == enums.ChatMemberStatus.MEMBER:
                await client.send_message(
                    LOG_CHANNEL,
                    f"**Join Request Approved 👍**\n\n"
                    f"**User:** {user.mention} (ID: `{user.id}`)\n"
                    f"**Admin:** {admin.mention} (ID: `{admin.id}`)"
                )

    except Exception as e:
        logger.error(f"chat_member_update_handler mein error: {e}")


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    """
    Admin command: Pending list ko poori tarah clear karne ke liye.
    """
    await db.del_join_req()    
    await message.reply("<b>⚙️ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇQᴜᴇꜱᴛ ʟᴏɢꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")

