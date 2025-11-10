import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
# --- FIX: Dono database URI import karein ---
from info import (
    DATABASE_URI, DATABASE_URI2, DATABASE_NAME, COLLECTION_NAME, 
    MAX_BTN, QUALITIES
)

logger = logging.getLogger(__name__)

# --- FIX: Connection 1 (Primary) ---
client_primary = AsyncIOMotorClient(DATABASE_URI)
mydb_primary = client_primary[DATABASE_NAME]
instance_primary = Instance.from_db(mydb_primary)

# --- FIX: Connection 2 (Secondary - Aapka default indexing DB) ---
client_secondary = AsyncIOMotorClient(DATABASE_URI2)
mydb_secondary = client_secondary[DATABASE_NAME]
instance_secondary = Instance.from_db(mydb_secondary)


# --- FIX: Primary DB ke liye Media class ---
@instance_primary.register
class MediaPrimary(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        # Collection ka naam alag rakhein taaki primary DB mein mix na ho
        collection_name = f"{COLLECTION_NAME}_PRIMARY" 

# --- FIX: Secondary DB ke liye Media class ---
@instance_secondary.register
class MediaSecondary(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        # Yeh aapka original collection name istemaal karega
        collection_name = COLLECTION_NAME 

# --- Compatibility Fix ---
Media = MediaSecondary
mydb = mydb_secondary 
# --- End Compatibility Fix ---


async def get_files_db_size():
    try:
        return (await mydb_secondary.command("dbstats"))['dataSize']
    except Exception:
        return 0 

async def save_file(media, db_choice='secondary'):
    """Save file in the chosen database"""

    file_id, file_ref = unpack_new_file_id(media.file_id)
    
    if db_choice == 'secondary':
        # 1. Pehle Primary DB (MediaPrimary) mein check karo
        try:
            if await MediaPrimary.find_one({'_id': file_id}):
                logger.warning(f'{getattr(media, "file_name", "NO_FILE")} pehle se Primary DB mein hai. Secondary DB mein skip kar raha hoon.')
                return 'dup' 
        except Exception as e:
            logger.error(f"Primary DB check karte waqt error: {e}")
            pass 

    MediaClass = MediaPrimary if db_choice == 'primary' else MediaSecondary
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    
    try:
        file = MediaClass(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
            file_type=media.mime_type.split('/')[0]
        )
    except ValidationError:
        logger.error('File save karte waqt Validation Error')
        return 'err'
    else:
        try:
            await file.commit()
        except DuplicateKeyError:      
            logger.warning(f'{getattr(media, "file_name", "NO_FILE")} pehle se {db_choice} database mein hai') 
            return 'dup'
        else:
            logger.info(f'{getattr(media, "file_name", "NO_FILE")} ko {db_choice} database mein save kar diya gaya')
            return 'suc'

# --- YEH HAI CAPTION SEARCH WALA FIX ---
async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, quality=None, year=None):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]') 
    
    try:
        # Simple regex (sirf search query ke liye, caption mein use hoga)
        simple_regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        simple_regex = query
        
    # file_name ke liye complex regex (quality/year ke saath)
    file_name_regex = simple_regex
    
    if quality and year:
        file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})(?=.*{re.escape(year)})", flags=re.IGNORECASE)
    elif quality:
        file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})", flags=re.IGNORECASE)
    elif year:
        file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(year)})", flags=re.IGNORECASE)

    # MongoDB $or filter:
    # (file_name complex regex se match ho) YA (caption simple regex se match ho)
    filter = {
        '$or': [
            {'file_name': file_name_regex},
            {'caption': simple_regex}
        ]
    }
    # --- CAPTION SEARCH FIX KHATAM ---

    try:
        files_primary = await MediaPrimary.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e:
        logger.error(f"Primary DB search error: {e}")
        files_primary = []
        
    try:
        files_secondary = await MediaSecondary.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e:
        logger.error(f"Secondary DB search error: {e}")
        files_secondary = []

    all_files = files_primary + files_secondary
    
    if all_files:
        unique_files = {}
        for file in all_files:
            if file.file_id not in unique_files:
                unique_files[file.file_id] = file
        all_files = list(unique_files.values())

    total_results = len(all_files)

    files_to_send = all_files[offset : offset + max_results]
    
    next_offset = offset + len(files_to_send)
    if next_offset >= total_results:
        next_offset = ''
        
    return files_to_send, next_offset, total_results
    
async def get_available_qualities(query):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        regex = query

    # --- FIX: Caption mein bhi search karo ---
    filter = {
        '$or': [
            {'file_name': regex},
            {'caption': regex}
        ]
    }
    # --- FIX KHATAM ---
    
    available_qualities = set()
    
    try:
        cursor_primary = MediaPrimary.find(filter).limit(200) 
        async for file in cursor_primary:
            # Check file_name and caption
            text_to_check = (file.file_name + " " + (file.caption or "")).lower()
            for quality in QUALITIES:
                if re.search(r'\b' + re.escape(quality.lower()) + r'\b', text_to_check) or \
                   (quality.endswith('p') and quality.lower() in text_to_check):
                    available_qualities.add(quality)
    except Exception as e:
        logger.error(f"Primary DB quality check error: {e}")

    try:
        cursor_secondary = MediaSecondary.find(filter).limit(200) 
        async for file in cursor_secondary:
            # Check file_name and caption
            text_to_check = (file.file_name + " " + (file.caption or "")).lower()
            for quality in QUALITIES:
                if re.search(r'\b' + re.escape(quality.lower()) + r'\b', text_to_check) or \
                   (quality.endswith('p') and quality.lower() in text_to_check):
                    available_qualities.add(quality)
    except Exception as e:
        logger.error(f"Secondary DB quality check error: {e}")
                
    return sorted(list(available_qualities), reverse=True) 

async def get_available_years(query):
    YEAR_REGEX = re.compile(r'\b(19\d{2}|20\d{2})\b') 

    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        regex = query

    # --- FIX: Caption mein bhi search karo ---
    filter = {
        '$or': [
            {'file_name': regex},
            {'caption': regex}
        ]
    }
    # --- FIX KHATAM ---
    
    available_years = set()

    try:
        cursor_primary = MediaPrimary.find(filter).limit(200) 
        async for file in cursor_primary:
            # Check file_name and caption
            text_to_check = file.file_name + " " + (file.caption or "")
            matches = YEAR_REGEX.findall(text_to_check)
            for year in matches:
                available_years.add(year)
    except Exception as e:
        logger.error(f"Primary DB year check error: {e}")

    try:
        cursor_secondary = MediaSecondary.find(filter).limit(200) 
        async for file in cursor_secondary:
            # Check file_name and caption
            text_to_check = file.file_name + " " + (file.caption or "")
            matches = YEAR_REGEX.findall(text_to_check)
            for year in matches:
                available_years.add(year)
    except Exception as e:
        logger.error(f"Secondary DB year check error: {e}")
                
    return sorted(list(available_years), reverse=True) 

async def get_bad_files(query, file_type=None, offset=0, filter=False):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return [], 0 # FIX: Empty list aur 0 return karein
        
    # --- FIX: $or filter add karein ---
    base_filter = {
        '$or': [
            {'file_name': regex},
            {'caption': regex}
        ]
    }
    
    if file_type:
        # Dono ko $and ke saath combine karein
        filter = {
            '$and': [
                base_filter,
                {'file_type': file_type}
            ]
        }
    else:
        filter = base_filter
    # --- FIX KHATAM ---
    
    try:
        files_primary = await MediaPrimary.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e:
        logger.error(f"Primary DB bad_files error: {e}")
        files_primary = []
        
    try:
        files_secondary = await MediaSecondary.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e:
        logger.error(f"Secondary DB bad_files error: {e}")
        files_secondary = []

    files = files_primary + files_secondary
    
    if files:
        unique_files = {}
        for file in files:
            if file.file_id not in unique_files:
                unique_files[file.file_id] = file
        files = list(unique_files.values())
        
    total_results = len(files)
    return files, total_results
    
async def get_file_details(query):
    filter = {'file_id': query}
    
    try:
        filedetails = await MediaSecondary.find(filter).to_list(length=1)
        if filedetails:
            return filedetails
    except Exception as e:
        logger.error(f"get_file_details Secondary DB error: {e}")

    try:
        filedetails = await MediaPrimary.find(filter).to_list(length=1)
        if filedetails:
            return filedetails
    except Exception as e:
        logger.error(f"get_file_details Primary DB error: {e}")
        
    return [] 

def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref
