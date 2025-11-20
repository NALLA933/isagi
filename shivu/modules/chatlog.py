import random
import asyncio
from pyrogram import Client
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Message
from pyrogram.errors import PeerIdInvalid, BadRequest, FloodWait, UserIsBlocked, ChatWriteForbidden
from shivu import user_collection, shivuu as app, LEAVELOGS, JOINLOGS


async def lul_message(chat_id: int, message: str):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await app.send_message(chat_id=chat_id, text=message, disable_web_page_preview=True)
            return True
        except FloodWait as e:
            wait_time = e.value + 1
            print(f"FloodWait: Waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time)
        except (PeerIdInvalid, BadRequest) as e:
            print(f"Peer/BadRequest error on attempt {attempt + 1}: {e}")
            await asyncio.sleep(3)
            try:
                chat = await app.get_chat(chat_id)
                print(f"Successfully resolved chat: {chat.id}")
                await asyncio.sleep(2)
            except Exception as resolve_err:
                print(f"Failed to resolve chat {chat_id}: {resolve_err}")
                if attempt == max_retries - 1:
                    return False
        except (UserIsBlocked, ChatWriteForbidden) as e:
            print(f"Cannot send to {chat_id}: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error on attempt {attempt + 1}: {e}")
            await asyncio.sleep(2)
    
    print(f"Failed to send message to {chat_id} after {max_retries} attempts")
    return False


async def track_bot_start(user_id: int, first_name: str, username: str, is_new: bool):
    try:
        user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        username_str = f"@{username}" if username else "ɴᴏ ᴜsᴇʀɴᴀᴍᴇ"

        if is_new:
            total_users = await user_collection.count_documents({})
            status = f"ɴᴇᴡ ᴜsᴇʀ #{total_users}"
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
        
        result = await lul_message(JOINLOGS, start_log)
        if result:
            print(f"✓ Bot start tracked for user {user_id}")
        else:
            print(f"✗ Failed to track bot start for user {user_id}")
            
    except Exception as e:
        print(f"Critical error in track_bot_start: {e}")


@app.on_message(filters.new_chat_members, group=1)
async def on_new_chat_members(client: Client, message: Message):
    try:
        bot = await client.get_me()
        bot_added = any(user.id == bot.id for user in message.new_chat_members)
        
        if bot_added:
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
            
            result = await lul_message(JOINLOGS, lemda_text)
            if result:
                print(f"✓ New chat logged: {chat_id}")
            else:
                print(f"✗ Failed to log new chat: {chat_id}")
                
    except Exception as e:
        print(f"Critical error in on_new_chat_members: {e}")


@app.on_message(filters.left_chat_member, group=1)
async def on_left_chat_member(client: Client, message: Message):
    try:
        bot = await client.get_me()
        
        if message.left_chat_member.id == bot.id:
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
            
            result = await lul_message(LEAVELOGS, left)
            if result:
                print(f"✓ Left chat logged: {chat_id}")
            else:
                print(f"✗ Failed to log left chat: {chat_id}")
                
    except Exception as e:
        print(f"Critical error in on_left_chat_member: {e}")