from pyrogram import filters, enums
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, FloodWait
from shivu import shivuu as app, global_ban_users_collection, BANNED_USERS, user_collection, user_totals_collection, group_user_totals_collection
import asyncio

OWNER_IDS = [8420981179, 5147822244]

@app.on_message(filters.command("gban"))
async def global_ban(_, message):
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
                target_user = await app.get_users(target_id)
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
    
    status_msg = await message.reply_text(f"🔨 Starting global ban for {target_name} ({target_id})...")
    
    await global_ban_users_collection.insert_one({
        "user_id": target_id,
        "username": target_username,
        "name": target_name,
        "reason": reason,
        "banned_by": user_id,
        "banned_at": message.date
    })
    
    await BANNED_USERS.insert_one({
        "user_id": target_id,
        "username": target_username,
        "reason": reason
    })
    
    await user_collection.delete_many({"user_id": target_id})
    await user_totals_collection.delete_many({"id": target_id})
    await group_user_totals_collection.delete_many({"user_id": target_id})
    
    banned_from = 0
    failed_bans = 0
    total_groups = 0
    
    async for chat in app.get_dialogs():
        if chat.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            total_groups += 1
            try:
                try:
                    await chat.chat.get_member(target_id)
                    user_in_chat = True
                except UserNotParticipant:
                    user_in_chat = False
                
                if user_in_chat:
                    try:
                        await app.ban_chat_member(chat.chat.id, target_id)
                        banned_from += 1
                        
                        if banned_from % 5 == 0:
                            await status_msg.edit_text(
                                f"🔨 Global Ban Progress:\n"
                                f"👤 User: {target_name}\n"
                                f"🆔 ID: {target_id}\n"
                                f"✅ Banned from: {banned_from} groups\n"
                                f"❌ Failed: {failed_bans}\n"
                                f"📊 Checked: {total_groups} groups"
                            )
                        
                        await asyncio.sleep(0.5)
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                        try:
                            await app.ban_chat_member(chat.chat.id, target_id)
                            banned_from += 1
                        except:
                            failed_bans += 1
                    except ChatAdminRequired:
                        failed_bans += 1
                    except Exception as e:
                        failed_bans += 1
                        
            except Exception as e:
                continue
    
    final_message = (
        f"✅ **Global Ban Completed**\n\n"
        f"👤 **User:** {target_name}\n"
        f"🆔 **ID:** `{target_id}`\n"
        f"👤 **Username:** @{target_username}\n"
        f"📝 **Reason:** {reason}\n\n"
        f"📊 **Statistics:**\n"
        f"✅ Banned from: {banned_from} groups\n"
        f"❌ Failed bans: {failed_bans}\n"
        f"🗂 Total groups checked: {total_groups}\n"
        f"🗑 Removed all user data from database\n\n"
        f"🔒 User is now globally banned from using the bot."
    )
    
    await status_msg.edit_text(final_message)

@app.on_message(filters.command("ungban"))
async def global_unban(_, message):
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
                target_user = await app.get_users(target_id)
                target_name = target_user.first_name
            except:
                target_name = "Unknown User"
        except ValueError:
            await message.reply_text("❌ Invalid user ID. Please reply to a user or provide a valid user ID.")
            return
    else:
        await message.reply_text("❌ Usage: `/ungban <user_id>` or reply to a user with `/ungban`")
        return
    
    existing_ban = await global_ban_users_collection.find_one({"user_id": target_id})
    if not existing_ban:
        await message.reply_text(f"⚠️ User {target_name} ({target_id}) is not globally banned!")
        return
    
    status_msg = await message.reply_text(f"🔓 Removing global ban for {target_name} ({target_id})...")
    
    await global_ban_users_collection.delete_one({"user_id": target_id})
    await BANNED_USERS.delete_one({"user_id": target_id})
    
    unbanned_from = 0
    failed_unbans = 0
    total_groups = 0
    
    async for chat in app.get_dialogs():
        if chat.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            total_groups += 1
            try:
                await app.unban_chat_member(chat.chat.id, target_id)
                unbanned_from += 1
                
                if unbanned_from % 5 == 0:
                    await status_msg.edit_text(
                        f"🔓 Global Unban Progress:\n"
                        f"👤 User: {target_name}\n"
                        f"🆔 ID: {target_id}\n"
                        f"✅ Unbanned from: {unbanned_from} groups\n"
                        f"❌ Failed: {failed_unbans}\n"
                        f"📊 Checked: {total_groups} groups"
                    )
                
                await asyncio.sleep(0.5)
            except FloodWait as e:
                await asyncio.sleep(e.value)
                try:
                    await app.unban_chat_member(chat.chat.id, target_id)
                    unbanned_from += 1
                except:
                    failed_unbans += 1
            except ChatAdminRequired:
                failed_unbans += 1
            except Exception as e:
                failed_unbans += 1
    
    final_message = (
        f"✅ **Global Unban Completed**\n\n"
        f"👤 **User:** {target_name}\n"
        f"🆔 **ID:** `{target_id}`\n\n"
        f"📊 **Statistics:**\n"
        f"✅ Unbanned from: {unbanned_from} groups\n"
        f"❌ Failed unbans: {failed_unbans}\n"
        f"🗂 Total groups checked: {total_groups}\n\n"
        f"🔓 User can now use the bot again."
    )
    
    await status_msg.edit_text(final_message)

@app.on_message(filters.command("gbanlist"))
async def gban_list(_, message):
    user_id = message.from_user.id
    
    if user_id not in OWNER_IDS:
        await message.reply_text("❌ You are not authorized to use this command.")
        return
    
    gbanned_users = await global_ban_users_collection.find().to_list(length=None)
    
    if not gbanned_users:
        await message.reply_text("📋 No users are currently globally banned.")
        return
    
    text = "📋 **Globally Banned Users:**\n\n"
    
    for idx, user in enumerate(gbanned_users, 1):
        text += f"{idx}. **{user['name']}**\n"
        text += f"   🆔 ID: `{user['user_id']}`\n"
        text += f"   👤 Username: @{user['username']}\n"
        text += f"   📝 Reason: {user['reason']}\n\n"
        
        if len(text) > 3500:
            await message.reply_text(text)
            text = ""
    
    if text:
        await message.reply_text(text)

@app.on_message(filters.group & filters.incoming)
async def check_gbanned_user(_, message):
    if message.from_user and message.from_user.id:
        user_id = message.from_user.id
        
        is_gbanned = await global_ban_users_collection.find_one({"user_id": user_id})
        
        if is_gbanned:
            try:
                await app.ban_chat_member(message.chat.id, user_id)
                await message.reply_text(
                    f"🚫 **User Globally Banned!**\n\n"
                    f"👤 User: {message.from_user.first_name}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"📝 Reason: {is_gbanned['reason']}\n\n"
                    f"This user has been automatically removed from this group."
                )
            except Exception as e:
                pass