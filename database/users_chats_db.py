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
        # (Yeh function sahi hai, koi badlaav nahi)
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
        # (Yeh function sahi hai, koi badlaav nahi)
        chat = await self.grp.find_one({'id':int(id)})
        if chat:
            return chat.get('settings', self.default)
        return self.default

    # --- (Baaki ke sabhi functions jaise add_join_request, add_user, etc. waise hi rahenge) ---
    # ...
    # (Aapke sabhi functions yahan...)
    # ...

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
            await self.misc.insert_one(res) # <-- Yahan 'await' add kiya (optional but good)
            return res
        return user

    async def update_notcopy_user(self, user_id, value:dict):
        # (Yeh function sahi hai, koi badlaav nahi)
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
        
        # Agar admin ne 0 set kiya hai, toh hamesha 'False' (expired) return karein
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
    
    # (Aapka purana 'user_verified' function (jo midnight reset karta tha) hata diya gaya hai)

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
        
        # Agar V1 valid hai (expiry time ke andar)
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
            
            # Check karein ki V1-V2 ka gap (jaise 10s) poora ho gaya hai ya nahi
            if time_difference > datetime.timedelta(seconds=gap_time):
                # Agar gap poora ho gaya hai, toh V2 dikhana hai
                # (Yeh check karta hai ki V2 ka timestamp V1 se purana hai)
                pastDate_v1 = user["last_verified"].astimezone(ist_timezone)
                pastDate_v2 = user["second_time_verified"].astimezone(ist_timezone)
                return pastDate_v2 < pastDate_v1
        
        # Agar V1 valid nahi hai (yaani expired hai), toh V2 nahi dikhana hai (V1 dikhega)
        return False
    # --- FIX KHATAM ---
   
    async def create_verify_id(self, user_id: int, hash):
        # (Yeh function sahi hai, koi badlaav nahi)
        res = {"user_id": user_id, "hash":hash, "verified":False}
        return await self.verify_id.insert_one(res)

    async def get_verify_id_info(self, user_id: int, hash):
        # (Yeh function sahi hai, koi badlaav nahi)
        return await self.verify_id.find_one({"user_id": user_id, "hash": hash})

    async def update_verify_id_info(self, user_id, hash, value: dict):
        # (Yeh function sahi hai, koi badlaav nahi)
        myquery = {"user_id": user_id, "hash": hash}
        newvalues = { "$set": value }
        return await self.verify_id.update_one(myquery, newvalues)

    async def get_user(self, user_id):
        # (Yeh function sahi hai, koi badlaav nahi)
        user_data = await self.users.find_one({"id": user_id})
        return user_data
        
    async def update_user(self, user_data):
        # (Yeh function sahi hai, koi badlaav nahi)
        await self.users.update_one({"id": user_data["id"]}, {"$set": user_data}, upsert=True)

    async def has_premium_access(self, user_id):
        # (Yeh function sahi hai, koi badlaav nahi)
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
        # (Yeh function sahi hai, koi badlaav nahi)
        try:
            result = await self.users.update_one(filter_query, update_data)
            return result.matched_count == 1
        except Exception as e:
            print(f"Error updating document: {e}")
            return False

    async def get_expired(self, current_time):
        # (Yeh function sahi hai, koi badlaav nahi)
        expired_users = []
        if data := self.users.find({"expiry_time": {"$lt": current_time}}):
            async for user in data:
                expired_users.append(user)
        return expired_users

    async def remove_premium_access(self, user_id):
        # (Yeh function sahi hai, koi badlaa_v nahi)
        return await self.update_one(
            {"id": user_id}, {"$set": {"expiry_time": None}}
        )

    async def get_user_data(self, user_id):
        # (Yeh function sahi hai, koi badlaav nahi)
        user = await self.col.find_one({'id': int(user_id)})
        return user

    async def get_user_by_referral_link(self, link):
        # (Yeh function sahi hai, koi badlaav nahi)
        return await self.ref_links.find_one({'_id': link})

    async def update_referral_link(self, user_id, link, chat_id):
        # (Yeh function sahi hai, koi badlaav nahi)
        await self.ref_links.insert_one({
            '_id': link, 
            'referrer_id': user_id, 
            'chat_id': chat_id
        })

    async def get_referral_link(self, user_id, chat_id):
        # (Yeh function sahi hai, koi badlaav nahi)
        return await self.ref_links.find_one({
            'referrer_id': user_id, 
            'chat_id': chat_id
        })
    
    async def log_referral(self, new_user_id, referrer_id, chat_id):
        # (Yeh function sahi hai, koi badlaav nahi)
        await self.referrals.insert_one({
            'user_id': new_user_id,
            'referrer_id': referrer_id,
            'chat_id': chat_id
        })

    async def has_been_referred_in_group(self, new_user_id, chat_id):
        # (Yeh function sahi hai, koi badlaav nahi)
        return bool(await self.referrals.find_one({
            'user_id': new_user_id,
            'chat_id': chat_id
        }))


db = Database()
