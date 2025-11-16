import re
import os
from os import environ
from pyrogram import enums
from Script import script  # Bot 1 ko bhi text ke liye iski zaroorat padegi
import asyncio
import json
from collections import defaultdict
from pyrogram import Client

id_pattern = re.compile(r'^-?\d+$')
def is_enabled(value, default):
    if value.lower() in ["true", "yes", "1", "enable", "y"]:
        return True
    elif value.lower() in ["false", "no", "0", "disable", "n"]:
        return False
    else:
        return default

# --- Bot 1 (Search Bot) ki Main Settings ---
API_ID = int(environ.get('API_ID', '20638104'))
API_HASH = environ.get('API_HASH', '6c884690ca85d39a4c5ad7c15b194e42')
BOT_TOKEN = environ.get('BOT_TOKEN', 'BOT_1_KA_TOKEN_YAHAAN') # <-- Yahaan Bot 1 ka Token Daalein
ADMINS = [int(admin) if id_pattern.search(admin) else admin for admin in environ.get('ADMINS', '7245547751').split()]
USERNAME = environ.get('USERNAME', 'https://t.me/ramSitaam') # Admin ka username
LOG_CHANNEL = int(environ.get('LOG_CHANNEL', '-1003163434752')) # Bot 1 ke logs
MOVIE_GROUP_LINK = environ.get('MOVIE_GROUP_LINK', 'https://t.me/+7vxlanrMnWw4N2Fl')

# --- ZAROORI: Indexing ---
# Bot 1 index nahi karega, isliye CHANNELS ko khaali rakhein
CHANNELS = [] 

# --- ZAROORI: Database Settings ---
# Yeh Bot 2 ke database se connect karega taaki files search kar sake
DATABASE_URI = environ.get('DATABASE_URI', "")
DATABASE_URI2 = environ.get('DATABASE_URI2', "")
DATABASE_URI3 = environ.get('DATABASE_URI3', "")
DATABASE_URI4 = environ.get('DATABASE_URI4', "")
DATABASE_NAME = environ.get('DATABASE_NAME', "") # Bot 2 wala naam
COLLECTION_NAME = environ.get('COLLECTION_NAME', '') # Bot 2 wala naam

# --- File Forwarding (Not Needed for Bot 1) ---
# BIN_CHANNEL = int(environ.get('BIN_CHANNEL', ''))
# URL = environ.get('URL', '')

# --- Verification System (Not Needed for Bot 1) ---
IS_VERIFY = is_enabled('IS_VERIFY', False) # Bot 1 verify nahi karega
LOG_VR_CHANNEL = int(environ.get('LOG_VR_CHANNEL', '-1003179051423'))
TUTORIAL = environ.get("TUTORIAL", "https://t.me/how_to_dwnload_mov") # "How to Download" button
# VERIFY_IMG = environ.get("VERIFY_IMG", "")
# SHORTENER_API = environ.get("SHORTENER_API", "")
# SHORTENER_WEBSITE = environ.get("SHORTENER_WEBSITE", "")
# SHORTENER_API2 = environ.get("SHORTENER_API2", "")
# SHORTENER_WEBSITE2 = environ.get("SHORTENER_WEBSITE2", "")
# TWO_VERIFY_GAP = int(environ.get('TWO_VERIFY_GAP', "0"))
# DEFAULT_VERIFY_DURATION = 0
# SHORTENER_WEBSITE3 = ""
# SHORTENER_API3 = ""
# THIRD_VERIFY_GAP = 0 

# --- Search Filter Settings (Yeh Bot 1 ko Chahiye) ---
LANGUAGES = ["hindi", "english", "telugu", "tamil", "kannada", "malayalam"]
QUALITIES = ["4K", "2160p", "1080p", "720p", "480p", "360p"]

# --- FSub (Not Needed for Bot 1) ---
AUTH_CHANNEL = None
AUTH_CHANNEL_2 = None
AUTH_CHANNEL_3 = None
AUTH_CHANNEL_4 = None
# AUTH_CHANNEL_4_TEXT = environ.get('AUTH_CHANNEL_4_TEXT', '')

SUPPORT_GROUP = int(environ.get('SUPPORT_GROUP', '-1003115990357'))
REQUEST_CHANNEL = int(environ.get('REQUEST_CHANNEL', '-1003140956750')) # Request channel same rahega

# --- Bot 1 Search Settings ---
IS_PM_SEARCH = is_enabled('IS_PM_SEARCH', False) # PM search on/off
AUTO_FILTER = is_enabled('AUTO_FILTER', True) # Group auto-filter
PORT = os.environ.get('PORT', '8080')
MAX_BTN = int(environ.get('MAX_BTN', '8'))
AUTO_DELETE = is_enabled('AUTO_DELETE', True) # Search results delete karega
DELETE_TIME = int(environ.get('DELETE_TIME', 1200))
IMDB = is_enabled('IMDB', True) # Search results ke saath IMDB dikhayega
FILE_CAPTION = environ.get('FILE_CAPTION', f'{script.FILE_CAPTION}')
IMDB_TEMPLATE = environ.get('IMDB_TEMPLATE', f'{script.IMDB_TEMPLATE_TXT}')
LONG_IMDB_DESCRIPTION = is_enabled('LONG_IMDB_DESCRIPTION', False)
PROTECT_CONTENT = is_enabled('PROTECT_CONTENT', False) # Bot 1 file nahi bhejta
SPELL_CHECK = is_enabled('SPELL_CHECK', True)
LINK_MODE = is_enabled('LINK_MODE', True) # Link ya button mode

# --- Premium/Referral (Not Needed for Bot 1) ---
# QR_CODE = environ.get('QR_CODE', '')
# REFERRAL_TARGET = 0
# PREMIUM_MONTH_DURATION = 0
# LOG_API_CHANNEL = int(environ.get('LOG_API_CHANNEL', ''))

