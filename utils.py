import logging
import urllib.parse
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
from info import (
    AUTH_CHANNEL, AUTH_CHANNEL_2, AUTH_CHANNEL_3, AUTH_CHANNEL_4, 
    LONG_IMDB_DESCRIPTION, IS_VERIFY,
    SHORTENER_WEBSITE, SHORTENER_API, 
    SHORTENER_WEBSITE2, SHORTENER_API2, 
    SHORTENER_WEBSITE3, SHORTENER_API3
)
from imdb import Cinemagoer
import asyncio
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram import enums
import pytz
import time
import re
import os 
from datetime import datetime, timedelta, timezone
from typing import Any
from database.users_chats_db import db
import aiohttp 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BANNED = {}
imdb = Cinemagoer() 
 
class temp(object):
    ME = None
    CURRENT=int(os.environ.get("SKIP", 2))
    CANCEL = False
    U_NAME = None
    B_NAME = None
    B_LINK = None
    SETTINGS = {}
    FILES_ID = {}
    USERS_CANCEL = False
    GROUPS_CANCEL = False    
    CHAT = {}
    FSUB_WAITING = {} # Stores state for setting FSub IDs via PM
    SHORTENER_WAITING = {} # Stores state for setting Shortener Details via PM

# --- FSUB HELPER FUNCTIONS ---

async def _get_fsub_status(bot, user_id, channel_id):
    """
    Advanced Fsub Check:
    1. Check API (Member/Admin) -> Return MEMBER
    2. Check API (Pending/Restricted) -> Return PENDING (Allow access)
    3. Check Database (Pending Request) -> Return PENDING (Allow access)
    """
    try:
        member = await bot.get_chat_member(channel_id, user_id)

        # Agar User pehle se Member, Admin ya Owner hai
        if member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return "MEMBER"
        
        # Agar User Banned ya Left hai
        if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
            # DB check karna zaroori hai, kyunki user leave status me ho sakta hai par request pending ho sakti hai
            if await db.is_join_request_pending(user_id, channel_id):
                return "PENDING" # DB me request hai, Access de do
            return "NOT_JOINED"
        
        # Agar Telegram khud status Restricted/Request dikha raha hai
        if member.status == enums.ChatMemberStatus.RESTRICTED:
            return "PENDING" # Access de do

    except UserNotParticipant:
        # User channel me bilkul nahi hai. 
        # Ab Database check karo ki kya usne request bheji thi?
        if await db.is_join_request_pending(user_id, channel_id):
            return "PENDING" # Haan request bheji thi, Access de do
        else:
            return "NOT_JOINED" # Nahi bheji
            
    except Exception as e:
        logger.error(f"Advanced Fsub check error for {channel_id}: {e}")
        # Fallback: DB check
        if await db.is_join_request_pending(user_id, channel_id):
            return "PENDING"
        return "NOT_JOINED"
    
    return "NOT_JOINED"

async def _get_normal_fsub_status(bot, user_id, channel_id):
    """(Internal) Ek single 'Normal' channel ka status (sirf member) check karta hai."""
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        
        if member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return "MEMBER"
        else:
            return "NOT_JOINED"
            
    except UserNotParticipant:
        return "NOT_JOINED"
            
    except Exception as e:
        logger.error(f"Normal Fsub check error for {channel_id}: {e}")
        return "NOT_JOINED"

async def check_fsub_status(bot, user_id, grp_id=None):
    """
    Checks status for Slot 1, 2 (Advanced) and Slot 3 (Normal).
    Prioritizes Group Settings > Global Settings.
    Returns: (status1, status2, status3, id1, id2, id3)
    """
    # Default Globals
    id_1 = AUTH_CHANNEL
    id_2 = AUTH_CHANNEL_2
    id_3 = AUTH_CHANNEL_3
    
    # Agar Group ID mila hai, to DB check karo
    if grp_id:
        settings = await get_settings(grp_id)
        
        # Safe integer conversion for IDs
        custom_id_1 = settings.get('fsub_id_1')
        if custom_id_1:
            try: id_1 = int(custom_id_1)
            except: pass
            
        custom_id_2 = settings.get('fsub_id_2')
        if custom_id_2:
            try: id_2 = int(custom_id_2)
            except: pass
            
        custom_id_3 = settings.get('fsub_id_3')
        if custom_id_3:
            # Normal ID can be username string or int
            id_3 = int(custom_id_3) if str(custom_id_3).lstrip('-').isdigit() else custom_id_3

    # Status Check Logic
    status_1 = "MEMBER"
    if id_1:
        status_1 = await _get_fsub_status(bot, user_id, id_1)
    
    status_2 = "MEMBER"
    if id_2:
        status_2 = await _get_fsub_status(bot, user_id, id_2)
        
    status_3 = "MEMBER"
    if id_3:
        status_3 = await _get_normal_fsub_status(bot, user_id, id_3)
    
    return status_1, status_2, status_3, id_1, id_2, id_3

async def check_fsub_4_status(bot, user_id, grp_id=None):
    """
    Checks status for Slot 4 (Post-Verify/Request).
    """
    id_4 = AUTH_CHANNEL_4
    
    if grp_id:
        settings = await get_settings(grp_id)
        custom_id_4 = settings.get('fsub_id_4')
        if custom_id_4:
            try: id_4 = int(custom_id_4)
            except: pass
        
    if not id_4:
        return "MEMBER", None 
    
    # Slot 4 is strictly Advanced/Request type
    status = await _get_fsub_status(bot, user_id, id_4)
    return status, id_4

# --- END FSUB HELPERS ---

async def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = (query.strip()).lower()
        title = query
        year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1]) 
        else:
            year = None
        movieid = imdb.search_movie(title.lower(), results=10)
        if not movieid:
            return None
        if year:
            filtered=list(filter(lambda k: str(k.get('year')) == str(year), movieid))
            if not filtered:
                filtered = movieid
        else:
            filtered = movieid
        movieid=list(filter(lambda k: k.get('kind') in ['movie', 'tv series'], filtered))
        if not movieid:
            movieid = filtered
        if bulk:
            return movieid
        movieid = movieid[0].movieID
    else:
        movieid = query
    movie = imdb.get_movie(movieid)
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"
    plot = ""
    if not LONG_IMDB_DESCRIPTION:
        plot = movie.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
    else:
        plot = movie.get('plot outline')
    if plot and len(plot) > 800:
        plot = plot[0:800] + "..."

    return {
        'title': movie.get('title'),
        'votes': movie.get('votes'),
        "aka": list_to_str(movie.get("akas")),
        "seasons": movie.get("number of seasons"),
        "box_office": movie.get('box office'),
        'localized_title': movie.get('localized title'),
        'kind': movie.get("kind"),
        "imdb_id": f"tt{movie.get('imdbID')}",
        "cast": list_to_str(movie.get("cast")),
        "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_str(movie.get("countries")),
        "certificates": list_to_str(movie.get("certificates")),
        "languages": list_to_str(movie.get("languages")),
        "director": list_to_str(movie.get("director")),
        "writer":list_to_str(movie.get("writer")),
        "producer":list_to_str(movie.get("producer")),
        "composer":list_to_str(movie.get("composer")) ,
        "cinematographer":list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")),
        "distributors": list_to_str(movie.get("distributors")),
        'release_date': date,
        'year': movie.get('year'),
        'genres': list_to_str(movie.get("genres")),
        'poster': movie.get('full-size cover url'),
        'plot': plot,
        'rating': str(movie.get("rating")),
        'url':f'https://www.imdb.com/title/tt{movieid}'
    }

async def users_broadcast(user_id, message, is_pin):
    try:
        m=await message.copy(chat_id=user_id)
        if is_pin:
            await m.pin(both_sides=True)
        return True, "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await users_broadcast(user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id}-Removed from Database, since deleted account.")
        return False, "Deleted"
    except UserIsBlocked:
        logging.info(f"{user_id} -Blocked the bot.")
        await db.delete_user(user_id)
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        logging.info(f"{user_id} - PeerIdInvalid")
        return False, "Error"
    except Exception as e:
        return False, "Error"

async def groups_broadcast(chat_id, message, is_pin):
    try:
        m = await message.copy(chat_id=chat_id)
        if is_pin:
            try:
                await m.pin()
            except:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return await groups_broadcast(chat_id, message)
    except Exception as e:
        await db.delete_chat(chat_id)
        return "Error"

async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS.update({group_id: settings})
    return settings
    
async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current.update({key: value})
    temp.SETTINGS.update({group_id: current})
    await db.update_settings(group_id, current)
    
def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def get_name(name):
    regex = re.sub(r'@\w+', '', name)
    return regex

def list_to_str(k):
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    else:
        return ', '.join(f'{elem}, ' for elem in k)

# --- 3-STEP 'get_shortlink' FUNCTION ---
async def get_shortlink(link, grp_id, shortener_level: int):
    settings = await get_settings(grp_id)
    
    if shortener_level == 3:
        site = settings.get('shortner_three', SHORTENER_WEBSITE3)
        api = settings.get('api_three', SHORTENER_API3)
    elif shortener_level == 2:
        site = settings.get('shortner_two', SHORTENER_WEBSITE2)
        api = settings.get('api_two', SHORTENER_API2)
    else: # Default or level 1
        site = settings.get('shortner', SHORTENER_WEBSITE)
        api = settings.get('api', SHORTENER_API)

    if not IS_VERIFY or not api or not site:
        return link

    encoded_link = urllib.parse.quote(link)
    api_url = f"https://{site}/api?api={api}&url={encoded_link}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    logger.error(f"Shortener (L{shortener_level}) HTTP Error {resp.status} for {site}")
                    return link 
                
                data = await resp.json()
        
        if data.get('status') == 'success':
            return data.get('shortenedUrl', link)
        else:
            error_message = data.get('message', data.get('msg', 'Unknown API error'))
            logger.error(f"Shortener (L{shortener_level}) API Error: {error_message} for {site}")
            return link 
            
    except Exception as e:
        logger.error(f"Aiohttp error in get_shortlink (L{shortener_level}): {e}")
        return link 

def get_file_id(message: "Message") -> Any:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )    
    if message.media:
        for attr in media_types:
            media = getattr(message, attr, None)
            if media:
                setattr(media, "message_type", attr)
                return media

def get_hash(media_msg: Message) -> str:
    media = get_file_id(media_msg)
    return getattr(media, "file_unique_id", "")[:6]

def get_status():
    tz = pytz.timezone('Asia/Kolkata')
    hour = datetime.now(tz).time().hour
    if 5 <= hour < 12:
        sts = "ɢᴏᴏᴅ ᴍᴏʀɴɪNɢ"
    elif 12 <= hour < 18:
        sts = "ɢᴏᴏᴅ ᴀꜰᴛᴇʀɴᴏᴏN"
    else:
        sts = "ɢᴏᴏᴅ ᴇᴠᴇNɪNɢ"
    return sts

async def is_check_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except:
        return False

async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""
        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1
        unit = ts[index:].lstrip()
        if value:
            value = int(value)
        return value, unit

    value, unit = extract_value_and_unit(time_string)
    
    unit_lower = unit.lower()
    
    if unit_lower.startswith('s'): # sec
        return value
    elif unit_lower.startswith('min'): # min
        return value * 60
    elif unit_lower.startswith('hour'): # hour
        return value * 3600
    elif unit_lower.startswith('day'): # day
        return value * 86400
    elif unit_lower.startswith('month'): # month
        return value * 86400 * 30
    elif unit_lower.startswith('year'): # year
        return value * 86400 * 365
    elif value == 0 and unit_lower == "": # Handle "0"
        return 0
    else:
        return 0 

def get_readable_time(seconds):
    if seconds == 0:
        return "0 seconds"
        
    periods = [('month', 2592000), ('day', 86400), ('hour', 3600), ('minute', 60), ('second', 1)]
    result_parts = []
    
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value = int(seconds // period_seconds)
            seconds = seconds % period_seconds
            
            if period_value > 1:
                period_name += 's'
            
            result_parts.append(f"{period_value} {period_name}")
    
    if result_parts:
        return result_parts[0] 
    
    return "less than a second"

# --- SHORTENER TEST FUNCTION (Added for "Test connected Shorteners") ---
async def check_shortener_status(site, api):
    if not site or not api:
        return "❌ Not Configured"
    
    url = f"https://{site}/api?api={api}&url=https://google.com"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('status') == 'success' or data.get('shortenedUrl'):
                        return "✅ Working"
                    else:
                        return f"⚠️ Error: {data.get('message', 'Invalid Response')}"
                else:
                    return f"❌ HTTP Error: {resp.status}"
    except Exception as e:
        return f"❌ Error: {str(e)}"
