from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_CHANNEL
import asyncio

# (Aapka on_chat_join_request wala code yahan rahega...)
@Client.on_chat_join_request(filters.chat(AUTH_CHANNEL))
async def join_reqs_handler(client: Client, message: ChatJoinRequest):
    try:
        await db.add_join_request(message.from_user.id, message.chat.id)
    except Exception as e:
        print(f"Error saving join request: {e}")


# --- YEH HAI AAPKA MUKHYA FUNCTION ---

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

    # --- NAYA LOGIC ---

    # Case 1: User ne request bheji (Old=None, New=RESTRICTED)
    # Ya user abhi bhi pending hai
    if message.new_chat_member.status == enums.ChatMemberStatus.RESTRICTED:
        # User abhi 'pending' state mein hai.
        # Use database se *nahi* hatana hai.
        return

    # Case 2: User ka status 'pending' nahi raha
    # (Matlab admin ne approve kiya, dismiss kiya, ya user ne cancel kiya)
    #
    # Old=RESTRICTED, New=MEMBER (Approved)
    # Old=RESTRICTED, New=LEFT (Dismissed ya Cancelled)
    #
    # Dono hi sooraton mein, woh ab 'pending' nahi hai.
    # Isliye hum unhe 'join_requests' (pending) collection se remove kar denge.
    try:
        # Yeh function user ko 'pending' list se delete kar dega.
        # Yahi aapka "Approve" aur "Dismiss" dono ka logic handle kar lega,
        # kyunki dono hi cases mein user ab 'pending' nahi rehta.
        await db.remove_join_request(user_id, chat_id)
    except Exception as e:
        print(f"Error cleaning up join request: {e}")


# (Aapka /delreq admin command yahan rahega...)
@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    await db.del_join_req()    
    await message.reply("<b>⚙️ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴘᴇɴᴅɪɴɢ ᴊᴏɪɴ ʀᴇQᴜᴇꜱᴛ ʟᴏɢꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")

