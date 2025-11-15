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
    'penalty': 0.20,
    'char_value': {
        '🟢 Common': 5000,
        '🟣 Rare': 10000,
        '🟡 Legendary': 20000,
        '💮 Special Edition': 30000,
        '💫 Neon': 35000,
        '✨ Manga': 25000,
        '🎭 Cosplay': 28000,
        '🎐 Celestial': 45000,
        '🔮 Premium Edition': 55000,
        '💋 Erotic': 40000,
        '🌤 Summer': 22000,
        '☃️ Winter': 22000,
        '☔️ Monsoon': 22000,
        '💝 Valentine': 50000,
        '🎃 Halloween': 38000,
        '🎄 Christmas': 42000,
        '🏵 Mythic': 100000,
        '🎗 Special Events': 65000,
        '🎥 AMV': 32000,
        '👼 Tiny': 18000
    },
    'daily_deduction': 0.10
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

async def get_char_value(cid):
    cdata = await collection.find_one({'id': cid})
    if not cdata:
        return 5000
    rarity = cdata.get('rarity', '🟢 Common')
    return BANK_CFG['char_value'].get(rarity, 5000)

async def check_loans():
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
                    remaining_debt = 0

                    if bal >= total:
                        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -total}, '$set': {'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': 0}})
                        seized.append(f"💰 {total} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                    elif funds >= total:
                        await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': bank - (total - bal), 'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': 0}})
                        seized.append(f"💰 {bal} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                        seized.append(f"🏦 {total - bal} ɢᴏʟᴅ ғʀᴏᴍ ʙᴀɴᴋ")
                    else:
                        if funds > 0:
                            await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': 0}})
                            seized.append(f"💰 {funds} ɢᴏʟᴅ (ᴀʟʟ ғᴜɴᴅꜱ)")
                        
                        remaining_debt = total - funds
                        chars = user.get('characters', [])
                        
                        if chars:
                            seized_chars = []
                            for cid in chars[:]:
                                if remaining_debt <= 0:
                                    break
                                
                                char_value = await get_char_value(cid)
                                cdata = await collection.find_one({'id': cid})
                                cname = cdata.get('name', 'ᴜɴᴋɴᴏᴡɴ') if cdata else 'ᴜɴᴋɴᴏᴡɴ'
                                crarity = cdata.get('rarity', '⚪ 𝖢𝗈𝗆𝗆𝗈𝗇') if cdata else '⚪ 𝖢𝗈𝗆𝗆𝗈𝗇'
                                
                                seized.append(f"👤 {cname} ({crarity}) - ᴠᴀʟᴜᴇ: {char_value} ɢᴏʟᴅ")
                                seized_chars.append(cid)
                                remaining_debt -= char_value
                            
                            for cid in seized_chars:
                                chars.remove(cid)
                            
                            if remaining_debt <= 0:
                                await user_collection.update_one({'id': uid}, {'$set': {'characters': chars, 'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': 0}})
                            else:
                                await user_collection.update_one({'id': uid}, {'$set': {'characters': chars, 'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': remaining_debt}})
                                seized.append(f"⚠️ ʀᴇᴍᴀɪɴɪɴɢ ᴅᴇʙᴛ: {remaining_debt} ɢᴏʟᴅ")
                                seized.append(f"📉 ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ: {int(BANK_CFG['daily_deduction']*100)}% ᴏғ ᴇᴀʀɴɪɴɢꜱ")
                        else:
                            await user_collection.update_one({'id': uid}, {'$set': {'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': remaining_debt}})
                            seized.append(f"⚠️ ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ: {remaining_debt} ɢᴏʟᴅ")
                            seized.append(f"📉 ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ: {int(BANK_CFG['daily_deduction']*100)}% ᴏғ ᴇᴀʀɴɪɴɢꜱ")

                    time_str = now.strftime("%d/%m/%Y %H:%M:%S UTC")

                    msg = f"╭────────────────╮\n│   ⚠️ ʟᴏᴀɴ ᴄᴏʟʟᴇᴄᴛᴇᴅ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ᴘᴇɴᴀʟᴛʏ: <code>{penalty}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n⟡ ᴛɪᴍᴇ: <code>{time_str}</code>\n\n<b>ꜱᴇɪᴢᴇᴅ ɪᴛᴇᴍꜱ:</b>\n" + "\n".join(f"  • {i}" for i in seized)

                    await user_collection.update_one({'id': uid}, {'$push': {'notifications': {'type': 'loan_collection', 'message': msg, 'timestamp': now}}})

                    try:
                        await application.bot.send_message(
                            chat_id=uid,
                            text=msg,
                            parse_mode="HTML"
                        )
                    except Exception as dm_error:
                        print(f"ᴄᴏᴜʟᴅɴ'ᴛ ꜱᴇɴᴅ ᴅᴍ ᴛᴏ {uid}: {dm_error}")

            except Exception as e:
                print(f"ʟᴏᴀɴ ᴇʀʀᴏʀ: {e}")
            await asyncio.sleep(3600)

async def deduct_debt():
    while True:
        try:
            await asyncio.sleep(86400)
            async for user in user_collection.find({'permanent_debt': {'$gt': 0}}):
                uid = user['id']
                debt = user.get('permanent_debt', 0)
                bal = user.get('balance', 0)
                
                if bal > 0:
                    deduction = int(bal * BANK_CFG['daily_deduction'])
                    deduction = min(deduction, debt)
                    
                    new_debt = debt - deduction
                    new_bal = bal - deduction
                    
                    await user_collection.update_one(
                        {'id': uid},
                        {'$set': {'balance': new_bal, 'permanent_debt': max(0, new_debt)}}
                    )
                    
                    msg = f"╭────────────────╮\n│   💳 ᴅᴇʙᴛ ᴅᴇᴅᴜᴄᴛɪᴏɴ   │\n╰────────────────╯\n\n⟡ ᴅᴇᴅᴜᴄᴛᴇᴅ: <code>{deduction}</code> ɢᴏʟᴅ\n⟡ ʀᴇᴍᴀɪɴɪɴɢ ᴅᴇʙᴛ: <code>{new_debt}</code> ɢᴏʟᴅ\n⟡ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <code>{new_bal}</code> ɢᴏʟᴅ"
                    
                    if new_debt <= 0:
                        msg += "\n\n✅ ᴅᴇʙᴛ ғᴜʟʟʏ ʀᴇᴘᴀɪᴅ!"
                    
                    await user_collection.update_one(
                        {'id': uid},
                        {'$push': {'notifications': {'type': 'debt_deduction', 'message': msg, 'timestamp': datetime.utcnow()}}}
                    )
                    
                    try:
                        await application.bot.send_message(
                            chat_id=uid,
                            text=msg,
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                        
        except Exception as e:
            print(f"ᴅᴇʙᴛ ᴅᴇᴅᴜᴄᴛɪᴏɴ ᴇʀʀᴏʀ: {e}")

async def post_init(app):
    asyncio.create_task(check_loans())
    asyncio.create_task(deduct_debt())

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
    debt = user.get('permanent_debt', 0)
    msg = f"╭────────────────╮\n│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n╰────────────────╯\n\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n"
    if loan > 0:
        due = user.get('loan_due_date')
        if due:
            left = (due - datetime.utcnow()).total_seconds()
            msg += f"\n⚠️ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⏳ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n"
    if debt > 0:
        msg += f"\n🔴 ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ: <code>{debt}</code> ɢᴏʟᴅ\n📉 ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ: {int(BANK_CFG['daily_deduction']*100)}%\n"
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
    
    debt = user.get('permanent_debt', 0)
    if debt > 0:
        await update.message.reply_text(f"╭────────────────╮\n│   ⚠️ ᴅᴇʙᴛ ᴀᴄᴛɪᴠᴇ   │\n╰────────────────╯\n\n⟡ ᴄᴜʀʀᴇɴᴛ ᴅᴇʙᴛ: <code>{debt}</code> ɢᴏʟᴅ\n⟡ ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ: {int(BANK_CFG['daily_deduction']*100)}%\n\n⊗ ᴄʟᴇᴀʀ ʏᴏᴜʀ ᴅᴇʙᴛ ʙᴇғᴏʀᴇ ᴛᴀᴋɪɴɢ ᴀ ɴᴇᴡ ʟᴏᴀɴ", parse_mode="HTML")
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

async def clear_debt(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    debt = user.get('permanent_debt', 0)
    if debt <= 0:
        await update.message.reply_text("⊗ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴇʙᴛ")
        return
    bal = user.get('balance', 0)
    if bal < debt:
        await update.message.reply_text(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n⟡ ᴅᴇʙᴛ: <code>{debt}</code>\n⟡ ʙᴀʟᴀɴᴄᴇ: <code>{bal}</code>", parse_mode="HTML")
        return
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -debt}, '$set': {'permanent_debt': 0}})
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ᴅᴇʙᴛ ᴄʟᴇᴀʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{debt}</code> ɢᴏʟᴅ\n⟡ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <code>{bal - debt}</code>\n\n✅ ʏᴏᴜʀ ᴅᴇʙᴛ ɪꜱ ɴᴏᴡ ᴄʟᴇᴀʀ!", parse_mode="HTML")

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
        await update.message.reply_text("⊗ ᴄᴀɴɴᴏᴛ ᴘᴀʏ ʙᴏᴛꜱ")
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
    
    debt = user.get('permanent_debt', 0)
    daily_amt = 2000
    
    if debt > 0:
        deduction = int(daily_amt * BANK_CFG['daily_deduction'])
        deduction = min(deduction, debt)
        actual_amt = daily_amt - deduction
        new_debt = debt - deduction
        
        await user_collection.update_one(
            {'id': uid},
            {
                '$inc': {'balance': actual_amt},
                '$set': {'last_daily': now, 'permanent_debt': max(0, new_debt)}
            }
        )
        
        msg = f"╭────────────────╮\n│   ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ   │\n╰────────────────╯\n\n⟡ ᴇᴀʀɴᴇᴅ: <code>{daily_amt}</code> ɢᴏʟᴅ\n⟡ ᴅᴇʙᴛ ᴅᴇᴅᴜᴄᴛɪᴏɴ: <code>-{deduction}</code> ɢᴏʟᴅ\n⟡ ʀᴇᴄᴇɪᴠᴇᴅ: <code>{actual_amt}</code> ɢᴏʟᴅ\n\n🔴 ʀᴇᴍᴀɪɴɪɴɢ ᴅᴇʙᴛ: <code>{new_debt}</code> ɢᴏʟᴅ"
        
        if new_debt <= 0:
            msg += "\n\n✅ ᴅᴇʙᴛ ғᴜʟʟʏ ᴄʟᴇᴀʀᴇᴅ!"
    else:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': daily_amt}, '$set': {'last_daily': now}})
        msg = f"╭────────────────╮\n│   ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ   │\n╰────────────────╯\n\n⟡ ᴄʟᴀɪᴍᴇᴅ: <code>{daily_amt}</code> ɢᴏʟᴅ"
    
    await update.message.reply_text(msg, parse_mode="HTML")

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
    help_text = f"""╭─────────────────────╮
│  💰 ʙᴀɴᴋɪɴɢ ꜱʏꜱᴛᴇᴍ ɢᴜɪᴅᴇ  │
╰─────────────────────╯

<b>📊 BASIC COMMANDS</b>

⟡ <code>/bal</code> - ᴠɪᴇᴡ ʙᴀʟᴀɴᴄᴇ, ʟᴏᴀɴ & ᴅᴇʙᴛ
⟡ <code>/cclaim</code> - ᴄʟᴀɪᴍ 2000 ɢᴏʟᴅ ᴅᴀɪʟʏ
⟡ <code>/xp</code> - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ʟᴇᴠᴇʟ & ʀᴀɴᴋ

<b>🏦 BANK OPERATIONS</b>

⟡ <code>/deposit [amount]</code>
   ᴅᴇᴘᴏꜱɪᴛ ɢᴏʟᴅ ɪɴᴛᴏ ʙᴀɴᴋ
   💡 ᴇᴀʀɴꜱ 5% ɪɴᴛᴇʀᴇꜱᴛ ᴅᴀɪʟʏ
   
⟡ <code>/withdraw [amount]</code>
   ᴡɪᴛʜᴅʀᴀᴡ ɢᴏʟᴅ ғʀᴏᴍ ʙᴀɴᴋ

<b>💳 LOAN SYSTEM</b>

⟡ <code>/loan [amount]</code>
   • ᴍᴀx: <code>{BANK_CFG['max_loan']:,}</code> ɢᴏʟᴅ
   • ɪɴᴛᴇʀᴇꜱᴛ: <code>{int(BANK_CFG['loan_int']*100)}%</code>
   • ᴅᴜʀᴀᴛɪᴏɴ: <code>{BANK_CFG['loan_days']}</code> ᴅᴀʏꜱ
   • ᴘᴇɴᴀʟᴛʏ: <code>{int(BANK_CFG['penalty']*100)}%</code> ɪғ ᴏᴠᴇʀᴅᴜᴇ
   
⟡ <code>/repay</code>
   ʀᴇᴘᴀʏ ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ

⟡ <code>/cleardebt</code>
   ᴘᴀʏ ᴏғғ ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ

<b>⚠️ LOAN PENALTIES</b>

ɪғ ʏᴏᴜ ᴅᴏɴ'ᴛ ʀᴇᴘᴀʏ ᴏɴ ᴛɪᴍᴇ:
1️⃣ <code>{int(BANK_CFG['penalty']*100)}%</code> ᴘᴇɴᴀʟᴛʏ ᴀᴅᴅᴇᴅ
2️⃣ ɢᴏʟᴅ ꜱᴇɪᴢᴇᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ & ʙᴀɴᴋ
3️⃣ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ꜱᴇɪᴢᴇᴅ ʙʏ ʀᴀʀɪᴛʏ ᴠᴀʟᴜᴇ
4️⃣ ʀᴇᴍᴀɪɴɪɴɢ → ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ

<b>🔴 PERMANENT DEBT</b>

⟡ <code>{int(BANK_CFG['daily_deduction']*100)}%</code> ᴏғ ᴀʟʟ ᴇᴀʀɴɪɴɢꜱ ᴅᴇᴅᴜᴄᴛᴇᴅ
⟡ ᴀᴜᴛᴏᴍᴀᴛɪᴄ ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ
⟡ ᴄᴀɴɴᴏᴛ ᴛᴀᴋᴇ ɴᴇᴡ ʟᴏᴀɴꜱ ᴡɪᴛʜ ᴅᴇʙᴛ
⟡ ᴜꜱᴇ /cleardebt ᴛᴏ ᴘᴀʏ ᴏғғ

<b>💎 CHARACTER VALUES</b>

🟢 ᴄᴏᴍᴍᴏɴ: 5,000 ɢᴏʟᴅ
🟣 ʀᴀʀᴇ: 10,000 ɢᴏʟᴅ
👼 ᴛɪɴʏ: 18,000 ɢᴏʟᴅ
🟡 ʟᴇɢᴇɴᴅᴀʀʏ: 20,000 ɢᴏʟᴅ
🌤 ꜱᴇᴀꜱᴏɴᴀʟ: 22,000 ɢᴏʟᴅ
✨ ᴍᴀɴɢᴀ: 25,000 ɢᴏʟᴅ
🎭 ᴄᴏꜱᴘʟᴀʏ: 28,000 ɢᴏʟᴅ
💮 ꜱᴘᴇᴄɪᴀʟ ᴇᴅ: 30,000 ɢᴏʟᴅ
🎥 ᴀᴍᴠ: 32,000 ɢᴏʟᴅ
💫 ɴᴇᴏɴ: 35,000 ɢᴏʟᴅ
🎃 ʜᴀʟʟᴏᴡᴇᴇɴ: 38,000 ɢᴏʟᴅ
💋 ᴇʀᴏᴛɪᴄ: 40,000 ɢᴏʟᴅ
🎄 ᴄʜʀɪꜱᴛᴍᴀꜱ: 42,000 ɢᴏʟᴅ
🎐 ᴄᴇʟᴇꜱᴛɪᴀʟ: 45,000 ɢᴏʟᴅ
💝 ᴠᴀʟᴇɴᴛɪɴᴇ: 50,000 ɢᴏʟᴅ
🔮 ᴘʀᴇᴍɪᴜᴍ ᴇᴅ: 55,000 ɢᴏʟᴅ
🎗 ꜱᴘᴇᴄɪᴀʟ ᴇᴠᴇɴᴛꜱ: 65,000 ɢᴏʟᴅ
🏵 ᴍʏᴛʜɪᴄ: 100,000 ɢᴏʟᴅ

<b>💸 PAYMENTS</b>

⟡ <code>/pay [amount]</code>
   ʀᴇᴘʟʏ ᴛᴏ ᴜꜱᴇʀ'ꜱ ᴍᴇꜱꜱᴀɢᴇ
   • ᴍᴀx: <code>1,000,000</code> ɢᴏʟᴅ
   • ᴄᴏᴏʟᴅᴏᴡɴ: <code>10</code> ᴍɪɴᴜᴛᴇꜱ
   • ᴇxᴘɪʀᴇꜱ: <code>30</code> ꜱᴇᴄᴏɴᴅꜱ

<b>📬 OTHER</b>

⟡ <code>/notifications</code>
   ᴠɪᴇᴡ ᴄᴏʟʟᴇᴄᴛɪᴏɴ ɴᴏᴛɪᴄᴇꜱ

<b>💡 PRO TIPS</b>

✓ ᴅᴇᴘᴏꜱɪᴛ ɪɴ ʙᴀɴᴋ ғᴏʀ ᴘᴀꜱꜱɪᴠᴇ ɪɴᴄᴏᴍᴇ
✓ ʀᴇᴘᴀʏ ʟᴏᴀɴꜱ ᴇᴀʀʟʏ ᴛᴏ ᴀᴠᴏɪᴅ ᴘᴇɴᴀʟᴛɪᴇꜱ
✓ ᴄʟᴇᴀʀ ᴅᴇʙᴛ ғᴀꜱᴛ - ɪᴛ ᴛᴀᴋᴇꜱ ʏᴏᴜʀ ᴇᴀʀɴɪɴɢꜱ
✓ ʜɪɢʜᴇʀ ʀᴀʀɪᴛʏ = ʜɪɢʜᴇʀ ᴠᴀʟᴜᴇ

───────────────────"""

    btns = [
        [InlineKeyboardButton("💰 ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{update.effective_user.id}")],
        [
            InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"bank_{update.effective_user.id}"),
            InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"loan_{update.effective_user.id}")
        ]
    ]

    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def bank_example(update: Update, context: CallbackContext):
    examples = f"""╭─────────────────────╮
│  📚 ʙᴀɴᴋɪɴɢ ᴇxᴀᴍᴘʟᴇꜱ  │
╰─────────────────────╯

<b>💡 SCENARIO 1: EARNING INTEREST</b>

1️⃣ <code>/bal</code> - ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ
2️⃣ <code>/deposit 10000</code> - ᴅᴇᴘᴏꜱɪᴛ 10k
3️⃣ ᴡᴀɪᴛ 24 ʜᴏᴜʀꜱ
4️⃣ <code>/bal</code> - ɢᴇᴛ +500 ɪɴᴛᴇʀᴇꜱᴛ!

💰 <b>ʀᴇꜱᴜʟᴛ:</b> 10,000 → 10,500 ɢᴏʟᴅ

<b>💳 SCENARIO 2: LOAN REPAYMENT</b>

1️⃣ <code>/loan 50000</code> - ʙᴏʀʀᴏᴡ 50k
2️⃣ ʀᴇᴄᴇɪᴠᴇ 50k + ᴏᴡᴇ 55k (10%)
3️⃣ <code>/repay</code> - ᴡɪᴛʜɪɴ 3 ᴅᴀʏꜱ
4️⃣ ✅ ʟᴏᴀɴ ᴄʟᴇᴀʀᴇᴅ!

<b>⚠️ SCENARIO 3: LATE PAYMENT</b>

1️⃣ ʟᴏᴀɴ: 55k, ʏᴏᴜ ʜᴀᴠᴇ: 10k ɢᴏʟᴅ
2️⃣ ᴘᴇɴᴀʟᴛʏ: +11k (20%) = 66k ᴛᴏᴛᴀʟ
3️⃣ ꜱᴇɪᴢᴇᴅ: 10k ɢᴏʟᴅ
4️⃣ ᴅᴇʙᴛ: 56k ʀᴇᴍᴀɪɴɪɴɢ
5️⃣ ꜱᴇɪᴢᴇᴅ: 6 ᴄʜᴀʀᴀᴄᴛᴇʀꜱ
   • 2x ʟᴇɢᴇɴᴅᴀʀʏ (40k)
   • 2x ʀᴀʀᴇ (20k)
6️⃣ ʀᴇᴍᴀɪɴɪɴɢ: 6k → ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ

<b>🔴 SCENARIO 4: PERMANENT DEBT</b>

ᴅᴀʏ 1: ᴅᴇʙᴛ = 10,000 ɢᴏʟᴅ
ᴅᴀʏ 2: <code>/cclaim</code> → 2000 ɢᴏʟᴅ
       ᴅᴇᴅᴜᴄᴛɪᴏɴ: -200 (10%)
       ʀᴇᴄᴇɪᴠᴇᴅ: 1800 ɢᴏʟᴅ
       ᴅᴇʙᴛ: 9,800 ɢᴏʟᴅ
ᴅᴀʏ 3: ᴇᴀʀɴ 5000 ɢᴏʟᴅ
       ᴅᴇᴅᴜᴄᴛɪᴏɴ: -500 (10%)
       ᴅᴇʙᴛ: 9,300 ɢᴏʟᴅ
ᴅᴀʏ 10: <code>/cleardebt</code> → ᴘᴀʏ 9,300
        ✅ ᴅᴇʙᴛ ᴄʟᴇᴀʀᴇᴅ!

<b>💸 SCENARIO 5: SMART BANKING</b>

ᴅᴀʏ 1: <code>/cclaim</code> → 2000
       <code>/deposit 2000</code>
ᴅᴀʏ 2: ʙᴀɴᴋ: 2100 (+100 interest)
       <code>/cclaim</code> → 2000
       <code>/deposit 2000</code>
ᴅᴀʏ 3: ʙᴀɴᴋ: 4305 (+205 interest)
       💰 ᴄᴏᴍᴘᴏᴜɴᴅ ɪɴᴛᴇʀᴇꜱᴛ = 📈

─────────────────────
ᴜꜱᴇ /bankhelp ғᴏʀ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ"""

    btns = [[InlineKeyboardButton("📖 ғᴜʟʟ ɢᴜɪᴅᴇ", callback_data=f"help_guide_{update.effective_user.id}")]]
    await update.message.reply_text(examples, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def callback_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    valid_prefixes = ("bal_", "bank_", "loan_", "repay_", "clr_", "pok_", "pno_", "help_guide_")
    if not data.startswith(valid_prefixes):
        return

    await q.answer()

    if data.startswith("help_guide_"):
        target = int(data.split("_")[2])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        help_text = f"""╭─────────────────────╮
│  💰 ʙᴀɴᴋɪɴɢ ꜱʏꜱᴛᴇᴍ ɢᴜɪᴅᴇ  │
╰─────────────────────╯

<b>📊 BASIC COMMANDS</b>

⟡ <code>/bal</code> - ᴠɪᴇᴡ ʙᴀʟᴀɴᴄᴇ
⟡ <code>/cclaim</code> - ᴅᴀɪʟʏ 2000 ɢᴏʟᴅ
⟡ <code>/xp</code> - ᴄʜᴇᴄᴋ ʟᴇᴠᴇʟ

<b>🏦 BANK</b>
⟡ <code>/deposit [amount]</code>
⟡ <code>/withdraw [amount]</code>
⟡ 5% ᴅᴀɪʟʏ ɪɴᴛᴇʀᴇꜱᴛ

<b>💳 LOANS</b>
⟡ <code>/loan [amount]</code> - ᴍᴀx 100k
⟡ <code>/repay</code> - ᴘᴀʏ ʙᴀᴄᴋ
⟡ <code>/cleardebt</code> - ᴄʟᴇᴀʀ ᴅᴇʙᴛ
⟡ 10% ɪɴᴛᴇʀᴇꜱᴛ, 3 ᴅᴀʏꜱ

<b>🔴 DEBT SYSTEM</b>
⟡ 10% ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ
⟡ ᴄʜᴀʀꜱ ꜱᴇɪᴢᴇᴅ ʙʏ ᴠᴀʟᴜᴇ
⟡ ᴀᴜᴛᴏ-ʀᴇᴘᴀʏᴍᴇɴᴛ

<b>💸 OTHER</b>
⟡ <code>/pay [amount]</code> - ᴛʀᴀɴꜱғᴇʀ
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

        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ", show_alert=True)
            return

        interest = await calc_interest(uid)
        user = await get_user(uid)
        wallet = int(user.get('balance', 0))
        bank = int(user.get('bank', 0))
        total = wallet + bank
        loan = user.get('loan_amount', 0)
        debt = user.get('permanent_debt', 0)
        msg = f"╭────────────────╮\n│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n╰────────────────╯\n\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n⟡ ʙᴀɴᴋ: <code>{bank}</code> ɢᴏʟᴅ\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code> ɢᴏʟᴅ\n"
        if loan > 0:
            due = user.get('loan_due_date')
            if due:
                left = (due - datetime.utcnow()).total_seconds()
                msg += f"\n⚠️ ʟᴏᴀɴ: <code>{loan}</code> ɢᴏʟᴅ\n⏳ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n"
        if debt > 0:
            msg += f"\n🔴 ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ: <code>{debt}</code> ɢᴏʟᴅ\n📉 ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ: {int(BANK_CFG['daily_deduction']*100)}%\n"
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
            await q.answer("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ", show_alert=True)
            return

        bank = user.get('bank', 0)
        wallet = user.get('balance', 0)
        msg = f"╭────────────────╮\n│   🏦 ʙᴀɴᴋ ᴍᴇɴᴜ   │\n╰────────────────╯\n\n⟡ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ: <code>{bank}</code> ɢᴏʟᴅ\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code> ɢᴏʟᴅ\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>5%</code> ᴅᴀɪʟʏ\n\n<b>ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n• /deposit <amount> - ᴅᴇᴘᴏꜱɪᴛ ɢᴏʟᴅ\n• /withdraw <amount> - ᴡɪᴛʜᴅʀᴀᴡ ɢᴏʟᴅ\n\n💡 <b>ᴛɪᴘ:</b> ᴅᴇᴘᴏꜱɪᴛ ɢᴏʟᴅ ᴛᴏ ᴇᴀʀɴ ɪɴᴛᴇʀᴇꜱᴛ!"
        btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("🏦 ʙᴀɴᴋ ᴍᴇɴᴜ")

    elif data.startswith("loan_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ", show_alert=True)
            return

        debt = user.get('permanent_debt', 0)
        if debt > 0:
            msg = f"╭────────────────╮\n│   🔴 ᴅᴇʙᴛ ᴀᴄᴛɪᴠᴇ   │\n╰────────────────╯\n\n⟡ ᴄᴜʀʀᴇɴᴛ ᴅᴇʙᴛ: <code>{debt}</code> ɢᴏʟᴅ\n⟡ ᴅᴀɪʟʏ ᴅᴇᴅᴜᴄᴛɪᴏɴ: {int(BANK_CFG['daily_deduction']*100)}%\n\n⊗ ᴄʟᴇᴀʀ ʏᴏᴜʀ ᴅᴇʙᴛ ʙᴇғᴏʀᴇ ᴛᴀᴋɪɴɢ ᴀ ɴᴇᴡ ʟᴏᴀɴ\n\n<b>ᴄᴏᴍᴍᴀɴᴅ:</b>\n• /cleardebt - ᴘᴀʏ ᴏғғ ᴅᴇʙᴛ"
            btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
            await q.answer("⚠️ ᴅᴇʙᴛ ᴀᴄᴛɪᴠᴇ", show_alert=True)
            return

        loan = user.get('loan_amount', 0)
        if loan > 0:
            due = user.get('loan_due_date')
            left = (due - datetime.utcnow()).total_seconds()
            msg = f"╭────────────────╮\n│   💳 ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ ᴀᴍᴏᴜɴᴛ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ᴅᴜᴇ ɪɴ: {fmt_time(left)}\n\n<b>ᴄᴏᴍᴍᴀɴᴅ:</b>\n• /repay - ʀᴇᴘᴀʏ ʟᴏᴀɴ\n\n⚠️ <b>ᴡᴀʀɴɪɴɢ:</b> ʟᴀᴛᴇ ᴘᴀʏᴍᴇɴᴛ = 20% ᴘᴇɴᴀʟᴛʏ!"
            btns = [[InlineKeyboardButton("💰 ʀᴇᴘᴀʏ ɴᴏᴡ", callback_data=f"repay_{uid}")], [InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
            await q.answer("💳 ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ")
        else:
            msg = f"╭────────────────╮\n│   💳 ʟᴏᴀɴ ᴍᴇɴᴜ   │\n╰────────────────╯\n\n⟡ ᴍᴀx ʟᴏᴀɴ: <code>{BANK_CFG['max_loan']:,}</code> ɢᴏʟᴅ\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{int(BANK_CFG['loan_int']*100)}%</code>\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: <code>{BANK_CFG['loan_days']}</code> ᴅᴀʏꜱ\n⟡ ᴘᴇɴᴀʟᴛʏ: <code>{int(BANK_CFG['penalty']*100)}%</code> ɪғ ᴏᴠᴇʀᴅᴜᴇ\n\n<b>ᴄᴏᴍᴍᴀɴᴅ:</b>\n• /loan <amount> - ᴛᴀᴋᴇ ᴀ ʟᴏᴀɴ\n\n💡 <b>ᴇxᴀᴍᴘʟᴇ:</b> /loan 50000"
            btns = [[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
            await q.answer("⊗ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ", show_alert=True)

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
            await q.answer("⊗ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ", show_alert=True)
            return

        bal = user.get('balance', 0)
        if bal < loan:
            await q.answer(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\nɴᴇᴇᴅᴇᴅ: {loan}\nʏᴏᴜʀꜱ: {bal}", show_alert=True)
            return

        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -loan}, '$set': {'loan_amount': 0, 'loan_due_date': None}})
        new_bal = bal - loan
        msg = f"╭────────────────╮\n│   ✓ ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{loan}</code> ɢᴏʟᴅ\n⟡ ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ: <code>{new_bal}</code> ɢᴏʟᴅ\n\n✅ ʟᴏᴀɴ ᴄʟᴇᴀʀᴇᴅ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ!"
        btns = [[InlineKeyboardButton("💰 ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓ ʀᴇᴘᴀɪᴅ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ!")

    elif data.startswith("clr_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        await user_collection.update_one({'id': uid}, {'$set': {'notifications': []}})
        await q.edit_message_text("╭────────────────╮\n│   ✓ ᴄʟᴇᴀʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴀʟʟ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ")
        await q.answer("✓ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ")

    elif data.startswith("pok_"):
        pid = data.split("_", 1)[1]
        if pid not in pending_payments:
            await q.edit_message_text("╭────────────────╮\n│   ⊗ ᴇxᴘɪʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀʏᴍᴇɴᴛ ʀᴇǫᴜᴇꜱᴛ ᴇxᴘɪʀᴇᴅ\n⟡ ᴘʟᴇᴀꜱᴇ ᴛʀʏ ᴀɢᴀɪɴ")
            await q.answer("⊗ ᴘᴀʏᴍᴇɴᴛ ᴇxᴘɪʀᴇᴅ", show_alert=True)
            return

        payment = pending_payments[pid]
        if uid != payment['sender_id']:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        sender = await get_user(payment['sender_id'])
        if not sender or sender.get('balance', 0) < payment['amount']:
            await q.edit_message_text("╭────────────────╮\n│   ⊗ ғᴀɪʟᴇᴅ   │\n╰────────────────╯\n\n⟡ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n⟡ ᴘᴀʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ")
            del pending_payments[pid]
            await q.answer("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ", show_alert=True)
            return

        recipient = await get_user(payment['recipient_id'])
        if not recipient:
            await init_user(payment['recipient_id'])

        await user_collection.update_one({'id': payment['sender_id']}, {'$inc': {'balance': -payment['amount']}})
        await user_collection.update_one({'id': payment['recipient_id']}, {'$inc': {'balance': payment['amount']}})
        pay_cooldown[payment['sender_id']] = datetime.utcnow()

        try:
            recipient_user = await context.bot.get_chat(payment['recipient_id'])
            recipient_name = recipient_user.first_name
        except:
            recipient_name = "ᴜɴᴋɴᴏᴡɴ"

        del pending_payments[pid]

        msg = f"╭────────────────╮\n│   ✓ ᴘᴀʏᴍᴇɴᴛ ꜱᴇɴᴛ   │\n╰────────────────╯\n\n⟡ ʀᴇᴄɪᴘɪᴇɴᴛ: <b>{recipient_name}</b>\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{payment['amount']}</code> ɢᴏʟᴅ\n⟡ ꜱᴛᴀᴛᴜꜱ: <b>ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n\n✅ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴ ꜱᴜᴄᴄᴇꜱꜱғᴜʟ!"
        btns = [[InlineKeyboardButton("💰 ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓ ᴘᴀʏᴍᴇɴᴛ ꜱᴜᴄᴄᴇꜱꜱғᴜʟ!")

    elif data.startswith("pno_"):
        pid = data.split("_", 1)[1]
        if pid in pending_payments:
            payment = pending_payments[pid]
            if uid != payment['sender_id']:
                await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
                return
            del pending_payments[pid]

        await q.edit_message_text("╭────────────────╮\n│   ✗ ᴄᴀɴᴄᴇʟʟᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ\n⟡ ɴᴏ ɢᴏʟᴅ ᴡᴀꜱ ᴛʀᴀɴꜱғᴇʀʀᴇᴅ")
        await q.answer("✗ ᴘᴀʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ")

application.post_init = post_init

application.add_handler(CommandHandler("bal", balance, block=False))
application.add_handler(CommandHandler("deposit", deposit, block=False))
application.add_handler(CommandHandler("withdraw", withdraw, block=False))
application.add_handler(CommandHandler("loan", loan_cmd, block=False))
application.add_handler(CommandHandler("repay", repay, block=False))
application.add_handler(CommandHandler("cleardebt", clear_debt, block=False))
application.add_handler(CommandHandler("notifications", notifications, block=False))
application.add_handler(CommandHandler("pay", pay, block=False))
application.add_handler(CommandHandler("cclaim", daily, block=False))
application.add_handler(CommandHandler("xp", xp_cmd, block=False))
application.add_handler(CommandHandler("bankhelp", bank_help, block=False))
application.add_handler(CommandHandler("bankexample", bank_example, block=False))

application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(bal_|bank_|loan_|repay_|clr_|pok_|pno_|help_guide_)", block=False))