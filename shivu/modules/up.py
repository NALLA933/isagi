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

@app.on_message(filters.command("gban"))
async def global_ban(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("❌ You are not authorized to use this command.")
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
            try:
                target_user = await client.get_users(target_id)
                target_username = target_user.username or "No username"
                target_name = target_user.first_name
            except:
                target_username = "Unknown"
                target_name = "Unknown User"
            reason = " ".join(message.command[2:]) if len(message.command) > 2 else "No reason provided"
        except ValueError:
            await message.reply_text("❌ Invalid user ID. Please reply to a user or provide a valid user ID.")
            return
    else:
        await message.reply_text("❌ Usage: `/gban <user_id> <reason>` or reply to a user with `/gban <reason>`")
        return
    
    if target_id in OWNER_IDS:
        await message.reply_text("❌ Cannot ban an owner!")
        return
    
    existing_ban = await global_ban_users_collection.find_one({"user_id": target_id})
    if existing_ban:
        await message.reply_text(f"⚠️ User {target_name} ({target_id}) is already globally banned!")
        return
    
    status_msg = await message.reply_text(
        f"🔨 **Starting Global Ban**\n\n"
        f"👤 User: {target_name}\n"
        f"🆔 ID: `{target_id}`\n"
        f"📝 Reason: {reason}\n\n"
        f"⏳ Collecting all groups..."
    )
    
    await global_ban_users_collection.insert_one({
        "user_id": target_id,
        "username": target_username,
        "name": target_name,
        "reason": reason,
        "banned_by": user_id,
        "banned_at": datetime.now()
    })
    
    await BANNED_USERS.insert_one({
        "user_id": target_id,
        "username": target_username,
        "reason": reason
    })
    
    await user_collection.delete_many({"user_id": target_id})
    await user_totals_collection.delete_many({"id": target_id})
    await group_user_totals_collection.delete_many({"user_id": target_id})
    
    all_chats = await get_all_chats(client)
    total_groups = len(all_chats)
    
    await status_msg.edit_text(
        f"🔨 **Starting Global Ban**\n\n"
        f"👤 User: {target_name}\n"
        f"🆔 ID: `{target_id}`\n"
        f"📝 Reason: {reason}\n\n"
        f"📊 Found {total_groups} groups\n"
        f"⏳ Banning in progress..."
    )
    
    banned_from = 0
    no_permission = 0
    user_not_in_chat = 0
    other_errors = 0
    
    for idx, chat_id in enumerate(all_chats, 1):
        try:
            member = await client.get_chat_member(chat_id, client.me.id)
            
            if member.privileges and member.privileges.can_restrict_members:
                try:
                    await client.ban_chat_member(
                        chat_id=chat_id,
                        user_id=target_id
                    )
                    banned_from += 1
                except UserNotParticipant:
                    user_not_in_chat += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    try:
                        await client.ban_chat_member(chat_id, target_id)
                        banned_from += 1
                    except:
                        other_errors += 1
                except (ChatAdminRequired, UserAdminInvalid):
                    no_permission += 1
                except Exception as e:
                    other_errors += 1
            else:
                no_permission += 1
            
            if idx % 20 == 0 or idx == total_groups:
                try:
                    progress = (idx / total_groups) * 100
                    await status_msg.edit_text(
                        f"🔨 **Global Ban Progress**\n\n"
                        f"👤 User: {target_name}\n"
                        f"🆔 ID: `{target_id}`\n\n"
                        f"📊 Progress: {idx}/{total_groups} ({progress:.1f}%)\n\n"
                        f"✅ Banned: **{banned_from}**\n"
                        f"🚫 No Permission: **{no_permission}**\n"
                        f"👻 Not in Chat: **{user_not_in_chat}**\n"
                        f"❌ Other Errors: **{other_errors}**"
                    )
                except:
                    pass
            
            await asyncio.sleep(0.1)
            
        except Exception as e:
            other_errors += 1
            continue
    
    final_message = (
        f"✅ **Global Ban Completed!**\n\n"
        f"👤 **User:** {target_name}\n"
        f"🆔 **ID:** `{target_id}`\n"
        f"👤 **Username:** @{target_username}\n"
        f"📝 **Reason:** {reason}\n\n"
        f"📊 **Final Statistics:**\n"
        f"🗂 Total Groups: **{total_groups}**\n"
        f"✅ Successfully Banned: **{banned_from}**\n"
        f"🚫 No Ban Permission: **{no_permission}**\n"
        f"👻 User Not in Chat: **{user_not_in_chat}**\n"
        f"❌ Other Errors: **{other_errors}**\n\n"
        f"🗑 **Database:** All user data removed\n"
        f"🔒 **Status:** Globally banned!"
    )
    
    await status_msg.edit_text(final_message)

@app.on_message(filters.command("ungban"))
async def global_unban(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("❌ You are not authorized to use this command.")
        return
    
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_id = target_user.id
        target_name = target_user.first_name
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
            try:
                target_user = await client.get_users(target_id)
                target_name = target_user.first_name
            except:
                target_name = "Unknown User"
        except ValueError:
            await message.reply_text("❌ Invalid user ID.")
            return
    else:
        await message.reply_text("❌ Usage: `/ungban <user_id>` or reply to a user with `/ungban`")
        return
    
    existing_ban = await global_ban_users_collection.find_one({"user_id": target_id})
    if not existing_ban:
        await message.reply_text(f"⚠️ User {target_name} ({target_id}) is not globally banned!")
        return
    
    status_msg = await message.reply_text(
        f"🔓 **Removing Global Ban**\n\n"
        f"👤 User: {target_name}\n"
        f"🆔 ID: `{target_id}`\n\n"
        f"⏳ Collecting all groups..."
    )
    
    await global_ban_users_collection.delete_one({"user_id": target_id})
    await BANNED_USERS.delete_one({"user_id": target_id})
    
    all_chats = await get_all_chats(client)
    total_groups = len(all_chats)
    
    await status_msg.edit_text(
        f"🔓 **Removing Global Ban**\n\n"
        f"👤 User: {target_name}\n"
        f"🆔 ID: `{target_id}`\n\n"
        f"📊 Found {total_groups} groups\n"
        f"⏳ Unbanning in progress..."
    )
    
    unbanned_from = 0
    no_permission = 0
    not_banned = 0
    other_errors = 0
    
    for idx, chat_id in enumerate(all_chats, 1):
        try:
            member = await client.get_chat_member(chat_id, client.me.id)
            
            if member.privileges and member.privileges.can_restrict_members:
                try:
                    await client.unban_chat_member(chat_id, target_id)
                    unbanned_from += 1
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    try:
                        await client.unban_chat_member(chat_id, target_id)
                        unbanned_from += 1
                    except:
                        other_errors += 1
                except (ChatAdminRequired, UserAdminInvalid):
                    no_permission += 1
                except Exception as e:
                    other_errors += 1
            else:
                no_permission += 1
            
            if idx % 20 == 0 or idx == total_groups:
                try:
                    progress = (idx / total_groups) * 100
                    await status_msg.edit_text(
                        f"🔓 **Global Unban Progress**\n\n"
                        f"👤 User: {target_name}\n"
                        f"🆔 ID: `{target_id}`\n\n"
                        f"📊 Progress: {idx}/{total_groups} ({progress:.1f}%)\n\n"
                        f"✅ Unbanned: **{unbanned_from}**\n"
                        f"🚫 No Permission: **{no_permission}**\n"
                        f"❌ Other Errors: **{other_errors}**"
                    )
                except:
                    pass
            
            await asyncio.sleep(0.1)
            
        except Exception as e:
            other_errors += 1
            continue
    
    final_message = (
        f"✅ **Global Unban Completed!**\n\n"
        f"👤 **User:** {target_name}\n"
        f"🆔 **ID:** `{target_id}`\n\n"
        f"📊 **Final Statistics:**\n"
        f"🗂 Total Groups: **{total_groups}**\n"
        f"✅ Successfully Unbanned: **{unbanned_from}**\n"
        f"🚫 No Ban Permission: **{no_permission}**\n"
        f"❌ Other Errors: **{other_errors}**\n\n"
        f"🔓 **Status:** User can now use the bot!"
    )
    
    await status_msg.edit_text(final_message)

@app.on_message(filters.command("gbanlist"))
async def gban_list(client, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("❌ You are not authorized to use this command.")
        return
    
    gbanned_users = await global_ban_users_collection.find().to_list(length=None)
    
    if not gbanned_users:
        await message.reply_text("📋 No users are currently globally banned.")
        return
    
    text = f"📋 **Globally Banned Users ({len(gbanned_users)}):**\n\n"
    
    for idx, user in enumerate(gbanned_users, 1):
        text += f"**{idx}.** {user['name']}\n"
        text += f"   🆔 `{user['user_id']}`\n"
        text += f"   👤 @{user['username']}\n"
        text += f"   📝 {user['reason']}\n\n"
        
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
                    await message.reply_text(
                        f"🚫 **Globally Banned User Detected!**\n\n"
                        f"👤 {message.from_user.first_name}\n"
                        f"🆔 `{user_id}`\n"
                        f"📝 Reason: {is_gbanned['reason']}\n\n"
                        f"✅ User has been automatically banned!"
                    )
            except:
                pass