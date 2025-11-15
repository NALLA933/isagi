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
    'premium_int_rate': 0.06,
    'loan_int': 0.10,
    'max_loan': 100000,
    'max_premium_loan': 200000,
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
    'daily_deduction': 0.10,
    'fd_rates': {7: 0.07, 15: 0.10, 30: 0.15},
    'fd_penalty': 0.03,
    'emergency_loan_int': 0.15,
    'insurance_premium': 500,
    'premium_fee': 5000,
    'premium_daily_bonus': 500
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
        'characters': [],
        'transactions': [],
        'credit_score': 700,
        'fixed_deposits': [],
        'investments': [],
        'savings_goals': [],
        'insurance': {'char': False, 'deposit': False, 'last_premium': None},
        'premium': False,
        'premium_expiry': None,
        'referrals': [],
        'achievements': [],
        'pin': None,
        'frozen': False,
        'recurring_deposit': {'active': False, 'amount': 0, 'frequency': 'daily', 'last_deposit': None},
        'loan_history': [],
        'spending_limit': {'daily': 50000, 'used': 0, 'reset_date': None}
    })

async def add_transaction(uid, ttype, amount, desc=""):
    await user_collection.update_one(
        {'id': uid},
        {'$push': {'transactions': {
            'type': ttype,
            'amount': amount,
            'description': desc,
            'timestamp': datetime.utcnow()
        }}}
    )
    transactions = (await get_user(uid)).get('transactions', [])
    if len(transactions) > 100:
        await user_collection.update_one(
            {'id': uid},
            {'$pop': {'transactions': -1}}
        )

async def update_credit_score(uid, points):
    user = await get_user(uid)
    current = user.get('credit_score', 700)
    new_score = max(300, min(900, current + points))
    await user_collection.update_one({'id': uid}, {'$set': {'credit_score': new_score}})
    return new_score

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
    
    rate = BANK_CFG['premium_int_rate'] if user.get('premium') else BANK_CFG['int_rate']
    interest = int(bank * rate)
    await user_collection.update_one({'id': uid}, {'$inc': {'bank': interest}, '$set': {'last_interest': now}})
    await add_transaction(uid, 'interest', interest, f"ᴅᴀɪʟʏ ɪɴᴛᴇʀᴇꜱᴛ {int(rate*100)}%")
    return interest

async def get_char_value(cid):
    cdata = await collection.find_one({'id': cid})
    if not cdata:
        return 5000
    rarity = cdata.get('rarity', '🟢 Common')
    return BANK_CFG['char_value'].get(rarity, 5000)

async def check_fd_maturity():
    while True:
        try:
            await asyncio.sleep(3600)
            now = datetime.utcnow()
            async for user in user_collection.find({'fixed_deposits': {'$exists': True, '$ne': []}}):
                uid = user['id']
                fds = user.get('fixed_deposits', [])
                for fd in fds[:]:
                    if fd['maturity_date'] <= now:
                        principal = fd['amount']
                        interest = fd['interest']
                        total = principal + interest
                        
                        fds.remove(fd)
                        await user_collection.update_one(
                            {'id': uid},
                            {'$set': {'fixed_deposits': fds}, '$inc': {'bank': total}}
                        )
                        await add_transaction(uid, 'fd_maturity', total, f"ꜰᴅ ᴍᴀᴛᴜʀᴇᴅ: {fd['days']} ᴅᴀʏꜱ")
                        
                        msg = f"╭────────────────╮\n│   ✓ ꜰᴅ ᴍᴀᴛᴜʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘʀɪɴᴄɪᴘᴀʟ: <code>{principal}</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{interest}</code>\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code>\n\n✅ ᴄʀᴇᴅɪᴛᴇᴅ ᴛᴏ ʙᴀɴᴋ"
                        
                        await user_collection.update_one(
                            {'id': uid},
                            {'$push': {'notifications': {'type': 'fd_maturity', 'message': msg, 'timestamp': now}}}
                        )
                        
                        try:
                            await application.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                        except:
                            pass
        except Exception as e:
            print(f"ꜰᴅ ᴇʀʀᴏʀ: {e}")

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
                    
                    has_insurance = user.get('insurance', {}).get('deposit', False)
                    if has_insurance:
                        covered = min(total, 50000)
                        total -= covered
                        await user_collection.update_one(
                            {'id': uid},
                            {'$set': {'insurance.deposit': False}}
                        )
                    
                    funds = bal + bank
                    seized = []
                    remaining_debt = 0

                    if bal >= total:
                        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -total}, '$set': {'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': 0}})
                        seized.append(f"💰 {total} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                        await update_credit_score(uid, -50)
                    elif funds >= total:
                        await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': bank - (total - bal), 'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': 0}})
                        seized.append(f"💰 {bal} ɢᴏʟᴅ ғʀᴏᴍ ᴡᴀʟʟᴇᴛ")
                        seized.append(f"🏦 {total - bal} ɢᴏʟᴅ ғʀᴏᴍ ʙᴀɴᴋ")
                        await update_credit_score(uid, -50)
                    else:
                        if funds > 0:
                            await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': 0}})
                            seized.append(f"💰 {funds} ɢᴏʟᴅ (ᴀʟʟ ғᴜɴᴅꜱ)")
                        
                        remaining_debt = total - funds
                        chars = user.get('characters', [])
                        has_char_insurance = user.get('insurance', {}).get('char', False)
                        
                        if chars and not has_char_insurance:
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
                        else:
                            if has_char_insurance:
                                seized.append("🛡️ ᴄʜᴀʀᴀᴄᴛᴇʀꜱ ᴘʀᴏᴛᴇᴄᴛᴇᴅ")
                                await user_collection.update_one({'id': uid}, {'$set': {'insurance.char': False}})
                            await user_collection.update_one({'id': uid}, {'$set': {'loan_amount': 0, 'loan_due_date': None, 'permanent_debt': remaining_debt}})
                            seized.append(f"⚠️ ᴘᴇʀᴍᴀɴᴇɴᴛ ᴅᴇʙᴛ: {remaining_debt} ɢᴏʟᴅ")
                        
                        await update_credit_score(uid, -100)

                    await user_collection.update_one(
                        {'id': uid},
                        {'$push': {'loan_history': {'amount': loan, 'penalty': penalty, 'date': now, 'status': 'defaulted'}}}
                    )

                    time_str = now.strftime("%d/%m/%Y %H:%M UTC")
                    msg = f"╭────────────────╮\n│   ⚠️ ʟᴏᴀɴ ᴄᴏʟʟᴇᴄᴛᴇᴅ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{loan}</code>\n⟡ ᴘᴇɴᴀʟᴛʏ: <code>{penalty}</code>\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code>\n⟡ ᴛɪᴍᴇ: <code>{time_str}</code>\n\n<b>ꜱᴇɪᴢᴇᴅ:</b>\n" + "\n".join(f"• {i}" for i in seized)

                    await user_collection.update_one({'id': uid}, {'$push': {'notifications': {'type': 'loan_collection', 'message': msg, 'timestamp': now}}})

                    try:
                        await application.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                    except:
                        pass

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
                    await add_transaction(uid, 'debt_deduction', -deduction, "ᴅᴀɪʟʏ ᴅᴇʙᴛ ᴅᴇᴅᴜᴄᴛɪᴏɴ")
                    
                    msg = f"╭────────────────╮\n│   💳 ᴅᴇʙᴛ ᴅᴇᴅᴜᴄᴛɪᴏɴ   │\n╰────────────────╯\n\n⟡ ᴅᴇᴅᴜᴄᴛᴇᴅ: <code>{deduction}</code>\n⟡ ʀᴇᴍᴀɪɴɪɴɢ: <code>{new_debt}</code>\n⟡ ʙᴀʟᴀɴᴄᴇ: <code>{new_bal}</code>"
                    
                    if new_debt <= 0:
                        msg += "\n\n✅ ᴅᴇʙᴛ ᴄʟᴇᴀʀᴇᴅ!"
                        await update_credit_score(uid, 50)
                    
                    try:
                        await application.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                    except:
                        pass
                        
        except Exception as e:
            print(f"ᴅᴇʙᴛ ᴇʀʀᴏʀ: {e}")

async def check_insurance():
    while True:
        try:
            await asyncio.sleep(86400)
            now = datetime.utcnow()
            async for user in user_collection.find({'$or': [{'insurance.char': True}, {'insurance.deposit': True}]}):
                uid = user['id']
                insurance = user.get('insurance', {})
                last_premium = insurance.get('last_premium')
                
                if last_premium:
                    days_since = (now - last_premium).days
                    if days_since >= 30:
                        bal = user.get('balance', 0)
                        premium = BANK_CFG['insurance_premium']
                        
                        if bal >= premium:
                            await user_collection.update_one(
                                {'id': uid},
                                {'$inc': {'balance': -premium}, '$set': {'insurance.last_premium': now}}
                            )
                            await add_transaction(uid, 'insurance', -premium, "ᴍᴏɴᴛʜʟʏ ᴘʀᴇᴍɪᴜᴍ")
                        else:
                            await user_collection.update_one(
                                {'id': uid},
                                {'$set': {'insurance.char': False, 'insurance.deposit': False}}
                            )
        except Exception as e:
            print(f"ɪɴꜱᴜʀᴀɴᴄᴇ ᴇʀʀᴏʀ: {e}")

async def check_recurring_deposits():
    while True:
        try:
            await asyncio.sleep(3600)
            now = datetime.utcnow()
            async for user in user_collection.find({'recurring_deposit.active': True}):
                uid = user['id']
                rd = user.get('recurring_deposit', {})
                last_deposit = rd.get('last_deposit')
                amount = rd.get('amount', 0)
                frequency = rd.get('frequency', 'daily')
                
                should_deposit = False
                if not last_deposit:
                    should_deposit = True
                elif frequency == 'daily' and (now - last_deposit).days >= 1:
                    should_deposit = True
                elif frequency == 'weekly' and (now - last_deposit).days >= 7:
                    should_deposit = True
                
                if should_deposit:
                    bal = user.get('balance', 0)
                    if bal >= amount:
                        await user_collection.update_one(
                            {'id': uid},
                            {
                                '$inc': {'balance': -amount, 'bank': amount},
                                '$set': {'recurring_deposit.last_deposit': now}
                            }
                        )
                        await add_transaction(uid, 'recurring_deposit', amount, f"ᴀᴜᴛᴏ ({frequency})")
                    else:
                        await user_collection.update_one(
                            {'id': uid},
                            {'$set': {'recurring_deposit.active': False}}
                        )
        except Exception as e:
            print(f"ʀᴅ ᴇʀʀᴏʀ: {e}")

async def process_investments():
    while True:
        try:
            await asyncio.sleep(86400)
            async for user in user_collection.find({'investments': {'$exists': True, '$ne': []}}):
                uid = user['id']
                investments = user.get('investments', [])
                
                for inv in investments:
                    if inv['type'] == 'stock':
                        change = random.uniform(-0.15, 0.20)
                        inv['value'] = int(inv['value'] * (1 + change))
                    elif inv['type'] == 'bond':
                        inv['value'] = int(inv['value'] * 1.005)
                    elif inv['type'] == 'mutual_fund':
                        risk = inv.get('risk', 'medium')
                        if risk == 'low':
                            change = random.uniform(-0.05, 0.08)
                        elif risk == 'medium':
                            change = random.uniform(-0.10, 0.15)
                        else:
                            change = random.uniform(-0.20, 0.30)
                        inv['value'] = int(inv['value'] * (1 + change))
                
                await user_collection.update_one({'id': uid}, {'$set': {'investments': investments}})
        except Exception as e:
            print(f"ɪɴᴠᴇꜱᴛᴍᴇɴᴛ ᴇʀʀᴏʀ: {e}")

async def post_init(app):
    asyncio.create_task(check_loans())
    asyncio.create_task(deduct_debt())
    asyncio.create_task(check_fd_maturity())
    asyncio.create_task(check_insurance())
    asyncio.create_task(check_recurring_deposits())
    asyncio.create_task(process_investments())

async def sbi_balance(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await init_user(uid)
        user = await get_user(uid)
    
    if user.get('frozen'):
        await update.message.reply_text("⊗ ᴀᴄᴄᴏᴜɴᴛ ғʀᴏᴢᴇɴ\nᴜꜱᴇ /sbiunfreeze <pin>")
        return
    
    interest = await calc_interest(uid)
    user = await get_user(uid)
    wallet = int(user.get('balance', 0))
    bank = int(user.get('bank', 0))
    
    fds = user.get('fixed_deposits', [])
    fd_total = sum(fd['amount'] for fd in fds)
    
    invs = user.get('investments', [])
    inv_total = sum(inv['value'] for inv in invs)
    
    total = wallet + bank + fd_total + inv_total
    loan = user.get('loan_amount', 0)
    debt = user.get('permanent_debt', 0)
    credit = user.get('credit_score', 700)
    
    msg = f"╭────────────────╮\n│   ʙᴀʟᴀɴᴄᴇ ʀᴇᴘᴏʀᴛ   │\n╰────────────────╯\n\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code>\n⟡ ʙᴀɴᴋ: <code>{bank}</code>"
    
    if fd_total > 0:
        msg += f"\n⟡ ꜰᴅꜱ: <code>{fd_total}</code>"
    if inv_total > 0:
        msg += f"\n⟡ ɪɴᴠᴇꜱᴛᴍᴇɴᴛꜱ: <code>{inv_total}</code>"
    
    msg += f"\n⟡ ɴᴇᴛ ᴡᴏʀᴛʜ: <code>{total}</code>"
    
    if credit:
        rank = "ᴇxᴄᴇʟʟᴇɴᴛ" if credit >= 800 else "ɢᴏᴏᴅ" if credit >= 700 else "ꜰᴀɪʀ" if credit >= 600 else "ᴘᴏᴏʀ"
        msg += f"\n⟡ ᴄʀᴇᴅɪᴛ: <code>{credit}</code> ({rank})"
    
    if loan > 0:
        due = user.get('loan_due_date')
        if due:
            left = (due - datetime.utcnow()).total_seconds()
            msg += f"\n\n⚠️ ʟᴏᴀɴ: <code>{loan}</code>\n⏳ ᴅᴜᴇ: {fmt_time(left)}"
    if debt > 0:
        msg += f"\n\n🔴 ᴅᴇʙᴛ: <code>{debt}</code>\n📉 ᴅᴇᴅᴜᴄᴛɪᴏɴ: 10%"
    if interest > 0:
        msg += f"\n\n✨ ɪɴᴛᴇʀᴇꜱᴛ: <code>+{interest}</code>"
    
    if user.get('premium'):
        expiry = user.get('premium_expiry')
        if expiry:
            days = (expiry - datetime.utcnow()).days
            msg += f"\n\n💎 ᴘʀᴇᴍɪᴜᴍ: {days}ᴅ"
    
    msg += "\n\n───────"
    btns = [
        [InlineKeyboardButton("⟲ ʀᴇғʀᴇꜱʜ", callback_data=f"sbibal_{uid}")],
        [InlineKeyboardButton("🏦 ʙᴀɴᴋ", callback_data=f"sbibank_{uid}"), InlineKeyboardButton("💳 ʟᴏᴀɴ", callback_data=f"sbiloan_{uid}")],
        [InlineKeyboardButton("📊 ɪɴᴠᴇꜱᴛ", callback_data=f"sbiinvest_{uid}"), InlineKeyboardButton("🎯 ɢᴏᴀʟꜱ", callback_data=f"sbigoals_{uid}")],
        [InlineKeyboardButton("🛡️ ɪɴꜱᴜʀᴀɴᴄᴇ", callback_data=f"sbiinsurance_{uid}"), InlineKeyboardButton("📜 ʜɪꜱᴛᴏʀʏ", callback_data=f"sbihistory_{uid}")]
    ]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def sbi_deposit(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /sbibalance ꜰɪʀꜱᴛ")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⊗ ᴀᴄᴄᴏᴜɴᴛ ғʀᴏᴢᴇɴ")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /sbideposit <amount>")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ")
        return
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt, 'bank': amt}})
    await add_transaction(uid, 'deposit', amt, "ʙᴀɴᴋ ᴅᴇᴘᴏꜱɪᴛ")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ᴅᴇᴘᴏꜱɪᴛᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: 5% ᴅᴀɪʟʏ", parse_mode="HTML")

async def sbi_withdraw(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /sbibalance ꜰɪʀꜱᴛ")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⊗ ᴀᴄᴄᴏᴜɴᴛ ғʀᴏᴢᴇɴ")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /sbiwithdraw <amount>")
        return
    
    if user.get('bank', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ ʙᴀɴᴋ")
        return
    
    await user_collection.update_one({'id': uid}, {'$inc': {'bank': -amt, 'balance': amt}})
    await add_transaction(uid, 'withdraw', amt, "ᴡɪᴛʜᴅʀᴀᴡᴀʟ")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ᴡɪᴛʜᴅʀᴀᴡɴ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>", parse_mode="HTML")

async def sbi_loan(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /sbibalance ꜰɪʀꜱᴛ")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⊗ ᴀᴄᴄᴏᴜɴᴛ ғʀᴏᴢᴇɴ")
        return
    
    debt = user.get('permanent_debt', 0)
    if debt > 0:
        await update.message.reply_text(f"╭────────────────╮\n│   ⚠️ ᴅᴇʙᴛ   │\n╰────────────────╯\n\n⟡ ᴅᴇʙᴛ: <code>{debt}</code>\n\n⊗ ᴄʟᴇᴀʀ ᴅᴇʙᴛ ꜰɪʀꜱᴛ", parse_mode="HTML")
        return
    
    curr = user.get('loan_amount', 0)
    if curr > 0:
        due = user.get('loan_due_date')
        left = (due - datetime.utcnow()).total_seconds()
        msg = f"╭────────────────╮\n│   ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{curr}</code>\n⟡ ᴅᴜᴇ: {fmt_time(left)}\n\n/sbirepay"
        btns = [[InlineKeyboardButton("💰 ʀᴇᴘᴀʏ", callback_data=f"sbirepay_{uid}")]]
        await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        credit = user.get('credit_score', 700)
        max_loan = BANK_CFG['max_premium_loan'] if user.get('premium') else BANK_CFG['max_loan']
        rate = 5 if credit >= 800 else 8 if credit >= 700 else 10
        await update.message.reply_text(f"⊗ ᴜꜱᴀɢᴇ: /sbiloan <amount>\n\n⟡ ᴍᴀx: <code>{max_loan:,}</code>\n⟡ ʀᴀᴛᴇ: <code>{rate}%</code>\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: 3 ᴅᴀʏꜱ", parse_mode="HTML")
        return
    
    credit = user.get('credit_score', 700)
    max_loan = BANK_CFG['max_premium_loan'] if user.get('premium') else BANK_CFG['max_loan']
    
    if amt > max_loan:
        await update.message.reply_text(f"⊗ ᴍᴀx: {max_loan:,}")
        return
    
    rate = 0.05 if credit >= 800 else 0.08 if credit >= 700 else BANK_CFG['loan_int']
    interest = int(amt * rate)
    total = amt + interest
    due = datetime.utcnow() + timedelta(days=BANK_CFG['loan_days'])
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': amt}, '$set': {'loan_amount': total, 'loan_due_date': due}})
    await add_transaction(uid, 'loan', amt, f"ʟᴏᴀɴ ({int(rate*100)}%)")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{amt}</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{interest}</code>\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code>\n⟡ ᴅᴜᴇ: 3 ᴅᴀʏꜱ\n\n⚠️ 20% ᴘᴇɴᴀʟᴛʏ", parse_mode="HTML")

async def emergency_loan(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    if user.get('loan_amount', 0) > 0:
        await update.message.reply_text("⊗ ᴀᴄᴛɪᴠᴇ ʟᴏᴀɴ ᴇxɪꜱᴛꜱ")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0 or amt > 20000:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /emergency <amount>\n\n⟡ ᴍᴀx: 20,000\n⟡ ʀᴀᴛᴇ: 15%\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: 2 ᴅᴀʏꜱ")
        return
    
    interest = int(amt * BANK_CFG['emergency_loan_int'])
    total = amt + interest
    due = datetime.utcnow() + timedelta(days=2)
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': amt}, '$set': {'loan_amount': total, 'loan_due_date': due}})
    await add_transaction(uid, 'emergency', amt, "ᴇᴍᴇʀɢᴇɴᴄʏ ʟᴏᴀɴ")
    await update.message.reply_text(f"╭────────────────╮\n│   ⚡ ᴇᴍᴇʀɢᴇɴᴄʏ   │\n╰────────────────╯\n\n⟡ ʟᴏᴀɴ: <code>{amt}</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{interest}</code>\n⟡ ᴛᴏᴛᴀʟ: <code>{total}</code>\n⟡ ᴅᴜᴇ: 2 ᴅᴀʏꜱ", parse_mode="HTML")

async def repay(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    loan = user.get('loan_amount', 0)
    if loan <= 0:
        await update.message.reply_text("⊗ ɴᴏ ʟᴏᴀɴ")
        return
    
    bal = user.get('balance', 0)
    if bal < loan:
        await update.message.reply_text(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ\n\nɴᴇᴇᴅ: <code>{loan}</code>\nʜᴀᴠᴇ: <code>{bal}</code>", parse_mode="HTML")
        return
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -loan}, '$set': {'loan_amount': 0, 'loan_due_date': None}})
    await user_collection.update_one({'id': uid}, {'$push': {'loan_history': {'amount': loan, 'date': datetime.utcnow(), 'status': 'repaid'}}})
    await update_credit_score(uid, 20)
    await add_transaction(uid, 'repay', -loan, "ʟᴏᴀɴ ʀᴇᴘᴀɪᴅ")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ʀᴇᴘᴀɪᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{loan}</code>\n⟡ ɴᴇᴡ: <code>{bal - loan}</code>\n\n✨ ᴄʀᴇᴅɪᴛ +20", parse_mode="HTML")

async def clear_debt(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    debt = user.get('permanent_debt', 0)
    if debt <= 0:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴇʙᴛ")
        return
    
    bal = user.get('balance', 0)
    if bal < debt:
        await update.message.reply_text(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ\n\nᴅᴇʙᴛ: <code>{debt}</code>\nʙᴀʟ: <code>{bal}</code>", parse_mode="HTML")
        return
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -debt}, '$set': {'permanent_debt': 0}})
    await update_credit_score(uid, 50)
    await add_transaction(uid, 'clear_debt', -debt, "ᴅᴇʙᴛ ᴄʟᴇᴀʀᴇᴅ")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ᴄʟᴇᴀʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{debt}</code>\n⟡ ɴᴇᴡ: <code>{bal - debt}</code>\n\n✅ ᴅᴇʙᴛ ᴄʟᴇᴀʀᴇᴅ!\n✨ ᴄʀᴇᴅɪᴛ +50", parse_mode="HTML")

async def fixed_deposit(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        amt = int(context.args[0])
        days = int(context.args[1])
        if amt <= 0 or days not in [7, 15, 30]:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /fd <amount> <days>\n\n⟡ ᴅᴀʏꜱ: 7, 15, 30\n⟡ ʀᴀᴛᴇꜱ: 7%, 10%, 15%\n⟡ ᴘᴇɴᴀʟᴛʏ: 3%")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
        return
    
    rate = BANK_CFG['fd_rates'][days]
    interest = int(amt * rate)
    maturity = datetime.utcnow() + timedelta(days=days)
    
    fd = {
        'amount': amt,
        'days': days,
        'rate': rate,
        'interest': interest,
        'created': datetime.utcnow(),
        'maturity_date': maturity
    }
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt}, '$push': {'fixed_deposits': fd}})
    await add_transaction(uid, 'fd', -amt, f"ꜰᴅ ({days}ᴅ)")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ꜰᴅ ᴄʀᴇᴀᴛᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>\n⟡ ᴅᴀʏꜱ: <code>{days}</code>\n⟡ ʀᴀᴛᴇ: <code>{int(rate*100)}%</code>\n⟡ ɪɴᴛᴇʀᴇꜱᴛ: <code>{interest}</code>", parse_mode="HTML")

async def break_fd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    fds = user.get('fixed_deposits', [])
    if not fds:
        await update.message.reply_text("⊗ ɴᴏ ꜰᴅꜱ")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(fds):
            raise ValueError
    except (IndexError, ValueError):
        msg = "╭────────────────╮\n│   ʏᴏᴜʀ ꜰᴅꜱ   │\n╰────────────────╯\n\n"
        for i, fd in enumerate(fds, 1):
            days_left = (fd['maturity_date'] - datetime.utcnow()).days
            msg += f"{i}. <code>{fd['amount']}</code> - {days_left}ᴅ\n"
        msg += "\n⊗ ᴜꜱᴀɢᴇ: /breakfd <number>"
        await update.message.reply_text(msg, parse_mode="HTML")
        return
    
    fd = fds[idx]
    penalty = int(fd['amount'] * BANK_CFG['fd_penalty'])
    refund = fd['amount'] - penalty
    
    fds.pop(idx)
    await user_collection.update_one({'id': uid}, {'$set': {'fixed_deposits': fds}, '$inc': {'balance': refund}})
    await add_transaction(uid, 'break_fd', refund, f"ꜰᴅ ʙʀᴏᴋᴇɴ (ᴘᴇɴᴀʟᴛʏ: {penalty})")
    await update.message.reply_text(f"╭────────────────╮\n│   ꜰᴅ ʙʀᴏᴋᴇɴ   │\n╰────────────────╯\n\n⟡ ᴘʀɪɴᴄɪᴘᴀʟ: <code>{fd['amount']}</code>\n⟡ ᴘᴇɴᴀʟᴛʏ: <code>{penalty}</code>\n⟡ ʀᴇꜰᴜɴᴅ: <code>{refund}</code>", parse_mode="HTML")

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
        await update.message.reply_text("⊗ ʀᴇᴘʟʏ ᴛᴏ ᴜꜱᴇʀ")
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
        await update.message.reply_text("⊗ ᴍᴀx: 1,000,000")
        return
    
    sender = await get_user(sid)
    if not sender or sender.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
        return
    
    pid = f"{sid}_{rec.id}_{int(datetime.utcnow().timestamp())}"
    pending_payments[pid] = {'sender_id': sid, 'recipient_id': rec.id, 'amount': amt}
    btns = [[InlineKeyboardButton("✓ ᴄᴏɴꜰɪʀᴍ", callback_data=f"pok_{pid}"), InlineKeyboardButton("✗ ᴄᴀɴᴄᴇʟ", callback_data=f"pno_{pid}")]]
    await update.message.reply_text(f"╭────────────────╮\n│   ᴄᴏɴꜰɪʀᴍ   │\n╰────────────────╯\n\n⟡ ᴛᴏ: <b>{rec.first_name}</b>\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>\n\n⏳ 30ꜱ", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
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
        await update.message.reply_text(f"⊗ ᴄʟᴀɪᴍᴇᴅ\n⏳ {fmt_time(remaining.total_seconds())}")
        return
    
    debt = user.get('permanent_debt', 0)
    daily_amt = 2500 if user.get('premium') else 2000
    
    if debt > 0:
        deduction = int(daily_amt * BANK_CFG['daily_deduction'])
        deduction = min(deduction, debt)
        actual_amt = daily_amt - deduction
        new_debt = debt - deduction
        
        await user_collection.update_one(
            {'id': uid},
            {'$inc': {'balance': actual_amt}, '$set': {'last_daily': now, 'permanent_debt': max(0, new_debt)}}
        )
        await add_transaction(uid, 'daily', actual_amt, f"ᴅᴀɪʟʏ (ᴅᴇʙᴛ: -{deduction})")
        
        msg = f"╭────────────────╮\n│   ᴅᴀɪʟʏ   │\n╰────────────────╯\n\n⟡ ᴇᴀʀɴᴇᴅ: <code>{daily_amt}</code>\n⟡ ᴅᴇᴅᴜᴄᴛɪᴏɴ: <code>-{deduction}</code>\n⟡ ʀᴇᴄᴇɪᴠᴇᴅ: <code>{actual_amt}</code>\n\n🔴 ᴅᴇʙᴛ: <code>{new_debt}</code>"
        
        if new_debt <= 0:
            msg += "\n\n✅ ᴅᴇʙᴛ ᴄʟᴇᴀʀᴇᴅ!"
    else:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': daily_amt, 'user_xp': 10}, '$set': {'last_daily': now}})
        await add_transaction(uid, 'daily', daily_amt, "ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ")
        msg = f"╭────────────────╮\n│   ᴅᴀɪʟʏ   │\n╰────────────────╯\n\n⟡ ᴄʟᴀɪᴍᴇᴅ: <code>{daily_amt}</code>\n⟡ xᴘ: +10"
    
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
    
    achievements = user.get('achievements', [])
    
    await update.message.reply_text(f"╭────────────────╮\n│   ʟᴇᴠᴇʟ & ʀᴀɴᴋ   │\n╰────────────────╯\n\n⟡ ʟᴇᴠᴇʟ: <code>{lvl}</code>\n⟡ ʀᴀɴᴋ: <code>{rank}</code>\n⟡ xᴘ: <code>{xp}</code>\n⟡ ɴᴇᴇᴅᴇᴅ: <code>{needed}</code>\n⟡ ᴀᴄʜɪᴇᴠᴇᴍᴇɴᴛꜱ: <code>{len(achievements)}</code>", parse_mode="HTML")

async def history(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    transactions = user.get('transactions', [])
    if not transactions:
        await update.message.reply_text("⊗ ɴᴏ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ")
        return
    
    recent = transactions[-10:]
    msg = "╭────────────────╮\n│   📜 ʜɪꜱᴛᴏʀʏ   │\n╰────────────────╯\n\n"
    
    for t in reversed(recent):
        ttype = t.get('type', 'ᴜɴᴋɴᴏᴡɴ')
        amt = t.get('amount', 0)
        desc = t.get('description', '')
        timestamp = t.get('timestamp')
        date_str = timestamp.strftime('%d/%m %H:%M') if timestamp else 'ɴ/ᴀ'
        
        emoji = "💰" if amt > 0 else "💸"
        msg += f"{emoji} <code>{amt:+d}</code> • {ttype}\n"
        if desc:
            msg += f"   {desc}\n"
        msg += f"   {date_str}\n\n"
    
    btns = [[InlineKeyboardButton("💰 ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{uid}")]]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def invest_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        itype = context.args[0].lower()
        amt = int(context.args[1])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /invest <type> <amount>\n\n⟡ ᴛʏᴘᴇꜱ:\n  • stock (ʜɪɢʜ ʀɪꜱᴋ)\n  • bond (ʟᴏᴡ ʀɪꜱᴋ)\n  • mf_low/med/high")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
        return
    
    valid_types = {
        'stock': {'type': 'stock', 'name': 'ꜱᴛᴏᴄᴋ'},
        'bond': {'type': 'bond', 'name': 'ʙᴏɴᴅ'},
        'mf_low': {'type': 'mutual_fund', 'risk': 'low', 'name': 'ᴍꜰ (ʟᴏᴡ)'},
        'mf_med': {'type': 'mutual_fund', 'risk': 'medium', 'name': 'ᴍꜰ (ᴍᴇᴅ)'},
        'mf_high': {'type': 'mutual_fund', 'risk': 'high', 'name': 'ᴍꜰ (ʜɪɢʜ)'}
    }
    
    if itype not in valid_types:
        await update.message.reply_text("⊗ ɪɴᴠᴀʟɪᴅ ᴛʏᴘᴇ")
        return
    
    inv_data = valid_types[itype]
    investment = {
        'type': inv_data['type'],
        'value': amt,
        'initial': amt,
        'created': datetime.utcnow(),
        'name': inv_data['name']
    }
    
    if 'risk' in inv_data:
        investment['risk'] = inv_data['risk']
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt}, '$push': {'investments': investment}})
    await add_transaction(uid, 'invest', -amt, f"{inv_data['name']}")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ɪɴᴠᴇꜱᴛᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴛʏᴘᴇ: {inv_data['name']}\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>\n\n/portfolio", parse_mode="HTML")

async def portfolio(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    investments = user.get('investments', [])
    if not investments:
        await update.message.reply_text("⊗ ɴᴏ ɪɴᴠᴇꜱᴛᴍᴇɴᴛꜱ")
        return
    
    msg = "╭────────────────╮\n│   📊 ᴘᴏʀᴛꜰᴏʟɪᴏ   │\n╰────────────────╯\n\n"
    total_value = 0
    total_initial = 0
    
    for i, inv in enumerate(investments, 1):
        name = inv.get('name', 'ᴜɴᴋɴᴏᴡɴ')
        value = inv.get('value', 0)
        initial = inv.get('initial', 0)
        change = ((value - initial) / initial * 100) if initial > 0 else 0
        
        emoji = "📈" if change >= 0 else "📉"
        msg += f"{i}. {name}\n"
        msg += f"   ɪɴɪᴛɪᴀʟ: <code>{initial}</code>\n"
        msg += f"   ᴄᴜʀʀᴇɴᴛ: <code>{value}</code>\n"
        msg += f"   {emoji} <code>{change:+.2f}%</code>\n\n"
        
        total_value += value
        total_initial += initial
    
    total_change = ((total_value - total_initial) / total_initial * 100) if total_initial > 0 else 0
    msg += f"<b>ᴛᴏᴛᴀʟ:</b> <code>{total_value}</code>\n"
    msg += f"<b>ɢᴀɪɴ/ʟᴏꜱꜱ:</b> <code>{total_change:+.2f}%</code>\n\n"
    msg += "/sellinvest <number>"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def sell_investment(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    investments = user.get('investments', [])
    if not investments:
        await update.message.reply_text("⊗ ɴᴏ ɪɴᴠᴇꜱᴛᴍᴇɴᴛꜱ")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(investments):
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /sellinvest <number>\n\n/portfolio")
        return
    
    inv = investments[idx]
    value = inv.get('value', 0)
    initial = inv.get('initial', 0)
    profit = value - initial
    
    investments.pop(idx)
    await user_collection.update_one({'id': uid}, {'$set': {'investments': investments}, '$inc': {'balance': value}})
    await add_transaction(uid, 'sell', value, f"{inv.get('name', 'ɪɴᴠ')}")
    
    msg = f"╭────────────────╮\n│   ✓ ꜱᴏʟᴅ   │\n╰────────────────╯\n\n⟡ ᴛʏᴘᴇ: {inv.get('name', 'ᴜɴᴋɴᴏᴡɴ')}\n⟡ ɪɴɪᴛɪᴀʟ: <code>{initial}</code>\n⟡ ꜱᴏʟᴅ: <code>{value}</code>\n⟡ ᴘʀᴏꜰɪᴛ: <code>{profit:+d}</code>"
    await update.message.reply_text(msg, parse_mode="HTML")

async def set_goal(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        target = int(context.args[0])
        name = " ".join(context.args[1:])
        if target <= 0 or not name:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /setgoal <amount> <name>\n\nᴇx: /setgoal 50000 ɴᴇᴡ ᴄʜᴀʀ")
        return
    
    goal = {
        'name': name,
        'target': target,
        'current': 0,
        'created': datetime.utcnow()
    }
    
    await user_collection.update_one({'id': uid}, {'$push': {'savings_goals': goal}})
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ɢᴏᴀʟ ꜱᴇᴛ   │\n╰────────────────╯\n\n⟡ ɢᴏᴀʟ: {name}\n⟡ ᴛᴀʀɢᴇᴛ: <code>{target}</code>\n\n/addtogoal", parse_mode="HTML")

async def add_to_goal(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    goals = user.get('savings_goals', [])
    if not goals:
        await update.message.reply_text("⊗ ɴᴏ ɢᴏᴀʟꜱ\n\n/setgoal")
        return
    
    try:
        idx = int(context.args[0]) - 1
        amt = int(context.args[1])
        if idx < 0 or idx >= len(goals) or amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        msg = "╭────────────────╮\n│   🎯 ɢᴏᴀʟꜱ   │\n╰────────────────╯\n\n"
        for i, g in enumerate(goals, 1):
            progress = (g['current'] / g['target'] * 100) if g['target'] > 0 else 0
            msg += f"{i}. {g['name']}\n   {g['current']}/{g['target']} ({progress:.0f}%)\n\n"
        msg += "⊗ ᴜꜱᴀɢᴇ: /addtogoal <num> <amt>"
        await update.message.reply_text(msg, parse_mode="HTML")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
        return
    
    goal = goals[idx]
    goal['current'] += amt
    
    achieved = False
    if goal['current'] >= goal['target']:
        achieved = True
        goal['current'] = goal['target']
    
    await user_collection.update_one({'id': uid}, {'$set': {'savings_goals': goals}, '$inc': {'balance': -amt}})
    await add_transaction(uid, 'goal', -amt, f"{goal['name']}")
    
    progress = (goal['current'] / goal['target'] * 100) if goal['target'] > 0 else 0
    msg = f"╭────────────────╮\n│   ✓ ᴀᴅᴅᴇᴅ   │\n╰────────────────╯\n\n⟡ ɢᴏᴀʟ: {goal['name']}\n⟡ ᴀᴅᴅᴇᴅ: <code>{amt}</code>\n⟡ ᴘʀᴏɢʀᴇꜱꜱ: {goal['current']}/{goal['target']}\n⟡ {progress:.0f}%"
    
    if achieved:
        msg += "\n\n🎉 ɢᴏᴀʟ ᴀᴄʜɪᴇᴠᴇᴅ!"
        await user_collection.update_one({'id': uid}, {'$inc': {'user_xp': 50}})
        
        if 'goal_achiever' not in user.get('achievements', []):
            await user_collection.update_one({'id': uid}, {'$push': {'achievements': 'goal_achiever'}})
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def withdraw_goal(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    goals = user.get('savings_goals', [])
    if not goals:
        await update.message.reply_text("⊗ ɴᴏ ɢᴏᴀʟꜱ")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(goals):
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /withdrawgoal <num>")
        return
    
    goal = goals[idx]
    amt = goal['current']
    
    goals.pop(idx)
    await user_collection.update_one({'id': uid}, {'$set': {'savings_goals': goals}, '$inc': {'balance': amt}})
    await add_transaction(uid, 'withdraw_goal', amt, f"{goal['name']}")
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ᴡɪᴛʜᴅʀᴀᴡɴ   │\n╰────────────────╯\n\n⟡ ɢᴏᴀʟ: {goal['name']}\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>", parse_mode="HTML")

async def buy_insurance(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        itype = context.args[0].lower()
        if itype not in ['char', 'deposit']:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /buyinsurance <type>\n\n⟡ ᴛʏᴘᴇꜱ:\n  • char - ᴘʀᴏᴛᴇᴄᴛ ᴄʜᴀʀꜱ\n  • deposit - ᴄᴏᴠᴇʀ 50ᴋ\n\n⟡ ᴘʀᴇᴍɪᴜᴍ: 500/ᴍᴏɴᴛʜ")
        return
    
    premium = BANK_CFG['insurance_premium']
    if user.get('balance', 0) < premium:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
        return
    
    insurance = user.get('insurance', {})
    if insurance.get(itype):
        await update.message.reply_text("⊗ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ")
        return
    
    insurance[itype] = True
    insurance['last_premium'] = datetime.utcnow()
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -premium}, '$set': {'insurance': insurance}})
    await add_transaction(uid, 'insurance', -premium, f"ɪɴꜱᴜʀᴀɴᴄᴇ: {itype}")
    
    iname = "ᴄʜᴀʀᴀᴄᴛᴇʀ" if itype == 'char' else "ᴅᴇᴘᴏꜱɪᴛ"
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ɪɴꜱᴜʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴛʏᴘᴇ: {iname}\n⟡ ᴘʀᴇᴍɪᴜᴍ: <code>{premium}</code>\n⟡ ᴠᴀʟɪᴅ: 30 ᴅᴀʏꜱ\n\n🛡️ ᴘʀᴏᴛᴇᴄᴛᴇᴅ", parse_mode="HTML")

async def buy_premium(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    fee = BANK_CFG['premium_fee']
    if user.get('balance', 0) < fee:
        await update.message.reply_text(f"⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ\n\nᴄᴏꜱᴛ: {fee}")
        return
    
    expiry = datetime.utcnow() + timedelta(days=30)
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -fee}, '$set': {'premium': True, 'premium_expiry': expiry}})
    await add_transaction(uid, 'premium', -fee, "ᴘʀᴇᴍɪᴜᴍ (30ᴅ)")
    
    await update.message.reply_text(f"╭────────────────╮\n│   💎 ᴘʀᴇᴍɪᴜᴍ   │\n╰────────────────╯\n\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: 30 ᴅᴀʏꜱ\n⟡ ᴄᴏꜱᴛ: <code>{fee}</code>\n\n<b>ʙᴇɴᴇꜰɪᴛꜱ:</b>\n✓ +500 ᴅᴀɪʟʏ\n✓ +1% ɪɴᴛᴇʀᴇꜱᴛ\n✓ 200ᴋ ʟᴏᴀɴ\n✓ ʟᴏᴡᴇʀ ʀᴀᴛᴇꜱ", parse_mode="HTML")

async def set_pin(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        pin = context.args[0]
        if len(pin) != 4 or not pin.isdigit():
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /setpin <4-digit>")
        return
    
    await user_collection.update_one({'id': uid}, {'$set': {'pin': pin}})
    await update.message.reply_text("╭────────────────╮\n│   ✓ ᴘɪɴ ꜱᴇᴛ   │\n╰────────────────╯\n\n⟡ ꜱᴇᴄᴜʀᴇᴅ\n⟡ /freeze ᴛᴏ ʟᴏᴄᴋ")

async def freeze_account(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    if not user.get('pin'):
        await update.message.reply_text("⊗ ꜱᴇᴛ ᴘɪɴ ꜰɪʀꜱᴛ\n\n/setpin <4-digit>")
        return
    
    await user_collection.update_one({'id': uid}, {'$set': {'frozen': True}})
    await update.message.reply_text("╭────────────────╮\n│   🔒 ғʀᴏᴢᴇɴ   │\n╰────────────────╯\n\n⟡ ʟᴏᴄᴋᴇᴅ\n⟡ /unfreeze <pin>")

async def unfreeze_account(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    if not user.get('frozen'):
        await update.message.reply_text("⊗ ɴᴏᴛ ғʀᴏᴢᴇɴ")
        return
    
    try:
        pin = context.args[0]
    except IndexError:
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /unfreeze <pin>")
        return
    
    if user.get('pin') != pin:
        await update.message.reply_text("⊗ ɪɴᴄᴏʀʀᴇᴄᴛ ᴘɪɴ")
        return
    
    await user_collection.update_one({'id': uid}, {'$set': {'frozen': False}})
    await update.message.reply_text("╭────────────────╮\n│   🔓 ᴜɴʟᴏᴄᴋᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴀᴄᴛɪᴠᴇ")

async def setup_rd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        amt = int(context.args[0])
        freq = context.args[1].lower()
        if amt <= 0 or freq not in ['daily', 'weekly']:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /setuprd <amount> <freq>\n\n⟡ ғʀᴇǫ: daily, weekly\n⟡ ᴀᴜᴛᴏ-ᴅᴇᴘᴏꜱɪᴛ")
        return
    
    rd = {
        'active': True,
        'amount': amt,
        'frequency': freq,
        'last_deposit': None
    }
    
    await user_collection.update_one({'id': uid}, {'$set': {'recurring_deposit': rd}})
    await update.message.reply_text(f"╭────────────────╮\n│   ✓ ʀᴅ ꜱᴇᴛᴜᴘ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴏᴜɴᴛ: <code>{amt}</code>\n⟡ ғʀᴇǫ: {freq}\n\n🔄 ᴀᴄᴛɪᴠᴀᴛᴇᴅ", parse_mode="HTML")

async def stop_rd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    rd = user.get('recurring_deposit', {})
    if not rd.get('active'):
        await update.message.reply_text("⊗ ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴅ")
        return
    
    rd['active'] = False
    await user_collection.update_one({'id': uid}, {'$set': {'recurring_deposit': rd}})
    await update.message.reply_text("╭────────────────╮\n│   ✓ ʀᴅ ꜱᴛᴏᴘᴘᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴅɪꜱᴀʙʟᴇᴅ")

async def leaderboard(update: Update, context: CallbackContext):
    top_users = []
    async for user in user_collection.find().sort('bank', -1).limit(10):
        uid = user['id']
        bank = user.get('bank', 0)
        balance = user.get('balance', 0)
        total = bank + balance
        
        fds = user.get('fixed_deposits', [])
        fd_total = sum(fd['amount'] for fd in fds)
        
        invs = user.get('investments', [])
        inv_total = sum(inv['value'] for inv in invs)
        
        net_worth = total + fd_total + inv_total
        
        try:
            u = await application.bot.get_chat(uid)
            name = u.first_name
        except:
            name = "ᴜɴᴋɴᴏᴡɴ"
        
        top_users.append({'name': name, 'net_worth': net_worth})
    
    if not top_users:
        await update.message.reply_text("⊗ ɴᴏ ᴅᴀᴛᴀ")
        return
    
    msg = "╭────────────────╮\n│   🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ   │\n╰────────────────╯\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(top_users, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        msg += f"{medal} <b>{u['name']}</b>\n   <code>{u['net_worth']:,}</code>\n\n"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def referral(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    referrals = user.get('referrals', [])
    ref_code = f"REF{uid}"
    bonus = len(referrals) * 1000
    
    msg = f"╭────────────────╮\n│   💝 ʀᴇꜰᴇʀʀᴀʟ   │\n╰────────────────╯\n\n⟡ ᴄᴏᴅᴇ: <code>{ref_code}</code>\n⟡ ʀᴇꜰꜱ: <code>{len(referrals)}</code>\n⟡ ᴇᴀʀɴᴇᴅ: <code>{bonus}</code>\n\n💡 1000 ɢᴏʟᴅ ᴇᴀᴄʜ"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def gamble(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⊗ ᴜꜱᴇ /bal ꜰɪʀꜱᴛ")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0 or amt > 10000:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("⊗ ᴜꜱᴀɢᴇ: /gamble <amount>\n\n⟡ ᴍᴀx: 10,000\n⟡ 2x ᴏʀ ʟᴏꜱᴇ\n⟡ 45% ᴡɪɴ")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
        return
    
    win = random.random() < 0.45
    
    if win:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': amt, 'user_xp': 5}})
        await add_transaction(uid, 'gamble_win', amt, "ɢᴀᴍʙʟᴇ ᴡᴏɴ")
        msg = f"╭────────────────╮\n│   🎰 ᴡɪɴ!   │\n╰────────────────╯\n\n⟡ ʙᴇᴛ: <code>{amt}</code>\n⟡ ᴡᴏɴ: <code>{amt}</code>\n⟡ ᴛᴏᴛᴀʟ: <code>+{amt}</code>\n\n🎉 ᴄᴏɴɢʀᴀᴛꜱ!"
    else:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt}})
        await add_transaction(uid, 'gamble_loss', -amt, "ɢᴀᴍʙʟᴇ ʟᴏꜱᴛ")
        msg = f"╭────────────────╮\n│   🎰 ʟᴏꜱᴛ   │\n╰────────────────╯\n\n⟡ ʙᴇᴛ: <code>{amt}</code>\n⟡ ʟᴏꜱᴛ: <code>{amt}</code>\n\n💔 ʙᴇᴛᴛᴇʀ ʟᴜᴄᴋ!"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def bank_help(update: Update, context: CallbackContext):
    help_text = f"""╭─────────────────────╮
│  💰 ʙᴀɴᴋɪɴɢ ꜱʏꜱᴛᴇᴍ  │
╰─────────────────────╯

<b>📊 ʙᴀꜱɪᴄ</b>
/bal - ʙᴀʟᴀɴᴄᴇ
/deposit - ᴅᴇᴘᴏꜱɪᴛ
/withdraw - ᴡɪᴛʜᴅʀᴀᴡ
/cclaim - ᴅᴀɪʟʏ 2ᴋ

<b>💳 ʟᴏᴀɴꜱ</b>
/loan - ʙᴏʀʀᴏᴡ (100ᴋ)
/emergency - ғᴀꜱᴛ (20ᴋ)
/repay - ʀᴇᴘᴀʏ
/cleardebt - ᴄʟᴇᴀʀ

<b>🔒 ꜰɪxᴇᴅ ᴅᴇᴘᴏꜱɪᴛ</b>
/fd - ᴄʀᴇᴀᴛᴇ
/breakfd - ᴄᴀɴᴄᴇʟ

<b>📈 ɪɴᴠᴇꜱᴛ</b>
/invest - ʙᴜʏ
/portfolio - ᴠɪᴇᴡ
/sellinvest - ꜱᴇʟʟ

<b>🎯 ɢᴏᴀʟꜱ</b>
/setgoal - ᴄʀᴇᴀᴛᴇ
/addtogoal - ᴀᴅᴅ
/withdrawgoal - ʀᴇᴍᴏᴠᴇ

<b>🛡️ ꜱᴇᴄᴜʀɪᴛʏ</b>
/buyinsurance - ᴘʀᴏᴛᴇᴄᴛ
/setpin - ꜱᴇᴛ ᴘɪɴ
/freeze - ʟᴏᴄᴋ
/unfreeze - ᴜɴʟᴏᴄᴋ

<b>💎 ᴘʀᴇᴍɪᴜᴍ</b>
/buypremium - ᴜᴘɢʀᴀᴅᴇ

<b>🔄 ᴀᴜᴛᴏ</b>
/setuprd - ᴀᴜᴛᴏ-ᴅᴇᴘᴏꜱɪᴛ
/stoprd - ꜱᴛᴏᴘ

<b>📜 ᴏᴛʜᴇʀ</b>
/history - ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ
/pay - ꜱᴇɴᴅ ɢᴏʟᴅ
/xp - ʟᴇᴠᴇʟ
/leaderboard - ᴛᴏᴘ 10
/referral - ʀᴇꜰᴇʀ
/gamble - ʀɪꜱᴋ!
/notifications - ᴀʟᴇʀᴛꜱ"""

    btns = [[InlineKeyboardButton("💰 ʙᴀʟᴀɴᴄᴇ", callback_data=f"bal_{update.effective_user.id}")]]
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def callback_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    valid_prefixes = ("bal_", "bank_", "loan_", "repay_", "clr_", "pok_", "pno_", "invest_", "goals_", "insurance_", "history_")
    if not data.startswith(valid_prefixes):
        return

    await q.answer()

    if data.startswith("bal_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        if not user:
            await q.answer("⊗ ᴜꜱᴇ /bal", show_alert=True)
            return

        interest = await calc_interest(uid)
        user = await get_user(uid)
        wallet = int(user.get('balance', 0))
        bank = int(user.get('bank', 0))
        
        fds = user.get('fixed_deposits', [])
        fd_total = sum(fd['amount'] for fd in fds)
        
        invs = user.get('investments', [])
        inv_total = sum(inv['value'] for inv in invs)
        
        total = wallet + bank + fd_total + inv_total
        loan = user.get('loan_amount', 0)
        debt = user.get('permanent_debt', 0)
        credit = user.get('credit_score', 700)
        
        msg = f"╭────────────────╮\n│   ʙᴀʟᴀɴᴄᴇ   │\n╰────────────────╯\n\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code>\n⟡ ʙᴀɴᴋ: <code>{bank}</code>"
        
        if fd_total > 0:
            msg += f"\n⟡ ꜰᴅꜱ: <code>{fd_total}</code>"
        if inv_total > 0:
            msg += f"\n⟡ ɪɴᴠꜱ: <code>{inv_total}</code>"
        
        msg += f"\n⟡ ɴᴇᴛ: <code>{total}</code>"
        
        if credit:
            rank = "ᴇxᴄ" if credit >= 800 else "ɢᴏᴏᴅ" if credit >= 700 else "ꜰᴀɪʀ" if credit >= 600 else "ᴘᴏᴏʀ"
            msg += f"\n⟡ ᴄʀᴇᴅɪᴛ: <code>{credit}</code> ({rank})"
        
        if loan > 0:
            due = user.get('loan_due_date')
            if due:
                left = (due - datetime.utcnow()).total_seconds()
                msg += f"\n\n⚠️ ʟᴏᴀɴ: <code>{loan}</code>\n⏳ {fmt_time(left)}"
        if debt > 0:
            msg += f"\n\n🔴 ᴅᴇʙᴛ: <code>{debt}</code>"
        if interest > 0:
            msg += f"\n\n✨ +<code>{interest}</code>"
        
        if user.get('premium'):
            expiry = user.get('premium_expiry')
            if expiry:
                days = (expiry - datetime.utcnow()).days
                msg += f"\n\n💎 {days}ᴅ"
        
        msg += "\n\n───────"
        btns = [
            [InlineKeyboardButton("⟲", callback_data=f"bal_{uid}")],
            [InlineKeyboardButton("🏦", callback_data=f"bank_{uid}"), InlineKeyboardButton("💳", callback_data=f"loan_{uid}")],
            [InlineKeyboardButton("📊", callback_data=f"invest_{uid}"), InlineKeyboardButton("🎯", callback_data=f"goals_{uid}")],
            [InlineKeyboardButton("🛡️", callback_data=f"insurance_{uid}"), InlineKeyboardButton("📜", callback_data=f"history_{uid}")]
        ]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓")

    elif data.startswith("bank_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        bank = user.get('bank', 0)
        wallet = user.get('balance', 0)
        fds = user.get('fixed_deposits', [])
        
        msg = f"╭────────────────╮\n│   🏦 ʙᴀɴᴋ   │\n╰────────────────╯\n\n⟡ ʙᴀɴᴋ: <code>{bank}</code>\n⟡ ᴡᴀʟʟᴇᴛ: <code>{wallet}</code>\n⟡ ɪɴᴛ: 5% ᴅᴀɪʟʏ\n⟡ ꜰᴅꜱ: <code>{len(fds)}</code>\n\n/deposit <amt>\n/withdraw <amt>\n/fd <amt> <days>"
        btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("loan_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        debt = user.get('permanent_debt', 0)
        
        if debt > 0:
            msg = f"╭────────────────╮\n│   🔴 ᴅᴇʙᴛ   │\n╰────────────────╯\n\n⟡ ᴅᴇʙᴛ: <code>{debt}</code>\n⟡ -10% ᴅᴀɪʟʏ\n\n/cleardebt"
            btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
            return

        loan = user.get('loan_amount', 0)
        credit = user.get('credit_score', 700)
        
        if loan > 0:
            due = user.get('loan_due_date')
            left = (due - datetime.utcnow()).total_seconds()
            msg = f"╭────────────────╮\n│   💳 ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ᴀᴍᴛ: <code>{loan}</code>\n⟡ ᴅᴜᴇ: {fmt_time(left)}\n\n/repay"
            btns = [[InlineKeyboardButton("💰", callback_data=f"repay_{uid}")], [InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        else:
            max_loan = 200000 if user.get('premium') else 100000
            rate = 5 if credit >= 800 else 8 if credit >= 700 else 10
            
            msg = f"╭────────────────╮\n│   💳 ʟᴏᴀɴ   │\n╰────────────────╯\n\n⟡ ᴍᴀx: <code>{max_loan:,}</code>\n⟡ ʀᴀᴛᴇ: <code>{rate}%</code>\n⟡ ᴅᴜʀᴀᴛɪᴏɴ: 3ᴅ\n⟡ ᴄʀᴇᴅɪᴛ: <code>{credit}</code>\n\n/loan <amt>\n/emergency <amt>"
            btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("invest_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        invs = user.get('investments', [])
        total_value = sum(inv['value'] for inv in invs)
        
        msg = f"╭────────────────╮\n│   📊 ɪɴᴠᴇꜱᴛ   │\n╰────────────────╯\n\n⟡ ᴘᴏʀᴛꜰᴏʟɪᴏ: <code>{len(invs)}</code>\n⟡ ᴠᴀʟᴜᴇ: <code>{total_value}</code>\n\n<b>ᴛʏᴘᴇꜱ:</b>\n• stock\n• bond\n• mf_low/med/high\n\n/invest <type> <amt>\n/portfolio\n/sellinvest <num>"
        btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("goals_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        goals = user.get('savings_goals', [])
        
        if goals:
            msg = "╭────────────────╮\n│   🎯 ɢᴏᴀʟꜱ   │\n╰────────────────╯\n\n"
            for i, g in enumerate(goals, 1):
                progress = (g['current'] / g['target'] * 100) if g['target'] > 0 else 0
                msg += f"{i}. {g['name']}\n   {g['current']}/{g['target']} ({progress:.0f}%)\n\n"
            msg += "/addtogoal <n> <amt>\n/withdrawgoal <n>"
        else:
            msg = "╭────────────────╮\n│   🎯 ɢᴏᴀʟꜱ   │\n╰────────────────╯\n\n⊗ ɴᴏ ɢᴏᴀʟꜱ\n\n/setgoal <amt> <name>"
        
        btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("insurance_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        insurance = user.get('insurance', {})
        char_ins = "✅" if insurance.get('char') else "❌"
        dep_ins = "✅" if insurance.get('deposit') else "❌"
        
        msg = f"╭────────────────╮\n│   🛡️ ɪɴꜱᴜʀᴀɴᴄᴇ   │\n╰────────────────╯\n\n⟡ ᴄʜᴀʀ: {char_ins}\n⟡ ᴅᴇᴘᴏꜱɪᴛ: {dep_ins}\n⟡ ᴘʀᴇᴍɪᴜᴍ: 500/ᴍ\n\n/buyinsurance <type>"
        btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("history_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        transactions = user.get('transactions', [])
        
        if not transactions:
            msg = "╭────────────────╮\n│   📜 ʜɪꜱᴛᴏʀʏ   │\n╰────────────────╯\n\n⊗ ɴᴏ ᴛʀᴀɴꜱᴀᴄᴛɪᴏɴꜱ"
        else:
            recent = transactions[-5:]
            msg = "╭────────────────╮\n│   📜 ʜɪꜱᴛᴏʀʏ   │\n╰────────────────╯\n\n"
            
            for t in reversed(recent):
                amt = t.get('amount', 0)
                ttype = t.get('type', 'ᴜɴᴋɴᴏᴡɴ')
                emoji = "💰" if amt > 0 else "💸"
                msg += f"{emoji} <code>{amt:+d}</code> • {ttype}\n"
            
            msg += "\n/history"
        
        btns = [[InlineKeyboardButton("⬅️", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("repay_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        user = await get_user(uid)
        loan = user.get('loan_amount', 0)
        
        if loan <= 0:
            await q.answer("⊗ ɴᴏ ʟᴏᴀɴ", show_alert=True)
            return

        bal = user.get('balance', 0)
        if bal < loan:
            await q.answer(f"⊗ ɴᴇᴇᴅ: {loan}\nʜᴀᴠᴇ: {bal}", show_alert=True)
            return

        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -loan}, '$set': {'loan_amount': 0, 'loan_due_date': None}})
        await user_collection.update_one({'id': uid}, {'$push': {'loan_history': {'amount': loan, 'date': datetime.utcnow(), 'status': 'repaid'}}})
        await update_credit_score(uid, 20)
        await add_transaction(uid, 'repay', -loan, "ʀᴇᴘᴀɪᴅ")
        
        new_bal = bal - loan
        msg = f"╭────────────────╮\n│   ✓ ʀᴇᴘᴀɪᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀɪᴅ: <code>{loan}</code>\n⟡ ʙᴀʟ: <code>{new_bal}</code>\n\n✨ ᴄʀᴇᴅɪᴛ +20"
        btns = [[InlineKeyboardButton("💰", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓")

    elif data.startswith("clr_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        await user_collection.update_one({'id': uid}, {'$set': {'notifications': []}})
        await q.edit_message_text("╭────────────────╮\n│   ✓ ᴄʟᴇᴀʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ɴᴏᴛɪꜰɪᴄᴀᴛɪᴏɴꜱ ᴄʟᴇᴀʀᴇᴅ")
        await q.answer("✓")

    elif data.startswith("pok_"):
        pid = data.split("_", 1)[1]
        if pid not in pending_payments:
            await q.edit_message_text("╭────────────────╮\n│   ⊗ ᴇxᴘɪʀᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀʏᴍᴇɴᴛ ᴇxᴘɪʀᴇᴅ")
            await q.answer("⊗ ᴇxᴘɪʀᴇᴅ", show_alert=True)
            return

        payment = pending_payments[pid]
        if uid != payment['sender_id']:
            await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
            return

        sender = await get_user(payment['sender_id'])
        if not sender or sender.get('balance', 0) < payment['amount']:
            await q.edit_message_text("╭────────────────╮\n│   ⊗ ғᴀɪʟᴇᴅ   │\n╰────────────────╯\n\n⟡ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ")
            del pending_payments[pid]
            await q.answer("⊗ ɪɴꜱᴜꜰꜰɪᴄɪᴇɴᴛ", show_alert=True)
            return

        recipient = await get_user(payment['recipient_id'])
        if not recipient:
            await init_user(payment['recipient_id'])

        await user_collection.update_one({'id': payment['sender_id']}, {'$inc': {'balance': -payment['amount']}})
        await user_collection.update_one({'id': payment['recipient_id']}, {'$inc': {'balance': payment['amount']}})
        await add_transaction(payment['sender_id'], 'payment', -payment['amount'], "ᴘᴀɪᴅ")
        await add_transaction(payment['recipient_id'], 'received', payment['amount'], "ʀᴇᴄᴇɪᴠᴇᴅ")
        pay_cooldown[payment['sender_id']] = datetime.utcnow()

        try:
            recipient_user = await context.bot.get_chat(payment['recipient_id'])
            recipient_name = recipient_user.first_name
        except:
            recipient_name = "ᴜɴᴋɴᴏᴡɴ"

        del pending_payments[pid]

        msg = f"╭────────────────╮\n│   ✓ ꜱᴇɴᴛ   │\n╰────────────────╯\n\n⟡ ᴛᴏ: <b>{recipient_name}</b>\n⟡ ᴀᴍᴛ: <code>{payment['amount']}</code>\n\n✅ ꜱᴜᴄᴄᴇꜱꜱ"
        btns = [[InlineKeyboardButton("💰", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓")

    elif data.startswith("pno_"):
        pid = data.split("_", 1)[1]
        if pid in pending_payments:
            payment = pending_payments[pid]
            if uid != payment['sender_id']:
                await q.answer("⊗ ɴᴏᴛ ʏᴏᴜʀꜱ", show_alert=True)
                return
            del pending_payments[pid]

        await q.edit_message_text("╭────────────────╮\n│   ✗ ᴄᴀɴᴄᴇʟʟᴇᴅ   │\n╰────────────────╯\n\n⟡ ᴘᴀʏᴍᴇɴᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ")
        await q.answer("✗")

# Register handlers
application.post_init = post_init

application.add_handler(CommandHandler("bal", sbi_balance, block=False))
application.add_handler(CommandHandler("sbideposit", sbi_deposit, block=False))
application.add_handler(CommandHandler("sbiwithdraw", sbi_withdraw, block=False))
application.add_handler(CommandHandler("sbiloan", sbi_loan, block=False))
application.add_handler(CommandHandler("sbiemergency", emergency_loan, block=False))
application.add_handler(CommandHandler("sbirepay", repay, block=False))
application.add_handler(CommandHandler("sbicleardebt", clear_debt, block=False))
application.add_handler(CommandHandler("sbifd", fixed_deposit, block=False))
application.add_handler(CommandHandler("sbibreakfd", break_fd, block=False))
application.add_handler(CommandHandler("sbinotifications", notifications, block=False))
application.add_handler(CommandHandler("sbipay", pay, block=False))
application.add_handler(CommandHandler("sbidaily", daily, block=False))
application.add_handler(CommandHandler("sbixp", xp_cmd, block=False))
application.add_handler(CommandHandler("sbihistory", history, block=False))
application.add_handler(CommandHandler("sbiinvest", invest_cmd, block=False))
application.add_handler(CommandHandler("sbiportfolio", portfolio, block=False))
application.add_handler(CommandHandler("sbisellinvest", sell_investment, block=False))
application.add_handler(CommandHandler("sbisetgoal", set_goal, block=False))
application.add_handler(CommandHandler("sbiaddtogoal", add_to_goal, block=False))
application.add_handler(CommandHandler("sbiwithdrawgoal", withdraw_goal, block=False))
application.add_handler(CommandHandler("sbibuyinsurance", buy_insurance, block=False))
application.add_handler(CommandHandler("sbibuypremium", buy_premium, block=False))
application.add_handler(CommandHandler("sbisetpin", set_pin, block=False))
application.add_handler(CommandHandler("sbifreeze", freeze_account, block=False))
application.add_handler(CommandHandler("sbiunfreeze", unfreeze_account, block=False))
application.add_handler(CommandHandler("sbiseuprd", setup_rd, block=False))
application.add_handler(CommandHandler("sbistoprd", stop_rd, block=False))
application.add_handler(CommandHandler("sbileaderboard", leaderboard, block=False))
application.add_handler(CommandHandler("sbireferral", referral, block=False))
application.add_handler(CommandHandler("sbigamble", gamble, block=False))
application.add_handler(CommandHandler("sbibankhelp", bank_help, block=False))

application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(sbibal_|sbibank_|sbiloan_|sbirepay_|sbiclr_|sbipok_|sbipno_|sbiinvest_|sbigoals_|sbiinsurance_|sbihistory_)", block=False))