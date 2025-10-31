import asyncio
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, sudo_users_collection

# ───────────────────────────────
# CONFIG
# ───────────────────────────────
DEV_LIST = [8420981179, 5147822244]  # Permanent developers
AUTHORIZED_USERS = DEV_LIST

# ───────────────────────────────
# SMALL CAPS UTILITY
# ───────────────────────────────
def smallcaps(text: str) -> str:
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    small = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return text.translate(str.maketrans(normal, small))

# ───────────────────────────────
# DATABASE HELPERS
# ───────────────────────────────
async def is_sudo(user_id: int) -> bool:
    return await sudo_users_collection.find_one({"id": user_id}) is not None

async def add_sudo(user_id: int, username: str, title: str):
    await sudo_users_collection.update_one(
        {"id": user_id},
        {"$set": {
            "id": user_id,
            "username": username,
            "sudo_title": title,
            "added_on": datetime.utcnow()
        }},
        upsert=True
    )

async def remove_sudo(user_id: int):
    await sudo_users_collection.delete_one({"id": user_id})

async def fetch_sudo_users():
    return await sudo_users_collection.find().to_list(length=None)

def format_sudo_list(users):
    if not users:
        return smallcaps("no sudo users found.")
    text = ""
    for i, u in enumerate(users, start=1):
        uname = f"@{u.get('username', 'unknown')}"
        title = smallcaps(u.get('sudo_title', 'no title'))
        text += f"{i}. {uname}  |  {title}\n"
    return text.strip()

# ───────────────────────────────
# SUDO COMMANDS
# ───────────────────────────────
async def addsudo_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    msg = update.effective_message

    if user.id not in AUTHORIZED_USERS:
        return await msg.reply_text(smallcaps("you are not authorized to add sudo users."))

    if not msg.reply_to_message:
        return await msg.reply_text(smallcaps("reply to a user’s message to add them as sudo."))

    target = msg.reply_to_message.from_user
    title = " ".join(context.args) if context.args else "Sudo User"
    await add_sudo(target.id, target.username or "unknown", title)

    await msg.reply_html(
        f"<b>{smallcaps('added')}</b>: <a href='tg://user?id={target.id}'>{smallcaps(target.first_name)}</a>\n"
        f"<b>{smallcaps('title')}</b>: {smallcaps(title)}\n"
        f"<b>{smallcaps('status')}</b>: {smallcaps('successfully added to sudo users')}"
    )

async def removesudo_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    msg = update.effective_message

    if user.id not in AUTHORIZED_USERS:
        return await msg.reply_text(smallcaps("you are not authorized to remove sudo users."))

    if not msg.reply_to_message:
        return await msg.reply_text(smallcaps("reply to a sudo user’s message to remove them."))

    target = msg.reply_to_message.from_user
    if not await is_sudo(target.id):
        return await msg.reply_text(smallcaps("this user is not in sudo list."))

    await remove_sudo(target.id)
    await msg.reply_html(
        f"<b>{smallcaps('removed')}</b>: <a href='tg://user?id={target.id}'>{smallcaps(target.first_name)}</a>\n"
        f"<b>{smallcaps('status')}</b>: {smallcaps('successfully removed from sudo list')}"
    )

async def sudolist_cmd(update: Update, context: CallbackContext):
    msg = update.effective_message
    user = update.effective_user

    if user.id not in AUTHORIZED_USERS and not await is_sudo(user.id):
        return await msg.reply_text(smallcaps("you are not authorized to view sudo list."))

    sudo_users = await fetch_sudo_users()
    caption = f"<b>{smallcaps('current sudo users')}:</b>\n<blockquote>{format_sudo_list(sudo_users)}</blockquote>"
    await msg.reply_html(caption)

# ───────────────────────────────
# /CREDITS COMMAND
# ───────────────────────────────
async def credits_command(update: Update, context: CallbackContext):
    msg = update.effective_message
    sudo_users = await fetch_sudo_users()
    video_url = "https://files.catbox.moe/f3slnj.mp4"

    caption = f"""
<b>⸻ {smallcaps('official bot credits')} ⸻</b>

<b>{smallcaps('developers')} :</b>  
<blockquote>
{smallcaps('lead developer')} — <a href="tg://user?id=8420981179">{smallcaps('Touhid')}</a>  
{smallcaps('co-developer')} — <a href="tg://user?id=5147822244">{smallcaps('Siya')}</a>
</blockquote>

<b>{smallcaps('current sudo users')} :</b>
<blockquote>
{format_sudo_list(sudo_users)}
</blockquote>

<b>{smallcaps('special thanks')}</b>  
<blockquote>
{smallcaps('telegram api, mongodb, aiogram, pyrogram')}
</blockquote>

<b>⸻ {smallcaps('made with care by')} <a href="https://t.me/siyaprobot">{smallcaps('Siya')}</a> ⸻</b>
"""

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("View Developers", callback_data="credits_devs"),
            InlineKeyboardButton("Refresh Sudo List", callback_data="credits_refresh"),
        ],
        [
            InlineKeyboardButton("Close", callback_data="credits_close"),
        ]
    ])

    await msg.reply_video(
        video=video_url,
        caption=caption.strip(),
        parse_mode="HTML",
        reply_markup=buttons,
    )

# ───────────────────────────────
# CREDITS CALLBACK HANDLER
# ───────────────────────────────
async def credits_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "credits_devs":
        caption = f"""
<b>{smallcaps('developers list')}</b>

<blockquote>
{smallcaps('lead developer')} — <a href="tg://user?id=8420981179">{smallcaps('isagi')}</a>  
{smallcaps('co-developer')} — <a href="tg://user?id=5147822244">{smallcaps('Siya')}</a>
</blockquote>

{smallcaps('these individuals built and maintain the project.')}
"""
        await query.edit_message_caption(
            caption=caption.strip(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back", callback_data="credits_back")],
                [InlineKeyboardButton("Close", callback_data="credits_close")]
            ]),
        )

    elif query.data == "credits_refresh":
        sudo_users = await fetch_sudo_users()
        caption = f"""
<b>{smallcaps('updated sudo users list')}</b>
<blockquote>
{format_sudo_list(sudo_users)}
</blockquote>

<b>{smallcaps('list updated in real-time')}</b>
"""
        await query.edit_message_caption(
            caption=caption.strip(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Refresh Again", callback_data="credits_refresh")],
                [InlineKeyboardButton("Back", callback_data="credits_back")],
                [InlineKeyboardButton("Close", callback_data="credits_close")]
            ]),
        )

    elif query.data == "credits_back":
        await query.message.delete()
        await credits_command(update, context)

    elif query.data == "credits_close":
        await query.message.delete()

# ───────────────────────────────
# REGISTER COMMANDS
# ───────────────────────────────
application.add_handler(CommandHandler("addsudo", addsudo_cmd))
application.add_handler(CommandHandler("sudoremove", removesudo_cmd))
application.add_handler(CommandHandler("sudolist", sudolist_cmd))
application.add_handler(CommandHandler("credits", credits_command))
application.add_handler(CallbackQueryHandler(credits_callback, pattern=r"^credits_"))