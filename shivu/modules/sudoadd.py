import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, sudo_users_collection

# Static lists for Developers and Uploaders
DEVELOPERS = [
    {"id": 8420981179, "name": "Lead Developer", "username": "username1"},
    {"id": 5147822244, "name": "Co-Developer", "username": "username2"}
]

UPLOADERS = [
    {"id": 8297659126, "name": "Head Uploader", "username": "uploader1"},
    {"id": 6863917190, "name": "Content Manager", "username": "uploader2"}
]

AUTHORIZED_USERS = [8420981179, 5147822244]
VIDEO_URL = "https://files.catbox.moe/u863uh.mp4"

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
            "added_on": datetime.utcnow()
        }},
        upsert=True
    )

async def remove_sudo(user_id: int):
    await sudo_users_collection.delete_one({"id": user_id})

async def fetch_sudo_users():
    return await sudo_users_collection.find().to_list(length=None)

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
        f"<b>{smallcaps('status')}</b>: {smallcaps('successfully added to sudo users')}"
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
    sudo_users = await fetch_sudo_users()
    
    # Format developers
    dev_list = format_user_list(DEVELOPERS, show_title=True)
    
    # Format uploaders
    uploader_list = format_user_list(UPLOADERS, show_title=True)
    
    # Format sudo users
    sudo_list = format_user_list(sudo_users, show_title=True)
    
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

<b>⸻ {smallcaps('modular system')} ⸻</b>
"""
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("ᴠɪᴇᴡ ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ", callback_data="credits_devs"),
         InlineKeyboardButton("ᴠɪᴇᴡ ᴜᴘʟᴏᴀᴅᴇʀꜱ", callback_data="credits_uploaders")],
        [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ ꜱᴜᴅᴏ ʟɪꜱᴛ", callback_data="credits_refresh")],
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
        uploader_list = format_user_list(UPLOADERS, show_title=True)
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

    elif query.data == "credits_refresh":
        sudo_users = await fetch_sudo_users()
        sudo_list = format_user_list(sudo_users, show_title=True)
        
        caption = f"""
<b>{smallcaps('updated sudo users list')}</b>
<blockquote>
{sudo_list}
</blockquote>
<b>{smallcaps('list updated in real-time')}</b>
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ ᴀɢᴀɪɴ", callback_data="credits_refresh")],
            [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data="credits_back")],
            [InlineKeyboardButton("ᴄʟᴏꜱᴇ", callback_data="credits_close")]
        ])
        await query.edit_message_caption(
            caption=caption.strip(), 
            parse_mode="HTML", 
            reply_markup=buttons
        )

    elif query.data == "credits_back":
        sudo_users = await fetch_sudo_users()
        dev_list = format_user_list(DEVELOPERS, show_title=True)
        uploader_list = format_user_list(UPLOADERS, show_title=True)
        sudo_list = format_user_list(sudo_users, show_title=True)
        
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

<b>⸻ {smallcaps('modular system')} ⸻</b>
"""
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("ᴠɪᴇᴡ ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ", callback_data="credits_devs"),
             InlineKeyboardButton("ᴠɪᴇᴡ ᴜᴘʟᴏᴀᴅᴇʀꜱ", callback_data="credits_uploaders")],
            [InlineKeyboardButton("ʀᴇғʀᴇꜱʜ ꜱᴜᴅᴏ ʟɪꜱᴛ", callback_data="credits_refresh")],
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
application.add_handler(CommandHandler("sudoremove", removesudo_cmd))
application.add_handler(CommandHandler("sudolist", sudolist_cmd))
application.add_handler(CommandHandler("credits", credits_command))
application.add_handler(CallbackQueryHandler(credits_callback, pattern=r"^credits_"))