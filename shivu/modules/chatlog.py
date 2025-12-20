import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pyrogram import Client, filters
from pyrogram.types import Message, Chat, User
from pyrogram.errors import (
    PeerIdInvalid, BadRequest, FloodWait, 
    UserIsBlocked, ChatWriteForbidden
)
from shivu import user_collection, shivuu as app, LEAVELOGS, JOINLOGS


class AdvancedBotAnalytics:
    def __init__(self, max_cache_size: int = 500):
        self.stats = defaultdict(int)
        self.chat_cache = {}
        self.recent_events = deque(maxlen=100)
        self.max_cache_size = max_cache_size
        self.lock = asyncio.Lock()
        self.log_queue = asyncio.Queue(maxsize=100)
        self._processor_task = None
        self._started = False
    
    async def increment(self, key: str):
        async with self.lock:
            self.stats[key] += 1
    
    async def add_event(self, event_type: str, data: Dict[str, Any]):
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        async with self.lock:
            self.recent_events.append(event)
    
    async def cache_chat(self, chat_id: int, info: Dict[str, str]):
        async with self.lock:
            if len(self.chat_cache) >= self.max_cache_size:
                oldest = next(iter(self.chat_cache))
                del self.chat_cache[oldest]
            self.chat_cache[chat_id] = {
                **info,
                "cached_at": datetime.now().isoformat()
            }
    
    async def queue_log(self, chat_id: int, text: str, priority: int = 5):
        await self.ensure_processor_started()
        try:
            print(f"📥 Queuing log: priority={priority}, chat_id={chat_id}")
            await asyncio.wait_for(
                self.log_queue.put((priority, chat_id, text)),
                timeout=1.0
            )
            print(f"✓ Log queued successfully")
        except asyncio.TimeoutError:
            print(f"⚠️ Log queue full, dropping message for chat {chat_id}")
        except Exception as e:
            print(f"❌ Queue error: {e}")
    
    async def ensure_processor_started(self):
        if not self._started:
            print("⚡ Starting log processor for the first time")
            self._started = True
            self._processor_task = asyncio.create_task(self._process_logs())
            print("✓ Log processor task created")
    
    async def _process_logs(self):
        print("🚀 Log processor started")
        batch = []
        batch_timeout = 2.0
        
        while True:
            try:
                priority, chat_id, text = await asyncio.wait_for(
                    self.log_queue.get(),
                    timeout=batch_timeout
                )
                print(f"📨 Log received from queue: priority={priority}, chat_id={chat_id}")
                batch.append((priority, chat_id, text))
                
                if len(batch) >= 5:
                    print(f"📦 Batch size reached (5), sending batch")
                    await self._send_batch(batch)
                    batch = []
                    
            except asyncio.TimeoutError:
                if batch:
                    print(f"⏰ Timeout reached, sending {len(batch)} logs in batch")
                    await self._send_batch(batch)
                    batch = []
            except Exception as e:
                print(f"❌ Log processor error: {e}")
    
    async def _send_batch(self, batch: List[tuple]):
        print(f"📤 Sending batch of {len(batch)} logs")
        batch.sort(key=lambda x: x[0])
        
        tasks = [
            send_log_direct(chat_id, text, timeout=5)
            for _, chat_id, text in batch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in results if r is True)
        print(f"✓ Batch sent: {success_count}/{len(batch)} successful")


analytics = AdvancedBotAnalytics()


@asynccontextmanager
async def log_operation(operation_name: str):
    start = datetime.now()
    try:
        yield
    finally:
        duration = (datetime.now() - start).total_seconds()
        if duration > 3.0:
            print(f"⚠️ Slow operation: {operation_name} took {duration:.2f}s")


async def verify_log_channel():
    """Verify bot can access log channels"""
    try:
        # Try to get chat info
        chat = await app.get_chat(JOINLOGS)
        print(f"✅ Log channel verified: {chat.title} (ID: {JOINLOGS})")
        return True
    except PeerIdInvalid:
        print(f"❌ Cannot access log channel {JOINLOGS}")
        print(f"💡 Please add bot to channel and make it admin")
        return False
    except Exception as e:
        print(f"⚠️ Error verifying log channel: {e}")
        return False


async def send_log_direct(chat_id: int, text: str, timeout: int = 5) -> bool:
    print(f"🔄 Attempting to send log to chat_id={chat_id}")
    
    # Handle new supergroup ID format
    if str(chat_id).startswith("-100"):
        try:
            # Try sending with original ID first
            result = await attempt_send(chat_id, text, timeout)
            if result:
                return True
        except PeerIdInvalid:
            print(f"⚠️ PeerIdInvalid with original ID, trying alternative format")
    
    return await attempt_send(chat_id, text, timeout)


async def attempt_send(chat_id: int, text: str, timeout: int) -> bool:
    for attempt in range(2):
        try:
            result = await asyncio.wait_for(
                app.send_message(chat_id, text, disable_web_page_preview=True),
                timeout=timeout
            )
            print(f"✅ Log sent successfully to {chat_id}")
            return True
        except FloodWait as e:
            print(f"⏳ FloodWait: {e.value}s on attempt {attempt + 1}")
            if attempt == 1: return False
            await asyncio.sleep(min(e.value, 3))
        except (PeerIdInvalid, UserIsBlocked, ChatWriteForbidden) as e:
            print(f"🚫 Cannot send to {chat_id}: {type(e).__name__}")
            print(f"💡 Make sure bot is added to chat {chat_id} with message permissions")
            return False
        except Exception as e:
            print(f"❌ Send error (attempt {attempt + 1}): {type(e).__name__} - {e}")
            if attempt == 1: return False
            await asyncio.sleep(0.3)
    print(f"❌ Failed to send log to {chat_id} after 2 attempts")
    return False


async def send_log(chat_id: int, text: str, priority: int = 5):
    await analytics.queue_log(chat_id, text, priority)


async def get_user_stats() -> Dict[str, Any]:
    try:
        total = await asyncio.wait_for(
            user_collection.count_documents({}), 
            timeout=1.5
        )
        return {"total_users": total}
    except Exception:
        return {"total_users": "N/A"}


async def get_chat_info(chat: Chat) -> Dict[str, str]:
    cached = analytics.chat_cache.get(chat.id)
    if cached:
        try:
            cache_time = datetime.fromisoformat(cached["cached_at"])
            if (datetime.now() - cache_time).seconds < 3600:
                return cached
        except:
            pass
    
    info = {
        "title": chat.title or "Private",
        "username": f"@{chat.username}" if chat.username else "ᴘʀɪᴠᴀᴛᴇ",
        "type": chat.type.value if hasattr(chat, 'type') else "unknown",
        "member_count": "N/A"
    }
    
    try:
        if hasattr(chat, 'members_count') and chat.members_count:
            info["member_count"] = str(chat.members_count)
        elif chat.type in ["group", "supergroup"]:
            count = await asyncio.wait_for(
                app.get_chat_members_count(chat.id),
                timeout=1.5
            )
            info["member_count"] = str(count)
    except Exception:
        pass
    
    await analytics.cache_chat(chat.id, info)
    return info


def format_user_mention(user: Optional[User]) -> str:
    if not user:
        return "ᴜɴᴋɴᴏᴡɴ ᴜsᴇʀ"
    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"


def create_log_message(template: str, data: Dict[str, Any]) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S %d/%m/%y")
    base = f"{template}\n"
    for key, value in data.items():
        base += f"{key} : {value}\n"
    base += f"ᴛɪᴍᴇ : {timestamp}"
    return base


async def track_bot_start(user_id: int, first_name: str, username: str, is_new: bool):
    try:
        print(f"🔍 track_bot_start called: user={user_id}, is_new={is_new}")
        
        await analytics.increment("bot_starts")
        if is_new:
            await analytics.increment("new_users")
        
        user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        username_str = f"@{username}" if username else "ɴᴏ ᴜsᴇʀɴᴀᴍᴇ"
        
        stats = await get_user_stats()
        status = f"ɴᴇᴡ ᴜsᴇʀ #{stats['total_users']}" if is_new else "ʀᴇᴛᴜʀɴɪɴɢ ᴜsᴇʀ"
        
        data = {
            "sᴛᴀᴛᴜs": status,
            "ᴜsᴇʀ": user_mention,
            "ᴜsᴇʀ ɪᴅ": f"<code>{user_id}</code>",
            "ᴜsᴇʀɴᴀᴍᴇ": username_str
        }
        
        log = create_log_message("˹𝐁ᴏᴛ 𝐒ᴛᴀʀᴛᴇᴅ˼ 🌸\n#BOTSTART", data)
        
        print(f"📤 Queuing log to JOINLOGS={JOINLOGS}")
        await send_log(JOINLOGS, log, priority=3 if is_new else 5)
        print(f"✓ Log queued successfully for user {user_id}")
        
        await analytics.add_event("bot_start", {
            "user_id": user_id,
            "is_new": is_new
        })
    except Exception as e:
        print(f"❌ track_bot_start error: {e}")
        import traceback
        traceback.print_exc()


@app.on_message(filters.new_chat_members, group=1)
async def on_new_chat(client: Client, message: Message):
    try:
        async with log_operation("on_new_chat"):
            bot = await client.get_me()
            if not any(u.id == bot.id for u in message.new_chat_members):
                return

            await analytics.increment("chats_joined")
            
            chat_info = await get_chat_info(message.chat)
            added_by = format_user_mention(message.from_user)
            
            data = {
                "ᴄʜᴀᴛ": chat_info['title'],
                "ɪᴅ": f"<code>{message.chat.id}</code>",
                "ᴜsᴇʀɴᴀᴍᴇ": chat_info['username'],
                "ᴛʏᴘᴇ": chat_info['type'],
                "ᴍᴇᴍʙᴇʀs": chat_info['member_count'],
                "ᴀᴅᴅᴇᴅ ʙʏ": added_by
            }
            
            log = create_log_message("˹𝐆ʀᴀʙʙɪɴɢ 𝐘ᴏᴜʀ 𝐖ᴀɪғᴜ˼ 🥀\n#NEWCHAT", data)
            
            await send_log(JOINLOGS, log, priority=2)
            
            await analytics.add_event("chat_joined", {
                "chat_id": message.chat.id,
                "member_count": chat_info['member_count']
            })
    except Exception as e:
        print(f"❌ on_new_chat: {e}")


@app.on_message(filters.left_chat_member, group=1)
async def on_left_chat(client: Client, message: Message):
    try:
        async with log_operation("on_left_chat"):
            bot = await client.get_me()
            if message.left_chat_member.id != bot.id:
                return

            await analytics.increment("chats_left")
            
            chat_info = await get_chat_info(message.chat)
            removed_by = format_user_mention(message.from_user)
            
            data = {
                "ᴄʜᴀᴛ": chat_info['title'],
                "ɪᴅ": f"<code>{message.chat.id}</code>",
                "ᴜsᴇʀɴᴀᴍᴇ": chat_info['username'],
                "ᴛʏᴘᴇ": chat_info['type'],
                "ʀᴇᴍᴏᴠᴇᴅ ʙʏ": removed_by
            }
            
            log = create_log_message("#ʟᴇғᴛ ɢʀᴏᴜᴘ ✫", data)
            
            await send_log(LEAVELOGS, log, priority=4)
            
            await analytics.add_event("chat_left", {
                "chat_id": message.chat.id
            })
            
            if message.chat.id in analytics.chat_cache:
                async with analytics.lock:
                    del analytics.chat_cache[message.chat.id]
    except Exception as e:
        print(f"❌ on_left_chat: {e}")


print("✓ Chatlog module loaded successfully")


# Verify log channel access on startup
async def startup_check():
    print("🔍 Verifying log channel access...")
    await verify_log_channel()

asyncio.create_task(startup_check()) if asyncio.get_event_loop().is_running() else None