import logging
import urllib.parse  # <-- YEH IMPORT ZAROORI HAI
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
# --- Sabhi 4 channels imported hain ---
from info import (
    AUTH_CHANNEL, AUTH_CHANNEL_2, AUTH_CHANNEL_3, AUTH_CHANNEL_4, 
    LONG_IMDB_DESCRIPTION, IS_VERIFY
)
from imdb import Cinemagoer
import asyncio
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram import enums
import pytz
import time
import re
import os 
from shortzy import Shortzy # (Aapki request ke mutaabik rakha gaya hai)
from datetime import datetime, timedelta, timezone
from typing import Any
from database.users_chats_db import db
import aiohttp # (Ise rehne dein, yeh doosre functions mein kaam aa sakta hai)

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

# --- YAHAN SE AAPKA FSUB CODE SHURU HOTA HAI ---
# (Yeh poora code block sahi hai, ismein koi badlaav nahi)

async def _get_fsub_status(bot, user_id, channel_id):
    """(Internal) Ek single 'Advanced' channel ka status check karta hai (API + DB)."""
    try:
        member = await bot.get_chat_member(channel_id, user_id)

        if member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return "MEMBER"
        if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
            return "NOT_JOINED"
        if member.status == enums.ChatMemberStatus.RESTRICTED:
            return "PENDING"

    except UserNotParticipant:
        if await db.is_join_request_pending(user_id, channel_id):
            return "PENDING"
        else:
            return "NOT_JOINED"
            
    except Exception as e:
        logger.error(f"Advanced Fsub check error for {channel_id}: {e}")
        return "NOT_JOINED"
    
    return "NOT_JOINED" # Fallback

async def _get_normal_fsub_status(bot, user_id, channel_id):
    """(Internal) Ek single 'Normal' channel ka status (sirf member) check karta hai."""
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        
        if member.status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            return "MEMBER"
        else:
            return "NOT_JOINED" # (Left, Banned, etc. sab 'not joined' hain)
            
    except UserNotParticipant:
        return "NOT_JOINED" # User member nahi hai
            
    except Exception as e:
        logger.error(f"Normal Fsub check error for {channel_id}: {e}")
        return "NOT_JOINED" # Safety fallback

async def check_fsub_status(bot, user_id):
    """
    Pehle teen channels (FSub 1, 2, 3) ka status check karta hai.
    Returns: (status1, status2, status3)
    """
    
    # Pehla channel (Advanced)
    if not AUTH_CHANNEL:
        status_1 = "MEMBER"
    else:
        status_1 = await _get_fsub_status(bot, user_id, AUTH_CHANNEL)
    
    # Doosra channel (Advanced)
    if not AUTH_CHANNEL_2:
        status_2 = "MEMBER"
    else:
        status_2 = await _get_fsub_status(bot, user_id, AUTH_CHANNEL_2)
        
    # Teesra channel (Normal)
    if not AUTH_CHANNEL_3:
        status_3 = "MEMBER"
    else:
        status_3 = await _get_normal_fsub_status(bot, user_id, AUTH_CHANNEL_3)
    
    return status_1, status_2, status_3

async def check_fsub_4_status(bot, user_id):
    """
    Sirf chauthe (post-verify) channel ka status check karta hai.
    Returns: "MEMBER", "PENDING", "NOT_JOINED"
    """
    if not AUTH_CHANNEL_4:
        return "MEMBER" # Agar set nahi hai, toh maan lo joined hai
    
    # Chautha channel "Advanced" (request) type ka hai
    return await _get_fsub_status(bot, user_id, AUTH_CHANNEL_4)
# --- YAHAN FSUB LOGIC KHATAM HOTA HAI ---


async def get_poster(query, bulk=False, id=False, file=None):
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
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
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
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
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
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
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS.update({group_id: settings})
    return settings
    
async def save_group_settings(group_id, key, value):
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    current = await get_settings(group_id)
    current.update({key: value})
    temp.SETTINGS.update({group_id: current})
    await db.update_settings(group_id, current)
    
def get_size(size):
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

def get_name(name):
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    regex = re.sub(r'@\w+', '', name)
    return regex

def list_to_str(k):
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    else:
        return ', '.join(f'{elem}, ' for elem in k)

#--- YEH HAI AAPKE 'get_shortlink' FUNCTION KA NAYA AUR SAHI FIX ---
async def get_shortlink(link, grp_id, is_second_shortener=False):
    settings = await get_settings(grp_id)    
    if not IS_VERIFY:
        return link # Agar verify off hai, toh original link return karo
        
    api_key, site_key = ('api_two', 'shortner_two') if is_second_shortener else ('api', 'shortner')
    api, site = settings[api_key], settings[site_key]        
    
    if not api or not site:
        logger.warning(f"Shortener API/Site (is_second: {is_second_shortener}) settings nahi mili.")
        return link
        
    # Link ko encode karein taaki special characters (?) error na dein
    encoded_link = urllib.parse.quote(link)
    
    # --- YEH HAI ASLI FIX: Hum 'shortzy' library ka istemaal nahi karenge ---
    # Hum 'commands.py' ki tarah direct API call karenge
    
    api_url = f"https://{site}/api?api={api}&url={encoded_link}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    logger.error(f"Shortener HTTP Error {resp.status} for {site}")
                    return link # API fail hui, original link return karo
                
                data = await resp.json()
        
        if data.get('status') == 'success':
            return data['shortenedUrl']
        else:
            # softurl.in 'message' bhejta hai, doosre 'msg' bhej sakte hain
            error_message = data.get('message', data.get('msg', 'Unknown API error'))
            logger.error(f"Shortener API Error: {error_message} for {site}")
            return link # API ne error diya, original link return karo
            
    except Exception as e:
        logger.error(f"Aiohttp error in get_shortlink: {e}")
        return link # Koi aur error, original link return karo
# --- 'get_shortlink' FIX KHATAM ---


def get_file_id(message: "Message") -> Any:
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
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
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    media = get_file_id(media_msg)
    return getattr(media, "file_unique_id", "")[:6]

def get_status():
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
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
    # (Yeh function poora waise hi rahega, koi badlaav nahi)
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
    except:
        return False

# --- YEH HAI AAPKA NAYA 'get_seconds' FUNCTION ---
async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""
        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1
        unit = ts[index:].lstrip() # unit will be "hours", "day", "mins" etc.
        if value:
            value = int(value)
        return value, unit

    value, unit = extract_value_and_unit(time_string)
    
    unit_lower = unit.lower()
    
    if unit_lower.startswith('s'): # sec, second, seconds
        return value
    elif unit_lower.startswith('min'): # min, minute, minutes
        return value * 60
    elif unit_lower.startswith('hour'): # hour, hours
        return value * 3600
    elif unit_lower.startswith('day'): # day, days
        return value * 86400
    elif unit_lower.startswith('month'): # month, months
        return value * 86400 * 30
    elif unit_lower.startswith('year'): # year, years
        return value * 86400 * 365
    elif value == 0 and unit_lower == "": # Handle "0"
        return 0
    else:
        return 0 # Invalid format
# --- FIX KHATAM ---

# --- YEH HAI AAPKA NAYA 'get_readable_time' FUNCTION ---
def get_readable_time(seconds):
    if seconds == 0:
        return "0 seconds" # Agar time 0 hai
        
    periods = [('month', 2592000), ('day', 86400), ('hour', 3600), ('minute', 60), ('second', 1)]
    result_parts = []
    
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value = int(seconds // period_seconds)
            seconds = seconds % period_seconds
            
            # 's' add karein agar value 1 se zyada hai
            if period_value > 1:
                period_name += 's'
            
            result_parts.append(f"{period_value} {period_name}")
    
    # Sabhi parts ko join karein (jaise "1 day, 6 hours")
    # Hum sirf sabse bada part dikhayenge (jaise "7 days" ya "6 hours")
    if result_parts:
        return result_parts[0] # Sirf sabse bada unit dikhayein, jaise "7 days"
    
    return "less than a second" # Fallback
# --- FIX KHATAM ---
