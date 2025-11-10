import datetime
import pytz
from motor.motor_asyncio import AsyncIOMotorClient
# --- YEH IMPORT ADD KAREIN ---
from info import (
    IS_VERIFY, LINK_MODE, FILE_CAPTION, TUTORIAL, DATABASE_NAME, DATABASE_URI, 
    DATABASE_URI2, IMDB, IMDB_TEMPLATE, PROTECT_CONTENT, AUTO_DELETE, 
    SPELL_CHECK, AUTO_FILTER, LOG_VR_CHANNEL, SHORTENER_WEBSITE, 
    SHORTENER_API, SHORTENER_WEBSITE2, SHORTENER_API2, TWO_VERIFY_GAP, 
    VERIFY_DURATION  # <-- YEH ZAROORI HAI
)

client = AsyncIOMotorClient(DATABASE_URI)
mydb = client[DATABASE_NAME]

class Database:
    default = {
            'spell_check': SPELL_CHECK,
            'auto_filter': AUTO_FILTER,
            'file_secure': PROTECT_CONTENT,
            'auto_delete': AUTO_DELETE,
            'template': IMDB_TEMPLATE,
            'caption': FILE_CAPTION,
            'tutorial': TUTORIAL,
            'shortner': SHORTENER_WEBSITE,
            'api': SHORTENER_API,
            'shortner_two': SHORTENER_WEBSITE2,
            'api_two': SHORTENER_API2,
            'log': LOG_VR_CHANNEL,
            'imdb': IMDB,
            'link': LINK_MODE, 
            'is_verify': IS_VERIFY, 
            'verify_time': TWO_VERIFY_GAP,
            'verify_duration': VERIFY_DURATION  # <-- FIX 1: YEH LINE ADD KI GAYI HAI
    }
    
    def __init__(self):
        self.col = mydb.users
        self.grp = mydb.groups
        self.misc = mydb.misc
        self.verify_id = mydb.verify_id
        self.users = self.col 
        self.req = mydb.requests
        self.ref_links = mydb.referral_links
        self.referrals = mydb.referrals
        
        self.join_requests = mydb.join_requests

    def new_user(self, id, name):
        return dict(
            id = id,
            name = name,
            ban_status=dict(
                is_banned=False,
                ban_reason=""
            ),
            referral_count=0
        )

    async def get_settings(self, id):
        chat = await self.grp.find_one({'id':int(id)})
        if chat:
            return chat.get('settings', self.default)
        return self.default

    async def add_join_request(self, user_id, chat_id):
        """User ko pending request list mein add karta hai"""
        await self.join_requests.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {'$set': {'timestamp': datetime.datetime.now(pytz.utc)}},
            upsert=True
        )

    async def is_join_request_pending(self, user_id, chat_id):
        """Check karta hai ki user pending list mein hai ya nahi"""
        return bool(await self.join_requests.find_one(
            {'user_id': user_id, 'chat_id': chat_id}
        ))

    async def remove_join_request(self, user_id, chat_id):
        """User ko pending request list se remove karta hai (cleanup)"""
        await self.join_requests.delete_one(
            {'user_id': user_id, 'chat_id': chat_id}
        )
    
    async def clear_all_join_requests(self):
        """Safely deletes all documents from the join_requests collection"""
        await self.join_requests.delete_many({})

    async def del_join_req(self):
        """Alias for clear_all_join_requests() for compatibility with Join_req.py"""
        await self.clear_all_join_requests()

    def new_group(self, id, title):
        return dict(
            id = id,
            title = title,
            chat_status=dict(
                is_disabled=False,
                reason=""
            )
        )
    
    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.insert_one(user)
    
    async def is_user_exist(self, id):
        user = await self.col.find_one({'id':int(id)})
        return bool(user)
    
    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count
    
    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def delete_chat(self, id):
        await self.grp.delete_many({'id': int(id)})
        
    # --- YEH FUNCTION AAPNE DELETE KAR DIYA THA ---
    async def get_banned(self):
        users = self.col.find({'ban_status.is_banned': True})
        chats = self.grp.find({'chat_status.is_disabled': True})
        b_chats = [chat['id'] async for chat in chats]
        b_users = [user['id'] async for user in users]
        return b_users, b_chats
    # --- FIX KHATAM ---
    
    async def increment_referral_count(self, user_id):
        await self.col.update_one(
            {'id': int(user_id)},
            {'$inc': {'referral_count': 1}}
        )

    async def get_referral_count(self, user_id):
        user = await self.col.find_one({'id': int(user_id)})
        if user:
            return user.get('referral_count', 0)
        return 0
    
    # --- YEH FUNCTIONS AAPNE DELETE KAR DIYE THE ---
    async def add_chat(self, chat, title):
        chat = self.new_group(chat, title)
        await self.grp.insert_one(chat)

    async def get_chat(self, chat):
        chat = await self.grp.find_one({'id':int(chat)})
        return False if not chat else chat.get('chat_status')  

    async def update_settings(self, id, settings):
        await self.grp.update_one({'id': int(id)}, {'$set': {'settings': settings}})   
    
    async def total_chat_count(self):
        count = await self.grp.count_documents({})
        return count
    
    async def get_all_chats(self):
        return self.grp.find({})
    # --- FIX KHATAM ---

    async def get_db_size(self):
        return (await mydb.command("dbstats"))['dataSize'] 

    async def get_notcopy_user(self, user_id):
        user_id = int(user_id)
        user = await self.misc.find_one({"user_id": user_id})
        ist_timezone = pytz.timezone('Asia/Kolkata')
        if not user:
            res = {
                "user_id": user_id,
                "last_verified": datetime.datetime(2020, 5, 17, 0, 0, 0, tzinfo=ist_timezone),
                "second_time_verified": datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_timezone),
            }
            await self.misc.insert_one(res) 
            return res
        return user

    async def update_notcopy_user(self, user_id, value:dict):
        user_id = int(user_id)
        myquery = {"user_id": user_id}
        newvalues = {"$set": value}
        return await self.misc.update_one(myquery, newvalues)

    # --- FIX 2: is_user_verified (Link 1) ko update kiya gaya ---
    async def is_user_verified(self, user_id, grp_id, duration):
        """Link 1 (last_verified) ka expiry check karta hai."""
        user = await self.get_notcopy_user(user_id)
        try:
            pastDate = user["last_verified"]
        except Exception:
            user = await self.get_notcopy_user(user_id)
            pastDate = user["last_verified"]
            
        ist_timezone = pytz.timezone('Asia/Kolkata')
        pastDate = pastDate.astimezone(ist_timezone)
        current_time = datetime.datetime.now(tz=ist_timezone)
        
        time_diff = current_time - pastDate
        total_seconds = time_diff.total_seconds()
        
        if duration == 0:
             return False 

        return total_seconds <= duration
    # --- FIX KHATAM ---

    # --- FIX 3: Naya function (Link 2 ke liye) add kiya gaya ---
    async def is_user_verified_second(self, user_id, grp_id, duration):
        """Link 2 (second_time_verified) ka expiry check karta hai."""
        user = await self.get_notcopy_user(user_id)
        try:
            pastDate = user["second_time_verified"]
        except Exception:
            user = await self.get_notcopy_user(user_id)
            pastDate = user["second_time_verified"]
            
        ist_timezone = pytz.timezone('Asia/Kolkata')
        pastDate = pastDate.astimezone(ist_timezone)
        current_time = datetime.datetime.now(tz=ist_timezone)
        
        time_diff = current_time - pastDate
        total_seconds = time_diff.total_seconds()
        
        if duration == 0:
             return False
        return total_seconds <= duration
    # --- FUNCTION KHATAM ---
    
    # --- FIX 4: use_second_shortener ka logic poori tarah badal diya gaya hai ---
    async def use_second_shortener(self, user_id, grp_id, gap_time, is_v1_valid):
        """
        Pata lagata hai ki Link 2 dikhana hai ya nahi.
        gap_time: V1 aur V2 ke beech ka gap (seconds mein).
        is_v1_valid: Kya V1 abhi bhi expiry time ke andar hai.
        """
        user = await self.get_notcopy_user(user_id)
        if not user.get("second_time_verified"):
            ist_timezone = pytz.timezone('Asia/Kolkata')
            await self.update_notcopy_user(user_id, {"second_time_verified":datetime.datetime(2019, 5, 17, 0, 0, 0, tzinfo=ist_timezone)})
            user = await self.get_notcopy_user(user_id)
        
        if is_v1_valid:
            try:
                pastDate = user["last_verified"]
            except Exception:
                user = await self.get_notcopy_user(user_id)
                pastDate = user["last_verified"]
                
            ist_timezone = pytz.timezone('Asia/Kolkata')
            pastDate = pastDate.astimezone(ist_timezone)
            current_time = datetime.datetime.now(tz=ist_timezone)
            time_difference = current_time - pastDate
            
            if time_difference > datetime.timedelta(seconds=gap_time):
                pastDate_v1 = user["last_verified"].astimezone(ist_timezone)
                pastDate_v2 = user["second_time_verified"].astimezone(ist_timezone)
                return pastDate_v2 < pastDate_v1
        
        return False
    # --- FIX KHATAM ---
   
    async def create_verify_id(self, user_id: int, hash):
        res = {"user_id": user_id, "hash":hash, "verified":False}
        return await self.verify_id.insert_one(res)

    async def get_verify_id_info(self, user_id: int, hash):
        return await self.verify_id.find_one({"user_id": user_id, "hash": hash})

    async def update_verify_id_info(self, user_id, hash, value: dict):
        myquery = {"user_id": user_id, "hash": hash}
        newvalues = { "$set": value }
        return await self.verify_id.update_one(myquery, newvalues)

    async def get_user(self, user_id):
        user_data = await self.users.find_one({"id": user_id})
        return user_data
        
    async def update_user(self, user_data):
        await self.users.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def has_premium_access(self, user_id):
        user_data = await self.get_user(user_id)
        if user_data:
            expiry_time = user_data.get("expiry_time")
            if expiry_time is None:
                return False
            elif isinstance(expiry_time, datetime.datetime) and datetime.datetime.now() <= expiry_time:
                return True
            else:
                await self.users.update_one({"id": user_id}, {"$set": {"expiry_time": None}})
        return False
        
    async def update_one(self, filter_query, update_data):
        try:
            result = await self.users.update_one(filter_query, update_data)
            return result.matched_count == 1
        except Exception as e:
            print(f"Error updating document: {e}")
            return False

    async def get_expired(self, current_time):
        expired_users = []
        if data := self.users.find({"expiry_time": {"$lt": current_time}}):
            async for user in data:
                expired_users.append(user)
        return expired_users

    async def remove_premium_access(self, user_id):
        return await self.update_one(
            {"id": user_id}, {"$set": {"expiry_time": None}}
        )

    async def get_user_data(self, user_id):
        user = await self.col.find_one({'id': int(user_id)})
        return user

    async def get_user_by_referral_link(self, link):
        return await self.ref_links.find_one({'_id': link})

    async def update_referral_link(self, user_id, link, chat_id):
        await self.ref_links.insert_one({
            '_id': link, 
            'referrer_id': user_id, 
            'chat_id': chat_id
        })

    async def get_referral_link(self, user_id, chat_id):
        return await self.ref_links.find_one({
            'referrer_id': user_id, 
            'chat_id': chat_id
        })
    
    async def log_referral(self, new_user_id, referrer_id, chat_id):
        await self.referrals.insert_one({
            'user_id': new_user_id,
            'referrer_id': referrer_id,
            'chat_id': chat_id
        })

    async def has_been_referred_in_group(self, new_user_id, chat_id):
        return bool(await self.referrals.find_one({
            'user_id': new_user_id,
            'chat_id': chat_id
        }))


db = Database()
