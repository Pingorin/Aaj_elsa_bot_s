from aiohttp import web
from .route import routes
from asyncio import sleep 
from datetime import datetime
from database.users_chats_db import db
from info import LOG_CHANNEL

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

async def check_expired_premium(client):
    while True:
        try:
            # Get users whose plan has expired
            data = await db.get_expired(datetime.now())
            for user in data:
                user_id = user["id"]
                await db.remove_premium_access(user_id)
                try:
                    user_info = await client.get_users(user_id)
                    await client.send_message(
                        chat_id=user_id,
                        text=f"<b>ʜᴇʏ {user_info.mention},\n\nʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ᴇxᴘɪʀᴇᴅ, ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜsɪɴɢ ᴏᴜʀ sᴇʀᴠɪᴄᴇ 😊\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛᴀᴋᴇ ᴛʜᴇ ᴘʀᴇᴍɪᴜᴍ ᴀɢᴀɪɴ, ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ /plan ꜰᴏʀ ᴛʜᴇ ᴅᴇᴛᴀɪʟs ᴏꜰ ᴛʜᴇ ᴘʟᴀɴs...</b>"
                    )
                    await client.send_message(LOG_CHANNEL, text=f"<b>#Premium_Expire\n\nUser name: {user_info.mention}\nUser id: <code>{user_id}</code></b>")
                except Exception as e:
                    print(f"Error notifying expired user {user_id}: {e}")
                await sleep(0.5) # Rate limit for notifications
        except Exception as e:
            print(f"Error in check_expired_premium: {e}")
            
        # Check every 5 minutes
        await sleep(300)
