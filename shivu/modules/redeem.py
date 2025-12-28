import random
import string
import html
import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes
import aiohttp
from telegram.error import BadRequest

# Database imports
from shivu import collection, user_collection, application
# Hum nayi collection banayenge codes save karne ke liye
from shivu import db 
codes_collection = db['redeem_codes'] 

from shivu.modules.database.sudo import is_user_sudo

# --- CONFIGURATION ---
LOG_GROUP_ID = -1003110990230
OWNER_ID = 8297659126
# ---------------------

# --- HELPER FUNCTIONS ---

async def validate_image_url(url: str) -> bool:
    """Validate if URL points to a valid image."""
    if not url or not isinstance(url, str):
        return False
    
    # Check common image extensions
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    if any(url.lower().endswith(ext) for ext in valid_extensions):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=5) as response:
                    content_type = response.headers.get('Content-Type', '')
                    return content_type.startswith('image/')
        except:
            return False
    return False

def generate_unique_code():
    """Generates a professional looking code like SIYA-ABCD-1234"""
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"SIYA-{part1}-{part2}"

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

# --- CURRENCY GENERATION ---

async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not await check_auth(update):
        await msg.reply_text("⛔ <b>Access Denied</b>", parse_mode=ParseMode.HTML)
        return

    try:
        if len(context.args) < 2:
            await msg.reply_text("Usage: <code>/gen [Amount] [Quantity]</code>", parse_mode=ParseMode.HTML)
            return

        amount = float(context.args[0])
        quantity = int(context.args[1])
    except ValueError:
        await msg.reply_text("❌ Invalid format. Use numbers.", parse_mode=ParseMode.HTML)
        return

    code_str = generate_unique_code()
    
    # Save to MongoDB
    code_data = {
        'code': code_str,
        'type': 'currency',
        'amount': amount,
        'quantity': quantity,
        'claimed_by': [],
        'created_at': datetime.datetime.utcnow()
    }
    await codes_collection.insert_one(code_data)

    formatted_amount = f"{amount:,.0f}" if amount.is_integer() else f"{amount:,.2f}"

    await msg.reply_text(
        f"✅ <b>Currency Code Created!</b>\n\n"
        f"🎫 <b>Code:</b> <code>{code_str}</code>\n"
        f"💰 <b>Value:</b> {formatted_amount}\n"
        f"👥 <b>Total Claims:</b> {quantity}\n\n"
        f"<i>Bot restart hone par bhi ye code work karega.</i>",
        parse_mode=ParseMode.HTML
    )

    # --- LOG ---
    executor_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#CURRENCY_GEN</b>\n"
        f"Admin: {executor_name} (<code>{user_id}</code>)\n"
        f"Amount: {formatted_amount} | Qty: {quantity}\n"
        f"Code: <code>{code_str}</code>"
    )
    await send_log(context, log_text)

# --- WAIFU GENERATION ---

async def waifu_gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not await check_auth(update):
        await msg.reply_text("⛔ <b>Access Denied</b>", parse_mode=ParseMode.HTML)
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
        await msg.reply_text("❌ Character ID not found.", parse_mode=ParseMode.HTML)
        return

    # Validate image URL before creating code
    if 'img_url' in waifu and not await validate_image_url(waifu['img_url']):
        await msg.reply_text("⚠️ Warning: Character image URL appears to be invalid. Code will still be created but may fail to display image when redeemed.", parse_mode=ParseMode.HTML)

    code_str = generate_unique_code()

    # Save to MongoDB
    code_data = {
        'code': code_str,
        'type': 'character',
        'waifu_data': waifu, # Storing full data ensures safety if char is deleted later
        'quantity': quantity,
        'claimed_by': [],
        'created_at': datetime.datetime.utcnow()
    }
    await codes_collection.insert_one(code_data)

    await msg.reply_text(
        f"✅ <b>Waifu Code Created!</b>\n\n"
        f"🎫 <b>Code:</b> <code>{code_str}</code>\n"
        f"👤 <b>Character:</b> {html.escape(waifu['name'])}\n"
        f"👥 <b>Total Claims:</b> {quantity}",
        parse_mode=ParseMode.HTML
    )

    # --- LOG ---
    executor_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#WAIFU_GEN</b>\n"
        f"Admin: {executor_name} (<code>{user_id}</code>)\n"
        f"Char: {html.escape(waifu['name'])} (<code>{char_id}</code>)\n"
        f"Code: <code>{code_str}</code>"
    )
    await send_log(context, log_text)

# --- UNIVERSAL REDEEM COMMAND ---

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user_id = msg.from_user.id

    if not context.args:
        await msg.reply_text("Usage: <code>/redeem SIYA-XXXX-XXXX</code>", parse_mode=ParseMode.HTML)
        return

    code = context.args[0]

    # Find in DB
    code_info = await codes_collection.find_one({'code': code})

    if not code_info:
        await msg.reply_text("❌ Invalid code.", parse_mode=ParseMode.HTML)
        return

    # Check Logic
    if user_id in code_info['claimed_by']:
        await msg.reply_text("⚠️ You have already claimed this code.", parse_mode=ParseMode.HTML)
        return

    if len(code_info['claimed_by']) >= code_info['quantity']:
        await msg.reply_text("❌ This code has been fully claimed.", parse_mode=ParseMode.HTML)
        return

    # --- HANDLE REWARD TYPE ---
    
    if code_info['type'] == 'currency':
        amount = code_info['amount']
        await user_collection.update_one({'id': user_id}, {'$inc': {'balance': float(amount)}})
        
        formatted_amount = f"{amount:,.0f}" if isinstance(amount, int) or amount.is_integer() else f"{amount:,.2f}"
        
        await msg.reply_text(
            f"🎉 <b>Redeemed Successfully!</b>\n\n"
            f"💰 <b>Received:</b> {formatted_amount} tokens.\n"
            f"🔗 <b>Powered by:</b> <a href='https://t.me/siyaprobot'>Siya</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        log_detail = f"Amount: {formatted_amount}"

    elif code_info['type'] == 'character':
        waifu = code_info['waifu_data']
        await user_collection.update_one({'id': user_id}, {'$push': {'characters': waifu}})
        
        # Check if image URL exists and seems valid
        img_url = waifu.get('img_url')
        image_sent = False
        
        if img_url and await validate_image_url(img_url):
            try:
                # LINE 205 (modified with try-except)
                await msg.reply_photo(
                    photo=img_url,
                    caption=(
                        f"🎉 <b>New Character Unlocked!</b>\n\n"
                        f"👤 <b>Name:</b> {html.escape(waifu['name'])}\n"
                        f"🏵️ <b>Rarity:</b> {waifu['rarity']}\n"
                        f"📺 <b>Anime:</b> {html.escape(waifu['anime'])}"
                    ),
                    parse_mode=ParseMode.HTML
                )
                image_sent = True
            except BadRequest as e:
                print(f"Failed to send image for character {waifu['name']}: {e}")
                image_sent = False
        
        # If image wasn't sent (either invalid URL or BadRequest exception)
        if not image_sent:
            await msg.reply_text(
                text=(
                    f"🎉 <b>New Character Unlocked!</b>\n\n"
                    f"👤 <b>Name:</b> {html.escape(waifu['name'])}\n"
                    f"🏵️ <b>Rarity:</b> {waifu['rarity']}\n"
                    f"📺 <b>Anime:</b> {html.escape(waifu['anime'])}\n\n"
                    f"⚠️ <i>Note: Character image unavailable</i>"
                ),
                parse_mode=ParseMode.HTML
            )
        
        log_detail = f"Character: {html.escape(waifu['name'])}"

    # Update DB: Add user to claimed list
    await codes_collection.update_one({'code': code}, {'$push': {'claimed_by': user_id}})

    # --- LOG ---
    user_name = html.escape(msg.from_user.first_name)
    log_text = (
        f"📢 <b>#REDEEM_LOG</b>\n"
        f"User: {user_name} (<code>{user_id}</code>)\n"
        f"Code: <code>{code}</code>\n"
        f"Reward: {log_detail}"
    )
    await send_log(context, log_text)

# --- ADMIN REVOKE COMMAND ---

async def revoke_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not await check_auth(update):
        return

    if not context.args:
        await msg.reply_text("Usage: <code>/revoke [Code]</code>", parse_mode=ParseMode.HTML)
        return

    code = context.args[0]
    result = await codes_collection.delete_one({'code': code})

    if result.deleted_count > 0:
        await msg.reply_text(f"🗑️ Code <code>{code}</code> has been deleted from database.", parse_mode=ParseMode.HTML)
        await send_log(context, f"🗑️ <b>#CODE_REVOKED</b>\nCode: <code>{code}</code>\nBy: {msg.from_user.first_name}")
    else:
        await msg.reply_text("❌ Code not found.", parse_mode=ParseMode.HTML)

# --- REGISTER HANDLERS ---
application.add_handler(CommandHandler("gen", gen_command, block=False))
application.add_handler(CommandHandler("sgen", waifu_gen_command, block=False))
application.add_handler(CommandHandler("redeem", redeem_command, block=False)) # Sredeem ki zarurat nahi, redeem dono handle karega
application.add_handler(CommandHandler("sredeem", redeem_command, block=False)) # Alias for old users
application.add_handler(CommandHandler("revoke", revoke_code_command, block=False))