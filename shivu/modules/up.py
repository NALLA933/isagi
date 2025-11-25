from pyrogram import filters, enums
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, FloodWait, UserAdminInvalid, PeerIdInvalid, RPCError
from shivu import shivuu as app, global_ban_users_collection, BANNED_USERS, user_collection, user_totals_collection, group_user_totals_collection
import asyncio
from datetime import datetime
import time

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
            "username": user.username or "No username",
            "full_name": f"{user.first_name} {user.last_name}" if user.last_name else user.first_name
        }
    except:
        return {
            "id": target_id,
            "name": "Unknown User",
            "username": "Unknown",
            "full_name": "Unknown User"
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

async def process_chats_parallel(client, chats, user_id, operation="ban", status_msg=None, target_info=None):
    results = {"success": 0, "no_permission": 0, "not_in_chat": 0, "error": 0}
    total_chats = len(chats)
    processed = 0
    
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
    
    semaphore = asyncio.Semaphore(15)
    
    async def process_with_semaphore(chat_id):
        nonlocal processed
        async with semaphore:
            result = await process_single_chat(chat_id)
            processed += 1
            
            if status_msg and target_info and processed % 50 == 0:
                try:
                    progress = (processed / total_chats) * 100
                    temp_results = {k: results.get(k, 0) for k in results}
                    for r in ["success", "no_permission", "not_in_chat", "error"]:
                        temp_results[r] = results.get(r, 0)
                    
                    await status_msg.edit_text(
                        f"{'Banning' if operation == 'ban' else 'Unbanning'} in Progress\n\n"
                        f"User: {target_info['name']}\n"
                        f"ID: {target_info['id']}\n"
                        f"Username: @{target_info['username']}\n\n"
                        f"Progress: {processed}/{total_chats} ({progress:.1f}%)\n"
                        f"Success: {temp_results['success']} | "
                        f"No Perm: {temp_results['no_permission']} | "
                        f"Errors: {temp_results['error']}"
                    )
                except:
                    pass
            
            await asyncio.sleep(0.03)
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
        target_full_name = f"{target_user.first_name} {target_user.last_name}" if target_user.last_name else target_user.first_name
        reason = " ".join(message.command[1:]) if len(message.command) > 1 else "No reason provided"
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
            user_info = await get_user_info(client, target_id)
            target_name = user_info["name"]
            target_username = user_info["username"]
            target_full_name = user_info["full_name"]
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
    
    start_time = time.time()
    
    status_msg = await message.reply_text(
        f"Initiating Global Ban\n\n"
        f"Target User: {target_full_name}\n"
        f"User ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Reason: {reason}\n\n"
        f"Scanning groups and preparing database..."
    )
    
    banned_by_user = message.from_user
    banned_by_name = f"{banned_by_user.first_name} {banned_by_user.last_name}" if banned_by_user.last_name else banned_by_user.first_name
    
    all_chats = await get_all_chats(client)
    total_groups = len(all_chats)
    
    await status_msg.edit_text(
        f"Initiating Global Ban\n\n"
        f"Target User: {target_full_name}\n"
        f"User ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Reason: {reason}\n\n"
        f"Groups Found: {total_groups}\n"
        f"Updating database and executing ban..."
    )
    
    await asyncio.gather(
        global_ban_users_collection.insert_one({
            "user_id": target_id,
            "username": target_username,
            "name": target_name,
            "full_name": target_full_name,
            "reason": reason,
            "banned_by": user_id,
            "banned_by_name": banned_by_name,
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
    
    target_info = {
        "id": target_id,
        "name": target_full_name,
        "username": target_username
    }
    
    results = await process_chats_parallel(client, all_chats, target_id, "ban", status_msg, target_info)
    
    elapsed_time = time.time() - start_time
    ban_rate = results['success'] / elapsed_time if elapsed_time > 0 else 0
    
    final_message = (
        f"Global Ban Executed Successfully\n\n"
        f"Target Information:\n"
        f"Name: {target_full_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Reason: {reason}\n"
        f"Banned By: {banned_by_name}\n\n"
        f"Execution Statistics:\n"
        f"Total Groups Scanned: {total_groups}\n"
        f"Successfully Banned From: {results['success']}\n"
        f"No Permission: {results['no_permission']}\n"
        f"User Not Present: {results.get('not_in_chat', 0)}\n"
        f"Failed Operations: {results['error']}\n\n"
        f"Performance Metrics:\n"
        f"Execution Time: {elapsed_time:.2f}s\n"
        f"Ban Rate: {ban_rate:.2f} groups/sec\n\n"
        f"Database Status: All user data purged\n"
        f"Global Status: User is now globally banned"
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
        target_full_name = f"{target_user.first_name} {target_user.last_name}" if target_user.last_name else target_user.first_name
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
            user_info = await get_user_info(client, target_id)
            target_name = user_info["name"]
            target_username = user_info["username"]
            target_full_name = user_info["full_name"]
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
    
    start_time = time.time()
    
    status_msg = await message.reply_text(
        f"Initiating Global Unban\n\n"
        f"User: {target_full_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Original Reason: {existing_ban.get('reason', 'Unknown')}\n\n"
        f"Scanning groups and updating database..."
    )
    
    all_chats = await get_all_chats(client)
    total_groups = len(all_chats)
    
    await status_msg.edit_text(
        f"Initiating Global Unban\n\n"
        f"User: {target_full_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n\n"
        f"Groups Found: {total_groups}\n"
        f"Removing ban records and executing unban..."
    )
    
    await asyncio.gather(
        global_ban_users_collection.delete_one({"user_id": target_id}),
        BANNED_USERS.delete_one({"user_id": target_id})
    )
    
    target_info = {
        "id": target_id,
        "name": target_full_name,
        "username": target_username
    }
    
    results = await process_chats_parallel(client, all_chats, target_id, "unban", status_msg, target_info)
    
    elapsed_time = time.time() - start_time
    unban_rate = results['success'] / elapsed_time if elapsed_time > 0 else 0
    
    unbanned_by_user = message.from_user
    unbanned_by_name = f"{unbanned_by_user.first_name} {unbanned_by_user.last_name}" if unbanned_by_user.last_name else unbanned_by_user.first_name
    
    final_message = (
        f"Global Unban Executed Successfully\n\n"
        f"User Information:\n"
        f"Name: {target_full_name}\n"
        f"ID: {target_id}\n"
        f"Username: @{target_username}\n"
        f"Unbanned By: {unbanned_by_name}\n\n"
        f"Execution Statistics:\n"
        f"Total Groups Scanned: {total_groups}\n"
        f"Successfully Unbanned From: {results['success']}\n"
        f"No Permission: {results['no_permission']}\n"
        f"Failed Operations: {results['error']}\n\n"
        f"Performance Metrics:\n"
        f"Execution Time: {elapsed_time:.2f}s\n"
        f"Unban Rate: {unban_rate:.2f} groups/sec\n\n"
        f"Status: User has been globally unbanned"
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
    
    text = f"Globally Banned Users Database\nTotal: {len(gbanned_users)} users\n\n"
    
    for idx, user in enumerate(gbanned_users, 1):
        banned_date = user.get('banned_at', 'Unknown')
        if isinstance(banned_date, datetime):
            banned_date = banned_date.strftime("%Y-%m-%d %H:%M")
        
        text += f"{idx}. {user.get('full_name', user['name'])}\n"
        text += f"   ID: {user['user_id']}\n"
        text += f"   Username: @{user['username']}\n"
        text += f"   Reason: {user['reason']}\n"
        text += f"   Banned By: {user.get('banned_by_name', 'Unknown')}\n"
        text += f"   Date: {banned_date}\n\n"
        
        if len(text) > 3500:
            await message.reply_text(text)
            text = ""
    
    if text:
        await message.reply_text(text)

@app.on_message(filters.command("gbaninfo"))
async def gban_info(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("You are not authorized to use this command.")
        return
    
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
        except ValueError:
            await message.reply_text("Invalid user ID.")
            return
    else:
        await message.reply_text("Usage: /gbaninfo <user_id> or reply to a user")
        return
    
    ban_info = await global_ban_users_collection.find_one({"user_id": target_id})
    
    if not ban_info:
        await message.reply_text(f"User {target_id} is not globally banned.")
        return
    
    banned_date = ban_info.get('banned_at', 'Unknown')
    if isinstance(banned_date, datetime):
        banned_date = banned_date.strftime("%Y-%m-%d %H:%M:%S")
    
    info_text = (
        f"Global Ban Information\n\n"
        f"User: {ban_info.get('full_name', ban_info['name'])}\n"
        f"ID: {ban_info['user_id']}\n"
        f"Username: @{ban_info['username']}\n"
        f"Reason: {ban_info['reason']}\n"
        f"Banned By: {ban_info.get('banned_by_name', 'Unknown')} ({ban_info['banned_by']})\n"
        f"Banned On: {banned_date}\n"
    )
    
    await message.reply_text(info_text)

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
                    user_full_name = f"{message.from_user.first_name} {message.from_user.last_name}" if message.from_user.last_name else message.from_user.first_name
                    username = message.from_user.username or "No username"
                    
                    await message.reply_text(
                        f"Globally Banned User Detected and Removed\n\n"
                        f"User: {user_full_name}\n"
                        f"ID: {user_id}\n"
                        f"Username: @{username}\n"
                        f"Ban Reason: {is_gbanned['reason']}\n"
                        f"Banned By: {is_gbanned.get('banned_by_name', 'Unknown')}\n\n"
                        f"Action: User automatically banned from this group"
                    )
            except:
                pass