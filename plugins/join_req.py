from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNEL
import logging

# Logger सेट अप करें
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
        logger.error(f"Join request add karte hue error: {e}")


@Client.on_chat_member_updated(filters.chat(AUTH_CHANNEL))
async def chat_member_update_handler(client: Client, update: ChatMemberUpdated):
    """
    Component 2: Database Cleanup (Approve या Dismiss होने पर)
    """
    if not update.new_chat_member:
        return

    # हम उस यूज़र का ID लेंगे जिसका स्टेटस बदला है
    user_id = update.new_chat_member.user.id
    chat_id = update.chat.id

    try:
        # जब यूज़र रिक्वेस्ट भेजता है, तब नया स्टेटस 'RESTRICTED' (पेंडिंग) होता है।
        # हमें इस स्टेटस को अनदेखा (ignore) करना है।
        if update.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
            return  # यूज़र अभी भी पेंडिंग है, उसे लिस्ट से *नहीं* हटाना है

        # अगर स्टेटस 'RESTRICTED' नहीं है, इसका मतलब यूज़र या तो:
        # 1. 'MEMBER' बन गया (Approve हो गया)
        # 2. 'LEFT' हो गया (Dismiss या Cancel हो गया)
        #
        # दोनों ही मामलों में, वह अब 'pending' नहीं है।
        # इसलिए हम उसे 'pending' लिस्ट से हटा देंगे।
        
        await db.remove_join_request(user_id, chat_id)

    except Exception as e:
        logger.error(f"Pending list se user {user_id} ko remove karne me error: {e}")


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    """
    Admin command: Pending list ko poori tarah clear karne ke liye.
    """
    await db.del_join_req()    
    await message.reply("<b>⚙️ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴘᴇɴᴅɪNG ᴊᴏɪɴ ʀᴇQᴜᴇꜱᴛ ʟᴏɢꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")
