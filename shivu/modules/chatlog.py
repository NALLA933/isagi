import random
import asyncio
from pyrogram import Client
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Message
from pyrogram.errors import PeerIdInvalid, BadRequest, FloodWait, UserIsBlocked, ChatWriteForbidden
from shivu import user_collection, shivuu as app, LEAVELOGS, JOINLOGS


async def lul_message(chat_id: int, message: str, timeout: int = 10):
    """
    Send message with retry logic and timeout protection
    """
    max_retries = 3  # Reduced from 5 to 3 for faster failure
    
    try:
        # Wrap the entire retry logic in a timeout
        return await asyncio.wait_for(
            _send_with_retry(chat_id, message, max_retries),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        print(f"⏱️ Timeout sending message to {chat_id} after {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in lul_message: {e}")
        return False


async def _send_with_retry(chat_id: int, message: str, max_retries: int):
    """Internal function for retry logic"""
    for attempt in range(max_retries):
        try:
            await app.send_message(chat_id=chat_id, text=message, disable_web_page_preview=True)
            return True
            
        except FloodWait as e:
            if attempt == max_retries - 1:
                print(f"❌ FloodWait limit reached for {chat_id}")
                return False
            wait_time = min(e.value + 1, 5)  # Cap wait time at 5 seconds
            print(f"⏳ FloodWait: Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
            
        except PeerIdInvalid:
            print(f"⚠️ Invalid peer ID: {chat_id}. Bot may not be member of this chat.")
            return False
            
        except BadRequest as e:
            if "PEER_ID_INVALID" in str(e):
                print(f"⚠️ Chat {chat_id} not accessible. Bot needs to join this chat first.")
                return False
            print(f"⚠️ BadRequest on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            else:
                return False
                
        except (UserIsBlocked, ChatWriteForbidden) as e:
            print(f"🚫 Cannot send to {chat_id}: {e}")
            return False
            
        except Exception as e:
            print(f"❌ Error on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
            else:
                return False

    print(f"❌ Failed to send message to {chat_id} after {max_retries} attempts")
    return False


async def track_bot_start(user_id: int, first_name: str, username: str, is_new: bool):
    """
    Track bot start event. Called asynchronously from start.py
    """
    try:
        user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        username_str = f"@{username}" if username else "ɴᴏ ᴜsᴇʀɴᴀᴍᴇ"

        if is_new:
            try:
                total_users = await asyncio.wait_for(
                    user_collection.count_documents({}),
                    timeout=3.0
                )
                status = f"ɴᴇᴡ ᴜsᴇʀ #{total_users}"
            except asyncio.TimeoutError:
                status = "ɴᴇᴡ ᴜsᴇʀ"
                print(f"⏱️ Timeout counting users for {user_id}")
        else:
            status = "ʀᴇᴛᴜʀɴɪɴɢ ᴜsᴇʀ"

        start_log = (
            f"˹𝐁ᴏᴛ 𝐒ᴛᴀʀᴛᴇᴅ˼ 🌸\n"
            f"#BOTSTART\n"
            f" sᴛᴀᴛᴜs : {status}\n"
            f" ᴜsᴇʀ : {user_mention}\n"
            f" ᴜsᴇʀ ɪᴅ : <code>{user_id}</code>\n"
            f" ᴜsᴇʀɴᴀᴍᴇ : {username_str}"
        )

        # Use timeout of 8 seconds for the entire operation
        result = await lul_message(JOINLOGS, start_log, timeout=8)
        
        if result:
            print(f"✓ Bot start tracked for user {user_id}")
        else:
            print(f"✗ Failed to track bot start for user {user_id}")

    except Exception as e:
        print(f"❌ Critical error in track_bot_start: {e}")


@app.on_message(filters.new_chat_members, group=1)
async def on_new_chat_members(client: Client, message: Message):
    """Log when bot is added to new chats"""
    try:
        bot = await client.get_me()
        bot_added = any(user.id == bot.id for user in message.new_chat_members)

        if not bot_added:
            return

        added_by = message.from_user.mention if message.from_user else "ᴜɴᴋɴᴏᴡɴ ᴜsᴇʀ"
        matlabi_jhanto = message.chat.title
        chat_id = message.chat.id
        chatusername = f"@{message.chat.username}" if message.chat.username else "ᴩʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ"

        lemda_text = (
            f"˹𝐆ʀᴀʙʙɪɴɢ 𝐘ᴏᴜʀ 𝐖ᴀɪғᴜ˼ 🥀\n"
            f"#NEWCHAT\n"
            f" ᴄʜᴀᴛ ᴛɪᴛʟᴇ : {matlabi_jhanto}\n"
            f" ᴄʜᴀᴛ ɪᴅ : <code>{chat_id}</code>\n"
            f" ᴄʜᴀᴛ ᴜɴᴀᴍᴇ : {chatusername}\n"
            f" ᴀᴅᴅᴇᴅ ʙʏ : {added_by}"
        )

        # Send log in background without blocking
        asyncio.create_task(_log_new_chat(chat_id, lemda_text))

    except Exception as e:
        print(f"❌ Critical error in on_new_chat_members: {e}")


async def _log_new_chat(chat_id: int, message: str):
    """Background task to log new chat"""
    try:
        result = await lul_message(JOINLOGS, message, timeout=10)
        if result:
            print(f"✓ New chat logged: {chat_id}")
        else:
            print(f"✗ Failed to log new chat: {chat_id}")
    except Exception as e:
        print(f"❌ Error logging new chat: {e}")


@app.on_message(filters.left_chat_member, group=1)
async def on_left_chat_member(client: Client, message: Message):
    """Log when bot leaves or is removed from chats"""
    try:
        bot = await client.get_me()

        if message.left_chat_member.id != bot.id:
            return

        remove_by = message.from_user.mention if message.from_user else "ᴜɴᴋɴᴏᴡɴ ᴜꜱᴇʀ"
        title = message.chat.title
        username = f"@{message.chat.username}" if message.chat.username else "ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ"
        chat_id = message.chat.id

        left = (
            f"#ʟᴇꜰᴛ ɢʀᴏᴜᴘ ✫\n"
            f" ᴄʜᴀᴛ ᴛɪᴛʟᴇ : {title}\n"
            f" ᴄʜᴀᴛ ɪᴅ : <code>{chat_id}</code>\n"
            f" ᴄʜᴀᴛ ᴜɴᴀᴍᴇ : {username}\n"
            f" ʀᴇᴍᴏᴠᴇᴅ ʙʏ : {remove_by}"
        )

        # Send log in background without blocking
        asyncio.create_task(_log_left_chat(chat_id, left))

    except Exception as e:
        print(f"❌ Critical error in on_left_chat_member: {e}")


async def _log_left_chat(chat_id: int, message: str):
    """Background task to log left chat"""
    try:
        result = await lul_message(LEAVELOGS, message, timeout=10)
        if result:
            print(f"✓ Left chat logged: {chat_id}")
        else:
            print(f"✗ Failed to log left chat: {chat_id}")
    except Exception as e:
        print(f"❌ Error logging left chat: {e}")