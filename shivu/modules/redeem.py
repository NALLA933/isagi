import random
import string
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes

from shivu import collection, user_collection, application
from shivu.modules.database.sudo import is_user_sudo

# --- CONFIGURATION ---
LOG_GROUP_ID = -1003110990230
OWNER_ID = 8420981179
# ---------------------

# Temporary Memory storage for codes (Restart hone par reset ho jayega)
generated_codes = {}
generated_waifu_codes = {}

# --- HELPER FUNCTIONS ---

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

async def send_log(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Logs activity to the configured log channel."""
    try:
        await context.bot.send_message(chat_id=LOG_GROUP_ID, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Logging Error: {e}")

async def check_auth(update: Update):
    """Checks if the user is Owner or Sudo."""
    user_id = update.message.from_user.id
    if user_id != OWNER_ID and not await is_user_sudo(user_id):
        return False
    return True

# --- CURRENCY SYSTEM (GEN & REDEEM) ---

async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not await check_auth(update):
        await msg.reply_text("⛔ <b>Access Denied:</b> Only authorized users can generate codes.", parse_mode=ParseMode.HTML)
        return

    try:
        if len(context.args) < 2:
            await msg.reply_text("Usage: <code>/gen [Amount] [Quantity]</code>", parse_mode=ParseMode.HTML)
            return

        amount = float(context.args[0])
        quantity = int(context.args[1])
    except ValueError:
        await msg.reply_text("❌ Invalid format. Amount and Quantity must be numbers.", parse_mode=ParseMode.HTML)
        return

    code_str = f"@siyaprobot_{generate_random_string()}"
    generated_codes[code_str] = {
        'amount': amount, 
        'quantity': quantity, 
        'claimed_by': []
    }

    formatted_amount = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"

    await msg.reply_text(
        f"✅ <b>Code Generated!</b>\n\n"
        f"🎫 <b>Code:</b> <code>{code_str}</code>\n"
        f"💰 <b>Amount:</b> {formatted_amount}\n"
        f"🔢 <b>Quantity:</b> {quantity}",
        parse_mode=ParseMode.HTML
    )

    # --- LOG ---
    executor_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#CURRENCY_GEN</b>\n\n"
        f"<b>Admin:</b> {executor_name} (<code>{user_id}</code>)\n"
        f"<b>Amount:</b> {formatted_amount}\n"
        f"<b>Qty:</b> {quantity}\n"
        f"<b>Code:</b> <code>{code_str}</code>"
    )
    await send_log(context, log_text)


async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not context.args:
        await msg.reply_text("Usage: <code>/redeem @siyaprobot_Code</code>", parse_mode=ParseMode.HTML)
        return

    code = context.args[0]

    if code not in generated_codes:
        await msg.reply_text("❌ Invalid or expired code.", parse_mode=ParseMode.HTML)
        return

    code_info = generated_codes[code]

    if user_id in code_info['claimed_by']:
        await msg.reply_text("⚠️ You have already claimed this code.", parse_mode=ParseMode.HTML)
        return

    if len(code_info['claimed_by']) >= code_info['quantity']:
        await msg.reply_text("❌ This code has been fully claimed.", parse_mode=ParseMode.HTML)
        return

    # Update Database
    await user_collection.update_one(
        {'id': user_id},
        {'$inc': {'balance': float(code_info['amount'])}}
    )

    code_info['claimed_by'].append(user_id)
    formatted_amount = f"{code_info['amount']:,.0f}" if code_info['amount'].is_integer() else f"{code_info['amount']:,.2f}"

    await msg.reply_text(
        f"🎉 <b>Redeemed Successfully!</b>\n\n"
        f"💰 <b>Added:</b> {formatted_amount} tokens to your wallet.\n"
        f"🔗 <b>Powered by:</b> <a href='https://t.me/siyaprobot'>Siya</a>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

    # --- LOG ---
    user_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#REDEEM_LOG</b>\n\n"
        f"<b>User:</b> {user_name} (<code>{user_id}</code>)\n"
        f"<b>Code:</b> <code>{code}</code>\n"
        f"<b>Amount:</b> {formatted_amount}"
    )
    await send_log(context, log_text)


# --- WAIFU SYSTEM (SGEN & SREDEEM) ---

async def waifu_gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not await check_auth(update):
        await msg.reply_text("⛔ <b>Access Denied:</b> Only authorized users can generate waifus.", parse_mode=ParseMode.HTML)
        return

    try:
        if len(context.args) < 2:
            await msg.reply_text("Usage: <code>/sgen [Character_ID] [Quantity]</code>", parse_mode=ParseMode.HTML)
            return
        
        char_id = context.args[0]
        quantity = int(context.args[1])
    except ValueError:
        await msg.reply_text("❌ Quantity must be a number.", parse_mode=ParseMode.HTML)
        return

    waifu = await collection.find_one({'id': char_id})
    if not waifu:
        await msg.reply_text("❌ Character ID not found in database.", parse_mode=ParseMode.HTML)
        return

    code_str = f"@siyaprobot_{generate_random_string()}"
    generated_waifu_codes[code_str] = {
        'waifu': waifu,
        'quantity': quantity,
        'claimed_by': []
    }

    await msg.reply_text(
        f"✅ <b>Waifu Code Generated!</b>\n\n"
        f"🎫 <b>Code:</b> <code>{code_str}</code>\n"
        f"👤 <b>Name:</b> {html.escape(waifu['name'])}\n"
        f"🔢 <b>Quantity:</b> {quantity}",
        parse_mode=ParseMode.HTML
    )

    # --- LOG ---
    executor_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#WAIFU_GEN</b>\n\n"
        f"<b>Admin:</b> {executor_name} (<code>{user_id}</code>)\n"
        f"<b>Character:</b> {html.escape(waifu['name'])} (<code>{char_id}</code>)\n"
        f"<b>Qty:</b> {quantity}\n"
        f"<b>Code:</b> <code>{code_str}</code>"
    )
    await send_log(context, log_text)


async def waifu_redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not context.args:
        await msg.reply_text("Usage: <code>/sredeem @siyaprobot_Code</code>", parse_mode=ParseMode.HTML)
        return

    code = context.args[0]

    if code not in generated_waifu_codes:
        await msg.reply_text("❌ Invalid or expired code.", parse_mode=ParseMode.HTML)
        return

    details = generated_waifu_codes[code]

    if user_id in details['claimed_by']:
        await msg.reply_text("⚠️ You have already claimed this character.", parse_mode=ParseMode.HTML)
        return

    if details['quantity'] <= 0:
        await msg.reply_text("❌ Out of stock.", parse_mode=ParseMode.HTML)
        # Optional: cleanup empty code
        del generated_waifu_codes[code]
        return

    waifu = details['waifu']

    # Update Database
    await user_collection.update_one(
        {'id': user_id},
        {'$push': {'characters': waifu}}
    )

    details['quantity'] -= 1
    details['claimed_by'].append(user_id)

    # Cleanup if empty
    if details['quantity'] == 0:
        del generated_waifu_codes[code]

    caption = (
        f"🎉 <b>Character Claimed!</b>\n\n"
        f"👤 <b>Name:</b> {html.escape(waifu['name'])}\n"
        f"🏵️ <b>Rarity:</b> {waifu['rarity']}\n"
        f"📺 <b>Anime:</b> {html.escape(waifu['anime'])}\n\n"
        f"🔗 <b>Powered by:</b> <a href='https://t.me/siyaprobot'>Siya</a>"
    )

    await msg.reply_photo(
        photo=waifu['img_url'],
        caption=caption,
        parse_mode=ParseMode.HTML
    )

    # --- LOG ---
    user_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#WAIFU_REDEEM</b>\n\n"
        f"<b>User:</b> {user_name} (<code>{user_id}</code>)\n"
        f"<b>Character:</b> {html.escape(waifu['name'])}\n"
        f"<b>Code:</b> <code>{code}</code>"
    )
    await send_log(context, log_text)

# --- REGISTER HANDLERS ---
application.add_handler(CommandHandler("gen", gen_command, block=False))
application.add_handler(CommandHandler("redeem", redeem_command, block=False))
application.add_handler(CommandHandler("sgen", waifu_gen_command, block=False))
application.add_handler(CommandHandler("sredeem", waifu_redeem_command, block=False))
