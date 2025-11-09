import math
import random
import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection, collection

pay_cooldown = {}
pending_payments = {}
loan_check_lock = asyncio.Lock()

BANK_CFG = {
    'int_rate': 0.05,
    'loan_int': 0.10,
    'max_loan': 100000,
    'loan_days': 3,
    'penalty': 0.20
}

def fmt_time(s):
    h, r = divmod(int(s), 3600)
    m, s = divmod(r, 60)
    if h >= 24:
        d, h = h // 24, h % 24
        return f"{d}ᴅ {h}ʜ {m}ᴍ"
    return f"{h}ʜ {m}ᴍ {s}ꜱ" if h else f"{m}ᴍ {s}ꜱ"

async def get_user(uid):
    return await user_collection.find_one({'id': uid})

async def init_user(uid):
    await user_collection.insert_one({
        'id': uid,
        'balance': 0,
        'bank': 0,
        'user_xp': 0,
        'last_daily': None,
        'last_interest': None,
        'loan_amount': 0,
        'loan_due_date': None,
        'notifications': [],
        'permanent_debt': 0,
        'characters': []
    })

async def calc_interest(uid):
    user = await get_user(uid)
    if not user:
        return 0
    bank = user.get('bank', 0)
    if bank <= 0:
        return 0
    last = user.get('last_interest')
    now = datetime.utcnow()
    if last and (now - last).total_seconds() < 86400:
        return 0
    interest = int(bank * BANK_CFG['int_rate'])
    await user_collection.update_one({'id': uid}, {'$inc': {'bank': interest}, '$set': {'last_interest': now}})
    return interest

async def check_loans():
    """Background task to check and collect overdue loans"""
    async with loan_check_lock:
        while True:
            try:
                now = datetime.utcnow()
                async for user in user_collection.find({'loan_amount': {'$gt': 0}, 'loan_due_date': {'$lt': now}}):
                    uid = user['id']
                    loan = user.get('loan_amount', 0)
                    penalty = int(loan * BANK_CFG['penalty'])
                    total = loan + penalty
                    bal = user.get('balance', 0)
                    bank = user.get('bank', 0)
                    funds = bal + bank
                    seized = []

                    if bal >= total:
                        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -total}, '$set': {'loan_amount': 0, 'loan_due_date': None}})
                        seized.append(f"💰 {total} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                    elif funds >= total:
                        await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': bank - (total - bal), 'loan_amount': 0, 'loan_due_date': None}})
                        seized.append(f"💰 {bal} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                        seized.append(f"🏦 {total - bal} ɢᴏʟᴅ ғʀᴏᴍ ʙᴀɴᴋ")
                    else:
                        if funds > 0:
                            await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': 0}})
                            seized.append(f"💰 {funds} ɢᴏʟᴅ (ᴀʟʟ ғᴜɴᴅꜱ)")
                        debt = total - funds
                        chars_needed = math.ceil(debt / 10000)
                        chars = user.get('characters', [])
                        if chars:
                            take = min(chars_needed, len(chars))
                            taken = random.sample(chars, take)
                            for cid in taken:
                                cdata = await collection.find_one({'id': cid})
                                cname = cdata.get('name', 'ᴜɴᴋɴᴏᴡɴ') if cdata else 'ᴜɴᴋɴᴏᴡɴ'
                                seized.append(f"👤 {cname} (ɪᴅ: {cid})")
                                chars.remove(cid)
                            await user_collection.update_one({'id': uid}, {'$set': {'characters': chars, 'loan_amount': 0, 'loan_due_date': None}})
                        else:
                            await user_collection.update_one({'id': uid}, {'$set': {'loan_amount': 0, 'loan_due_date': None}, '$inc': {'permanent_debt': debt}})
                            seized.append(f"⚠️ ᴀᴅᴅᴇᴅ {debt} ᴛᴏ ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ")

                    msg = f"╭────────────────╮\n│   ⚠️ ʟᴏᴀɴ ᴄᴏʟʟᴇᴄᴛᴇᴅ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ᴘᴇɴᴀʟᴛʏ: <code>{penalty}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n\n<b>ꜱᴇɪᴢᴇᴅ ɪᴛᴇᴍꜱ:</b>\n" + "\n".join(f"  • {i}" for i in seized)
                    await user_collection.update_one({'id': uid}, {'$push': {'notifications': {'type': 'loan_collection', 'message': msg, 'timestamp': now}}})
            except Exception as e:
                print(f"ʟᴏᴀɴ ᴇʀʀᴏʀ: {e}")
            await asyncio.sleep(3600)

async def post_init(app):
    """Initialize background tasks after bot starts"""
    asyncio.create_task(check_loans())

async def balance(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await init_user(uid)
        user = await get_user(uid)
    interest = await calc_interest(uid)
    user = await get_user(uid)
    wallet = int(user.get('balance', 0))
    bank = int(user.get('bank', 0))
    total = wallet + bank
    loan = user.get('loan_amount', 0)
    msg = f"╭────────────────╮\n│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n╰────────────────╯\n\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n"
    if loan > 0:
        due = user.get('loan_due_date')
        if due:
            left = (due - datetime.utcnow()).total_seconds()
            msg += f"\n⚠️ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⏳ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n"
    if interest > 0:
        msg += f"\n✨ ɪɴᴛᴇʀᴇꜱᴛ: <code>+{interest}</code> ɢᴏʟᴅ"
    msg += "\n\n───────"
    btns = [[InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"bal_{uid}")], [InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"bank_{uid}"), InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"loan_{uid}")]]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def deposit(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /deposit <amount>")
        return
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt, 'bank': amt}})
    await update.message.reply_text(f"╭────────────────╮\n│   ᴅᴇᴘᴏꜱɪᴛ ꜱᴜᴄᴄᴇꜱꜱ   │\n╰────────────────╯\n\n⟡ ᴅᴇᴘᴏꜱɪᴛᴇᴅ: <code>{amt}</code> ɢᴏʟᴅ\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>5%</code> ᴅᴀɪʟʏ", parse_mode="HTML")

async def withdraw(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /withdraw <amount>")
        return
    if user.get('bank', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ")
        return
    await user_collection.update_one({'id': uid}, {'$inc': {'bank': -amt, 'balance': amt}})
    await update.message.reply_text(f"╭────────────────╮\n│   ᴡɪᴛʜᴅʀᴀᴡ ꜱᴜᴄᴄᴇꜱꜱ   │\n╰────────────────╯\n\n⟡ ᴡɪᴛʜᴅʀᴇᴡ: <code>{amt}</code> ɢᴏʟᴅ", parse_mode="HTML")

async def loan_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    curr = user.get('loan_amount', 0)
    if curr > 0:
        due = user.get('loan_due_date')
        left = (due - datetime.utcnow()).total_seconds()
        msg = f"╭────────────────╮\n│   ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{curr}</code> ɢᴏʟᴅ\n⟡ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n\n⚠️ ʀᴇᴘᴀʏ ᴡɪᴛʜ /repay"
        btns = [[InlineKeyboardButton("💰 ʀᴇᴘᴀʏ", callback_data=f"repay_{uid}")]]
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text(f"⊗ ᴜꜱᴀɢᴇ: /loan <amount>\n\n⟡ ᴍᴀx: <code>{BANK_CFG['max_loan']}</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{int(BANK_CFG['loan_int']*100)}%</code>\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: <code>{BANK_CFG['loan_days']}</code> ᴅᴀʏꜱ", parse_mode="HTML")
        return
    if amt > BANK_CFG['max_loan']:
        await update.message.reply_text(f"⊗ ᴍᴀx ʟᴏᴀɴ: {BANK_CFG['max_loan']} ɢᴏʟᴅ")
        return
    interest = int(amt * BANK_CFG['loan_int'])
    total = amt + interest
    due = datetime.utcnow() + timedelta(days=BANK_CFG['loan_days'])
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': amt}, '$set': {'loan_amount': total, 'loan_due_date': due}})
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ʟᴏᴀɴ ᴀᴘᴘʀᴏᴠᴇᴅ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{amt}</code> ɢᴏʟᴅ\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{interest}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ ʀᴇᴘᴀʏ: <code>{total}</code> ɢᴏʟᴅ\n⟡ ᴅᴜᴇ ɪɴ: <code>{BANK_CFG['loan_days']}</code> ᴅᴀʏꜱ\n\n⚠️ ᴘᴇɴᴀʟᴛʏ: <code>{int(BANK_CFG['penalty']*100)}%</code> ɪꜰ ᴏᴠᴇʀᴅᴜᴇ", parse_mode="HTML")

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
    bal = user.get('balance', 0)
    if bal < loan:
        await update.message.reply_text(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n⟡ ɴᴇᴇᴅᴇᴅ: <code>{loan}</code>\n⟡ ʏᴏᴜʀꜱ: <code>{bal}</code>", parse_mode="HTML")
        return
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -loan}, '$set': {'loan_amount': 0, 'loan_due_date': None}})
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ɴᴇᴡ: <code>{bal - loan}</code>", parse_mode="HTML")

async def notifications(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    notifs = user.get('notifications', [])
    if not notifs:
        await update.message.reply_text("⊗ ɴᴏ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ")
        return
    recent = notifs[-5:]
    msg = "╭────────────────╮\n│   📬 ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ   │\n╰────────────────╯\n\n"
    for i, n in enumerate(reversed(recent), 1):
        msg += f"<b>{i}.</b> {n.get('message', 'ɴᴏ ᴍᴇꜱꜱᴀɢᴇ')}\n\n"
    btns = [[InlineKeyboardButton("🗑️ ᴄʟᴇᴀʀ", callback_data=f"clr_{uid}")]]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def pay(update: Update, context: CallbackContext):
    sid = update.effective_user.id
    if not update.message.reply_to_message:
        await update.message.reply_text("⊗ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ")
        return
    rec = update.message.reply_to_message.from_user
    if rec.id == sid:
        await update.message.reply_text("⊗ ᴄᴀɴɴᴏᴛ ᴘᴀʏ ʏᴏᴜʀꜱᴇʟꜰ")
        return
    if rec.is_bot:
        await update.message.reply_text("⊗ɢᴀʏ ʜᴏ ᴋʏᴀ ʙᴇ???????")
        return
    if sid in pay_cooldown:
        elapsed = (datetime.utcnow() - pay_cooldown[sid]).total_seconds()
        if elapsed < 600:
            await update.message.reply_text(f"⊗ ᴄᴏᴏʟᴅᴏᴡɴ: {fmt_time(600 - elapsed)}")
            return
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /pay <amount>")
        return
    if amt > 1000000:
        await update.message.reply_text("⊗ ᴍᴀx: 1,000,000 ɢᴏʟᴅ")
        return
    sender = await get_user(sid)
    if not sender or sender.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    pid = f"{sid}_{rec.id}_{int(datetime.utcnow().timestamp())}"
    pending_payments[pid] = {'sender_id': sid, 'recipient_id': rec.id, 'amount': amt}
    btns = [[InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data=f"pok_{pid}"), InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data=f"pno_{pid}")]]
    await update.message.reply_text(f"╭────────────────╮\n│   ᴄᴏɴꜰɪʀᴍ ᴘᴀʏᴍᴇɴᴛ   │\n╰────────────────╯\n\n⟡ ᴛᴏ: <b>{rec.first_name}</b>\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code> ɢᴏʟᴅ\n\n⏳ ᴇxᴘɪʀᴇꜱ ɪɴ 30ꜱ", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    asyncio.create_task(expire_pay(pid))

async def expire_pay(pid):
    await asyncio.sleep(30)
    if pid in pending_payments:
        del pending_payments[pid]

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
        await update.message.reply_text(f"⊗ ᴄʟᴀɪᴍᴇᴅ ᴛᴏᴅᴀʏ\n⏳ ɴᴇxᴛ: {fmt_time(remaining.total_seconds())}")
        return
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': 2000}, '$set': {'last_daily': now}})
    await update.message.reply_text(f"╭────────────────╮\n│   ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ   │\n╰────────────────╯\n\n⟡ ᴄʟᴀɪᴍᴇᴅ: <code>2000</code> ɢᴏʟᴅ", parse_mode="HTML")

async def roll(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        amt = int(context.args[0])
        choice = context.args[1].upper()
        if choice not in ['ODD', 'EVEN'] or amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /roll <amount> <odd/even>")
        return
    user = await get_user(uid)
    if not user or user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    dice = await context.bot.send_dice(update.effective_chat.id, "🎲")
    val = dice.dice.value
    result = "ODD" if val % 2 != 0 else "EVEN"
    won = choice == result
    change = amt if won else -amt
    xp = 4 if won else -2
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': change, 'user_xp': xp}})
    await update.message.reply_text(f"╭────────────────╮\n│   {'✓ ᴡɪɴ' if won else '✗ ʟᴏꜱᴛ'}   │\n╰────────────────╯\n\n⟡ ᴅɪᴄᴇ: <code>{val}</code> ({result})\n⟡ ʙᴀʟᴀɴᴄᴇ: <code>{change:+d}</code>\n⟡ xᴘ: <code>{xp:+d}</code>", parse_mode="HTML")

async def xp_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    xp = user.get('user_xp', 0)
    lvl = min(math.floor(math.sqrt(max(xp, 0) / 100)) + 1, 100)
    ranks = {10: "ᴇ", 30: "ᴅ", 50: "ᴄ", 70: "ʙ", 90: "ᴀ", 100: "ꜱ"}
    rank = next((r for lim, r in ranks.items() if lvl <= lim), "ꜱ")
    needed = ((lvl) ** 2) * 100 - xp
    await update.message.reply_text(f"╭────────────────╮\n│   ʟᴇᴠᴇʟ & ʀᴀɴᴋ   │\n╰────────────────╯\n\n⟡ ʟᴇᴠᴇʟ: <code>{lvl}</code>\n⟡ ʀᴀɴᴋ: <code>{rank}</code>\n⟡ xᴘ: <code>{xp}</code>\n⟡ ɴᴇᴇᴅᴇᴅ: <code>{needed}</code>", parse_mode="HTML")

async def bank_help(update: Update, context: CallbackContext):
    """Comprehensive help command for the banking system"""
    help_text = """╭─────────────────────╮
│  💰 ʙᴀɴᴋɪɴɢ ꜱʏꜱᴛᴇᴍ ɢᴜɪᴅᴇ  │
╰─────────────────────╯

<b>📊 BASIC COMMANDS</b>

⟡ <code>/bal</code> - ᴠɪᴇᴡ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ, ʙᴀɴᴋ & ᴛᴏᴛᴀʟ ʙᴀʟᴀɴᴄᴇ
⟡ <code>/cclaim</code> - ᴄʟᴀɪᴍ 2000 ɢᴏʟᴅ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
⟡ <code>/xp</code> - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ʟᴇᴠᴇʟ & ʀᴀɴᴋ

<b>🏦 BANK OPERATIONS</b>

⟡ <code>/deposit [amount]</code>
   ᴅᴇᴘᴏꜱɪᴛ ɢᴏʟᴅ ɪɴᴛᴏ ʙᴀɴᴋ
   💡 ᴇᴀʀɴꜱ 5% ɪɴᴛᴇʀᴇꜱᴛ ᴅᴀɪʟʏ
   
⟡ <code>/withdraw [amount]</code>
   ᴡɪᴛʜᴅʀᴀᴡ ɢᴏʟᴅ ғʀᴏᴍ ʙᴀɴᴋ

<b>💳 LOAN SYSTEM</b>

⟡ <code>/loan [amount]</code>
   • ᴍᴀx: <code>{max_loan:,}</code> ɢᴏʟᴅ
   • ɪɴᴛᴇʀᴇꜱᴛ: <code>{loan_int}%</code>
   • ᴅᴜʀᴀᴛɪᴏɴ: <code>{loan_days}</code> ᴅᴀʏꜱ
   • ᴘᴇɴᴀʟᴛʏ: <code>{penalty}%</code> ɪғ ᴏᴠᴇʀᴅᴜᴇ
   
⟡ <code>/repay</code>
   ʀᴇᴘᴀʏ ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ

<b>⚠️ LOAN PENALTIES</b>

ɪғ ʏᴏᴜ ᴅᴏɴ'ᴛ ʀᴇᴘᴀʏ ᴏɴ ᴛɪᴍᴇ:
1️⃣ <code>{penalty}%</code> ᴘᴇɴᴀʟᴛʏ ᴀᴅᴅᴇᴅ ᴛᴏ ʟᴏᴀɴ
2️⃣ ɢᴏʟᴅ ꜱᴇɪᴢᴇᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ & ʙᴀɴᴋ
3️⃣ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ꜱᴇɪᴢᴇᴅ (10k ɢᴏʟᴅ ᴇᴀᴄʜ)
4️⃣ ʀᴇᴍᴀɪɴɪɴɢ ᴅᴇʙᴛ ʙᴇᴄᴏᴍᴇꜱ ᴘᴇʀᴍᴀɴᴇɴᴛ

<b>💸 PAYMENTS</b>

⟡ <code>/pay [amount]</code>
   ʀᴇᴘʟʏ ᴛᴏ ᴜꜱᴇʀ'ꜱ ᴍᴇꜱꜱᴀɢᴇ
   • ᴍᴀx: <code>1,000,000</code> ɢᴏʟᴅ
   • ᴄᴏᴏʟᴅᴏᴡɴ: <code>10</code> ᴍɪɴᴜᴛᴇꜱ
   • ᴇxᴘɪʀᴇꜱ: <code>30</code> ꜱᴇᴄᴏɴᴅꜱ

<b>🎲 GAMBLING</b>

⟡ <code>/roll [amount] [odd/even]</code>
   ʙᴇᴛ ᴏɴ ᴅɪᴄᴇ ʀᴏʟʟ
   • ᴡɪɴ: +ᴀᴍᴏᴜɴᴛ & +4 xᴘ
   • ʟᴏꜱᴇ: -ᴀᴍᴏᴜɴᴛ & -2 xᴘ

<b>📬 NOTIFICATIONS</b>

⟡ <code>/notifications</code>
   ᴠɪᴇᴡ ʟᴏᴀɴ ᴄᴏʟʟᴇᴄᴛɪᴏɴ ɴᴏᴛɪᴄᴇꜱ

<b>🎯 RANK SYSTEM</b>

ʟᴠʟ 1-10: ʀᴀɴᴋ ᴇ
ʟᴠʟ 11-30: ʀᴀɴᴋ ᴅ
ʟᴠʟ 31-50: ʀᴀɴᴋ ᴄ
ʟᴠʟ 51-70: ʀᴀɴᴋ ʙ
ʟᴠʟ 71-90: ʀᴀɴᴋ ᴀ
ʟᴠʟ 91-100: ʀᴀɴᴋ ꜱ

<b>💡 PRO TIPS</b>

✓ ᴅᴇᴘᴏꜱɪᴛ ɪɴ ʙᴀɴᴋ ғᴏʀ ᴘᴀꜱꜱɪᴠᴇ ɪɴᴄᴏᴍᴇ
✓ ʀᴇᴘᴀʏ ʟᴏᴀɴꜱ ᴇᴀʀʟʏ ᴛᴏ ᴀᴠᴏɪᴅ ᴘᴇɴᴀʟᴛɪᴇꜱ
✓ ᴜꜱᴇ /bal ʙᴜᴛᴛᴏɴꜱ ғᴏʀ Qᴜɪᴄᴋ ᴀᴄᴄᴇꜱꜱ
✓ ɢᴀᴍʙʟᴇ ʀᴇꜱᴘᴏɴꜱɪʙʟʏ!

───────────────────"""
    
    help_text = help_text.format(
        max_loan=BANK_CFG['max_loan'],
        loan_int=int(BANK_CFG['loan_int'] * 100),
        loan_days=BANK_CFG['loan_days'],
        penalty=int(BANK_CFG['penalty'] * 100)
    )
    
    btns = [
        [InlineKeyboardButton("💰 ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{update.effective_user.id}")],
        [
            InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"bank_{update.effective_user.id}"),
            InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"loan_{update.effective_user.id}")
        ]
    ]
    
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def bank_example(update: Update, context: CallbackContext):
    """Show practical examples of banking system usage"""
    examples = """╭─────────────────────╮
│  📚 ʙᴀɴᴋɪɴɢ ᴇxᴀᴍᴘʟᴇꜱ  │
╰─────────────────────╯

<b>💡 SCENARIO 1: EARNING INTEREST</b>

1️⃣ <code>/bal</code> - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ
2️⃣ <code>/deposit 10000</code> - ᴅᴇᴘᴏꜱɪᴛ 10k
3️⃣ ᴡᴀɪᴛ 24 ʜᴏᴜʀꜱ
4️⃣ <code>/bal</code> - ɢᴇᴛ +500 ɪɴᴛᴇʀᴇꜱᴛ!

💰 <b>ʀᴇꜱᴜʟᴛ:</b> 10,000 → 10,500 ɢᴏʟᴅ

<b>💳 SCENARIO 2: TAKING A LOAN</b>

1️⃣ <code>/loan 50000</code> - ʙᴏʀʀᴏᴡ 50k
2️⃣ ʀᴇᴄᴇɪᴠᴇ 50k ɪɴ ᴡᴀʟʟᴇᴛ
3️⃣ ᴍᴜꜱᴛ ʀᴇᴘᴀʏ 55k (50k + 10%)
4️⃣ <code>/repay</code> - ᴡɪᴛʜɪɴ 3 ᴅᴀʏꜱ

⚠️ <b>ʟᴀᴛᴇ ʀᴇᴘᴀʏᴍᴇɴᴛ:</b>
• ᴘᴇɴᴀʟᴛʏ: +11k (20% ᴏғ 55k)
• ᴛᴏᴛᴀʟ ᴅᴜᴇ: 66k
• ᴀꜱꜱᴇᴛꜱ ꜱᴇɪᴢᴇᴅ!

<b>💸 SCENARIO 3: SENDING PAYMENT</b>

1️⃣ ʀᴇᴘʟʏ ᴛᴏ ᴜꜱᴇʀ'ꜱ ᴍᴇꜱꜱᴀɢᴇ
2️⃣ <code>/pay 5000</code>
3️⃣ ᴄʟɪᴄᴋ "✓ ᴄᴏɴꜰɪʀᴍ" ʙᴜᴛᴛᴏɴ
4️⃣ ᴡᴀɪᴛ 10 ᴍɪɴ ᴄᴏᴏʟᴅᴏᴡɴ

<b>🎲 SCENARIO 4: GAMBLING</b>

1️⃣ <code>/roll 1000 odd</code>
2️⃣ ᴅɪᴄᴇ ʀᴏʟʟꜱ 3 (ᴏᴅᴅ)
3️⃣ ʏᴏᴜ ᴡɪɴ!
4️⃣ ɢᴇᴛ +1000 ɢᴏʟᴅ & +4 xᴘ

❌ <b>ɪғ ʟᴏꜱᴛ:</b> -1000 ɢᴏʟᴅ & -2 xᴘ

<b>📊 SCENARIO 5: SMART BANKING</b>

ᴅᴀʏ 1: <code>/cclaim</code> → 2000 ɢᴏʟᴅ
ᴅᴀʏ 1: <code>/deposit 2000</code>
ᴅᴀʏ 2: <code>/cclaim</code> → 2000 ɢᴏʟᴅ
ᴅᴀʏ 2: <code>/bal</code> → 2100 ɪɴ ʙᴀɴᴋ (+100)
ᴅᴀʏ 2: <code>/deposit 2000</code> → 4100 ᴛᴏᴛᴀʟ
ᴅᴀʏ 3: ɢᴇᴛ +205 ɪɴᴛᴇʀᴇꜱᴛ!

💡 <b>ᴛɪᴘ:</b> ᴄᴏᴍᴘᴏᴜɴᴅ ɪɴᴛᴇʀᴇꜱᴛ = 📈

───────────────────
ᴜꜱᴇ /bankhelp ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ"""
    
    btns = [[InlineKeyboardButton("📖 ғᴜʟʟ ɢᴜɪᴅᴇ", callback_data=f"help_guide_{update.effective_user.id}")]]
    await update.message.reply_text(examples, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def callback_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    # Only handle banking-related callbacks
    valid_prefixes = ("bal_", "bank_", "loan_", "repay_", "clr_", "pok_", "pno_", "help_guide_")
    if not data.startswith(valid_prefixes):
        return  # Let other handlers process this callback
    
    await q.answer()
    
    # Handle help guide callback
    if data.startswith("help_guide_"):
        target = int(data.split("_")[2])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        
        help_text = """╭─────────────────────╮
│  💰 ʙᴀɴᴋɪɴɢ ꜱʏꜱᴛᴇᴍ ɢᴜɪᴅᴇ  │
╰─────────────────────╯

<b>📊 BASIC COMMANDS</b>

⟡ <code>/bal</code> - ᴠɪᴇᴡ ʙᴀʟᴀɴᴄᴇ
⟡ <code>/cclaim</code> - ᴅᴀɪʟʏ 2000 ɢᴏʟᴅ
⟡ <code>/xp</code> - ᴄʜᴇᴄᴋ ʟᴇᴠᴇʟ

<b>🏦 BANK</b>
⟡ <code>/deposit [amount]</code>
⟡ <code>/withdraw [amount]</code>
⟡ 5% ᴅᴀɪʟʹ ɪɴᴛᴇʀᴇꜱᴛ

<b>💳 LOANS</b>
⟡ <code>/loan [amount]</code> - ᴍᴀx 100k
⟡ <code>/repay</code> - ᴘᴀʏ ʙᴀᴄᴋ
⟡ 10% ɪɴᴛᴇʀᴇꜱᴛ, 3 ᴅᴀʏꜱ

<b>💸 OTHER</b>
⟡ <code>/pay [amount]</code> - ᴛʀᴀɴꜱғᴇʀ
⟡ <code>/roll [amt] [odd/even]</code>
⟡ <code>/notifications</code>

ᴜꜱᴇ /bankexample ғᴏʀ ᴇxᴀᴍᴘʟᴇꜱ"""
        
        btns = [[InlineKeyboardButton("💰 ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return

    if data.startswith("bal_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        interest = await calc_interest(uid)
        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴇʀʀᴏʀ", show_alert=True)
            return
        wallet = int(user.get('balance', 0))
        bank = int(user.get('bank', 0))
        total = wallet + bank
        loan = user.get('loan_amount', 0)
        msg = f"╭────────────────╮\n│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n╰────────────────╯\n\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n"
        if loan > 0:
            due = user.get('loan_due_date')
            if due:
                left = (due - datetime.utcnow()).total_seconds()
                msg += f"\n⚠️ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⏳ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n"
        if interest > 0:
            msg += f"\n✨ ɪɴᴛᴇʀᴇꜱᴛ: <code>+{interest}</code> ɢᴏʟᴅ"
        msg += "\n\n───────"
        btns = [[InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"bal_{uid}")], [InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"bank_{uid}"), InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"loan_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓ ʀᴇғʀᴇꜱʜᴇᴅ")

    elif data.startswith("bank_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴇʀʀᴏʀ", show_alert=True)
            return
        bank = user.get('bank', 0)
        msg = f"╭────────────────╮\n│   🏦 ʙᴀɴᴋ ᴍᴇɴᴜ   │\n╰────────────────╯\n\n⟡ ʙᴀʟᴀɴᴄᴇ: <code>{bank}</code> ɢᴏʟᴅ\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>5%</code> ᴅᴀɪʟʏ\n\nᴜꜱᴇ /deposit <amount>\nᴜꜱᴇ /withdraw <amount>"
        btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("loan_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴇʀʀᴏʀ", show_alert=True)
            return
        loan = user.get('loan_amount', 0)
        if loan > 0:
            due = user.get('loan_due_date')
            left = (due - datetime.utcnow()).total_seconds()
            msg = f"╭────────────────╮\n│   💳 ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n\nᴜꜱᴇ /repay"
        else:
            msg = f"╭────────────────╮\n│   💳 ʟᴏᴀɴ ᴍᴇɴᴜ   │\n╰────────────────╯\n\n⟡ ᴍᴀx: <code>{BANK_CFG['max_loan']}</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{int(BANK_CFG['loan_int']*100)}%</code>\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: <code>{BANK_CFG['loan_days']}</code> ᴅᴀʏꜱ\n⟡ ᴘᴇɴᴀʟᴛʏ: <code>{int(BANK_CFG['penalty']*100)}%</code>\n\nᴜꜱᴇ /loan <amount>"
        btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("repay_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴇʀʀᴏʀ", show_alert=True)
            return
        loan = user.get('loan_amount', 0)
        if loan <= 0:
            await q.answer("⊗ ɴᴏ ʟᴏᴀɴ", show_alert=True)
            return
        bal = user.get('balance', 0)
        if bal < loan:
            await q.answer(f"⊗ ɴᴇᴇᴅ {loan}, ʜᴀᴠᴇ {bal}", show_alert=True)
            return
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -loan}, '$set': {'loan_amount': 0, 'loan_due_date': None}})
        await q.edit_message_text(f"╭────────────────╮\n│   ✓ ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ɴᴇᴡ: <code>{bal - loan}</code>", parse_mode="HTML")
        await q.answer("✓ ʀᴇᴘᴀɪᴅ")

    elif data.startswith("clr_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        await user_collection.update_one({'id': uid}, {'$set': {'notifications': []}})
        await q.edit_message_text("✓ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ")
        await q.answer("✓ ᴄʟᴇᴀʀᴇᴅ")

    elif data.startswith("pok_"):
        pid = data.split("_", 1)[1]
        if pid not in pending_payments:
            await q.edit_message_text("⊗ ᴇxᴘɪʀᴇᴅ")
            return
        payment = pending_payments[pid]
        if uid != payment['sender_id']:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return
        sender = await get_user(payment['sender_id'])
        if not sender or sender.get('balance', 0) < payment['amount']:
            await q.edit_message_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
            del pending_payments[pid]
            return
        
        # Ensure recipient exists
        recipient = await get_user(payment['recipient_id'])
        if not recipient:
            await init_user(payment['recipient_id'])
        
        await user_collection.update_one({'id': payment['sender_id']}, {'$inc': {'balance': -payment['amount']}})
        await user_collection.update_one({'id': payment['recipient_id']}, {'$inc': {'balance': payment['amount']}})
        pay_cooldown[payment['sender_id']] = datetime.utcnow()
        del pending_payments[pid]
        await q.edit_message_text(f"╭────────────────╮\n│   ✓ ᴘᴀʏᴍᴇɴᴛ ꜱᴇɴᴛ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{payment['amount']}</code> ɢᴏʟᴅ", parse_mode="HTML")
        await q.answer("✓ ᴘᴀɪᴅ")

    elif data.startswith("pno_"):
        pid = data.split("_", 1)[1]
        if pid in pending_payments:
            payment = pending_payments[pid]
            if uid != payment['sender_id']:
                await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
                return
            del pending_payments[pid]
        await q.edit_message_text("⊗ ᴄᴀɴᴄᴇʟʟᴇᴅ")
        await q.answer("✗ ᴄᴀɴᴄᴇʟʟᴇᴅ")

# Set the post_init callback
application.post_init = post_init

# Register command handlers
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
application.add_handler(CommandHandler("bankhelp", bank_help, block=False))
application.add_handler(CommandHandler("bankexample", bank_example, block=False))

# Only handle banking-related callback queries using pattern matching
application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(bal_|bank_|loan_|repay_|clr_|pok_|pno_|help_guide_)", block=False))