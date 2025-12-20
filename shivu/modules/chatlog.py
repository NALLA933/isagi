import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from collections import defaultdict
from pyrogram import Client, filters
from pyrogram.types import Message, Chat, User
from pyrogram.errors import (
    PeerIdInvalid, BadRequest, FloodWait, 
    UserIsBlocked, ChatWriteForbidden
)
from shivu import user_collection, shivuu as app, LEAVELOGS, JOINLOGS


class BotAnalytics:
    def __init__(self):
        self.stats = defaultdict(int)
        self.chat_cache = {}
        self.lock = asyncio.Lock()
    
    async def increment(self, key: str):
        async with self.lock:
            self.stats[key] += 1
    
    async def get_stats(self) -> Dict[str, int]:
        async with self.lock:
            return dict(self.stats)


analytics = BotAnalytics()


async def send_log(chat_id: int, text: str, timeout: int = 8) -> bool:
    for attempt in range(3):
        try:
            await asyncio.wait_for(
                app.send_message(chat_id, text, disable_web_page_preview=True),
                timeout=timeout
            )
            return True
        except FloodWait as e:
            if attempt == 2: return False
            await asyncio.sleep(min(e.value + 1, 5))
        except (PeerIdInvalid, UserIsBlocked, ChatWriteForbidden):
            return False
        except Exception:
            if attempt == 2: return False
            await asyncio.sleep(0.5)
    return False


async def get_user_stats() -> Dict[str, Any]:
    try:
        total = await asyncio.wait_for(
            user_collection.count_documents({}), 
            timeout=2
        )
        return {"total_users": total}
    except asyncio.TimeoutError:
        return {"total_users": "N/A"}
    except Exception:
        return {"total_users": "Error"}


async def get_chat_info(chat: Chat) -> Dict[str, str]:
    cached = analytics.chat_cache.get(chat.id)
    if cached:
        return cached
    
    info = {
        "title": chat.title or "Private",
        "username": f"@{chat.username}" if chat.username else "ᴘʀɪᴠᴀᴛᴇ",
        "type": chat.type.value if hasattr(chat, 'type') else "unknown",
        "member_count": "N/A"
    }
    
    try:
        if hasattr(chat, 'members_count'):
            info["member_count"] = str(chat.members_count)
        elif chat.type in ["group", "supergroup"]:
            count = await asyncio.wait_for(
                app.get_chat_members_count(chat.id),
                timeout=2
            )
            info["member_count"] = str(count)
    except Exception:
        pass
    
    analytics.chat_cache[chat.id] = info
    return info


def format_user_mention(user: Optional[User]) -> str:
    if not user:
        return "ᴜɴᴋɴᴏᴡɴ ᴜsᴇʀ"
    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"


async def track_bot_start(user_id: int, first_name: str, username: str, is_new: bool):
    try:
        await analytics.increment("bot_starts")
        if is_new:
            await analytics.increment("new_users")
        
        user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        username_str = f"@{username}" if username else "ɴᴏ ᴜsᴇʀɴᴀᴍᴇ"
        
        if is_new:
            stats = await get_user_stats()
            status = f"ɴᴇᴡ ᴜsᴇʀ #{stats['total_users']}"
        else:
            status = "ʀᴇᴛᴜʀɴɪɴɢ ᴜsᴇʀ"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log = (
            f"˹𝐁ᴏᴛ 𝐒ᴛᴀʀᴛᴇᴅ˼ 🌸\n"
            f"#BOTSTART\n"
            f"sᴛᴀᴛᴜs : {status}\n"
            f"ᴜsᴇʀ : {user_mention}\n"
            f"ᴜsᴇʀ ɪᴅ : <code>{user_id}</code>\n"
            f"ᴜsᴇʀɴᴀᴍᴇ : {username_str}\n"
            f"ᴛɪᴍᴇ : {timestamp}"
        )
        
        await send_log(JOINLOGS, log)
    except Exception as e:
        print(f"❌ track_bot_start: {e}")


@app.on_message(filters.new_chat_members, group=1)
async def on_new_chat(client: Client, message: Message):
    try:
        bot = await client.get_me()
        if not any(u.id == bot.id for u in message.new_chat_members):
            return

        await analytics.increment("chats_joined")
        
        chat_info = await get_chat_info(message.chat)
        added_by = format_user_mention(message.from_user)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log = (
            f"˹𝐆ʀᴀʙʙɪɴɢ 𝐘ᴏᴜʀ 𝐖ᴀɪғᴜ˼ 🥀\n"
            f"#NEWCHAT\n"
            f"ᴄʜᴀᴛ : {chat_info['title']}\n"
            f"ɪᴅ : <code>{message.chat.id}</code>\n"
            f"ᴜsᴇʀɴᴀᴍᴇ : {chat_info['username']}\n"
            f"ᴛʏᴘᴇ : {chat_info['type']}\n"
            f"ᴍᴇᴍʙᴇʀs : {chat_info['member_count']}\n"
            f"ᴀᴅᴅᴇᴅ ʙʏ : {added_by}\n"
            f"ᴛɪᴍᴇ : {timestamp}"
        )
        
        asyncio.create_task(send_log(JOINLOGS, log))
    except Exception as e:
        print(f"❌ on_new_chat: {e}")


@app.on_message(filters.left_chat_member, group=1)
async def on_left_chat(client: Client, message: Message):
    try:
        bot = await client.get_me()
        if message.left_chat_member.id != bot.id:
            return

        await analytics.increment("chats_left")
        
        chat_info = await get_chat_info(message.chat)
        removed_by = format_user_mention(message.from_user)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log = (
            f"#ʟᴇғᴛ ɢʀᴏᴜᴘ ✫\n"
            f"ᴄʜᴀᴛ : {chat_info['title']}\n"
            f"ɪᴅ : <code>{message.chat.id}</code>\n"
            f"ᴜsᴇʀɴᴀᴍᴇ : {chat_info['username']}\n"
            f"ᴛʏᴘᴇ : {chat_info['type']}\n"
            f"ʀᴇᴍᴏᴠᴇᴅ ʙʏ : {removed_by}\n"
            f"ᴛɪᴍᴇ : {timestamp}"
        )
        
        asyncio.create_task(send_log(LEAVELOGS, log))
        
        if message.chat.id in analytics.chat_cache:
            del analytics.chat_cache[message.chat.id]
    except Exception as e:
        print(f"❌ on_left_chat: {e}")