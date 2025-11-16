import math
import random
import asyncio
import hashlib
import aiohttp
from datetime import datetime, timedelta
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection, collection

pay_cooldown = {}
pending_payments = {}
loan_check_lock = asyncio.Lock()
pin_attempts = {}
insurance_claims = {}

BANK_CFG = {
    'int_rate': 0.05,
    'premium_int_rate': 0.06,
    'loan_int': 0.10,
    'max_loan': 100000,
    'max_premium_loan': 200000,
    'loan_days': 3,
    'emergency_loan_days': 2,
    'emergency_loan_limit': 3,
    'penalty': 0.20,
    'emergency_penalty': 0.30,
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
    'insurance_premium': 500,
    'insurance_char_coverage': 100000,
    'insurance_deposit_coverage': 50000,
    'premium_fee': 5000,
    'premium_daily_bonus': 500,
    'max_pin_attempts': 3,
    'pin_lockout_hours': 24
}

STOCK_SYMBOLS = {
    'nifty50': '^NSEI',
    'banknifty': '^NSEBANK',
    'reliance': 'RELIANCE.NS',
    'tcs': 'TCS.NS',
    'infosys': 'INFY.NS',
    'hdfc': 'HDFCBANK.NS',
    'icici': 'ICICIBANK.NS',
    'sbi': 'SBIN.NS',
    'bharti': 'BHARTIARTL.NS',
    'itc': 'ITC.NS'
}

def fmt_time(s):
    h, r = divmod(int(s), 3600)
    m, s = divmod(r, 60)
    if h >= 24:
        d, h = h // 24, h % 24
        return f"{d}d {h}h {m}m"
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

def safe_html(text):
    return escape(str(text))

def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()

async def get_stock_price(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data['chart']['result'][0]
                    meta = result['meta']
                    
                    current_price = meta.get('regularMarketPrice', 0)
                    previous_close = meta.get('previousClose', current_price)
                    change = current_price - previous_close
                    change_percent = (change / previous_close * 100) if previous_close > 0 else 0
                    
                    market_state = meta.get('marketState', 'CLOSED')
                    
                    return {
                        'price': round(current_price, 2),
                        'previous_close': round(previous_close, 2),
                        'change': round(change, 2),
                        'change_percent': round(change_percent, 2),
                        'market_state': market_state,
                        'currency': meta.get('currency', 'INR')
                    }
                return None
    except Exception as e:
        print(f"Stock fetch error for {symbol}: {e}")
        return None

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
        'loan_type': None,
        'emergency_loan_count': 0,
        'notifications': [],
        'permanent_debt': 0,
        'characters': [],
        'transactions': [],
        'credit_score': 700,
        'fixed_deposits': [],
        'investments': [],
        'insurance': {
            'char': False,
            'deposit': False,
            'last_premium_char': None,
            'last_premium_deposit': None
        },
        'premium': False,
        'premium_expiry': None,
        'achievements': [],
        'pin': None,
        'frozen': False,
        'pin_locked_until': None,
        'failed_attempts': 0,
        'recurring_deposit': {
            'active': False,
            'amount': 0,
            'frequency': 'daily',
            'last_deposit': None
        },
        'loan_history': [],
        'spending_limit': {
            'daily': 50000,
            'used': 0,
            'reset_date': None
        }
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
    await add_transaction(uid, 'interest', interest, f"Daily interest {int(rate*100)}%")
    return interest

async def get_char_value(cid):
    cdata = await collection.find_one({'id': cid})
    if not cdata:
        return 5000
    rarity = cdata.get('rarity', '🟢 Common')
    return BANK_CFG['char_value'].get(rarity, 5000)

async def check_insurance_validity(uid, insurance_type):
    user = await get_user(uid)
    insurance = user.get('insurance', {})
    
    if insurance_type == 'char':
        if not insurance.get('char'):
            return False
        last_premium = insurance.get('last_premium_char')
        if last_premium and (datetime.utcnow() - last_premium).days >= 30:
            await user_collection.update_one(
                {'id': uid},
                {'$set': {'insurance.char': False}}
            )
            return False
        return True
    elif insurance_type == 'deposit':
        if not insurance.get('deposit'):
            return False
        last_premium = insurance.get('last_premium_deposit')
        if last_premium and (datetime.utcnow() - last_premium).days >= 30:
            await user_collection.update_one(
                {'id': uid},
                {'$set': {'insurance.deposit': False}}
            )
            return False
        return True
    return False

async def process_insurance_claim(uid, claim_type, amount):
    if claim_type == 'char':
        coverage = BANK_CFG['insurance_char_coverage']
    elif claim_type == 'deposit':
        coverage = BANK_CFG['insurance_deposit_coverage']
    else:
        return 0
    
    covered = min(amount, coverage)
    await user_collection.update_one(
        {'id': uid},
        {'$set': {f'insurance.{claim_type}': False}}
    )
    
    claim_id = f"{uid}_{int(datetime.utcnow().timestamp())}"
    insurance_claims[claim_id] = {
        'user_id': uid,
        'type': claim_type,
        'amount': covered,
        'timestamp': datetime.utcnow()
    }
    
    return covered

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
                        await add_transaction(uid, 'fd_maturity', total, f"FD matured: {fd['days']} days")
                        
                        msg = f"<b>FD Matured</b>\n\nPrincipal: {principal}\nInterest: {interest}\nTotal: {total}\n\nCredited to bank"
                        
                        await user_collection.update_one(
                            {'id': uid},
                            {'$push': {'notifications': {'type': 'fd_maturity', 'message': msg, 'timestamp': now}}}
                        )
                        
                        try:
                            await application.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                        except:
                            pass
        except Exception as e:
            print(f"FD error: {e}")

async def check_loans():
    async with loan_check_lock:
        while True:
            try:
                now = datetime.utcnow()
                async for user in user_collection.find({'loan_amount': {'$gt': 0}, 'loan_due_date': {'$lt': now}}):
                    uid = user['id']
                    loan = user.get('loan_amount', 0)
                    loan_type = user.get('loan_type', 'normal')
                    
                    penalty_rate = BANK_CFG['emergency_penalty'] if loan_type == 'emergency' else BANK_CFG['penalty']
                    penalty = int(loan * penalty_rate)
                    total = loan + penalty
                    
                    bal = user.get('balance', 0)
                    bank = user.get('bank', 0)
                    
                    has_deposit_insurance = await check_insurance_validity(uid, 'deposit')
                    covered_amount = 0
                    if has_deposit_insurance:
                        covered_amount = await process_insurance_claim(uid, 'deposit', total)
                        total -= covered_amount
                    
                    funds = bal + bank
                    seized = []
                    remaining_debt = 0

                    if bal >= total:
                        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -total}, '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_type': None, 'permanent_debt': 0}})
                        seized.append(f"{total} gold from wallet")
                        await update_credit_score(uid, -50)
                    elif funds >= total:
                        await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': bank - (total - bal), 'loan_amount': 0, 'loan_due_date': None, 'loan_type': None, 'permanent_debt': 0}})
                        seized.append(f"{bal} gold from wallet")
                        seized.append(f"{total - bal} gold from bank")
                        await update_credit_score(uid, -50)
                    else:
                        if funds > 0:
                            await user_collection.update_one({'id': uid}, {'$set': {'balance': 0, 'bank': 0}})
                            seized.append(f"{funds} gold (all funds)")
                        
                        remaining_debt = total - funds
                        chars = user.get('characters', [])
                        has_char_insurance = await check_insurance_validity(uid, 'char')
                        
                        if chars and not has_char_insurance:
                            seized_chars = []
                            for cid in chars[:]:
                                if remaining_debt <= 0:
                                    break
                                
                                char_value = await get_char_value(cid)
                                cdata = await collection.find_one({'id': cid})
                                cname = safe_html(cdata.get('name', 'Unknown')) if cdata else 'Unknown'
                                crarity = cdata.get('rarity', 'Common') if cdata else 'Common'
                                
                                seized.append(f"{cname} ({crarity}) - Value: {char_value} gold")
                                seized_chars.append(cid)
                                remaining_debt -= char_value
                            
                            for cid in seized_chars:
                                chars.remove(cid)
                            
                            if remaining_debt <= 0:
                                await user_collection.update_one({'id': uid}, {'$set': {'characters': chars, 'loan_amount': 0, 'loan_due_date': None, 'loan_type': None, 'permanent_debt': 0}})
                            else:
                                await user_collection.update_one({'id': uid}, {'$set': {'characters': chars, 'loan_amount': 0, 'loan_due_date': None, 'loan_type': None, 'permanent_debt': remaining_debt}})
                                seized.append(f"Remaining debt: {remaining_debt} gold")
                        else:
                            if has_char_insurance:
                                char_coverage = await process_insurance_claim(uid, 'char', remaining_debt)
                                remaining_debt -= char_coverage
                                seized.append(f"Insurance covered: {char_coverage} gold")
                            
                            await user_collection.update_one({'id': uid}, {'$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_type': None, 'permanent_debt': max(0, remaining_debt)}})
                            if remaining_debt > 0:
                                seized.append(f"Permanent debt: {remaining_debt} gold")
                        
                        await update_credit_score(uid, -100)

                    await user_collection.update_one(
                        {'id': uid},
                        {'$push': {'loan_history': {'amount': loan, 'penalty': penalty, 'date': now, 'type': loan_type, 'status': 'defaulted'}}}
                    )

                    time_str = now.strftime("%d/%m/%Y %H:%M UTC")
                    msg = f"<b>Loan Collected</b>\n\nLoan: {loan}\nPenalty: {penalty}\nTotal: {loan + penalty}"
                    if covered_amount > 0:
                        msg += f"\nInsurance Coverage: {covered_amount}"
                    msg += f"\nTime: {time_str}\n\n<b>Seized:</b>\n" + "\n".join(f"• {i}" for i in seized)

                    await user_collection.update_one({'id': uid}, {'$push': {'notifications': {'type': 'loan_collection', 'message': msg, 'timestamp': now}}})

                    try:
                        await application.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                    except:
                        pass

            except Exception as e:
                print(f"Loan error: {e}")
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
                    await add_transaction(uid, 'debt_deduction', -deduction, "Daily debt deduction")
                    
                    msg = f"<b>Debt Deduction</b>\n\nDeducted: {deduction}\nRemaining: {new_debt}\nBalance: {new_bal}"
                    
                    if new_debt <= 0:
                        msg += "\n\nDebt cleared!"
                        await update_credit_score(uid, 50)
                    
                    try:
                        await application.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
                    except:
                        pass
                        
        except Exception as e:
            print(f"Debt error: {e}")

async def check_insurance():
    while True:
        try:
            await asyncio.sleep(86400)
            now = datetime.utcnow()
            async for user in user_collection.find({'$or': [{'insurance.char': True}, {'insurance.deposit': True}]}):
                uid = user['id']
                insurance = user.get('insurance', {})
                
                if insurance.get('char'):
                    last_premium = insurance.get('last_premium_char')
                    if last_premium and (now - last_premium).days >= 30:
                        bal = user.get('balance', 0)
                        premium = BANK_CFG['insurance_premium']
                        
                        if bal >= premium:
                            await user_collection.update_one(
                                {'id': uid},
                                {'$inc': {'balance': -premium}, '$set': {'insurance.last_premium_char': now}}
                            )
                            await add_transaction(uid, 'insurance', -premium, "Character insurance premium")
                        else:
                            await user_collection.update_one(
                                {'id': uid},
                                {'$set': {'insurance.char': False}}
                            )
                            try:
                                await application.bot.send_message(
                                    chat_id=uid,
                                    text="<b>⚠️ Insurance Cancelled</b>\n\nCharacter insurance cancelled due to insufficient funds",
                                    parse_mode="HTML"
                                )
                            except:
                                pass
                
                if insurance.get('deposit'):
                    last_premium = insurance.get('last_premium_deposit')
                    if last_premium and (now - last_premium).days >= 30:
                        bal = user.get('balance', 0)
                        premium = BANK_CFG['insurance_premium']
                        
                        if bal >= premium:
                            await user_collection.update_one(
                                {'id': uid},
                                {'$inc': {'balance': -premium}, '$set': {'insurance.last_premium_deposit': now}}
                            )
                            await add_transaction(uid, 'insurance', -premium, "Deposit insurance premium")
                        else:
                            await user_collection.update_one(
                                {'id': uid},
                                {'$set': {'insurance.deposit': False}}
                            )
                            try:
                                await application.bot.send_message(
                                    chat_id=uid,
                                    text="<b>⚠️ Insurance Cancelled</b>\n\nDeposit insurance cancelled due to insufficient funds",
                                    parse_mode="HTML"
                                )
                            except:
                                pass
        except Exception as e:
            print(f"Insurance error: {e}")

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
                        await add_transaction(uid, 'recurring_deposit', amount, f"Auto deposit ({frequency})")
                    else:
                        await user_collection.update_one(
                            {'id': uid},
                            {'$set': {'recurring_deposit.active': False}}
                        )
        except Exception as e:
            print(f"RD error: {e}")

async def process_investments():
    while True:
        try:
            await asyncio.sleep(1800)
            async for user in user_collection.find({'investments': {'$exists': True, '$ne': []}}):
                uid = user['id']
                investments = user.get('investments', [])
                updated = False
                
                for inv in investments:
                    if inv['type'] == 'stock':
                        symbol = inv.get('symbol')
                        if symbol and symbol in STOCK_SYMBOLS:
                            stock_data = await get_stock_price(STOCK_SYMBOLS[symbol])
                            if stock_data:
                                current_price = stock_data['price']
                                units = inv.get('units', 1)
                                inv['current_price'] = current_price
                                inv['value'] = int(units * current_price)
                                updated = True
                    elif inv['type'] == 'bond':
                        inv['value'] = int(inv['value'] * 1.005)
                        updated = True
                    elif inv['type'] == 'mutual_fund':
                        risk = inv.get('risk', 'medium')
                        if risk == 'low':
                            change = random.uniform(-0.05, 0.08)
                        elif risk == 'medium':
                            change = random.uniform(-0.10, 0.15)
                        else:
                            change = random.uniform(-0.20, 0.30)
                        inv['value'] = int(inv['value'] * (1 + change))
                        updated = True
                
                if updated:
                    await user_collection.update_one({'id': uid}, {'$set': {'investments': investments}})
        except Exception as e:
            print(f"Investment error: {e}")

async def post_init(app):
    asyncio.create_task(check_loans())
    asyncio.create_task(deduct_debt())
    asyncio.create_task(check_fd_maturity())
    asyncio.create_task(check_insurance())
    asyncio.create_task(check_recurring_deposits())
    asyncio.create_task(process_investments())

async def verify_pin(uid, pin):
    user = await get_user(uid)
    if not user:
        return False
    
    locked_until = user.get('pin_locked_until')
    if locked_until and datetime.utcnow() < locked_until:
        remaining = (locked_until - datetime.utcnow()).total_seconds()
        return f"locked:{int(remaining)}"
    
    stored_pin = user.get('pin')
    if not stored_pin:
        return False
    
    if hash_pin(pin) == stored_pin:
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'failed_attempts': 0}}
        )
        return True
    else:
        failed = user.get('failed_attempts', 0) + 1
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'failed_attempts': failed}}
        )
        
        if failed >= BANK_CFG['max_pin_attempts']:
            lockout_time = datetime.utcnow() + timedelta(hours=BANK_CFG['pin_lockout_hours'])
            await user_collection.update_one(
                {'id': uid},
                {'$set': {'pin_locked_until': lockout_time, 'failed_attempts': 0}}
            )
            return f"locked:{BANK_CFG['pin_lockout_hours'] * 3600}"
        
        return False

async def balance_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await init_user(uid)
        user = await get_user(uid)
    
    if user.get('frozen'):
        await update.message.reply_text("⚠️ Account frozen\nUse /unlockaccount &lt;pin&gt;", parse_mode="HTML")
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
    
    msg = f"<b>💰 Balance Report</b>\n\nWallet: <code>{wallet}</code>\nBank: <code>{bank}</code>"
    
    if fd_total > 0:
        msg += f"\nFixed Deposits: <code>{fd_total}</code>"
    if inv_total > 0:
        msg += f"\nInvestments: <code>{inv_total}</code>"
    
    msg += f"\nNet Worth: <code>{total}</code>"
    
    if credit:
        rank = "Excellent" if credit >= 800 else "Good" if credit >= 700 else "Fair" if credit >= 600 else "Poor"
        msg += f"\nCredit Score: <code>{credit}</code> ({rank})"
    
    if loan > 0:
        due = user.get('loan_due_date')
        if due:
            left = (due - datetime.utcnow()).total_seconds()
            loan_type = user.get('loan_type', 'normal')
            type_emoji = "⚡" if loan_type == 'emergency' else "💳"
            msg += f"\n\n{type_emoji} Active Loan: <code>{loan}</code>\nDue in: {fmt_time(left)}"
    if debt > 0:
        msg += f"\n\n🔴 Permanent Debt: <code>{debt}</code>\nDaily Deduction: 10%"
    if interest > 0:
        msg += f"\n\n✨ Interest Earned: <code>+{interest}</code>"
    
    if user.get('premium'):
        expiry = user.get('premium_expiry')
        if expiry:
            days = (expiry - datetime.utcnow()).days
            msg += f"\n\n💎 Premium Active: {days} days left"
    
    btns = [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"bal_{uid}")],
        [InlineKeyboardButton("🏦 Bank", callback_data=f"bank_{uid}"), InlineKeyboardButton("💳 Loans", callback_data=f"loan_{uid}")],
        [InlineKeyboardButton("📊 Invest", callback_data=f"invest_{uid}"), InlineKeyboardButton("🛡️ Insurance", callback_data=f"insure_{uid}")],
        [InlineKeyboardButton("📜 History", callback_data=f"history_{uid}")]
    ]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def deposit_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⚠️ Account frozen")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /deposit &lt;amount&gt;", parse_mode="HTML")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⚠️ Insufficient balance")
        return
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt, 'bank': amt}})
    await add_transaction(uid, 'deposit', amt, "Bank deposit")
    await update.message.reply_text(f"<b>✅ Deposited</b>\n\nAmount: <code>{amt}</code>\nDaily Interest: 5%", parse_mode="HTML")

async def withdraw_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⚠️ Account frozen")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /withdraw &lt;amount&gt;", parse_mode="HTML")
        return
    
    if user.get('bank', 0) < amt:
        await update.message.reply_text("⚠️ Insufficient bank balance")
        return
    
    await user_collection.update_one({'id': uid}, {'$inc': {'bank': -amt, 'balance': amt}})
    await add_transaction(uid, 'withdraw', amt, "Withdrawal")
    await update.message.reply_text(f"<b>✅ Withdrawn</b>\n\nAmount: <code>{amt}</code>", parse_mode="HTML")

async def getloan_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⚠️ Account frozen")
        return
    
    debt = user.get('permanent_debt', 0)
    if debt > 0:
        await update.message.reply_text(f"<b>❌ Outstanding Debt</b>\n\nDebt: <code>{debt}</code>\n\nClear debt first with /cleardebt", parse_mode="HTML")
        return
    
    curr = user.get('loan_amount', 0)
    if curr > 0:
        due = user.get('loan_due_date')
        left = (due - datetime.utcnow()).total_seconds()
        loan_type = user.get('loan_type', 'normal')
        type_name = "Emergency" if loan_type == 'emergency' else "Regular"
        msg = f"<b>Active {type_name} Loan</b>\n\nAmount: <code>{curr}</code>\nDue in: {fmt_time(left)}\n\nRepay with /repayloan"
        btns = [[InlineKeyboardButton("💰 Repay", callback_data=f"repay_{uid}")]]
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
        await update.message.reply_text(f"Usage: /getloan &lt;amount&gt;\n\nMax Loan: <code>{max_loan:,}</code>\nInterest Rate: <code>{rate}%</code>\nDuration: 3 days", parse_mode="HTML")
        return
    
    credit = user.get('credit_score', 700)
    max_loan = BANK_CFG['max_premium_loan'] if user.get('premium') else BANK_CFG['max_loan']
    
    if amt > max_loan:
        await update.message.reply_text(f"⚠️ Maximum loan: {max_loan:,}")
        return
    
    rate = 0.05 if credit >= 800 else 0.08 if credit >= 700 else BANK_CFG['loan_int']
    interest = int(amt * rate)
    total = amt + interest
    due = datetime.utcnow() + timedelta(days=BANK_CFG['loan_days'])
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': amt}, '$set': {'loan_amount': total, 'loan_due_date': due, 'loan_type': 'normal'}})
    await add_transaction(uid, 'loan', amt, f"Loan ({int(rate*100)}%)")
    await update.message.reply_text(f"<b>✅ Loan Approved</b>\n\nLoan Amount: <code>{amt}</code>\nInterest: <code>{interest}</code>\nTotal Payable: <code>{total}</code>\nDue: 3 days\n\n⚠️ Penalty: 20% if late", parse_mode="HTML")

async def emergency_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⚠️ Account frozen")
        return
    
    emergency_count = user.get('emergency_loan_count', 0)
    debt = user.get('permanent_debt', 0)
    
    if emergency_count >= BANK_CFG['emergency_loan_limit']:
        if debt > 0:
            await update.message.reply_text(
                f"<b>⚠️ Emergency Loan Limit Reached</b>\n\n"
                f"You have taken {emergency_count}/3 emergency loans.\n\n"
                f"Outstanding Debt: <code>{debt}</code>\n\n"
                f"Clear your debt with /cleardebt to unlock emergency loans again.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"<b>⚠️ Emergency Loan Limit Reached</b>\n\n"
                f"You have taken {emergency_count}/3 emergency loans.\n\n"
                f"Repay your existing loans to unlock emergency loans again.",
                parse_mode="HTML"
            )
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0 or amt > 20000:
            raise ValueError
    except (IndexError, ValueError):
        remaining = BANK_CFG['emergency_loan_limit'] - emergency_count
        await update.message.reply_text(
            f"Usage: /emergencyloan &lt;amount&gt;\n\n"
            f"Max: 20,000\n"
            f"Interest: 15%\n"
            f"Duration: 2 days\n"
            f"Penalty: 30%\n\n"
            f"Emergency Loans: {emergency_count}/{BANK_CFG['emergency_loan_limit']}\n"
            f"Remaining: {remaining}\n\n"
            f"Available even with active loan",
            parse_mode="HTML"
        )
        return
    
    interest = int(amt * 0.15)
    total = amt + interest
    due = datetime.utcnow() + timedelta(days=BANK_CFG['emergency_loan_days'])
    
    curr_loan = user.get('loan_amount', 0)
    new_total = curr_loan + total
    new_count = emergency_count + 1
    
    await user_collection.update_one(
        {'id': uid}, 
        {
            '$inc': {'balance': amt}, 
            '$set': {
                'loan_amount': new_total, 
                'loan_due_date': due, 
                'loan_type': 'emergency',
                'emergency_loan_count': new_count
            }
        }
    )
    await add_transaction(uid, 'emergency', amt, "Emergency loan")
    
    remaining = BANK_CFG['emergency_loan_limit'] - new_count
    
    msg = f"<b>⚡ Emergency Loan Approved</b>\n\n"
    msg += f"Loan: <code>{amt}</code>\n"
    msg += f"Interest: <code>{interest}</code>\n"
    msg += f"Total: <code>{total}</code>\n"
    msg += f"Due: 2 days\n\n"
    msg += f"⚠️ Higher penalty: 30%\n\n"
    msg += f"Emergency Loans Used: {new_count}/{BANK_CFG['emergency_loan_limit']}\n"
    msg += f"Remaining: {remaining}"
    
    if curr_loan > 0:
        msg += f"\n\n<b>Total Debt:</b> <code>{new_total}</code>"
    
    if remaining == 0:
        msg += "\n\n🔴 <b>Limit Reached!</b>\nClear debt to unlock more."
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def repayloan_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    loan = user.get('loan_amount', 0)
    if loan <= 0:
        await update.message.reply_text("⚠️ No active loan")
        return
    
    bal = user.get('balance', 0)
    if bal < loan:
        await update.message.reply_text(f"⚠️ Insufficient balance\n\nNeed: <code>{loan}</code>\nHave: <code>{bal}</code>", parse_mode="HTML")
        return
    
    loan_type = user.get('loan_type', 'normal')
    
    update_data = {
        '$inc': {'balance': -loan}, 
        '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_type': None}
    }
    
    if loan_type == 'emergency':
        emergency_count = user.get('emergency_loan_count', 0)
        if emergency_count > 0:
            update_data['$set']['emergency_loan_count'] = emergency_count - 1
    
    await user_collection.update_one({'id': uid}, update_data)
    await user_collection.update_one({'id': uid}, {'$push': {'loan_history': {'amount': loan, 'date': datetime.utcnow(), 'type': loan_type, 'status': 'repaid'}}})
    await update_credit_score(uid, 20)
    await add_transaction(uid, 'repay', -loan, "Loan repaid")
    
    msg = f"<b>✅ Loan Repaid</b>\n\nPaid: <code>{loan}</code>\nNew Balance: <code>{bal - loan}</code>\n\n✨ Credit Score +20"
    
    if loan_type == 'emergency':
        new_count = max(0, emergency_count - 1)
        remaining = BANK_CFG['emergency_loan_limit'] - new_count
        msg += f"\n\n⚡ Emergency Loans: {new_count}/{BANK_CFG['emergency_loan_limit']}\nRemaining: {remaining}"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def cleardebt_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    debt = user.get('permanent_debt', 0)
    if debt <= 0:
        await update.message.reply_text("⚠️ No debt")
        return
    
    bal = user.get('balance', 0)
    if bal < debt:
        await update.message.reply_text(f"⚠️ Insufficient balance\n\nDebt: <code>{debt}</code>\nBalance: <code>{bal}</code>", parse_mode="HTML")
        return
    
    emergency_count = user.get('emergency_loan_count', 0)
    
    await user_collection.update_one(
        {'id': uid}, 
        {
            '$inc': {'balance': -debt}, 
            '$set': {'permanent_debt': 0, 'emergency_loan_count': 0}
        }
    )
    await update_credit_score(uid, 50)
    await add_transaction(uid, 'clear_debt', -debt, "Debt cleared")
    
    msg = f"<b>✅ Debt Cleared</b>\n\nPaid: <code>{debt}</code>\nNew Balance: <code>{bal - debt}</code>\n\n✅ Debt free!\n✨ Credit Score +50"
    
    if emergency_count > 0:
        msg += f"\n\n⚡ Emergency loans reset to 0/3"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def fixeddeposit_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    try:
        amt = int(context.args[0])
        days = int(context.args[1])
        if amt <= 0 or days not in [7, 15, 30]:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /fixeddeposit &lt;amount&gt; &lt;days&gt;\n\nDays: 7, 15, 30\nRates: 7%, 10%, 15%\nEarly withdrawal penalty: 3%", parse_mode="HTML")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⚠️ Insufficient balance")
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
    await add_transaction(uid, 'fd', -amt, f"FD ({days}d)")
    await update.message.reply_text(f"<b>✅ Fixed Deposit Created</b>\n\nAmount: <code>{amt}</code>\nDuration: <code>{days}</code> days\nRate: <code>{int(rate*100)}%</code>\nInterest: <code>{interest}</code>", parse_mode="HTML")

async def breakfd_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    fds = user.get('fixed_deposits', [])
    if not fds:
        await update.message.reply_text("⚠️ No fixed deposits")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(fds):
            raise ValueError
    except (IndexError, ValueError):
        msg = "<b>Your Fixed Deposits</b>\n\n"
        for i, fd in enumerate(fds, 1):
            days_left = (fd['maturity_date'] - datetime.utcnow()).days
            msg += f"{i}. <code>{fd['amount']}</code> - {days_left} days left\n"
        msg += "\nUsage: /breakfd &lt;number&gt;"
        await update.message.reply_text(msg, parse_mode="HTML")
        return
    
    fd = fds[idx]
    penalty = int(fd['amount'] * BANK_CFG['fd_penalty'])
    refund = fd['amount'] - penalty
    
    fds.pop(idx)
    await user_collection.update_one({'id': uid}, {'$set': {'fixed_deposits': fds}, '$inc': {'balance': refund}})
    await add_transaction(uid, 'break_fd', refund, f"FD broken (penalty: {penalty})")
    await update.message.reply_text(f"<b>FD Broken</b>\n\nPrincipal: <code>{fd['amount']}</code>\nPenalty: <code>{penalty}</code>\nRefund: <code>{refund}</code>", parse_mode="HTML")

async def notifications_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    notifs = user.get('notifications', [])
    if not notifs:
        await update.message.reply_text("⚠️ No notifications")
        return
    
    recent = notifs[-5:]
    msg = "<b>📬 Recent Notifications</b>\n\n"
    for i, n in enumerate(reversed(recent), 1):
        msg += f"<b>{i}.</b> {n.get('message', 'No message')}\n\n"
    btns = [[InlineKeyboardButton("🗑️ Clear All", callback_data=f"clear_{uid}")]]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def sendgold_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    sid = update.effective_user.id
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a user's message")
        return
    
    rec = update.message.reply_to_message.from_user
    if rec.id == sid:
        await update.message.reply_text("⚠️ Cannot send to yourself")
        return
    
    if rec.is_bot:
        await update.message.reply_text("⚠️ Cannot send to bots")
        return
    
    if sid in pay_cooldown:
        elapsed = (datetime.utcnow() - pay_cooldown[sid]).total_seconds()
        if elapsed < 600:
            await update.message.reply_text(f"⚠️ Cooldown: {fmt_time(600 - elapsed)}")
            return
    
    try:
        amt = int(context.args[0])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /sendgold &lt;amount&gt;", parse_mode="HTML")
        return
    
    if amt > 1000000:
        await update.message.reply_text("⚠️ Maximum: 1,000,000")
        return
    
    sender = await get_user(sid)
    if not sender or sender.get('balance', 0) < amt:
        await update.message.reply_text("⚠️ Insufficient balance")
        return
    
    pid = f"{sid}_{rec.id}_{int(datetime.utcnow().timestamp())}"
    pending_payments[pid] = {'sender_id': sid, 'recipient_id': rec.id, 'amount': amt}
    
    rec_name = safe_html(rec.first_name)
    btns = [[InlineKeyboardButton("✓ Confirm", callback_data=f"confirm_{pid}"), InlineKeyboardButton("✗ Cancel", callback_data=f"cancel_{pid}")]]
    await update.message.reply_text(f"<b>Confirm Transfer</b>\n\nTo: <b>{rec_name}</b>\nAmount: <code>{amt}</code>\n\nExpires in 30s", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
    asyncio.create_task(expire_pay(pid))

async def expire_pay(pid):
    await asyncio.sleep(30)
    if pid in pending_payments:
        del pending_payments[pid]

async def dailyreward_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await init_user(uid)
        user = await get_user(uid)
    
    last = user.get('last_daily')
    now = datetime.utcnow()
    if last and last.date() == now.date():
        remaining = timedelta(days=1) - (now - last)
        await update.message.reply_text(f"⚠️ Already claimed\nNext claim in: {fmt_time(remaining.total_seconds())}")
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
        await add_transaction(uid, 'daily', actual_amt, f"Daily (debt: -{deduction})")
        
        msg = f"<b>Daily Reward</b>\n\nEarned: <code>{daily_amt}</code>\nDeduction: <code>-{deduction}</code>\nReceived: <code>{actual_amt}</code>\n\n🔴 Debt: <code>{new_debt}</code>"
        
        if new_debt <= 0:
            msg += "\n\n✅ Debt cleared!"
    else:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': daily_amt, 'user_xp': 10}, '$set': {'last_daily': now}})
        await add_transaction(uid, 'daily', daily_amt, "Daily reward")
        msg = f"<b>Daily Reward</b>\n\nClaimed: <code>{daily_amt}</code>\nXP: +10"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def userlevel_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    xp = user.get('user_xp', 0)
    lvl = min(math.floor(math.sqrt(max(xp, 0) / 100)) + 1, 100)
    ranks = {10: "E", 30: "D", 50: "C", 70: "B", 90: "A", 100: "S"}
    rank = next((r for lim, r in ranks.items() if lvl <= lim), "S")
    needed = ((lvl) ** 2) * 100 - xp
    
    achievements = user.get('achievements', [])
    
    await update.message.reply_text(f"<b>Level and Rank</b>\n\nLevel: <code>{lvl}</code>\nRank: <code>{rank}</code>\nXP: <code>{xp}</code>\nNeeded: <code>{needed}</code>\nAchievements: <code>{len(achievements)}</code>", parse_mode="HTML")

async def txhistory_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    transactions = user.get('transactions', [])
    if not transactions:
        await update.message.reply_text("⚠️ No transactions")
        return
    
    recent = transactions[-10:]
    msg = "<b>📜 Transaction History</b>\n\n"
    
    for t in reversed(recent):
        ttype = safe_html(t.get('type', 'unknown'))
        amt = t.get('amount', 0)
        desc = safe_html(t.get('description', ''))
        timestamp = t.get('timestamp')
        date_str = timestamp.strftime('%d/%m %H:%M') if timestamp else 'N/A'
        
        emoji = "💰" if amt > 0 else "💸"
        msg += f"{emoji} <code>{amt:+d}</code> • {ttype}\n"
        if desc:
            msg += f"   {desc}\n"
        msg += f"   {date_str}\n\n"
    
    btns = [[InlineKeyboardButton("💰 Balance", callback_data=f"bal_{uid}")]]
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def investstock_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    try:
        symbol = context.args[0].lower()
        amt = int(context.args[1])
        if amt <= 0:
            raise ValueError
    except (IndexError, ValueError):
        stock_list = "\n".join([f"• {k}" for k in list(STOCK_SYMBOLS.keys())[:5]])
        await update.message.reply_text(f"Usage: /investstock &lt;symbol&gt; &lt;amount&gt;\n\n<b>Available Stocks:</b>\n{stock_list}\n\nUse /stocklist for all", parse_mode="HTML")
        return
    
    if symbol not in STOCK_SYMBOLS:
        await update.message.reply_text("⚠️ Invalid stock symbol\nUse /stocklist to see available stocks")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⚠️ Insufficient balance")
        return
    
    stock_data = await get_stock_price(STOCK_SYMBOLS[symbol])
    if not stock_data:
        await update.message.reply_text("⚠️ Unable to fetch stock price. Try again later.")
        return
    
    current_price = stock_data['price']
    change = stock_data['change']
    change_percent = stock_data['change_percent']
    market_state = stock_data['market_state']
    
    units = amt / current_price
    
    investment = {
        'type': 'stock',
        'symbol': symbol,
        'name': symbol.upper(),
        'value': amt,
        'initial': amt,
        'buy_price': current_price,
        'current_price': current_price,
        'units': units,
        'created': datetime.utcnow()
    }
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt}, '$push': {'investments': investment}})
    await add_transaction(uid, 'invest', -amt, f"Stock: {symbol.upper()}")
    
    emoji = "📈" if change >= 0 else "📉"
    sign = "+" if change >= 0 else ""
    
    market_status = "🟢 Open" if market_state in ['REGULAR', 'PRE', 'POST'] else "🔴 Closed"
    
    await update.message.reply_text(
        f"<b>✅ Stock Purchased</b>\n\n"
        f"Stock: <b>{symbol.upper()}</b>\n"
        f"Price: ₹{current_price} {emoji} {sign}{change_percent}%\n"
        f"Units: {units:.4f}\n"
        f"Invested: <code>{amt}</code>\n"
        f"Market: {market_status}\n\n"
        f"Use /portfolio to view",
        parse_mode="HTML"
    )

async def stocklist_cmd(update: Update, context: CallbackContext):
    msg = "<b>📈 Live Stock Market</b>\n\n"
    
    market_open = False
    for symbol, code in STOCK_SYMBOLS.items():
        stock_data = await get_stock_price(code)
        if stock_data:
            price = stock_data['price']
            change = stock_data['change']
            change_percent = stock_data['change_percent']
            market_state = stock_data['market_state']
            
            if market_state in ['REGULAR', 'PRE', 'POST']:
                market_open = True
            
            if change >= 0:
                emoji = "📈"
                sign = "+"
            else:
                emoji = "📉"
                sign = ""
            
            msg += f"<b>{symbol.upper()}</b>\n"
            msg += f"₹{price} {emoji} {sign}{change} ({sign}{change_percent}%)\n\n"
        else:
            msg += f"<b>{symbol.upper()}</b> - N/A\n\n"
    
    ist_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
    current_time = ist_time.strftime("%I:%M %p IST")
    
    if market_open:
        status = "🟢 Market Open"
    else:
        hour = ist_time.hour
        if 0 <= hour < 9 or (hour == 9 and ist_time.minute < 15):
            status = "🔴 Pre-Market (Opens 9:15 AM)"
        elif hour >= 15 and ist_time.minute >= 30:
            status = "🔴 Market Closed (Opens 9:15 AM)"
        elif ist_time.weekday() >= 5:
            status = "🔴 Weekend (Opens Monday 9:15 AM)"
        else:
            status = "🟢 Market Hours (9:15 AM - 3:30 PM)"
    
    msg += f"<b>Status:</b> {status}\n"
    msg += f"<b>Time:</b> {current_time}\n\n"
    msg += "Usage: /investstock &lt;symbol&gt; &lt;amount&gt;"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def portfolio_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    investments = user.get('investments', [])
    if not investments:
        await update.message.reply_text("⚠️ No investments")
        return
    
    msg = "<b>📊 Investment Portfolio</b>\n\n"
    total_value = 0
    total_initial = 0
    
    for i, inv in enumerate(investments, 1):
        name = safe_html(inv.get('name', 'Unknown'))
        initial = inv.get('initial', 0)
        
        if inv['type'] == 'stock':
            symbol = inv.get('symbol')
            stock_data = await get_stock_price(STOCK_SYMBOLS.get(symbol, ''))
            
            if stock_data:
                current_price = stock_data['price']
                units = inv.get('units', 0)
                value = int(units * current_price)
                
                inv['current_price'] = current_price
                inv['value'] = value
                
                change = ((value - initial) / initial * 100) if initial > 0 else 0
                price_change = stock_data['change']
                price_change_percent = stock_data['change_percent']
                
                emoji = "📈" if change >= 0 else "📉"
                price_emoji = "🟢" if price_change >= 0 else "🔴"
                sign = "+" if price_change >= 0 else ""
                
                msg += f"{i}. <b>{name}</b> {price_emoji}\n"
                msg += f"   Units: {units:.4f} × ₹{current_price}\n"
                msg += f"   Day Change: {sign}{price_change_percent}%\n"
                msg += f"   Initial: <code>{initial}</code>\n"
                msg += f"   Current: <code>{value}</code>\n"
                msg += f"   {emoji} <code>{change:+.2f}%</code>\n\n"
            else:
                value = inv.get('value', initial)
                change = ((value - initial) / initial * 100) if initial > 0 else 0
                emoji = "📈" if change >= 0 else "📉"
                
                msg += f"{i}. <b>{name}</b>\n"
                msg += f"   Initial: <code>{initial}</code>\n"
                msg += f"   Current: <code>{value}</code>\n"
                msg += f"   {emoji} <code>{change:+.2f}%</code>\n\n"
        else:
            value = inv.get('value', 0)
            change = ((value - initial) / initial * 100) if initial > 0 else 0
            emoji = "📈" if change >= 0 else "📉"
            
            msg += f"{i}. {name}\n"
            msg += f"   Initial: <code>{initial}</code>\n"
            msg += f"   Current: <code>{value}</code>\n"
            msg += f"   {emoji} <code>{change:+.2f}%</code>\n\n"
        
        total_value += value
        total_initial += initial
    
    await user_collection.update_one({'id': uid}, {'$set': {'investments': investments}})
    
    total_change = ((total_value - total_initial) / total_initial * 100) if total_initial > 0 else 0
    overall_emoji = "📈" if total_change >= 0 else "📉"
    
    msg += f"<b>Total Investment:</b> <code>{total_initial}</code>\n"
    msg += f"<b>Current Value:</b> <code>{total_value}</code>\n"
    msg += f"<b>Overall P&L:</b> {overall_emoji} <code>{total_change:+.2f}%</code>\n\n"
    msg += "Use /sellinvest &lt;number&gt; to sell"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def sellinvest_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    investments = user.get('investments', [])
    if not investments:
        await update.message.reply_text("⚠️ No investments")
        return
    
    try:
        idx = int(context.args[0]) - 1
        if idx < 0 or idx >= len(investments):
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /sellinvest &lt;number&gt;\n\nUse /portfolio to see list", parse_mode="HTML")
        return
    
    inv = investments[idx]
    value = inv.get('value', 0)
    initial = inv.get('initial', 0)
    profit = value - initial
    
    investments.pop(idx)
    await user_collection.update_one({'id': uid}, {'$set': {'investments': investments}, '$inc': {'balance': value}})
    await add_transaction(uid, 'sell', value, f"{inv.get('name', 'inv')}")
    
    msg = f"<b>✅ Investment Sold</b>\n\nType: {safe_html(inv.get('name', 'Unknown'))}\nInitial: <code>{initial}</code>\nSold For: <code>{value}</code>\nProfit: <code>{profit:+d}</code>"
    await update.message.reply_text(msg, parse_mode="HTML")

async def buyinsurance_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    try:
        itype = context.args[0].lower()
        if itype not in ['character', 'deposit']:
            raise ValueError
    except (IndexError, ValueError):
        char_cov = BANK_CFG['insurance_char_coverage']
        dep_cov = BANK_CFG['insurance_deposit_coverage']
        await update.message.reply_text(f"Usage: /buyinsurance &lt;type&gt;\n\n<b>Types:</b>\n• character - Protect characters (up to {char_cov:,})\n• deposit - Cover loan defaults (up to {dep_cov:,})\n\nPremium: 500 gold/month\nAuto-renewal from wallet", parse_mode="HTML")
        return
    
    premium = BANK_CFG['insurance_premium']
    if user.get('balance', 0) < premium:
        await update.message.reply_text("⚠️ Insufficient balance")
        return
    
    insurance = user.get('insurance', {})
    ins_key = 'char' if itype == 'character' else 'deposit'
    premium_key = f'last_premium_{ins_key}'
    
    if insurance.get(ins_key):
        await update.message.reply_text("⚠️ Already have this insurance")
        return
    
    insurance[ins_key] = True
    insurance[premium_key] = datetime.utcnow()
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -premium}, '$set': {'insurance': insurance}})
    await add_transaction(uid, 'insurance', -premium, f"Insurance: {itype}")
    
    iname = "Character" if itype == 'character' else "Deposit"
    coverage = BANK_CFG['insurance_char_coverage'] if itype == 'character' else BANK_CFG['insurance_deposit_coverage']
    await update.message.reply_text(f"<b>✅ Insurance Purchased</b>\n\nType: {iname}\nCoverage: {coverage:,}\nPremium: <code>{premium}</code>\nValid: 30 days\n\n🛡️ Protected", parse_mode="HTML")

async def buypremium_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    fee = BANK_CFG['premium_fee']
    if user.get('balance', 0) < fee:
        await update.message.reply_text(f"⚠️ Insufficient balance\n\nCost: {fee}")
        return
    
    expiry = datetime.utcnow() + timedelta(days=30)
    
    await user_collection.update_one({'id': uid}, {'$inc': {'balance': -fee}, '$set': {'premium': True, 'premium_expiry': expiry}})
    await add_transaction(uid, 'premium', -fee, "Premium (30d)")
    
    await update.message.reply_text(f"<b>💎 Premium Activated</b>\n\nDuration: 30 days\nCost: <code>{fee}</code>\n\n<b>Benefits:</b>\n✓ +500 daily reward\n✓ +1% interest rate\n✓ 200k max loan\n✓ Lower interest rates", parse_mode="HTML")

async def setpin_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    try:
        pin = context.args[0]
        if len(pin) != 4 or not pin.isdigit():
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setpin &lt;4-digit&gt;\n\nExample: /setpin 1234\n\nKeep your PIN secure!", parse_mode="HTML")
        return
    
    hashed = hash_pin(pin)
    await user_collection.update_one({'id': uid}, {'$set': {'pin': hashed, 'failed_attempts': 0, 'pin_locked_until': None}})
    await update.message.reply_text("<b>✅ PIN Set</b>\n\nAccount secured\nUse /lockaccount to lock\n\n⚠️ Don't share your PIN!", parse_mode="HTML")

async def lockaccount_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    if not user.get('pin'):
        await update.message.reply_text("⚠️ Set PIN first\n\nUse /setpin &lt;4-digit&gt;", parse_mode="HTML")
        return
    
    if user.get('frozen'):
        await update.message.reply_text("⚠️ Account already locked")
        return
    
    await user_collection.update_one({'id': uid}, {'$set': {'frozen': True}})
    await update.message.reply_text("<b>🔒 Account Locked</b>\n\nAccount frozen\nAll transactions blocked\n\nUse /unlockaccount &lt;pin&gt; to unlock", parse_mode="HTML")

async def unlockaccount_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    if not user.get('frozen'):
        await update.message.reply_text("⚠️ Account not locked")
        return
    
    try:
        pin = context.args[0]
    except IndexError:
        await update.message.reply_text("Usage: /unlockaccount &lt;pin&gt;", parse_mode="HTML")
        return
    
    result = await verify_pin(uid, pin)
    
    if isinstance(result, str) and result.startswith("locked:"):
        remaining = int(result.split(":")[1])
        await update.message.reply_text(f"⚠️ Too many failed attempts\n\nAccount locked for: {fmt_time(remaining)}")
        return
    
    if not result:
        user = await get_user(uid)
        attempts_left = BANK_CFG['max_pin_attempts'] - user.get('failed_attempts', 0)
        await update.message.reply_text(f"⚠️ Incorrect PIN\n\nAttempts remaining: {attempts_left}")
        return
    
    await user_collection.update_one({'id': uid}, {'$set': {'frozen': False}})
    await update.message.reply_text("<b>🔓 Account Unlocked</b>\n\nAccount active\nTransactions enabled", parse_mode="HTML")

async def changepin_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    if not user.get('pin'):
        await update.message.reply_text("⚠️ No PIN set\n\nUse /setpin first")
        return
    
    try:
        old_pin = context.args[0]
        new_pin = context.args[1]
        if len(new_pin) != 4 or not new_pin.isdigit():
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /changepin &lt;old_pin&gt; &lt;new_pin&gt;\n\nExample: /changepin 1234 5678", parse_mode="HTML")
        return
    
    result = await verify_pin(uid, old_pin)
    
    if isinstance(result, str) and result.startswith("locked:"):
        remaining = int(result.split(":")[1])
        await update.message.reply_text(f"⚠️ Account locked\n\nTry again in: {fmt_time(remaining)}")
        return
    
    if not result:
        user = await get_user(uid)
        attempts_left = BANK_CFG['max_pin_attempts'] - user.get('failed_attempts', 0)
        await update.message.reply_text(f"⚠️ Incorrect old PIN\n\nAttempts remaining: {attempts_left}")
        return
    
    hashed = hash_pin(new_pin)
    await user_collection.update_one({'id': uid}, {'$set': {'pin': hashed, 'failed_attempts': 0}})
    await update.message.reply_text("<b>✅ PIN Changed</b>\n\nNew PIN set successfully", parse_mode="HTML")

async def autosetup_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    try:
        amt = int(context.args[0])
        freq = context.args[1].lower()
        if amt <= 0 or freq not in ['daily', 'weekly']:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /autosetup &lt;amount&gt; &lt;frequency&gt;\n\nFrequency: daily, weekly\nAuto-deposit to bank", parse_mode="HTML")
        return
    
    rd = {
        'active': True,
        'amount': amt,
        'frequency': freq,
        'last_deposit': None
    }
    
    await user_collection.update_one({'id': uid}, {'$set': {'recurring_deposit': rd}})
    await update.message.reply_text(f"<b>✅ Auto-Deposit Set</b>\n\nAmount: <code>{amt}</code>\nFrequency: {freq}\n\n🔄 Activated", parse_mode="HTML")

async def autostop_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ No data")
        return
    
    rd = user.get('recurring_deposit', {})
    if not rd.get('active'):
        await update.message.reply_text("⚠️ No active auto-deposit")
        return
    
    rd['active'] = False
    await user_collection.update_one({'id': uid}, {'$set': {'recurring_deposit': rd}})
    await update.message.reply_text("<b>✅ Auto-Deposit Stopped</b>\n\nDisabled", parse_mode="HTML")

async def leaderboard_cmd(update: Update, context: CallbackContext):
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
            name = safe_html(u.first_name)
        except:
            name = "Unknown"
        
        top_users.append({'name': name, 'net_worth': net_worth})
    
    if not top_users:
        await update.message.reply_text("⚠️ No data")
        return
    
    msg = "<b>🏆 Top 10 Richest Users</b>\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(top_users, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        msg += f"{medal} <b>{u['name']}</b>\n   <code>{u['net_worth']:,}</code>\n\n"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def gamble_cmd(update: Update, context: CallbackContext):
    if not update.effective_user:
        return
    
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("⚠️ Use /balance first")
        return
    
    try:
        amt = int(context.args[0])
        if amt <= 0 or amt > 10000:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /gamble &lt;amount&gt;\n\nMax: 10,000\nDouble or lose\nWin chance: 45%", parse_mode="HTML")
        return
    
    if user.get('balance', 0) < amt:
        await update.message.reply_text("⚠️ Insufficient balance")
        return
    
    win = random.random() < 0.45
    
    if win:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': amt, 'user_xp': 5}})
        await add_transaction(uid, 'gamble_win', amt, "Gamble won")
        msg = f"<b>🎰 WIN!</b>\n\nBet: <code>{amt}</code>\nWon: <code>{amt}</code>\nTotal: <code>+{amt}</code>\n\n🎉 Congratulations!"
    else:
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -amt}})
        await add_transaction(uid, 'gamble_loss', -amt, "Gamble lost")
        msg = f"<b>🎰 LOST</b>\n\nBet: <code>{amt}</code>\nLost: <code>{amt}</code>\n\n💔 Better luck next time!"
    
    await update.message.reply_text(msg, parse_mode="HTML")

async def vaulthelp_cmd(update: Update, context: CallbackContext):
    help_text = """<b>💰 Vault System Commands</b>

<b>📊 Basic</b>
/bal - View balance
/deposit - Deposit to bank
/withdraw - Withdraw from bank
/cclaim - Claim daily reward

<b>💳 Loans</b>
/getloan - Borrow money (100k max)
/emergencyloan - Fast loan (20k, even with active loan)
/repayloan - Repay active loan
/cleardebt - Clear permanent debt

<b>🔒 Fixed Deposits</b>
/fixeddeposit - Create FD
/breakfd - Break FD early

<b>📈 Investments</b>
/investstock - Buy stocks
/stocklist - View available stocks
/portfolio - View portfolio
/sellinvest - Sell investment

<b>🛡️ Security</b>
/buyinsurance - Purchase insurance
/setpin - Set account PIN
/changepin - Change PIN
/lockaccount - Lock account
/unlockaccount - Unlock account

<b>💎 Premium</b>
/buypremium - Upgrade to premium

<b>🔄 Automation</b>
/autosetup - Auto-deposit
/autostop - Stop auto-deposit

<b>📜 Other</b>
/txhistory - Transaction history
/pay - Send gold (reply to user)
/userlevel - View level and rank
/leaders - Top 10 richest
/bgamble - Gamble gold
/notifications - View alerts"""

    btns = [[InlineKeyboardButton("💰 View Balance", callback_data=f"bal_{update.effective_user.id}")]]
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

async def callback_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    if not q or not q.data:
        return
    
    data = q.data
    uid = q.from_user.id

    valid_prefixes = ("bal_", "bank_", "loan_", "repay_", "clear_", "confirm_", "cancel_", "invest_", "insure_", "history_")
    if not data.startswith(valid_prefixes):
        return

    await q.answer()

    if data.startswith("bal_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        if not user:
            await q.answer("⚠️ Use /balance", show_alert=True)
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
        
        msg = f"<b>💰 Balance Report</b>\n\nWallet: <code>{wallet}</code>\nBank: <code>{bank}</code>"
        
        if fd_total > 0:
            msg += f"\nFixed Deposits: <code>{fd_total}</code>"
        if inv_total > 0:
            msg += f"\nInvestments: <code>{inv_total}</code>"
        
        msg += f"\nNet Worth: <code>{total}</code>"
        
        if credit:
            rank = "Excellent" if credit >= 800 else "Good" if credit >= 700 else "Fair" if credit >= 600 else "Poor"
            msg += f"\nCredit: <code>{credit}</code> ({rank})"
        
        if loan > 0:
            due = user.get('loan_due_date')
            if due:
                left = (due - datetime.utcnow()).total_seconds()
                loan_type = user.get('loan_type', 'normal')
                type_emoji = "⚡" if loan_type == 'emergency' else "💳"
                msg += f"\n\n{type_emoji} Loan: <code>{loan}</code>\nDue: {fmt_time(left)}"
        if debt > 0:
            msg += f"\n\n🔴 Debt: <code>{debt}</code>"
        if interest > 0:
            msg += f"\n\n✨ +<code>{interest}</code>"
        
        if user.get('premium'):
            expiry = user.get('premium_expiry')
            if expiry:
                days = (expiry - datetime.utcnow()).days
                msg += f"\n\n💎 Premium: {days}d"
        
        btns = [
            [InlineKeyboardButton("🔄", callback_data=f"bal_{uid}")],
            [InlineKeyboardButton("🏦", callback_data=f"bank_{uid}"), InlineKeyboardButton("💳", callback_data=f"loan_{uid}")],
            [InlineKeyboardButton("📊", callback_data=f"invest_{uid}"), InlineKeyboardButton("🛡️", callback_data=f"insure_{uid}")],
            [InlineKeyboardButton("📜", callback_data=f"history_{uid}")]
        ]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓")

    elif data.startswith("bank_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        bank = user.get('bank', 0)
        wallet = user.get('balance', 0)
        fds = user.get('fixed_deposits', [])
        
        msg = f"<b>🏦 Bank Details</b>\n\nBank Balance: <code>{bank}</code>\nWallet: <code>{wallet}</code>\nInterest: 5% daily\nFixed Deposits: <code>{len(fds)}</code>\n\n/deposit &lt;amount&gt;\n/withdraw &lt;amount&gt;\n/fixeddeposit &lt;amount&gt; &lt;days&gt;"
        btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("loan_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        debt = user.get('permanent_debt', 0)
        
        if debt > 0:
            emergency_count = user.get('emergency_loan_count', 0)
            msg = f"<b>🔴 Outstanding Debt</b>\n\nDebt: <code>{debt}</code>\nDaily Deduction: 10%\n\n"
            if emergency_count > 0:
                msg += f"⚡ Emergency Loans: {emergency_count}/3\n\n"
            msg += "/cleardebt"
            btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
            return

        loan = user.get('loan_amount', 0)
        credit = user.get('credit_score', 700)
        emergency_count = user.get('emergency_loan_count', 0)
        
        if loan > 0:
            due = user.get('loan_due_date')
            left = (due - datetime.utcnow()).total_seconds()
            loan_type = user.get('loan_type', 'normal')
            type_name = "Emergency" if loan_type == 'emergency' else "Regular"
            
            msg = f"<b>💳 Active {type_name} Loan</b>\n\nAmount: <code>{loan}</code>\nDue: {fmt_time(left)}\n\n"
            if loan_type == 'emergency':
                remaining = BANK_CFG['emergency_loan_limit'] - emergency_count
                msg += f"⚡ Emergency: {emergency_count}/{BANK_CFG['emergency_loan_limit']}\n\n"
            msg += "/repayloan"
            
            btns = [[InlineKeyboardButton("💰 Repay", callback_data=f"repay_{uid}")], [InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        else:
            max_loan = 200000 if user.get('premium') else 100000
            rate = 5 if credit >= 800 else 8 if credit >= 700 else 10
            emergency_remaining = BANK_CFG['emergency_loan_limit'] - emergency_count
            
            msg = f"<b>💳 Loan Information</b>\n\n"
            msg += f"Max Loan: <code>{max_loan:,}</code>\n"
            msg += f"Interest Rate: <code>{rate}%</code>\n"
            msg += f"Duration: 3 days\n"
            msg += f"Credit Score: <code>{credit}</code>\n\n"
            msg += f"⚡ Emergency: {emergency_count}/{BANK_CFG['emergency_loan_limit']}\n"
            msg += f"Available: {emergency_remaining}\n\n"
            msg += "/getloan &lt;amount&gt;\n/emergencyloan &lt;amount&gt;"
            
            btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
            await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("invest_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        invs = user.get('investments', [])
        total_value = sum(inv['value'] for inv in invs)
        
        msg = f"<b>📊 Investments</b>\n\nPortfolio Items: <code>{len(invs)}</code>\nTotal Value: <code>{total_value}</code>\n\n<b>Real Stocks Available:</b>\nNifty 50, Bank Nifty, Reliance, TCS, Infosys, HDFC, ICICI, SBI\n\n/stocklist - View all\n/investstock &lt;symbol&gt; &lt;amount&gt;\n/portfolio\n/sellinvest &lt;number&gt;"
        btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("insure_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        insurance = user.get('insurance', {})
        
        char_ins = await check_insurance_validity(uid, 'char')
        dep_ins = await check_insurance_validity(uid, 'deposit')
        
        char_status = "✅ Active" if char_ins else "❌ Inactive"
        dep_status = "✅ Active" if dep_ins else "❌ Inactive"
        
        char_cov = BANK_CFG['insurance_char_coverage']
        dep_cov = BANK_CFG['insurance_deposit_coverage']
        
        msg = f"<b>🛡️ Insurance</b>\n\nCharacter Protection: {char_status}\n• Coverage: {char_cov:,}\n\nDeposit Coverage: {dep_status}\n• Coverage: {dep_cov:,}\n\nPremium: 500/month\nAuto-renewal\n\n/buyinsurance &lt;type&gt;"
        btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("history_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        transactions = user.get('transactions', [])
        
        if not transactions:
            msg = "<b>📜 Transaction History</b>\n\n⚠️ No transactions"
        else:
            recent = transactions[-5:]
            msg = "<b>📜 Recent Transactions</b>\n\n"
            
            for t in reversed(recent):
                amt = t.get('amount', 0)
                ttype = safe_html(t.get('type', 'unknown'))
                emoji = "💰" if amt > 0 else "💸"
                msg += f"{emoji} <code>{amt:+d}</code> • {ttype}\n"
            
            msg += "\n/txhistory for full list"
        
        btns = [[InlineKeyboardButton("⬅️ Back", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("repay_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        user = await get_user(uid)
        loan = user.get('loan_amount', 0)
        
        if loan <= 0:
            await q.answer("⚠️ No active loan", show_alert=True)
            return

        bal = user.get('balance', 0)
        if bal < loan:
            await q.answer(f"⚠️ Need: {loan}\nHave: {bal}", show_alert=True)
            return

        loan_type = user.get('loan_type', 'normal')
        await user_collection.update_one({'id': uid}, {'$inc': {'balance': -loan}, '$set': {'loan_amount': 0, 'loan_due_date': None, 'loan_type': None}})
        await user_collection.update_one({'id': uid}, {'$push': {'loan_history': {'amount': loan, 'date': datetime.utcnow(), 'type': loan_type, 'status': 'repaid'}}})
        await update_credit_score(uid, 20)
        await add_transaction(uid, 'repay', -loan, "Repaid")
        
        new_bal = bal - loan
        msg = f"<b>✅ Loan Repaid</b>\n\nPaid: <code>{loan}</code>\nBalance: <code>{new_bal}</code>\n\n✨ Credit Score +20"
        btns = [[InlineKeyboardButton("💰 Balance", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓")

    elif data.startswith("clear_"):
        target = int(data.split("_")[1])
        if uid != target:
            await q.answer("⚠️ Not your account", show_alert=True)
            return

        await user_collection.update_one({'id': uid}, {'$set': {'notifications': []}})
        await q.edit_message_text("<b>✅ Notifications Cleared</b>\n\nAll notifications removed", parse_mode="HTML")
        await q.answer("✓")

    elif data.startswith("confirm_"):
        pid = data.split("_", 1)[1]
        if pid not in pending_payments:
            await q.edit_message_text("<b>⚠️ Expired</b>\n\nPayment request expired", parse_mode="HTML")
            await q.answer("⚠️ Expired", show_alert=True)
            return

        payment = pending_payments[pid]
        if uid != payment['sender_id']:
            await q.answer("⚠️ Not your payment", show_alert=True)
            return

        sender = await get_user(payment['sender_id'])
        if not sender or sender.get('balance', 0) < payment['amount']:
            await q.edit_message_text("<b>⚠️ Failed</b>\n\nInsufficient balance", parse_mode="HTML")
            del pending_payments[pid]
            await q.answer("⚠️ Insufficient balance", show_alert=True)
            return

        recipient = await get_user(payment['recipient_id'])
        if not recipient:
            await init_user(payment['recipient_id'])

        await user_collection.update_one({'id': payment['sender_id']}, {'$inc': {'balance': -payment['amount']}})
        await user_collection.update_one({'id': payment['recipient_id']}, {'$inc': {'balance': payment['amount']}})
        await add_transaction(payment['sender_id'], 'payment', -payment['amount'], "Paid")
        await add_transaction(payment['recipient_id'], 'received', payment['amount'], "Received")
        pay_cooldown[payment['sender_id']] = datetime.utcnow()

        try:
            recipient_user = await context.bot.get_chat(payment['recipient_id'])
            recipient_name = safe_html(recipient_user.first_name)
        except:
            recipient_name = "Unknown"

        del pending_payments[pid]

        msg = f"<b>✅ Transfer Complete</b>\n\nTo: <b>{recipient_name}</b>\nAmount: <code>{payment['amount']}</code>\n\n✅ Success"
        btns = [[InlineKeyboardButton("💰 Balance", callback_data=f"bal_{uid}")]]
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(btns))
        await q.answer("✓")

    elif data.startswith("cancel_"):
        pid = data.split("_", 1)[1]
        if pid in pending_payments:
            payment = pending_payments[pid]
            if uid != payment['sender_id']:
                await q.answer("⚠️ Not your payment", show_alert=True)
                return
            del pending_payments[pid]

        await q.edit_message_text("<b>✗ Cancelled</b>\n\nPayment cancelled", parse_mode="HTML")
        await q.answer("✗")

application.post_init = post_init

application.add_handler(CommandHandler("bal", balance_cmd, block=False))
application.add_handler(CommandHandler("deposit", deposit_cmd, block=False))
application.add_handler(CommandHandler("withdraw", withdraw_cmd, block=False))
application.add_handler(CommandHandler("getloan", getloan_cmd, block=False))
application.add_handler(CommandHandler("emergencyloan", emergency_cmd, block=False))
application.add_handler(CommandHandler("repayloan", repayloan_cmd, block=False))
application.add_handler(CommandHandler("cleardebt", cleardebt_cmd, block=False))
application.add_handler(CommandHandler("fixeddeposit", fixeddeposit_cmd, block=False))
application.add_handler(CommandHandler("breakfd", breakfd_cmd, block=False))
application.add_handler(CommandHandler("notifications", notifications_cmd, block=False))
application.add_handler(CommandHandler("pay", sendgold_cmd, block=False))
application.add_handler(CommandHandler("cclaim", dailyreward_cmd, block=False))
application.add_handler(CommandHandler("userlevel", userlevel_cmd, block=False))
application.add_handler(CommandHandler("txhistory", txhistory_cmd, block=False))
application.add_handler(CommandHandler("investstock", investstock_cmd, block=False))
application.add_handler(CommandHandler("stocklist", stocklist_cmd, block=False))
application.add_handler(CommandHandler("portfolio", portfolio_cmd, block=False))
application.add_handler(CommandHandler("sellinvest", sellinvest_cmd, block=False))
application.add_handler(CommandHandler("buyinsurance", buyinsurance_cmd, block=False))
application.add_handler(CommandHandler("buypremium", buypremium_cmd, block=False))
application.add_handler(CommandHandler("setpin", setpin_cmd, block=False))
application.add_handler(CommandHandler("changepin", changepin_cmd, block=False))
application.add_handler(CommandHandler("lockaccount", lockaccount_cmd, block=False))
application.add_handler(CommandHandler("unlockaccount", unlockaccount_cmd, block=False))
application.add_handler(CommandHandler("autosetup", autosetup_cmd, block=False))
application.add_handler(CommandHandler("autostop", autostop_cmd, block=False))
application.add_handler(CommandHandler("leaders", leaderboard_cmd, block=False))
application.add_handler(CommandHandler("bgamble", gamble_cmd, block=False))
application.add_handler(CommandHandler("bankhelp", vaulthelp_cmd, block=False))

application.add_handler(CallbackQueryHandler(callback_handler, pattern="^(bal_|bank_|loan_|repay_|clear_|confirm_|cancel_|invest_|insure_|history_)", block=False))