import logging
from struct import pack
import re
import base64
import asyncio  # <-- YEH HAI FIX
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError, OperationFailure
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import (
    DATABASE_URI, DATABASE_URI2, DATABASE_URI3, DATABASE_URI4, 
    DATABASE_NAME, COLLECTION_NAME, MAX_BTN, QUALITIES
)

logger = logging.getLogger(__name__)

# --- Sabhi 4 connections (Jaise pehle the) ---
client_primary = AsyncIOMotorClient(DATABASE_URI)
mydb_primary = client_primary[DATABASE_NAME]
instance_primary = Instance.from_db(mydb_primary)

client_secondary = AsyncIOMotorClient(DATABASE_URI2)
mydb_secondary = client_secondary[DATABASE_NAME]
instance_secondary = Instance.from_db(mydb_secondary)

client_third = AsyncIOMotorClient(DATABASE_URI3)
mydb_third = client_third[DATABASE_NAME]
instance_third = Instance.from_db(mydb_third)

client_fourth = AsyncIOMotorClient(DATABASE_URI4)
mydb_fourth = client_fourth[DATABASE_NAME]
instance_fourth = Instance.from_db(mydb_fourth)


# --- NAYA CHHOTA COLLECTION (files_data) ---
@instance_primary.register
class FilesData(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    message_id = fields.IntField(required=True)
    channel_id = fields.IntField(required=True)
    file_size = fields.IntField(required=True)
    
    class Meta:
        collection_name = "files_data"
        indexes = (['message_id', 'channel_id'], )


# --- BADA COLLECTION (files_search) MEIN BADLAAV ---

@instance_primary.register
class MediaPrimary(Document):
    file_id = fields.StrField(attribute='_id')
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    caption = fields.StrField(allow_none=True)
    link_id = fields.StrField(required=True) 
    class Meta:
        indexes = ('$file_name', )
        collection_name = f"{COLLECTION_NAME}_PRIMARY" 

@instance_secondary.register
class MediaSecondary(Document):
    file_id = fields.StrField(attribute='_id')
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    caption = fields.StrField(allow_none=True)
    link_id = fields.StrField(required=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

@instance_third.register
class MediaThird(Document):
    file_id = fields.StrField(attribute='_id')
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    caption = fields.StrField(allow_none=True)
    link_id = fields.StrField(required=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = f"{COLLECTION_NAME}_THIRD" 

@instance_fourth.register
class MediaFourth(Document):
    file_id = fields.StrField(attribute='_id')
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    caption = fields.StrField(allow_none=True)
    link_id = fields.StrField(required=True)
    class Meta:
        indexes = ('$file_name', )
        collection_name = f"{COLLECTION_NAME}_FOURTH" 

Media = MediaSecondary
mydb = mydb_secondary 


async def get_files_db_size():
    try: return (await mydb_secondary.command("dbstats"))['dataSize']
    except: return 0 

async def get_all_files_db_stats():
    stats = {}
    all_dbs = {
        'db1': (MediaPrimary, mydb_primary),
        'db2': (MediaSecondary, mydb_secondary),
        'db3': (MediaThird, mydb_third),
        'db4': (MediaFourth, mydb_fourth)
    }
    for db_key, (MediaClass, mydb_instance) in all_dbs.items():
        try:
            count = await MediaClass.count_documents()
            size = (await mydb_instance.command("dbstats"))['dataSize']
            stats[f'{db_key}_files'] = count
            stats[f'{db_key}_size'] = size
        except Exception as e:
            logger.error(f"{db_key} Stats Error: {e}")
            stats[f'{db_key}_files'] = "N/A"
            stats[f'{db_key}_size'] = 0
            
    try:
        stats['db_master_files'] = await FilesData.count_documents()
        stats['db_master_size'] = (await mydb_primary.command("dbstats", scale=1, collection="files_data"))['size']
    except Exception as e:
        logger.error(f"FilesData Stats Error: {e}")
        stats['db_master_files'] = "N/A"
        stats['db_master_size'] = 0
    return stats

async def save_file_data(media):
    file_id, file_ref = unpack_new_file_id(media.file_id)
    try:
        file_data = FilesData(
            file_id=file_id,
            file_ref=file_ref,
            message_id=media.message_id,
            channel_id=media.channel_id,
            file_size=media.file_size
        )
        await file_data.commit()
        logger.info(f"Master List mein save kiya: {media.file_name}")
        return file_data
    except DuplicateKeyError:
        logger.warning(f"{media.file_name} pehle se Master List (FilesData) mein hai.")
        return await FilesData.find_one({'_id': file_id})
    except Exception as e:
        logger.error(f"FilesData save karte hue error: {e}")
        return None

async def save_file(media, db_choice='secondary'):
    file_data = await save_file_data(media)
    if not file_data:
        return 'err'
    
    link_id = file_data.file_id 
    try:
        search_id_base = base64.urlsafe_b64encode(media.file_unique_id.encode()).decode()
        search_db_id = f"{search_id_base}_{db_choice}"
    except Exception:
        search_db_id = f"{link_id}_{db_choice}"

    if db_choice == 'primary': MediaClass = MediaPrimary
    elif db_choice == 'third': MediaClass = MediaThird
    elif db_choice == 'fourth': MediaClass = MediaFourth
    else: MediaClass = MediaSecondary
        
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    
    try:
        file_search_doc = MediaClass(
            file_id=search_db_id,
            file_name=file_name,
            file_size=media.file_size,
            caption=media.caption.html if media.caption else None,
            link_id=link_id
        )
        await file_search_doc.commit()
    except DuplicateKeyError:      
        logger.warning(f'{file_name} pehle se {db_choice} Search Index mein hai') 
        return 'dup'
    except Exception as e:
        logger.error(f"Search Index save karte hue error: {e}")
        return 'err'
    
    logger.info(f"'{db_choice}' Search Index mein save kiya: {file_name}")
    return 'suc'

async def get_file_data_by_link_id(link_id: str):
    try:
        return await FilesData.find_one({'_id': link_id})
    except Exception as e:
        logger.error(f"get_file_data_by_link_id error: {e}")
        return None

async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, quality=None, year=None):
    query = query.strip()
    if not query: raw_pattern = '.'
    elif ' ' not in query: raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else: raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]') 
    
    try: simple_regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except: simple_regex = query
    file_name_regex = simple_regex
    
    if quality and year: file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})(?=.*{re.escape(year)})", flags=re.IGNORECASE)
    elif quality: file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})", flags=re.IGNORECASE)
    elif year: file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(year)})", flags=re.IGNORECASE)

    filter = {'$or': [{'file_name': file_name_regex}, {'caption': simple_regex}]}

    files_primary = files_secondary = files_third = files_fourth = []
    try: files_primary = await MediaPrimary.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e: logger.error(f"Primary DB search error: {e}")
    try: files_secondary = await MediaSecondary.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e: logger.error(f"Secondary DB search error: {e}")
    try: files_third = await MediaThird.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e: logger.error(f"Third DB search error: {e}")
    try: files_fourth = await MediaFourth.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e: logger.error(f"Fourth DB search error: {e}")

    all_files = files_primary + files_secondary + files_third + files_fourth
    
    if all_files:
        unique_files = {file.link_id: file for file in all_files}
        all_files = list(unique_files.values())

    total_results = len(all_files)
    files_to_send = all_files[offset : offset + max_results]
    next_offset = offset + len(files_to_send)
    if next_offset >= total_results: next_offset = ''
        
    return files_to_send, next_offset, total_results
    
async def get_available_qualities(query):
    query = query.strip()
    if not query: raw_pattern = '.'
    elif ' ' not in query: raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else: raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    try: regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except: regex = query
    filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    available_qualities = set()
    async def check_qualities_in_db(db_class, db_name):
        try:
            cursor = db_class.find(filter).limit(200) 
            async for file in cursor:
                text_to_check = (file.file_name + " " + (file.caption or "")).lower()
                for quality in QUALITIES:
                    if re.search(r'\b' + re.escape(quality.lower()) + r'\b', text_to_check) or \
                       (quality.endswith('p') and quality.lower() in text_to_check):
                        available_qualities.add(quality)
        except Exception as e: logger.error(f"{db_name} quality check error: {e}")

    # --- YAHIN PAR 'asyncio' KA ISTEMAAL HO RAHA HAI ---
    await asyncio.gather(
        check_qualities_in_db(MediaPrimary, "Primary DB"),
        check_qualities_in_db(MediaSecondary, "Secondary DB"),
        check_qualities_in_db(MediaThird, "Third DB"),
        check_qualities_in_db(MediaFourth, "Fourth DB")
    )
    return sorted(list(available_qualities), reverse=True) 

async def get_available_years(query):
    YEAR_REGEX = re.compile(r'\b(19\d{2}|20\d{2})\b') 
    query = query.strip()
    if not query: raw_pattern = '.'
    elif ' ' not in query: raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else: raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    try: regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except: regex = query
    filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    available_years = set()
    async def check_years_in_db(db_class, db_name):
        try:
            cursor = db_class.find(filter).limit(200) 
            async for file in cursor:
                text_to_check = file.file_name + " " + (file.caption or "")
                matches = YEAR_REGEX.findall(text_to_check)
                for year in matches: available_years.add(year)
        except Exception as e: logger.error(f"{db_name} year check error: {e}")
    
    # --- YAHIN PAR 'asyncio' KA ISTEMAAL HO RAHA HAI ---
    await asyncio.gather(
        check_years_in_db(MediaPrimary, "Primary DB"),
        check_years_in_db(MediaSecondary, "Secondary DB"),
        check_years_in_db(MediaThird, "Third DB"),
        check_years_in_db(MediaFourth, "Fourth DB")
    )
    return sorted(list(available_years), reverse=True) 

async def get_bad_files(query, file_type=None, offset=0, filter=False):
    query = query.strip()
    if not query: raw_pattern = '.'
    elif ' ' not in query: raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else: raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    try: regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except: return [], 0 
    base_filter = {'$or': [{'file_name': regex}, {'caption': regex}]}
    filter = {'$and': [base_filter, {'file_type': file_type}]} if file_type else base_filter
    files = []
    try: files.extend(await MediaPrimary.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e: logger.error(f"Primary DB bad_files error: {e}")
    try: files.extend(await MediaSecondary.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e: logger.error(f"Secondary DB bad_files error: {e}")
    try: files.extend(await MediaThird.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e: logger.error(f"Third DB bad_files error: {e}")
    try: files.extend(await MediaFourth.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e: logger.error(f"Fourth DB bad_files error: {e}")
    if files:
        unique_files = {file.link_id: file for file in files}
        files = list(unique_files.values())
    total_results = len(files)
    return files, total_results
    
async def get_file_details(query):
    logger.warning("Obsolete function get_file_details called. Returning empty.")
    return []

def encode_file_id(s: bytes) -> str:
    r, n = b"", 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0: n += 1
        else:
            if n: r += b"\x00" + bytes([n]); n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(pack("<iiqq", int(decoded.file_type), decoded.dc_id, decoded.media_id, decoded.access_hash))
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref
