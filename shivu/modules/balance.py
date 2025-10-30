import math
import random
import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection, collection

# ──────────────────────────────
# ɢʟᴏʙᴀʟ ᴄᴏᴏʟᴅᴏᴡɴꜱ & ᴘᴇɴᴅɪɴɢ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ
# ──────────────────────────────
pay_cooldown = {}
pending_payments = {}
loan_check_running = False

# ──────────────────────────────
# ʙᴀɴᴋ ᴄᴏɴꜰɪɢᴜʀᴀᴛɪᴏɴ
# ──────────────────────────────
BANK_CONFIG = {
    'interest_rate': 0.05,  # 5% daily interest on bank balance
    'loan_interest': 0.10,  # 10% interest on loans
    'max_loan': 100000,     # Maximum loan amount
    'loan_duration': 3,     # Days to repay loan
    'penalty_rate': 0.20    # 20% penalty if overdue
}

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
    if h >= 24:
        d = h // 24
        h = h % 24
        return f"{d}ᴅ {h}ʜ {m}ᴍ"
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
        'last_daily': None,
        'last_interest': None,
        'loan_amount': 0,
        'loan_due_date': None,
        'loan_taken_date': None,
        'notifications': [],
        'permanent_debt': 0
    })

async def get_user_characters(uid):
    """ɢᴇᴛ ᴜꜱᴇʀ'ꜱ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ"""
    user = await user_collection.find_one({'id': uid})
    return user.get('characters', []) if user else []

# ──────────────────────────────
# ʟᴏᴀɴ ᴄʜᴇᴄᴋ ꜱʏꜱᴛᴇᴍ
# ──────────────────────────────
async def check_overdue_loans():
    """ᴄʜᴇᴄᴋ ᴀɴᴅ ᴘʀᴏᴄᴇꜱꜱ ᴏᴠᴇʀᴅᴜᴇ ʟᴏᴀɴꜱ"""
    global loan_check_running
    if loan_check_running:
        return
    
    loan_check_running = True
    
    while True:
        try:
            now = datetime.utcnow()
            
            # Find users with overdue loans
            users_with_loans = user_collection.find({
                'loan_amount': {'$gt': 0},
                'loan_due_date': {'$lt': now}
            })
            
            async for user in users_with_loans:
                uid = user['id']
                loan_amount = user.get('loan_amount', 0)
                penalty = int(loan_amount * BANK_CONFIG['penalty_rate'])
                total_due = loan_amount + penalty
                
                balance = user.get('balance', 0)
                bank = user.get('bank', 0)
                total_funds = balance + bank
                
                seized_items = []
                
                # Try to collect from balance first
                if balance >= total_due:
                    await user_collection.update_one(
                        {'id': uid},
                        {
                            '$inc': {'balance': -total_due},
                            '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_taken_date': None}
                        }
                    )
                    seized_items.append(f"💰 {total_due} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                    
                # Try balance + bank
                elif total_funds >= total_due:
                    amount_from_balance = balance
                    amount_from_bank = total_due - balance
                    
                    await user_collection.update_one(
                        {'id': uid},
                        {
                            '$set': {
                                'balance': 0,
                                'bank': bank - amount_from_bank,
                                'loan_amount': 0,
                                'loan_due_date': None,
                                'loan_taken_date': None
                            }
                        }
                    )
                    seized_items.append(f"💰 {amount_from_balance} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                    seized_items.append(f"🏦 {amount_from_bank} ɢᴏʟᴅ ғʀᴏᴍ ʙᴀɴᴋ")
                    
                # Not enough funds - seize characters
                else:
                    # Take all available money
                    if total_funds > 0:
                        await user_collection.update_one(
                            {'id': uid},
                            {'$set': {'balance': 0, 'bank': 0}}
                        )
                        seized_items.append(f"💰 {total_funds} ɢᴏʟᴅ (ᴀʟʟ ғᴜɴᴅꜱ)")
                    
                    remaining_debt = total_due - total_funds
                    
                    # Calculate characters to seize (1 character = 10000 gold value)
                    characters_to_seize = math.ceil(remaining_debt / 10000)
                    
                    user_chars = await get_user_characters(uid)
                    
                    if user_chars and len(user_chars) > 0:
                        seized_count = min(characters_to_seize, len(user_chars))
                        
                        # Randomly select characters to seize
                        seized_chars = random.sample(user_chars, seized_count)
                        
                        # Remove seized characters
                        for char_id in seized_chars:
                            char_data = await collection.find_one({'id': char_id})
                            char_name = char_data.get('name', 'Unknown') if char_data else 'Unknown'
                            seized_items.append(f"👤 {char_name} (ɪᴅ: {char_id})")
                            
                            user_chars.remove(char_id)
                        
                        await user_collection.update_one(
                            {'id': uid},
                            {
                                '$set': {
                                    'characters': user_chars,
                                    'loan_amount': 0,
                                    'loan_due_date': None,
                                    'loan_taken_date': None
                                }
                            }
                        )
                    else:
                        # No characters to seize - just clear loan but add to permanent debt
                        await user_collection.update_one(
                            {'id': uid},
                            {
                                '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_taken_date': None},
                                '$inc': {'permanent_debt': remaining_debt}
                            }
                        )
                        seized_items.append(f"⚠️ ᴀᴅᴅᴇᴅ {remaining_debt} ᴛᴏ ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ")
                
                # Store notification for user
                notification_msg = (
                    f"╭────────────────╮\n"
                    f"│   ⚠️ ʟᴏᴀɴ ᴄᴏʟʟᴇᴄᴛᴇᴅ   │\n"
                    f"╰────────────────╯\n\n"
                    f"⟡ ʟᴏᴀɴ: <code>{loan_amount}</code> ɢᴏʟᴅ\n"
                    f"⟡ ᴘᴇɴᴀʟᴛʏ: <code>{penalty}</code> ɢᴏʟᴅ\n"
                    f"⟡ ᴛᴏᴛᴀʟ: <code>{total_due}</code> ɢᴏʟᴅ\n\n"
                    f"<b>ꜱᴇɪᴢᴇᴅ ɪᴛᴇᴍꜱ:</b>\n" +
                    "\n".join(f"  • {item}" for item in seized_items)
                )
                
                await user_collection.update_one(
                    {'id': uid},
                    {
                        '$push': {
                            'notifications': {
                                'type': 'loan_collection',
                                'message': notification_msg,
                                'timestamp': now
                            }
                        }
                    }
                )
                
        except Exception as e:
            print(f"Error in loan check: {e}")
        
        # Check every hour
        await asyncio.sleep(3600)

# Start loan checker
asyncio.create_task(check_overdue_loans())

# ──────────────────────────────
# ɪɴᴛᴇʀᴇꜱᴛ ᴄᴀʟᴄᴜʟᴀᴛɪᴏɴ
# ──────────────────────────────
async def calculate_interest(user_id):
    """ᴄᴀʟᴄᴜʟᴀᴛᴇ ᴀɴᴅ ᴀᴅᴅ ɪɴᴛᴇʀᴇꜱᴛ"""
    user = await get_user(user_id)
    if not user:
        return 0
    
    bank = user.get('bank', 0)
    if bank <= 0:
        return 0
    
    last_interest = user.get('last_interest')
    now = datetime.utcnow()
    
    # Calculate interest only once per day
    if last_interest and (now - last_interest).total_seconds() < 86400:
        return 0
    
    interest = int(bank * BANK_CONFIG['interest_rate'])
    
    await user_collection.update_one(
        {'id': user_id},
        {
            '$inc': {'bank': interest},
            '$set': {'last_interest': now}
        }
    )
    
    return interest

# ──────────────────────────────
# ⟡ /ʙᴀʟ - ʙᴀʟᴀɴᴄᴇ ᴄᴏᴍᴍᴀɴᴅ
# ──────────────────────────────
async def balance(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)

    if not user:
        await init_user(uid)
        user = await get_user(uid)

    # Check and add interest
    interest_earned = await calculate_interest(uid)
    user = await get_user(uid)  # Refresh data

    wallet = math.floor(user.get('balance', 0))
    bank = math.floor(user.get('bank', 0))
    total = wallet + bank
    loan = user.get('loan_amount', 0)

    msg = (
        f"╭────────────────╮\n"
        f"│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n"
        f"⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n"
        f"⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n"
    )
    
    if loan > 0:
        due_date = user.get('loan_due_date')
        if due_date:
            time_left = (due_date - datetime.utcnow()).total_seconds()
            msg += f"\n⚠️ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n"
            msg += f"⏳ ᴅᴜᴇ ɪɴ: {format_time(time_left)}\n"
    
    if interest_earned > 0:
        msg += f"\n✨ ɪɴᴛᴇʀᴇꜱᴛ ᴇᴀʀɴᴇᴅ: <code>+{interest_earned}</code> ɢᴏʟᴅ"
    
    msg += "\n\n───────"

    btns = [
        [InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"bal_refresh_{uid}")],
        [
            InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"bank_menu_{uid}"),
            InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"loan_menu_{uid}")
        ]
    ]
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

    new_bank = user.get('bank', 0) + amount

    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ᴅᴇᴘᴏꜱɪᴛ ꜱᴜᴄᴄᴇꜱꜱ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴅᴇᴘᴏꜱɪᴛᴇᴅ: <code>{amount}</code> ɢᴏʟᴅ\n"
        f"⟡ ɴᴇᴡ ʙᴀɴᴋ: <code>{new_bank}</code> ɢᴏʟᴅ\n"
        f"⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>5%</code> ᴅᴀɪʟʏ",
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

    new_wallet = user.get('balance', 0) + amount

    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ᴡɪᴛʜᴅʀᴀᴡ ꜱᴜᴄᴄᴇꜱꜱ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴡɪᴛʜᴅʀᴇᴡ: <code>{amount}</code> ɢᴏʟᴅ\n"
        f"⟡ ɴᴇᴡ ᴡᴀʟʟᴇᴛ: <code>{new_wallet}</code> ɢᴏʟᴅ",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /ʟᴏᴀɴ - ʟᴏᴀɴ ᴄᴏᴍᴍᴀɴᴅ
# ──────────────────────────────
async def loan_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)

    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return

    current_loan = user.get('loan_amount', 0)
    
    if current_loan > 0:
        due_date = user.get('loan_due_date')
        time_left = (due_date - datetime.utcnow()).total_seconds()
        
        msg = (
            f"╭────────────────╮\n"
            f"│   ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ   │\n"
            f"╰────────────────╯\n\n"
            f"⟡ ʟᴏᴀɴ: <code>{current_loan}</code> ɢᴏʟᴅ\n"
            f"⟡ ᴅᴜᴇ ɪɴ: {format_time(time_left)}\n\n"
            f"⚠️ ʀᴇᴘᴀʏ ᴡɪᴛʜ /repay"
        )
        
        btns = [[InlineKeyboardButton("💰 ʀᴇᴘᴀʏ", callback_data=f"repay_loan_{uid}")]]
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return

    try:
        amount = int(context.args[0]) if context.args else None
        if not amount or amount <= 0:
            raise ValueError
    except:
        await update.message.reply_text(
            f"⊗ ᴜꜱᴀɢᴇ: /loan <amount>\n\n"
            f"⟡ ᴍᴀx ʟᴏᴀɴ: <code>{BANK_CONFIG['max_loan']}</code>\n"
            f"⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{int(BANK_CONFIG['loan_interest']*100)}%</code>\n"
            f"⟡ ᴅᴜʀᴀᴛɪᴏɴ: <code>{BANK_CONFIG['loan_duration']}</code> ᴅᴀʏꜱ",
            parse_mode="HTML"
        )
        return

    if amount > BANK_CONFIG['max_loan']:
        await update.message.reply_text(f"⊗ ᴍᴀx ʟᴏᴀɴ: {BANK_CONFIG['max_loan']} ɢᴏʟᴅ")
        return

    interest = int(amount * BANK_CONFIG['loan_interest'])
    total_repay = amount + interest
    due_date = datetime.utcnow() + timedelta(days=BANK_CONFIG['loan_duration'])

    await user_collection.update_one(
        {'id': uid},
        {
            '$inc': {'balance': amount},
            '$set': {
                'loan_amount': total_repay,
                'loan_due_date': due_date,
                'loan_taken_date': datetime.utcnow()
            }
        }
    )

    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ✓ ʟᴏᴀɴ ᴀᴘᴘʀᴏᴠᴇᴅ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ʟᴏᴀɴ: <code>{amount}</code> ɢᴏʟᴅ\n"
        f"⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{interest}</code> ɢᴏʟᴅ\n"
        f"⟡ ᴛᴏᴛᴀʟ ʀᴇᴘᴀʏ: <code>{total_repay}</code> ɢᴏʟᴅ\n"
        f"⟡ ᴅᴜᴇ ɪɴ: <code>{BANK_CONFIG['loan_duration']}</code> ᴅᴀʏꜱ\n\n"
        f"⚠️ ᴘᴇɴᴀʟᴛʏ: <code>{int(BANK_CONFIG['penalty_rate']*100)}%</code> ɪꜰ ᴏᴠᴇʀᴅᴜᴇ",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /ʀᴇᴘᴀʏ - ʀᴇᴘᴀʏ ʟᴏᴀɴ
# ──────────────────────────────
async def repay(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)

    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return

    loan = user.get('loan_amount', 0)
    if loan <= 0:
        await update.message.reply_text("⊗ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ")
        return

    balance = user.get('balance', 0)
    if balance < loan:
        await update.message.reply_text(
            f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n"
            f"⟡ ɴᴇᴇᴅᴇᴅ: <code>{loan}</code> ɢᴏʟᴅ\n"
            f"⟡ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <code>{balance}</code> ɢᴏʟᴅ",
            parse_mode="HTML"
        )
        return

    await user_collection.update_one(
        {'id': uid},
        {
            '$inc': {'balance': -loan},
            '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_taken_date': None}
        }
    )

    await update.message.reply_text(
        f"╭────────────────╮\n"
        f"│   ✓ ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ   │\n"
        f"╰────────────────╯\n\n"
        f"⟡ ᴘᴀɪᴅ: <code>{loan}</code> ɢᴏʟᴅ\n"
        f"⟡ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <code>{balance - loan}</code> ɢᴏʟᴅ",
        parse_mode="HTML"
    )

# ──────────────────────────────
# ⟡ /ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ - ᴠɪᴇᴡ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ
# ──────────────────────────────
async def notifications(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)

    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ")
        return

    notifs = user.get('notifications', [])
    
    if not notifs:
        await update.message.reply_text("⊗ ɴᴏ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ")
        return

    # Show last 5 notifications
    recent_notifs = notifs[-5:]
    
    msg = "╭────────────────╮\n"
    msg += "│   📬 ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ   │\n"
    msg += "╰────────────────╯\n\n"
    
    for i, notif in enumerate(reversed(recent_notifs), 1):
        msg += f"<b>{i}.</b> {notif.get('message', 'ɴᴏ ᴍᴇꜱꜱᴀɢᴇ')}\n\n"
    
    btns = [[InlineKeyboardButton("🗑️ ᴄʟᴇᴀʀ ᴀʟʟ", callback_data=f"clear_notifs_{uid}")]]
    
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

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

        # Check and add interest
        interest_earned = await calculate_interest(uid)
        user = await get_user(uid)
        
        wallet = math.floor(user.get('balance', 0))
        bank = math.floor(user.get('bank', 0))
        total = wallet + bank
        loan = user.get('loan_amount', 0)

        msg = (
            f"╭────────────────╮\n"
            f"│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n"
            f"╰────────────────╯\n\n"
            f"⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n"
            f"⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n"
            f"⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n"
        )
        
        if loan > 0:
            due_date = user.get('loan_due_date')
            if due_date:
                time_left = (due_date - datetime.utcnow()).total_seconds()
                msg += f"\n⚠️ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n"
                msg += f"⏳ ᴅᴜᴇ ɪɴ: {format_time(time_left)}\n"
        
        if interest_earned > 0:
            msg += f"\n✨ ɪɴᴛᴇʀᴇꜱᴛ ᴇᴀʀɴᴇᴅ: <code>+{interest_earned}</code> ɢᴏʟᴅ"
        
        msg += "\n\n───────"

        btns = [
            [InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"bal_refresh_{uid}")],
            [
                InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"bank_menu_{uid}"),
                InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"loan_menu_{uid}")
            ]
        ]
        
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓ ʀᴇғʀᴇꜱʜᴇᴅ")

    # ʙᴀɴᴋ ᴍᴇɴᴜ
    elif data.startswith("bank_menu_"):
        target_uid = int(data.split("_")[2])
        if uid != target_uid:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀ ᴍᴇɴᴜ", show_alert=True)
            return

        user = await get_user(uid)
        bank = user.get('bank', 0)
        
        msg = (
            f"╭────────────────╮\n"
            f"│   🏦 ʙᴀɴᴋ ᴍᴇɴᴜ   │\n"
            f"╰────────────────╯\n\n"
            f"⟡ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ: <code>{bank}</code> ɢᴏʟᴅ\n"
            f"⟡ ɪɴᴛᴇʀᴇꜱᴛ ʀᴀᴛᴇ: <code>5%</code> ᴅᴀɪʟʏ\n\n"
            f"ᴜꜱᴇ /deposit <amount> ᴛᴏ ᴅᴇᴘᴏꜱɪᴛ\n"
            f"ᴜꜱᴇ /withdraw <amount> ᴛᴏ ᴡɪᴛʜᴅʀᴀᴡ"
        )
        
        btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_refresh_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    # ʟᴏᴀɴ ᴍᴇɴᴜ
    elif data.startswith("loan_menu_"):
        target_uid = int(data.split("_")[2])
        if uid != target_uid:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀ ᴍᴇɴᴜ", show_alert=True)
            return

        user = await get_user(uid)
        loan = user.get('loan_amount', 0)
        
        if loan > 0:
            due_date = user.get('loan_due_date')
            time_left = (due_date - datetime.utcnow()).total_seconds()
            
            msg = (
                f"╭────────────────╮\n"
                f"│   💳 ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ   │\n"
                f"╰────────────────╯\n\n"
                f"⟡ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n"
                f"⟡ ᴅᴜᴇ ɪɴ: {format_time(time_left)}\n\n"
                f"ᴜꜱᴇ /repay ᴛᴏ ʀᴇᴘᴀʏ ʟᴏᴀɴ"
            )
        else:
            msg = (
                f"╭────────────────╮\n"
                f"│   💳 ʟᴏᴀɴ ᴍᴇɴᴜ   │\n"
                f"╰────────────────╯\n\n"
                f"⟡ ᴍᴀx ʟᴏᴀɴ: <code>{BANK_CONFIG['max_loan']}</code> ɢᴏʟᴅ\n"
                f"⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{int(BANK_CONFIG['loan_interest']*100)}%</code>\n"
                f"⟡ ᴅᴜʀᴀᴛɪᴏɴ: <code>{BANK_CONFIG['loan_duration']}</code> ᴅᴀʏꜱ\n"
                f"⟡ ᴘᴇɴᴀʟᴛʏ: <code>{int(BANK_CONFIG['penalty_rate']*100)}%</code> ɪꜰ ᴏᴠᴇʀᴅᴜᴇ\n\n"
                f"ᴜꜱᴇ /loan <amount> ᴛᴏ ᴛᴀᴋᴇ ʟᴏᴀɴ"
            )
        
        btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_refresh_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    # ʀᴇᴘᴀʏ ʟᴏᴀɴ
    elif data.startswith("repay_loan_"):
        target_uid = int(data.split("_")[2])
        if uid != target_uid:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀ ʟᴏᴀɴ", show_alert=True)
            return

        user = await get_user(uid)
        loan = user.get('loan_amount', 0)
        
        if loan <= 0:
            await q.answer("⊗ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ", show_alert=True)
            return

        balance = user.get('balance', 0)
        if balance < loan:
            await q.answer(f"⊗ ɴᴇᴇᴅ {loan} ɢᴏʟᴅ, ʜᴀᴠᴇ {balance}", show_alert=True)
            return

        await user_collection.update_one(
            {'id': uid},
            {
                '$inc': {'balance': -loan},
                '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_taken_date': None}
            }
        )

        await q.edit_message_text(
            f"╭────────────────╮\n"
            f"│   ✓ ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ   │\n"
            f"╰────────────────╯\n\n"
            f"⟡ ᴘᴀɪᴅ: <code>{loan}</code> ɢᴏʟᴅ\n"
            f"⟡ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <code>{balance - loan}</code> ɢᴏʟᴅ",
            parse_mode="HTML"
        )
        await q.answer("✓ ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ")

    # ᴄʟᴇᴀʀ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ
    elif data.startswith("clear_notifs_"):
        target_uid = int(data.split("_")[2])
        if uid != target_uid:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ", show_alert=True)
            return

        await user_collection.update_one(
            {'id': uid},
            {'$set': {'notifications': []}}
        )

        await q.edit_message_text("✓ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ")
        await q.answer("✓ ᴄʟᴇᴀʀᴇᴅ")

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
application.add_handler(CommandHandler("loan", loan_cmd, block=False))
application.add_handler(CommandHandler("repay", repay, block=False))
application.add_handler(CommandHandler("notifications", notifications, block=False))
application.add_handler(CommandHandler("pay", pay, block=False))
application.add_handler(CommandHandler("cclaim", daily, block=False))
application.add_handler(CommandHandler("roll", roll, block=False))
application.add_handler(CommandHandler("xp", xp_cmd, block=False))
application.add_handler(CallbackQueryHandler(callback_handler, block=False))