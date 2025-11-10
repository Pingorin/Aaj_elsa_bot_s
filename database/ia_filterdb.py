import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
# --- FIX: Teeno database URI import karein ---
from info import (
    DATABASE_URI, DATABASE_URI2, DATABASE_URI3, DATABASE_NAME, COLLECTION_NAME, 
    MAX_BTN, QUALITIES
)

logger = logging.getLogger(__name__)

# --- Connection 1 (Primary) ---
client_primary = AsyncIOMotorClient(DATABASE_URI)
mydb_primary = client_primary[DATABASE_NAME]
instance_primary = Instance.from_db(mydb_primary)

# --- Connection 2 (Secondary) ---
client_secondary = AsyncIOMotorClient(DATABASE_URI2)
mydb_secondary = client_secondary[DATABASE_NAME]
instance_secondary = Instance.from_db(mydb_secondary)

# --- NAYA: Connection 3 (Third) ---
client_third = AsyncIOMotorClient(DATABASE_URI3)
mydb_third = client_third[DATABASE_NAME]
instance_third = Instance.from_db(mydb_third)


# --- Primary DB ke liye Media class ---
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
        collection_name = f"{COLLECTION_NAME}_PRIMARY" 

# --- Secondary DB ke liye Media class ---
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
        collection_name = COLLECTION_NAME # Default collection

# --- NAYA: Third DB ke liye Media class ---
@instance_third.register
class MediaThird(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        collection_name = f"{COLLECTION_NAME}_THIRD" 


# --- Compatibility Fix ---
Media = MediaSecondary
mydb = mydb_secondary 
# --- End Compatibility Fix ---


async def get_files_db_size():
    try:
        # Yeh abhi bhi sirf secondary DB ka size dikhayega
        return (await mydb_secondary.command("dbstats"))['dataSize']
    except Exception:
        return 0 

# --- NAYA SAVE_FILE LOGIC (3-DB CHECK KE SAATH) ---
async def save_file(media, db_choice='secondary'):
    """Save file in the chosen database"""

    file_id, file_ref = unpack_new_file_id(media.file_id)
    
    # Logic: Save karne se pehle check karo
    try:
        if db_choice == 'third':
            # Agar DB 3 mein save kar rahe hain, toh 1 aur 2 mein check karo
            if await MediaPrimary.find_one({'_id': file_id}) or await MediaSecondary.find_one({'_id': file_id}):
                logger.warning(f'{getattr(media, "file_name", "NO_FILE")} pehle se DB 1 ya 2 mein hai. DB 3 mein skip kar raha hoon.')
                return 'dup'
        
        elif db_choice == 'secondary':
            # Agar DB 2 mein save kar rahe hain, toh 1 mein check karo
            if await MediaPrimary.find_one({'_id': file_id}):
                logger.warning(f'{getattr(media, "file_name", "NO_FILE")} pehle se DB 1 mein hai. DB 2 mein skip kar raha hoon.')
                return 'dup' 
        
        # db_choice == 'primary' ke liye koi check zaroori nahi hai
            
    except Exception as e:
        logger.error(f"Duplicate check karte waqt error: {e}")
        pass 

    # Decide karo kaunsi class use karni hai
    if db_choice == 'primary':
        MediaClass = MediaPrimary
    elif db_choice == 'third':
        MediaClass = MediaThird
    else:
        MediaClass = MediaSecondary
        
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

# --- NAYA SEARCH FIX (Teeno DB mein Search karega) ---
async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, quality=None, year=None):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]') 
    
    try:
        simple_regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        simple_regex = query
        
    file_name_regex = simple_regex
    
    if quality and year:
        file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})(?=.*{re.escape(year)})", flags=re.IGNORECASE)
    elif quality:
        file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})", flags=re.IGNORECASE)
    elif year:
        file_name_regex = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(year)})", flags=re.IGNORECASE)

    filter = {
        '$or': [
            {'file_name': file_name_regex},
            {'caption': simple_regex}
        ]
    }

    # --- Teeno DB se data fetch karo ---
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
        
    try:
        files_third = await MediaThird.find(filter).sort('$natural', -1).to_list(length=None)
    except Exception as e:
        logger.error(f"Third DB search error: {e}")
        files_third = []

    # Teeno lists ko combine karo
    all_files = files_primary + files_secondary + files_third
    
    # file_id ke basis par duplicates hatao
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
    # --- SEARCH FIX KHATAM ---
    
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

    filter = {
        '$or': [
            {'file_name': regex},
            {'caption': regex}
        ]
    }
    
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
        except Exception as e:
            logger.error(f"{db_name} quality check error: {e}")

    await check_qualities_in_db(MediaPrimary, "Primary DB")
    await check_qualities_in_db(MediaSecondary, "Secondary DB")
    await check_qualities_in_db(MediaThird, "Third DB")
                
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

    filter = {
        '$or': [
            {'file_name': regex},
            {'caption': regex}
        ]
    }
    
    available_years = set()

    async def check_years_in_db(db_class, db_name):
        try:
            cursor = db_class.find(filter).limit(200) 
            async for file in cursor:
                text_to_check = file.file_name + " " + (file.caption or "")
                matches = YEAR_REGEX.findall(text_to_check)
                for year in matches:
                    available_years.add(year)
        except Exception as e:
            logger.error(f"{db_name} year check error: {e}")

    await check_years_in_db(MediaPrimary, "Primary DB")
    await check_years_in_db(MediaSecondary, "Secondary DB")
    await check_years_in_db(MediaThird, "Third DB")
                
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
        return [], 0 
        
    base_filter = {
        '$or': [
            {'file_name': regex},
            {'caption': regex}
        ]
    }
    
    filter = {'$and': [base_filter, {'file_type': file_type}]} if file_type else base_filter
    
    files = []
    try:
        files.extend(await MediaPrimary.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e:
        logger.error(f"Primary DB bad_files error: {e}")
        
    try:
        files.extend(await MediaSecondary.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e:
        logger.error(f"Secondary DB bad_files error: {e}")
        
    try:
        files.extend(await MediaThird.find(filter).sort('$natural', -1).to_list(length=None))
    except Exception as e:
        logger.error(f"Third DB bad_files error: {e}")

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
        
    try:
        filedetails = await MediaThird.find(filter).to_list(length=1)
        if filedetails:
            return filedetails
    except Exception as e:
        logger.error(f"get_file_details Third DB error: {e}")
        
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
