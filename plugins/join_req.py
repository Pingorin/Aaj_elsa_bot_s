from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
# --- YEH BADLAAV HAI: Sabhi 4 channels import karein ---
from info import ADMINS, AUTH_CHANNEL, AUTH_CHANNEL_2, AUTH_CHANNEL_4, LOG_CHANNEL
import logging

logger = logging.getLogger(__name__)

# --- YEH BADLAAV HAI: Hum ek list bana rahe hain taaki code crash na ho ---
# Yeh sirf un channels ko add karega jo None nahi hain.
ADV_FSUB_CHANNELS = []
if AUTH_CHANNEL:
    ADV_FSUB_CHANNELS.append(AUTH_CHANNEL)
if AUTH_CHANNEL_2:
    ADV_FSUB_CHANNELS.append(AUTH_CHANNEL_2)
if AUTH_CHANNEL_4:
    ADV_FSUB_CHANNELS.append(AUTH_CHANNEL_4)


# --- YEH BADLAAV HAI: Filter ab poori list ko sunega ---
@Client.on_chat_join_request(filters.chat(ADV_FSUB_CHANNELS))
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    """
    Sabhi 'Advanced Fsub' channels se request aane par DB mein add karega.
    """
    try:
        await db.add_join_request(message.from_user.id, message.chat.id)
    except Exception as e:
        logger.error(f"Join request add karte hue error: {e}")


# --- YEH BADLAAV HAI: Filter ab poori list ko sunega ---
@Client.on_chat_member_updated(filters.chat(ADV_FSUB_CHANNELS))
async def chat_member_update_handler(client: Client, update: ChatMemberUpdated):
    """
    Sabhi 'Advanced Fsub' channels par Approve/Dismiss hone par DB se remove karega.
    """
    if not update.new_chat_member:
        return

    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id
    
    try:
        if update.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            return  # Pending hai, kuch nahi karna

        # Agar status MEMBER ya LEFT hua, toh pending list se hata do
        await db.remove_join_request(user_id, chat_id)

        # Logging Logic
        if update.old_chat_member and update.old_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            
            admin = update.from_user 
            user = update.new_chat_member.user 
            chat_title = update.chat.title

            if update.new_chat_member.status == enums.ChatMemberStatus.LEFT:
                if admin.id == user.id:
                    log_message = (
                        f"**Join Request Cancelled 🤷‍♂️**\n\n"
                        f"**Channel:** {chat_title}\n"
                        f"**User:** {user.mention} (ID: `{user.id}`)\n"
                        f"*(User ne khud cancel kiya)*"
                    )
                else:
                    log_message = (
                        f"**Join Request Dismissed 👎**\n\n"
                        f"**Channel:** {chat_title}\n"
                        f"**User:** {user.mention} (ID: `{user.id}`)\n"
                        f"**Admin:** {admin.mention} (ID: `{admin.id}`)"
                    )
                await client.send_message(LOG_CHANNEL, log_message)

            elif update.new_chat_member.status == enums.ChatMemberStatus.MEMBER:
                await client.send_message(
                    LOG_CHANNEL,
                    f"**Join Request Approved 👍**\n\n"
                    f"**Channel:** {chat_title}\n"
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

