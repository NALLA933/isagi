from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, sudo_users_collection
from shivu.modules.database.sudo import add_to_sudo_users, remove_from_sudo_users, fetch_sudo_users, get_user_username

# ─────────────────────────────
# CONFIGURATION
# ─────────────────────────────
CREDIT_VIDEO = "https://files.catbox.moe/f3slnj.mp4"
AUTHORIZED_ADMINS = [8420981179, 5147822244]  # can add/remove sudo

DEVELOPERS = [
    {"id": 8420981179, "username": "dev_main", "title": "Project Lead"},
]

UPLOADERS = [
    {"id": 5147822244, "username": "upload_master", "title": "Media Manager"},
]


# ─────────────────────────────
# SUDO SYSTEM (REAL-TIME DB)
# ─────────────────────────────
async def is_user_sudo(user_id: int) -> bool:
    return bool(await sudo_users_collection.find_one({"id": user_id}))


async def addsudo_command(update: Update, context: CallbackContext):
    sender = update.message.from_user
    if sender.id not in AUTHORIZED_ADMINS:
        await update.message.reply_text("You are not authorized to add sudo users.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to make them sudo.")
        return

    target = update.message.reply_to_message.from_user
    username = await get_user_username(target.id)
    title = ' '.join(context.args) or "Sudo User"

    await add_to_sudo_users(target.id, username, title)
    await update.message.reply_text(f"Added @{username} as sudo with title: {title}")


async def removesudo_command(update: Update, context: CallbackContext):
    sender = update.message.from_user
    if sender.id not in AUTHORIZED_ADMINS:
        await update.message.reply_text("You are not authorized to remove sudo users.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to remove them from sudo.")
        return

    target = update.message.reply_to_message.from_user
    user = await sudo_users_collection.find_one({"id": target.id})
    if not user:
        await update.message.reply_text("User not found in sudo users.")
        return

    await remove_from_sudo_users(target.id)
    await update.message.reply_text(f"Removed @{user.get('username')} from sudo users.")


# ─────────────────────────────
# UI GENERATOR
# ─────────────────────────────
def format_section(title, users):
    if not users:
        return f"<b>{title}</b>\n   No users listed.\n"
    section = f"<b>{title}</b>\n"
    for u in users:
        uname = f"@{escape(u['username'])}" if u.get("username") else f"<code>{u['id']}</code>"
        role = escape(u.get("title", u.get("sudo_title", '')))
        section += f"   {uname} — {role}\n"
    return section + "\n"


async def generate_credits_text():
    sudo_users = await fetch_sudo_users()
    return (
        f"<b>⎯⎯⎯⎯⎯  ᴘʀᴏᴊᴇᴄᴛ ᴄʀᴇᴅɪᴛꜱ  ⎯⎯⎯⎯⎯</b>\n\n"
        f"{format_section('ᴅᴇᴠᴇʟᴏᴘᴇʀꜱ', DEVELOPERS)}"
        f"{format_section('ᴜᴘʟᴏᴀᴅᴇʀꜱ', UPLOADERS)}"
        f"{format_section('ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ', sudo_users)}"
        f"<b>⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯</b>\n"
        f"<i>Dynamic credits interface powered by your system.</i>"
    )


# ─────────────────────────────
# MAIN /CREDITS COMMAND
# ─────────────────────────────
async def credits_command(update: Update, context: CallbackContext):
    text = await generate_credits_text()

    keyboard = [
        [
            InlineKeyboardButton("⟲ Refresh", callback_data="refresh_credits"),
            InlineKeyboardButton("✕ Close", callback_data="close_credits"),
        ]
    ]

    await update.message.reply_html(
        f'<a href="{CREDIT_VIDEO}">&#8203;</a>{text}',
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=False
    )


# ─────────────────────────────
# CALLBACK HANDLER
# ─────────────────────────────
async def credits_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "close_credits":
        await query.delete_message()
        return

    elif query.data == "refresh_credits":
        text = await generate_credits_text()
        await query.edit_message_text(
            f'<a href="{CREDIT_VIDEO}">&#8203;</a>{text}',
            parse_mode="HTML",
            reply_markup=query.message.reply_markup,
            disable_web_page_preview=False
        )


# ─────────────────────────────
# COMMAND REGISTRATION
# ─────────────────────────────
application.add_handler(CommandHandler("credits", credits_command))
application.add_handler(CommandHandler("addsudo", addsudo_command))
application.add_handler(CommandHandler("removesudo", removesudo_command))
application.add_handler(CallbackQueryHandler(credits_callback, pattern="^(refresh_credits|close_credits)$"))