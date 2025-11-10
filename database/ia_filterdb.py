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
# Purana code 'Media' class ko dhoondega. Hum usey Secondary (default) par point karenge.
Media = MediaSecondary
mydb = mydb_secondary # Statistics ke liye
# --- End Compatibility Fix ---


async def get_files_db_size():
    # Yeh command abhi bhi sirf secondary DB ka size dikhayega
    return (await mydb_secondary.command("dbstats"))['dataSize']

# --- YEH HAI MUKHYA BADLAAV (UPDATED) ---
async def save_file(media, db_choice='secondary'):
    """Save file in the chosen database"""

    file_id, file_ref = unpack_new_file_id(media.file_id)
    
    # --- YEH HAI NAYA LOGIC ---
    if db_choice == 'secondary':
        # 1. Pehle Primary DB (MediaPrimary) mein check karo
        try:
            # Sirf file_id se check karna kaafi hai
            if await MediaPrimary.find_one({'_id': file_id}):
                logger.warning(f'{getattr(media, "file_name", "NO_FILE")} pehle se Primary DB mein hai. Secondary DB mein skip kar raha hoon.')
                return 'dup' # 'dup' return karein (taaki counter mein count ho)
        except Exception as e:
            logger.error(f"Primary DB check karte waqt error: {e}")
            # Agar Primary DB check fail hota hai, toh safety ke liye hum maan lenge ki file nahi hai
            pass 
    # --- NAYA LOGIC KHATAM ---

    # Ab file ko chune gaye DB (Primary ya Secondary) mein save karne ki koshish karo
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
# --- FUNCTION UPDATE KHATAM ---

# NEECHE DIYE GAYE SABHI FUNCTIONS (SEARCH, DELETE, ETC.)
# SIRF AAPKE SECONDARY DB (DATABASE_URI2) SE HI KAAM KARENGE.
# YEH DEFAULT BEHAVIOR HAI.

async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, quality=None, year=None):
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
        
    filter = {'file_name': regex}
    
    # Add quality to the filter if provided
    if quality:
        filter['file_name'] = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})", flags=re.IGNORECASE)
    
    # Add year to the filter if provided
    if year:
        # If quality is also set, combine all three regex patterns
        if quality:
             filter['file_name'] = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(quality)})(?=.*{re.escape(year)})", flags=re.IGNORECASE)
        else:
             filter['file_name'] = re.compile(f"(?=.*{raw_pattern})(?=.*{re.escape(year)})", flags=re.IGNORECASE)

    # Search sirf default 'Media' (yaani MediaSecondary) se karega
    cursor = Media.find(filter)
    cursor.sort('$natural', -1)
    
    cursor.skip(offset).limit(max_results)
    files = await cursor.to_list(length=max_results)
    total_results = await Media.count_documents(filter)
    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ''       
    return files, next_offset, total_results
    
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

    filter = {'file_name': regex}
    
    # Search sirf default 'Media' (yaani MediaSecondary) se karega
    cursor = Media.find(filter).limit(200) 
    
    available_qualities = set()
    async for file in cursor:
        file_name_lower = file.file_name.lower()
        for quality in QUALITIES:
            if re.search(r'\b' + re.escape(quality.lower()) + r'\b', file_name_lower) or \
               (quality.endswith('p') and quality.lower() in file_name_lower):
                available_qualities.add(quality)
                
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

    filter = {'file_name': regex}
    
    # Search sirf default 'Media' (yaani MediaSecondary) se karega
    cursor = Media.find(filter).limit(200) 
    
    available_years = set()
    async for file in cursor:
        matches = YEAR_REGEX.findall(file.file_name)
        for year in matches:
            available_years.add(year)
                
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
        return []
    filter = {'file_name': regex}
    if file_type:
        filter['file_type'] = file_type
    
    # Search sirf default 'Media' (yaani MediaSecondary) se karega
    total_results = await Media.count_documents(filter)
    cursor = Media.find(filter)
    cursor.sort('$natural', -1)
    files = await cursor.to_list(length=total_results)
    return files, total_results
    
async def get_file_details(query):
    # Search sirf default 'Media' (yaani MediaSecondary) se karega
    filter = {'file_id': query}
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    return filedetails

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
