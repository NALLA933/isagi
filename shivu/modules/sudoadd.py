import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, sudo_users_collection

# Static developers list
DEVELOPERS = [
    {"id": 5147822244, "name": "Lead ᴅᴇᴠᴇʟᴏᴘᴇʀ", "username": "username1"},
    {"id": 8420981179, "name": "ᴏᴡɴᴇʀ", "username": "username2"}
]

AUTHORIZED_USERS = [8420981179, 5147822244]
VIDEO_URL = "https://files.catbox.moe/u863uh.mp4"

# Maintenance bot info
MAINTENANCE_BOT = {
    "id": 8111617507,
    "name": "Siya",
    "username": "siyaprobot"
}

def smallcaps(text: str) -> str:
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    small = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return text.translate(str.maketrans(normal, small))

async def is_sudo(user_id: int) -> bool:
    return await sudo_users_collection.find_one({"id": user_id}) is not None

async def add_sudo(user_id: int, username: str, first_name: str, title: str):
    await sudo_users_collection.update_one(
        {"id": user_id},
        {"$set": {
            "id": user_id, 
            "username": username, 
            "first_name": first_name,
            "sudo_title": title,
            "role": "sudo user",
            "added_on": datetime.utcnow()
        }},
        upsert=True
    )

async def set_user_role(user_id: int, role: str):
    await sudo_users_collection.update_one(
        {"id": user_id},
        {"$set": {"role": role}},
        upsert=False
    )

async def remove_sudo(user_id: int):
    await sudo_users_collection.delete_one({"id": user_id})

async def fetch_sudo_users():
    return await sudo_users_collection.find().to_list(length=None)

async def fetch_users_by_role(role: str):
    return await sudo_users_collection.find({"role": role}).to_list(length=None)

def format_user_list(users, show_title=True):
    if not users:
        return smallcaps("no users found.")
    text = ""
    for i, u in enumerate(users, start=1):
        user_id = u.get('id')
        name = u.get('first_name', u.get('name', 'unknown'))
        title = u.get('sudo_title', u.get('name', 'no title'))

        # Create clickable mention link
        mention = f"<a href='tg://user?id={user_id}'>{smallcaps(name)}</a>"

        if show_title:
            text += f"{i}. {mention}  |  {smallcaps(title)}\n"
        else:
            text += f"{i}. {mention}\n"
    return text.strip()

async def addsudo_cmd(update: Update, context: CallbackContext):
    msg, user = update.effective_message, update.effective_user
    if user.id not in AUTHORIZED_USERS:
        return await msg.reply_text(smallcaps("you are not authorized to add sudo users."))
    if not msg.reply_to_message:
        return await msg.reply_text(smallcaps("reply to a user's message to add them as sudo."))

    target = msg.reply_to_message.from_user
    title = " ".join(context.args) if context.args else "sudo user"

    await add_sudo(
        target.id, 
        target.username or "unknown", 
        target.first_name or "unknown",
        title
    )

    await msg.reply_html(
        f"<b>{smallcaps('added')}</b>: <a href='tg://user?id={target.id}'>{smallcaps(target.first_name)}</a>\n"
        f"<b>{smallcaps('title')}</b>: {smallcaps(title)}\n"
        f"<b>{smallcaps('role')}</b>: {smallcaps('sudo user')}\n"
        f"<b>{smallcaps('status')}</b>: {smallcaps('successfully added to sudo users')}"
    )

async def setrole_cmd(update: Update, context: CallbackContext):
    msg, user = update.effective_message, update.effective_user
    if user.id not in AUTHORIZED_USERS:
        return await msg.reply_text(smallcaps("you are not authorized to set user roles."))
    
    if not msg.reply_to_message:
        return await msg.reply_text(smallcaps("reply to a sudo user's message to set their role."))
    
    if not context.args:
        return await msg.reply_text(smallcaps("usage: /setrole <role>\nvalid roles: uploader, sudo user"))
    
    target = msg.reply_to_message.from_user
    
    if not await is_sudo(target.id):
        return await msg.reply_text(smallcaps("this user is not in sudo list. add them first with /addsudo."))
    
    role = " ".join(context.args).lower()
    valid_roles = ["uploader", "sudo user"]
    
    if role not in valid_roles:
        return await msg.reply_text(smallcaps(f"invalid role. valid roles: {', '.join(valid_roles)}"))
    
    await set_user_role(target.id, role)
    
    await msg.reply_html(
        f"<b>{smallcaps('updated')}</b>: <a href='tg://user?id={target.id}'>{smallcaps(target.first_name)}</a>\n"
        f"<b>{smallcaps('new role')}</b>: {smallcaps(role)}\n"
        f"<b>{smallcaps('status')}</b>: {smallcaps('role updated successfully')}"
    )

async def removesudo_cmd(update: Update, context: CallbackContext):
    msg, user = update.effective_message, update.effective_user
    if user.id not in AUTHORIZED_USERS:
        return await msg.reply_text(smallcaps("you are not authorized to remove sudo users."))
    if not msg.reply_to_message:
        return await msg.reply_text(smallcaps("reply to a sudo user's message to remove them."))

    target = msg.reply_to_message.from_user
    if not await is_sudo(target.id):
        return await msg.reply_text(smallcaps("this user is not in sudo list."))

    await remove_sudo(target.id)
    await msg.reply_html(
        f"<b>{smallcaps('removed')}</b>: <a href='tg://user?id={target.id}'>{smallcaps(target.first_name)}</a>\n"
        f"<b>{smallcaps('status')}</b>: {smallcaps('successfully removed from sudo list')}"
    )

async def sudolist_cmd(update: Update, context: CallbackContext):
    msg, user = update.effective_message, update.effective_user
    if user.id not in AUTHORIZED_USERS and not await is_sudo(user.id):
        return await msg.reply_text(smallcaps("you are not authorized to view sudo list."))

    sudo_users = await fetch_sudo_users()
    caption = f"<b>{smallcaps('current sudo users')}:</b>\n<blockquote>{format_user_list(sudo_users)}</blockquote>"
    await msg.reply_html(caption)

async def credits_command(update: Update, context: CallbackContext):
    msg = update.effective_message
    
    # Fetch users by role
    uploaders = await fetch_users_by_role("uploader")
    sudo_users = await fetch_users_by_role("sudo user")

    # Format developers (static)
    dev_list = format_user_list(DEVELOPERS, show_title=True)

    # Format uploaders (from database)
    uploader_list = format_user_list(uploaders, show_title=True)

    # Format sudo users (from database)
    sudo_list = format_user_list(sudo_users, show_title=True)

    # Maintenance bot mention
    maintenance_mention = f"<a href='tg://user?id={MAINTENANCE_BOT['id']}'>{smallcaps(MAINTENANCE_BOT['name'])}</a>"
    maintenance_username = f"@{MAINTENANCE_BOT['username']}"

    caption = f"""
<b>⸻ {smallcaps('project credits')} ⸻</b>

<b>{smallcaps('developers')}</b>
<blockquote>
{dev_list}
</blockquote>

<b>{smallcaps('uploaders')}</b>
<blockquote>
{uploader_list}
</blockquote>

<b>{smallcaps('sudo users')}</b>
<blockquote>
{sudo_list}
</blockquote>

<b>{smallcaps('frameworks')}</b>
<blockquote>
{smallcaps('telegram api, mongodb, aiogram, pyrogram')}
</blockquote>

<b>{smallcaps('maintenance')}</b>
<blockquote>
{maintenance_mention} {maintenance_username}
</blockquote>

<b>⸻ {smallcaps('modular system')} ⸻</b>
"""
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("ᴠɪᴇᴡ ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ", callback_data="credits_devs"),
         InlineKeyboardButton("ᴠɪᴇᴡ ᴜᴘʟᴏᴀᴅᴇʀꜱ", callback_data="credits_uploaders")],
        [InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ", callback_data="credits_sudo")],
        [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="credits_refresh")],
        [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
    ])

    await msg.reply_video(
        video=VIDEO_URL, 
        caption=caption.strip(), 
        parse_mode="HTML", 
        reply_markup=buttons
    )

async def credits_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "credits_devs":
        dev_list = format_user_list(DEVELOPERS, show_title=True)
        caption = f"""
<b>{smallcaps('developers list')}</b>

<blockquote>
{dev_list}
</blockquote>

{smallcaps('these individuals built and maintain the project.')}
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="credits_back")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
        ])
        await query.edit_message_caption(
            caption=caption.strip(), 
            parse_mode="HTML", 
            reply_markup=buttons
        )

    elif query.data == "credits_uploaders":
        uploaders = await fetch_users_by_role("uploader")
        uploader_list = format_user_list(uploaders, show_title=True)
        caption = f"""
<b>{smallcaps('uploaders list')}</b>

<blockquote>
{uploader_list}
</blockquote>

{smallcaps('these individuals manage and upload content.')}
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="credits_back")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
        ])
        await query.edit_message_caption(
            caption=caption.strip(), 
            parse_mode="HTML", 
            reply_markup=buttons
        )

    elif query.data == "credits_sudo":
        sudo_users = await fetch_users_by_role("sudo user")
        sudo_list = format_user_list(sudo_users, show_title=True)
        caption = f"""
<b>{smallcaps('sudo users list')}</b>

<blockquote>
{sudo_list}
</blockquote>

{smallcaps('these individuals have sudo access to the bot.')}
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="credits_back")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
        ])
        await query.edit_message_caption(
            caption=caption.strip(), 
            parse_mode="HTML", 
            reply_markup=buttons
        )

    elif query.data == "credits_refresh":
        uploaders = await fetch_users_by_role("uploader")
        sudo_users = await fetch_users_by_role("sudo user")
        dev_list = format_user_list(DEVELOPERS, show_title=True)
        uploader_list = format_user_list(uploaders, show_title=True)
        sudo_list = format_user_list(sudo_users, show_title=True)
        
        maintenance_mention = f"<a href='tg://user?id={MAINTENANCE_BOT['id']}'>{smallcaps(MAINTENANCE_BOT['name'])}</a>"
        maintenance_username = f"@{MAINTENANCE_BOT['username']}"

        caption = f"""
<b>⸻ {smallcaps('project credits')} ⸻</b>

<b>{smallcaps('developers')}</b>
<blockquote>
{dev_list}
</blockquote>

<b>{smallcaps('uploaders')}</b>
<blockquote>
{uploader_list}
</blockquote>

<b>{smallcaps('sudo users')}</b>
<blockquote>
{sudo_list}
</blockquote>

<b>{smallcaps('frameworks')}</b>
<blockquote>
{smallcaps('telegram api, mongodb, aiogram, pyrogram')}
</blockquote>

<b>{smallcaps('maintenance')}</b>
<blockquote>
{maintenance_mention} {maintenance_username}
</blockquote>

<b>⸻ {smallcaps('modular system')} ⸻</b>
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ᴠɪᴇᴡ ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ", callback_data="credits_devs"),
             InlineKeyboardButton("ᴠɪᴇᴡ ᴜᴘʟᴏᴀᴅᴇʀꜱ", callback_data="credits_uploaders")],
            [InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ", callback_data="credits_sudo")],
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="credits_refresh")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
        ])
        await query.edit_message_caption(
            caption=caption.strip(), 
            parse_mode="HTML", 
            reply_markup=buttons
        )

    elif query.data == "credits_back":
        uploaders = await fetch_users_by_role("uploader")
        sudo_users = await fetch_users_by_role("sudo user")
        dev_list = format_user_list(DEVELOPERS, show_title=True)
        uploader_list = format_user_list(uploaders, show_title=True)
        sudo_list = format_user_list(sudo_users, show_title=True)
        
        maintenance_mention = f"<a href='tg://user?id={MAINTENANCE_BOT['id']}'>{smallcaps(MAINTENANCE_BOT['name'])}</a>"
        maintenance_username = f"@{MAINTENANCE_BOT['username']}"

        caption = f"""
<b>⸻ {smallcaps('project credits')} ⸻</b>

<b>{smallcaps('developers')}</b>
<blockquote>
{dev_list}
</blockquote>

<b>{smallcaps('uploaders')}</b>
<blockquote>
{uploader_list}
</blockquote>

<b>{smallcaps('sudo users')}</b>
<blockquote>
{sudo_list}
</blockquote>

<b>{smallcaps('frameworks')}</b>
<blockquote>
{smallcaps('telegram api, mongodb, aiogram, pyrogram')}
</blockquote>

<b>{smallcaps('maintenance')}</b>
<blockquote>
{maintenance_mention} {maintenance_username}
</blockquote>

<b>⸻ {smallcaps('modular system')} ⸻</b>
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ᴠɪᴇᴡ ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ", callback_data="credits_devs"),
             InlineKeyboardButton("ᴠɪᴇᴡ ᴜᴘʟᴏᴀᴅᴇʀꜱ", callback_data="credits_uploaders")],
            [InlineKeyboardButton("ᴠɪᴇᴡ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ", callback_data="credits_sudo")],
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ", callback_data="credits_refresh")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
        ])
        await query.edit_message_caption(
            caption=caption.strip(), 
            parse_mode="HTML", 
            reply_markup=buttons
        )

    elif query.data == "credits_close":
        await query.message.delete()

# Register handlers
application.add_handler(CommandHandler("addsudo", addsudo_cmd))
application.add_handler(CommandHandler("setrole", setrole_cmd))
application.add_handler(CommandHandler("sudoremove", removesudo_cmd))
application.add_handler(CommandHandler("sudolist", sudolist_cmd))
application.add_handler(CommandHandler("credits", credits_command))
application.add_handler(CallbackQueryHandler(credits_callback, pattern=r"^credits_"))