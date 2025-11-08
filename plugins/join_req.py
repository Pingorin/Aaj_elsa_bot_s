from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
# --- YEH BADLAAV HAI: Dono channel aur LOG_CHANNEL import karein ---
from info import ADMINS, AUTH_CHANNEL, AUTH_CHANNEL_2, LOG_CHANNEL
import logging

# Logger set up karein
logger = logging.getLogger(__name__)


# --- YEH BADLAAV HAI: Dono channels ko list mein daalein ---
@Client.on_chat_join_request(filters.chat([AUTH_CHANNEL, AUTH_CHANNEL_2]))
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    """
    Component 1: Dono channels se request aane par DB mein add karega.
    """
    try:
        # message.chat.id se yeh pata chal jaayega ki kaun se channel ki request hai
        await db.add_join_request(message.from_user.id, message.chat.id)
    except Exception as e:
        logger.error(f"Join request add karte hue error: {e}")


# --- YEH BADLAAV HAI: Dono channels ko list mein daalein ---
@Client.on_chat_member_updated(filters.chat([AUTH_CHANNEL, AUTH_CHANNEL_2]))
async def chat_member_update_handler(client: Client, update: ChatMemberUpdated):
    """
    Dono channels par Approve/Dismiss hone par DB se remove karega aur log karega.
    """
    if not update.new_chat_member:
        return

    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id
    
    try:
        # Step 1: Agar user 'pending' ban raha hai, toh DB se remove *mat* karo.
        if update.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            return  # User abhi request kar raha hai, DB mein add ho chuka hai, bas.

        # Step 2: Agar user 'pending' nahi raha (MEMBER ya LEFT hua),
        # toh use 'pending' DB se remove kar do.
        await db.remove_join_request(user_id, chat_id)

        # --- YEH BADLAAV HAI: Logging mein channel ka naam add karein ---
        
        # Hum sirf tab log karenge jab status 'pending' (RESTRICTED) se badla ho.
        if update.old_chat_member and update.old_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            
            admin = update.from_user # Admin/User jisne action liya
            user = update.new_chat_member.user # User jispar action hua
            chat_title = update.chat.title # Channel ka naam

            # Case A: Admin ne "Dismiss" kiya (ya user ne khud "Cancel" kiya)
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

            # Case B: Admin ne "Approve" kiya
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

