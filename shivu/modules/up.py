from pyrogram import filters, enums
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, FloodWait, UserAdminInvalid, PeerIdInvalid, RPCError
from shivu import shivuu as app, global_ban_users_collection, BANNED_USERS, user_collection, user_totals_collection, group_user_totals_collection
import asyncio
from datetime import datetime

OWNER_IDS = [8420981179, 5147822244]

async def get_all_chats(client):
    chats = []
    async for dialog in client.get_dialogs():
        if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            chats.append(dialog.chat.id)
    return chats

async def get_user_info(client, target_id):
    try:
        user = await client.get_users(target_id)
        return {
            "id": user.id,
            "name": user.first_name,
            "username": user.username or "No username"
        }
    except:
        return {
            "id": target_id,
            "name": "Unknown User",
            "username": "Unknown"
        }

async def ban_user_from_chat(client, chat_id, user_id):
    try:
        await client.ban_chat_member(chat_id, user_id)
        return "success"
    except UserNotParticipant:
        return "not_in_chat"
    except (ChatAdminRequired, UserAdminInvalid):
        return "no_permission"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await client.ban_chat_member(chat_id, user_id)
            return "success"
        except:
            return "error"
    except:
        return "error"

async def unban_user_from_chat(client, chat_id, user_id):
    try:
        await client.unban_chat_member(chat_id, user_id)
        return "success"
    except (ChatAdminRequired, UserAdminInvalid):
        return "no_permission"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await client.unban_chat_member(chat_id, user_id)
            return "success"
        except:
            return "error"
    except:
        return "error"

async def process_chats_parallel(client, chats, user_id, operation="ban"):
    results = {"success": 0, "no_permission": 0, "not_in_chat": 0, "error": 0}
    
    async def process_single_chat(chat_id):
        try:
            member = await client.get_chat_member(chat_id, client.me.id)
            if not (member.privileges and member.privileges.can_restrict_members):
                return "no_permission"
            
            if operation == "ban":
                return await ban_user_from_chat(client, chat_id, user_id)
            else:
                return await unban_user_from_chat(client, chat_id, user_id)
        except:
            return "no_permission"
    
    semaphore = asyncio.Semaphore(10)
    
    async def process_with_semaphore(chat_id):
        async with semaphore:
            result = await process_single_chat(chat_id)
            await asyncio.sleep(0.05)
            return result
    
    tasks = [process_with_semaphore(chat_id) for chat_id in chats]
    task_results = await asyncio.gather(*tasks)
    
    for result in task_results:
        results[result] = results.get(result, 0) + 1
    
    return results

@app.on_message(filters.command("gban"))
async def global_ban(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return
    
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_id = target_user.id
        target_username = target_user.username or "No username"
        target_name = target_user.first_name
        reason = " ".join(message.command[1:]) if len(message.command) > 1 else "No reason provided"
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
            user_info = await get_user_info(client, target_id)
            target_name = user_info["name"]
            target_username = user_info["username"]
            reason = " ".join(message.command[2:]) if len(message.command) > 2 else "No reason provided"
        except ValueError:
            await message.reply_text("Invalid user ID. Please reply to a user or provide a valid user ID.")
            return
    else:
        await message.reply_text("Usage: /gban <user_id> <reason> or reply to a user with /gban <reason>")
        return
    
    if target_id in OWNER_IDS:
        await message.reply_text("Cannot ban an owner.")
        return
    
    existing_ban = await global_ban_users_collection.find_one({"user_id": target_id})
    if existing_ban:
        await message.reply_text(f"User {target_name} ({target_id}) is already globally banned.")
        return
    
    status_msg = await message.reply_text(
        f"Starting Global Ban\n\n"
        f"User: {target_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Reason: {reason}\n\n"
        f"Processing..."
    )
    
    await asyncio.gather(
        global_ban_users_collection.insert_one({
            "user_id": target_id,
            "username": target_username,
            "name": target_name,
            "reason": reason,
            "banned_by": user_id,
            "banned_at": datetime.now()
        }),
        BANNED_USERS.insert_one({
            "user_id": target_id,
            "username": target_username,
            "reason": reason
        }),
        user_collection.delete_many({"user_id": target_id}),
        user_totals_collection.delete_many({"id": target_id}),
        group_user_totals_collection.delete_many({"user_id": target_id})
    )
    
    all_chats = await get_all_chats(client)
    total_groups = len(all_chats)
    
    await status_msg.edit_text(
        f"Starting Global Ban\n\n"
        f"User: {target_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Reason: {reason}\n\n"
        f"Found {total_groups} groups\n"
        f"Banning with parallel processing..."
    )
    
    results = await process_chats_parallel(client, all_chats, target_id, "ban")
    
    final_message = (
        f"Global Ban Completed\n\n"
        f"User: {target_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Reason: {reason}\n\n"
        f"Final Statistics:\n"
        f"Total Groups: {total_groups}\n"
        f"Successfully Banned: {results['success']}\n"
        f"No Ban Permission: {results['no_permission']}\n"
        f"User Not in Chat: {results.get('not_in_chat', 0)}\n"
        f"Other Errors: {results['error']}\n\n"
        f"Database: All user data removed\n"
        f"Status: Globally banned"
    )
    
    await status_msg.edit_text(final_message)

@app.on_message(filters.command("ungban"))
async def global_unban(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return
    
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_id = target_user.id
        target_username = target_user.username or "No username"
        target_name = target_user.first_name
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
            user_info = await get_user_info(client, target_id)
            target_name = user_info["name"]
            target_username = user_info["username"]
        except ValueError:
            await message.reply_text("Invalid user ID.")
            return
    else:
        await message.reply_text("Usage: /ungban <user_id> or reply to a user with /ungban")
        return
    
    existing_ban = await global_ban_users_collection.find_one({"user_id": target_id})
    if not existing_ban:
        await message.reply_text(f"User {target_name} ({target_id}) is not globally banned.")
        return
    
    status_msg = await message.reply_text(
        f"Removing Global Ban\n\n"
        f"User: {target_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n\n"
        f"Processing..."
    )
    
    await asyncio.gather(
        global_ban_users_collection.delete_one({"user_id": target_id}),
        BANNED_USERS.delete_one({"user_id": target_id})
    )
    
    all_chats = await get_all_chats(client)
    total_groups = len(all_chats)
    
    await status_msg.edit_text(
        f"Removing Global Ban\n\n"
        f"User: {target_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n\n"
        f"Found {total_groups} groups\n"
        f"Unbanning with parallel processing..."
    )
    
    results = await process_chats_parallel(client, all_chats, target_id, "unban")
    
    final_message = (
        f"Global Unban Completed\n\n"
        f"User: {target_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n\n"
        f"Final Statistics:\n"
        f"Total Groups: {total_groups}\n"
        f"Successfully Unbanned: {results['success']}\n"
        f"No Ban Permission: {results['no_permission']}\n"
        f"Other Errors: {results['error']}\n\n"
        f"Status: User can now use the bot"
    )
    
    await status_msg.edit_text(final_message)

@app.on_message(filters.command("gbanlist"))
async def gban_list(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return
    
    gbanned_users = await global_ban_users_collection.find().to_list(length=None)
    
    if not gbanned_users:
        await message.reply_text("No users are currently globally banned.")
        return
    
    text = f"Globally Banned Users ({len(gbanned_users)}):\n\n"
    
    for idx, user in enumerate(gbanned_users, 1):
        text += f"{idx}. {user['name']}\n"
        text += f"   ID: {user['user_id']}\n"
        text += f"   Username: @{user['username']}\n"
        text += f"   Reason: {user['reason']}\n\n"
        
        if len(text) > 3500:
            await message.reply_text(text)
            text = ""
    
    if text:
        await message.reply_text(text)

@app.on_message(filters.group & filters.incoming)
async def check_gbanned_user(client, message):
    if message.from_user and message.from_user.id:
        user_id = message.from_user.id
        
        is_gbanned = await global_ban_users_collection.find_one({"user_id": user_id})
        
        if is_gbanned:
            try:
                me = await client.get_chat_member(message.chat.id, client.me.id)
                
                if me.privileges and me.privileges.can_restrict_members:
                    await client.ban_chat_member(message.chat.id, user_id)
                    
                    user_name = message.from_user.first_name
                    username = message.from_user.username or "No username"
                    
                    await message.reply_text(
                        f"Globally Banned User Detected\n\n"
                        f"User: {user_name}\n"
                        f"ID: {user_id}\n"
                        f"Username: @{username}\n"
                        f"Reason: {is_gbanned['reason']}\n\n"
                        f"User has been automatically banned"
                    )
            except:
                pass