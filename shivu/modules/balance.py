import math
import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

# ──────────────────────────────
# ɢʟᴏʙᴀʟ ᴄᴏᴏʟᴅᴏᴡɴꜱ & ᴘᴇɴᴅɪɴɢ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ
# ──────────────────────────────
pay_cooldown = {}
pending_payments = {}

# ──────────────────────────────
# ʜᴇʟᴘᴇʀ ꜰᴜɴᴄᴛɪᴏɴꜱ
# ──────────────────────────────
def smallcaps(text):
    """ᴄᴏɴᴠᴇʀᴛ ᴛᴇxᴛ ᴛᴏ ꜱᴍᴀʟʟᴄᴀᴘꜱ"""
    trans = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
    )
    return text.translate(trans)

def format_time(seconds):
    """ꜰᴏʀᴍᴀᴛ ꜱᴇᴄᴏɴᴅꜱ ᴛᴏ ʜ:ᴍ:ꜱ"""
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}ʜ {m}ᴍ {s}ꜱ" if h else f"{m}ᴍ {s}ꜱ"

async def get_user(uid):
    """ɢᴇᴛ ᴜꜱᴇʀ ᴅᴀᴛᴀ ꜰʀᴏᴍ ᴅʙ"""
    return await user_collection.find_one({'id': uid})

async def init_user(uid):
    """ɪɴɪᴛɪᴀʟɪᴢᴇ ɴᴇᴡ ᴜꜱᴇʀ"""
    await user_collection.insert_one({
        'id': uid,
        'balance': 0,
        'bank': 0,
        'user_xp': 0,
        'last_daily': None
    })

# ──────────────────────────────
# ⟡ /ʙᴀʟ - ʙᴀʟᴀɴᴄᴇ ᴄᴏᴍᴍᴀɴᴅ
# ──────────────────────────────
async def balance(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await init_user(uid)
        user = await get_user(uid)
    
    wallet = math.floor(user.get('balance', 0))
    bank = math.floor(user.get('bank', 0))
    total = wallet + bank
    
    msg = (
        f"╭────────────────╮\n"
        f"│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n"
        f"⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n"
        f"⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n\n"
        f"───────"
    )
    
    btns = [[InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"bal_refresh_{uid}")]]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

# ──────────────────────────────
# ⟡ /ᴅᴇᴘᴏꜱɪᴛ - ᴅᴇᴘᴏꜱɪᴛ ᴛᴏ ʙᴀɴᴋ
# ──────────────────────────────
async def deposit(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        amount = int(context.args[0]) if context.args else None
        if not amount or amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /deposit <amount>")
        return
    
    wallet = user.get('balance', 0)
    if wallet < amount:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ᴡᴀʟʟᴇᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    
    await user_collection.update_one(
        {'id': uid},
        {'$inc': {'balance': -amount, 'bank': amount}}
    )
    
    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ᴅᴇᴘᴏꜱɪᴛ ꜱᴜᴄᴄᴇꜱꜱ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴅᴇᴘᴏꜱɪᴛᴇᴅ: <code>{amount}</code> ɢᴏʟᴅ\n"
        f"⟡ ɴᴇᴡ ʙᴀɴᴋ: <code>{user.get('bank', 0) + amount}</code> ɢᴏʟᴅ",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /ᴡɪᴛʜᴅʀᴀᴡ - ᴡɪᴛʜᴅʀᴀᴡ ꜰʀᴏᴍ ʙᴀɴᴋ
# ──────────────────────────────
async def withdraw(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        amount = int(context.args[0]) if context.args else None
        if not amount or amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /withdraw <amount>")
        return
    
    bank = user.get('bank', 0)
    if bank < amount:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ")
        return
    
    await user_collection.update_one(
        {'id': uid},
        {'$inc': {'bank': -amount, 'balance': amount}}
    )
    
    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ᴡɪᴛʜᴅʀᴀᴡ ꜱᴜᴄᴄᴇꜱꜱ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴡɪᴛʜᴅʀᴇᴡ: <code>{amount}</code> ɢᴏʟᴅ\n"
        f"⟡ ɴᴇᴡ ᴡᴀʟʟᴇᴛ: <code>{user.get('balance', 0) + amount}</code> ɢᴏʟᴅ",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /ᴘᴀʏ - ᴘᴀʏᴍᴇɴᴛ ᴄᴏᴍᴍᴀɴᴅ
# ──────────────────────────────
async def pay(update: Update, context: CallbackContext):
    sender_id = update.effective_user.id
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⊗ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ ᴛᴏ ᴘᴀʏ")
        return
    
    recipient = update.message.reply_to_message.from_user
    if recipient.id == sender_id:
        await update.message.reply_text("⊗ ᴄᴀɴɴᴏᴛ ᴘᴀʏ ʏᴏᴜʀꜱᴇʟꜰ")
        return
    
    # ᴄʜᴇᴄᴋ ᴄᴏᴏʟᴅᴏᴡɴ
    if sender_id in pay_cooldown:
        elapsed = (datetime.utcnow() - pay_cooldown[sender_id]).total_seconds()
        if elapsed < 600:  # 10 minutes
            remaining = format_time(600 - elapsed)
            await update.message.reply_text(f"⊗ ᴄᴏᴏʟᴅᴏᴡɴ: {remaining}")
            return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /pay <amount>")
        return
    
    if amount > 1000000:
        await update.message.reply_text("⊗ ᴍᴀx ᴘᴀʏᴍᴇɴᴛ: 1,000,000 ɢᴏʟᴅ")
        return
    
    sender = await get_user(sender_id)
    if not sender or sender.get('balance', 0) < amount:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    
    # ᴄʀᴇᴀᴛᴇ ᴄᴏɴꜰɪʀᴍᴀᴛɪᴏɴ
    pay_id = f"{sender_id}_{recipient.id}_{int(datetime.utcnow().timestamp())}"
    pending_payments[pay_id] = {
        'sender_id': sender_id,
        'recipient_id': recipient.id,
        'amount': amount,
        'expires': datetime.utcnow() + timedelta(seconds=30)
    }
    
    btns = [
        [
            InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data=f"pay_ok_{pay_id}"),
            InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data=f"pay_no_{pay_id}")
        ]
    ]
    
    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ᴄᴏɴꜰɪʀᴍ ᴘᴀʏᴍᴇɴᴛ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴛᴏ: <b>{recipient.first_name}</b>\n"
        f"⟡ ᴀᴍᴏᴜɴᴛ: <code>{amount}</code> ɢᴏʟᴅ\n\n"
        f"⏳ ᴇxᴘɪʀᴇꜱ ɪɴ 30ꜱ",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(btns)
    )
    
    # ᴀᴜᴛᴏ-ᴇxᴘɪʀᴇ
    asyncio.create_task(expire_payment(pay_id))

async def expire_payment(pay_id):
    """ᴇxᴘɪʀᴇ ᴘᴇɴᴅɪɴɢ ᴘᴀʏᴍᴇɴᴛ ᴀꜰᴛᴇʀ 30ꜱ"""
    await asyncio.sleep(30)
    if pay_id in pending_payments:
        del pending_payments[pay_id]

# ──────────────────────────────
# ⟡ /ᴄᴄʟᴀɪᴍ - ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
# ──────────────────────────────
async def daily(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await init_user(uid)
        user = await get_user(uid)
    
    last = user.get('last_daily')
    now = datetime.utcnow()
    
    if last and last.date() == now.date():
        remaining = timedelta(days=1) - (now - last)
        time_left = format_time(remaining.total_seconds())
        await update.message.reply_text(f"⊗ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ\n⏳ ɴᴇxᴛ: {time_left}")
        return
    
    await user_collection.update_one(
        {'id': uid},
        {
            '$inc': {'balance': 2000},
            '$set': {'last_daily': now}
        }
    )
    
    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴄʟᴀɪᴍᴇᴅ: <code>2000</code> ɢᴏʟᴅ\n"
        f"⟡ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <code>{user.get('balance', 0) + 2000}</code>",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /ʀᴏʟʟ - ɢᴀᴍʙʟɪɴɢ ɢᴀᴍᴇ
# ──────────────────────────────
async def roll(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    
    try:
        amount = int(context.args[0])
        choice = context.args[1].upper()
        if choice not in ['ODD', 'EVEN'] or amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /roll <amount> <odd/even>")
        return
    
    user = await get_user(uid)
    if not user or user.get('balance', 0) < amount:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    
    dice = await context.bot.send_dice(update.effective_chat.id, "🎲")
    val = dice.dice.value
    result = "ODD" if val % 2 != 0 else "EVEN"
    won = choice == result
    
    balance_change = amount if won else -amount
    xp_change = 4 if won else -2
    
    await user_collection.update_one(
        {'id': uid},
        {'$inc': {'balance': balance_change, 'user_xp': xp_change}}
    )
    
    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   {'✓ ᴡɪɴ' if won else '✗ ʟᴏꜱᴛ'}   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴅɪᴄᴇ: <code>{val}</code> ({result})\n"
        f"⟡ ʙᴀʟᴀɴᴄᴇ: <code>{balance_change:+d}</code>\n"
        f"⟡ xᴘ: <code>{xp_change:+d}</code>",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /xᴘ - ʟᴇᴠᴇʟ & ʀᴀɴᴋ
# ──────────────────────────────
async def xp_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ")
        return
    
    xp = user.get('user_xp', 0)
    level = min(math.floor(math.sqrt(max(xp, 0) / 100)) + 1, 100)
    
    ranks = {10: "ᴇ", 30: "ᴅ", 50: "ᴄ", 70: "ʙ", 90: "ᴀ", 100: "ꜱ"}
    rank = next((r for lim, r in ranks.items() if level <= lim), "ꜱ")
    
    next_lvl = ((level) ** 2) * 100
    needed = next_lvl - xp
    
    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ʟᴇᴠᴇʟ & ʀᴀɴᴋ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ʟᴇᴠᴇʟ: <code>{level}</code>\n"
        f"⟡ ʀᴀɴᴋ: <code>{rank}</code>\n"
        f"⟡ xᴘ: <code>{xp}</code>\n"
        f"⟡ ɴᴇᴇᴅᴇᴅ: <code>{needed}</code>",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ᴄᴀʟʟʙᴀᴄᴋ ʜᴀɴᴅʟᴇʀꜱ
# ──────────────────────────────
async def callback_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id
    
    # ʙᴀʟᴀɴᴄᴇ ʀᴇғʀᴇꜱʜ
    if data.startswith("bal_refresh_"):
        target_uid = int(data.split("_")[2])
        if uid != target_uid:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ", show_alert=True)
            return
        
        user = await get_user(uid)
        wallet = math.floor(user.get('balance', 0))
        bank = math.floor(user.get('bank', 0))
        total = wallet + bank
        
        msg = (
            f"╭────────────────╮\n"
            f"│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n"
            f"╰────────────────╯\n\n"
            f"⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n"
            f"⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n"
            f"⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n\n"
            f"───────"
        )
        
        btns = [[InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"bal_refresh_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓ ʀᴇғʀᴇꜱʜᴇᴅ")
    
    # ᴘᴀʏᴍᴇɴᴛ ᴄᴏɴꜰɪʀᴍ
    elif data.startswith("pay_ok_"):
        pay_id = data.split("_", 2)[2]
        
        if pay_id not in pending_payments:
            await q.edit_message_text("⊗ ᴘᴀʏᴍᴇɴᴛ ᴇxᴘɪʀᴇᴅ")
            return
        
        payment = pending_payments[pay_id]
        if uid != payment['sender_id']:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀ ᴘᴀʏᴍᴇɴᴛ", show_alert=True)
            return
        
        sender = await get_user(payment['sender_id'])
        if sender.get('balance', 0) < payment['amount']:
            await q.edit_message_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
            del pending_payments[pay_id]
            return
        
        # ᴘʀᴏᴄᴇꜱꜱ ᴘᴀʏᴍᴇɴᴛ
        await user_collection.update_one(
            {'id': payment['sender_id']},
            {'$inc': {'balance': -payment['amount']}}
        )
        await user_collection.update_one(
            {'id': payment['recipient_id']},
            {'$inc': {'balance': payment['amount']}}
        )
        
        pay_cooldown[payment['sender_id']] = datetime.utcnow()
        del pending_payments[pay_id]
        
        await q.edit_message_text(
            f"╭────────────────╮\n"
            f"│   ✓ ᴘᴀʏᴍᴇɴᴛ ꜱᴇɴᴛ   │\n"
            f"╰────────────────╯\n\n"
            f"⟡ ᴀᴍᴏᴜɴᴛ: <code>{payment['amount']}</code> ɢᴏʟᴅ",
            parse_mode="HTML"
        )
        await q.answer("✓ ᴘᴀɪᴅ")
    
    # ᴘᴀʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟ
    elif data.startswith("pay_no_"):
        pay_id = data.split("_", 2)[2]
        if pay_id in pending_payments:
            del pending_payments[pay_id]
        await q.edit_message_text("⊗ ᴘᴀʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ")
        await q.answer("✗ ᴄᴀɴᴄᴇʟʟᴇᴅ")

# ──────────────────────────────
# ʀᴇɢɪꜱᴛᴇʀ ʜᴀɴᴅʟᴇʀꜱ
# ──────────────────────────────
application.add_handler(CommandHandler("bal", balance, block=False))
application.add_handler(CommandHandler("deposit", deposit, block=False))
application.add_handler(CommandHandler("withdraw", withdraw, block=False))
application.add_handler(CommandHandler("pay", pay, block=False))
application.add_handler(CommandHandler("cclaim", daily, block=False))
application.add_handler(CommandHandler("roll", roll, block=False))
application.add_handler(CommandHandler("xp", xp_cmd, block=False))
application.add_handler(CallbackQueryHandler(callback_handler, block=False))