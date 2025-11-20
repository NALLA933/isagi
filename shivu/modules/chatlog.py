import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import PeerIdInvalid, BadRequest, FloodWait
from shivu import user_collection, shivuu as app, LEAVELOGS, JOINLOGS


async def send_log_message(chat_id: int, message: str, retries: int = 3):
    for attempt in range(retries):
        try:
            await app.send_message(chat_id=chat_id, text=message)
            return True
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except (PeerIdInvalid, BadRequest):
            if attempt < retries - 1:
                await asyncio.sleep(2)
                try:
                    await app.get_chat(chat_id)
                    await asyncio.sleep(1)
                except:
                    pass
            else:
                return False
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(2)
            else:
                return False
    return False


async def track_bot_start(user_id: int, first_name: str, username: str, is_new: bool):
    try:
        user_mention = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        username_str = f"@{username}" if username else "No Username"

        if is_new:
            total_users = await user_collection.count_documents({})
            status = f"New User #{total_users}"
        else:
            status = "Returning User"

        start_log = (
            f"BOT STARTED\n"
            f"#BOTSTART\n"
            f"Status: {status}\n"
            f"User: {user_mention}\n"
            f"User ID: `{user_id}`\n"
            f"Username: {username_str}"
        )
        
        await send_log_message(JOINLOGS, start_log)
    except Exception as e:
        print(f"Failed to track bot start: {e}")


@app.on_message(filters.new_chat_members)
async def on_new_chat_members(client: Client, message: Message):
    try:
        bot_id = (await client.get_me()).id
        if bot_id in [user.id for user in message.new_chat_members]:
            added_by = message.from_user.mention if message.from_user else "Unknown User"
            chat_title = message.chat.title
            chat_id = message.chat.id
            chat_username = f"@{message.chat.username}" if message.chat.username else "Private Chat"
            
            join_log = (
                f"isagi randi dekh \n"
                f"#NEWCHAT\n"
                f"Chat Title: {chat_title}\n"
                f"Chat ID: {chat_id}\n"
                f"Chat Username: {chat_username}\n"
                f"mera lelo mume: {added_by}"
            )
            
            await send_log_message(JOINLOGS, join_log)
    except Exception as e:
        print(f"Error in new chat handler: {e}")


@app.on_message(filters.left_chat_member)
async def on_left_chat_member(client: Client, message: Message):
    try:
        bot_id = (await client.get_me()).id
        if message.left_chat_member.id == bot_id:
            removed_by = message.from_user.mention if message.from_user else "Unknown User"
            chat_title = message.chat.title
            chat_username = f"@{message.chat.username}" if message.chat.username else "Private Chat"
            chat_id = message.chat.id
            
            leave_log = (
                f"LEFT GROUP\n"
                f"#LEFTGROUP\n"
                f"Chat Title: {chat_title}\n"
                f"Chat ID: {chat_id}\n"
                f"Chat Username: {chat_username}\n"
                f"MKC iss bandeki: {removed_by}"
            )
            
            await send_log_message(LEAVELOGS, leave_log)
    except Exception as e:
        print(f"Error in left chat handler: {e}")