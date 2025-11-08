from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNEL
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
    Component 2: Database Cleanup (Approve ya Dismiss hone par)
    """
    if not update.new_chat_member:
        return

    # Hum us user ka ID lenge jiska status badla hai
    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id

    try:
        # Jab user request bhejta hai, tab naya status 'RESTRICTED' (pending) hota hai.
        # Humein is status ko अनदेखा (ignore) karna hai.
        if update.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            return  # User abhi bhi pending hai, use list se *nahi* hatana hai

        # Agar status 'RESTRICTED' nahi hai, (matlab MEMBER ya LEFT hua)
        # toh woh ab 'pending' nahi hai. Use list se hata do.
        await db.remove_join_request(user_id, chat_id)

    except Exception as e:
        logger.error(f"Pending list se user {user_id} ko remove karne me error: {e}")


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    """
    Admin command: Pending list ko poori tarah clear karne ke liye.
    """
    await db.del_join_req()    
    await message.reply("<b>⚙️ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇQᴜᴇꜱᴛ ʟᴏɢꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")

