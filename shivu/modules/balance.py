import math
import random
import asyncio
import hashlib
import aiohttp
import logging
from datetime import datetime, timedelta
from html import escape
from typing import Dict, List, Optional, Tuple, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection, collection

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants and Configuration
BANK_CFG = {
    'interest_rates': {
        'regular': 0.05,
        'premium': 0.06,
        'loan': 0.10,
        'emergency_loan': 0.15,
    },
    'loan_limits': {
        'regular': 100000,
        'premium': 200000,
        'emergency': 20000
    },
    'loan_durations': {
        'regular': 3,  # days
        'emergency': 2,  # days
    },
    'penalties': {
        'loan_default': 0.20,
        'emergency_default': 0.30,
        'fd_break': 0.03
    },
    'character_values': {
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
    'fixed_deposit': {
        'rates': {7: 0.07, 15: 0.10, 30: 0.15},
        'minimum_amount': 1000
    },
    'insurance': {
        'premium': 500,
        'character_coverage': 100000,
        'deposit_coverage': 50000
    },
    'premium': {
        'fee': 5000,
        'daily_bonus': 500,
        'duration_days': 30
    },
    'security': {
        'max_pin_attempts': 3,
        'pin_lockout_hours': 24,
        'payment_cooldown': 600  # seconds
    },
    'daily': {
        'regular_reward': 2000,
        'premium_reward': 2500,
        'debt_deduction': 0.10
    }
}

STOCK_SYMBOLS = {
    'nifty50': {'symbol': '^NSEI', 'name': 'NIFTY 50'},
    'banknifty': {'symbol': '^NSEBANK', 'name': 'BANK NIFTY'},
    'reliance': {'symbol': 'RELIANCE.NS', 'name': 'Reliance Industries'},
    'tcs': {'symbol': 'TCS.NS', 'name': 'Tata Consultancy Services'},
    'infosys': {'symbol': 'INFY.NS', 'name': 'Infosys'},
    'hdfc': {'symbol': 'HDFCBANK.NS', 'name': 'HDFC Bank'},
    'icici': {'symbol': 'ICICIBANK.NS', 'name': 'ICICI Bank'},
    'sbi': {'symbol': 'SBIN.NS', 'name': 'State Bank of India'},
    'bharti': {'symbol': 'BHARTIARTL.NS', 'name': 'Bharti Airtel'},
    'itc': {'symbol': 'ITC.NS', 'name': 'ITC Limited'}
}

# Global states
pay_cooldown: Dict[int, datetime] = {}
pending_payments: Dict[str, Dict] = {}
pin_attempts: Dict[int, Dict] = {}
insurance_claims: Dict[str, Dict] = {}
loan_check_lock = asyncio.Lock()


class BankFormatter:
    """Utility class for formatting bank-related text"""
    
    @staticmethod
    def format_time(seconds: int) -> str:
        """Format seconds into human readable time"""
        if seconds < 0:
            return "Expired"
        
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 and days == 0:  # Don't show seconds if days exist
            parts.append(f"{seconds}s")
            
        return " ".join(parts) if parts else "0s"
    
    @staticmethod
    def format_currency(amount: int) -> str:
        """Format currency with commas"""
        return f"{amount:,}"
    
    @staticmethod
    def safe_html(text: str) -> str:
        """Escape HTML characters"""
        return escape(str(text))
    
    @staticmethod
    def format_loan_type(loan_type: str) -> str:
        """Format loan type for display"""
        types = {
            'normal': '💳 Regular Loan',
            'emergency': '⚡ Emergency Loan'
        }
        return types.get(loan_type, '💳 Loan')


class BankSecurity:
    """Handles security-related operations"""
    
    @staticmethod
    def hash_pin(pin: str) -> str:
        """Hash PIN for secure storage"""
        return hashlib.sha256(pin.encode()).hexdigest()
    
    @staticmethod
    async def verify_pin(user_id: int, pin: str) -> Tuple[bool, Optional[str]]:
        """Verify user PIN with lockout mechanism"""
        user = await user_collection.find_one({'id': user_id})
        if not user:
            return False, "User not found"
        
        # Check if account is locked
        locked_until = user.get('pin_locked_until')
        if locked_until and datetime.utcnow() < locked_until:
            remaining = (locked_until - datetime.utcnow()).total_seconds()
            return False, f"Account locked for {BankFormatter.format_time(remaining)}"
        
        stored_pin = user.get('pin')
        if not stored_pin:
            return False, "No PIN set"
        
        if BankSecurity.hash_pin(pin) == stored_pin:
            # Reset failed attempts on successful login
            await user_collection.update_one(
                {'id': user_id},
                {'$set': {'failed_attempts': 0}}
            )
            return True, None
        else:
            # Increment failed attempts
            failed = user.get('failed_attempts', 0) + 1
            await user_collection.update_one(
                {'id': user_id},
                {'$set': {'failed_attempts': failed}}
            )
            
            # Check if should lock account
            if failed >= BANK_CFG['security']['max_pin_attempts']:
                lockout_time = datetime.utcnow() + timedelta(
                    hours=BANK_CFG['security']['pin_lockout_hours']
                )
                await user_collection.update_one(
                    {'id': user_id},
                    {'$set': {
                        'pin_locked_until': lockout_time,
                        'failed_attempts': 0
                    }}
                )
                return False, f"Account locked for {BANK_CFG['security']['pin_lockout_hours']} hours"
            
            attempts_left = BANK_CFG['security']['max_pin_attempts'] - failed
            return False, f"Incorrect PIN. {attempts_left} attempts remaining"


class BankOperations:
    """Core banking operations"""
    
    @staticmethod
    async def get_user(user_id: int) -> Optional[Dict]:
        """Get user from database"""
        return await user_collection.find_one({'id': user_id})
    
    @staticmethod
    async def init_user(user_id: int) -> None:
        """Initialize new user in database"""
        user_data = {
            'id': user_id,
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
                'reset_date': datetime.utcnow().date()
            }
        }
        await user_collection.insert_one(user_data)
    
    @staticmethod
    async def add_transaction(user_id: int, ttype: str, amount: int, description: str = "") -> None:
        """Add transaction to user history"""
        transaction = {
            'type': ttype,
            'amount': amount,
            'description': description,
            'timestamp': datetime.utcnow()
        }
        
        await user_collection.update_one(
            {'id': user_id},
            {'$push': {'transactions': {'$each': [transaction], '$position': 0}}}
        )
        
        # Keep only last 100 transactions
        await user_collection.update_one(
            {'id': user_id},
            {'$push': {
                'transactions': {
                    '$each': [],
                    '$slice': 100
                }
            }}
        )
    
    @staticmethod
    async def calculate_interest(user_id: int) -> int:
        """Calculate and apply daily interest"""
        user = await BankOperations.get_user(user_id)
        if not user:
            return 0
        
        bank_balance = user.get('bank', 0)
        if bank_balance <= 0:
            return 0
        
        # Check if interest was already calculated today
        last_interest = user.get('last_interest')
        now = datetime.utcnow()
        if last_interest and (now - last_interest).total_seconds() < 86400:
            return 0
        
        # Determine interest rate
        if user.get('premium'):
            rate = BANK_CFG['interest_rates']['premium']
        else:
            rate = BANK_CFG['interest_rates']['regular']
        
        interest = int(bank_balance * rate)
        
        # Update user record
        await user_collection.update_one(
            {'id': user_id},
            {
                '$inc': {'bank': interest},
                '$set': {'last_interest': now}
            }
        )
        
        # Add transaction record
        await BankOperations.add_transaction(
            user_id,
            'interest',
            interest,
            f"Daily interest {int(rate * 100)}%"
        )
        
        return interest
    
    @staticmethod
    async def get_character_value(character_id: int) -> int:
        """Get market value of a character"""
        character = await collection.find_one({'id': character_id})
        if not character:
            return 5000  # Default value
        
        rarity = character.get('rarity', '🟢 Common')
        return BANK_CFG['character_values'].get(rarity, 5000)


class StockMarket:
    """Handle stock market operations"""
    
    @staticmethod
    async def get_stock_price(symbol_code: str) -> Optional[Dict]:
        """Fetch current stock price from Yahoo Finance"""
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_code}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if 'chart' not in data or 'result' not in data['chart'] or not data['chart']['result']:
                            return None
                        
                        result = data['chart']['result'][0]
                        meta = result['meta']
                        
                        current_price = meta.get('regularMarketPrice', 0)
                        previous_close = meta.get('previousClose', current_price)
                        change = current_price - previous_close
                        change_percent = (change / previous_close * 100) if previous_close > 0 else 0
                        
                        return {
                            'price': round(current_price, 2),
                            'previous_close': round(previous_close, 2),
                            'change': round(change, 2),
                            'change_percent': round(change_percent, 2),
                            'market_state': meta.get('marketState', 'CLOSED'),
                            'currency': meta.get('currency', 'INR'),
                            'volume': meta.get('regularMarketVolume', 0)
                        }
        except Exception as e:
            logger.error(f"Stock fetch error for {symbol_code}: {e}")
            return None
    
    @staticmethod
    def get_market_status() -> str:
        """Get current market status based on IST time"""
        utc_now = datetime.utcnow()
        ist_time = utc_now + timedelta(hours=5, minutes=30)
        
        # Market hours: 9:15 AM to 3:30 PM IST, Monday to Friday
        market_open = (
            0 <= ist_time.weekday() <= 4 and  # Monday to Friday
            (
                (ist_time.hour == 9 and ist_time.minute >= 15) or
                (10 <= ist_time.hour <= 14) or
                (ist_time.hour == 15 and ist_time.minute <= 30)
            )
        )
        
        return "OPEN" if market_open else "CLOSED"


class BankCommands:
    """Handle all bank-related commands"""
    
    @staticmethod
    async def balance_command(update: Update, context: CallbackContext) -> None:
        """Display user's balance and financial overview"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        # Initialize user if not exists
        if not user:
            await BankOperations.init_user(user_id)
            user = await BankOperations.get_user(user_id)
        
        # Check if account is frozen
        if user.get('frozen'):
            await update.message.reply_text(
                "🔒 <b>Account Frozen</b>\n\n"
                "Your account has been locked for security reasons.\n"
                "Use /unlockaccount &lt;PIN&gt; to unlock.",
                parse_mode="HTML"
            )
            return
        
        # Calculate interest
        interest_earned = await BankOperations.calculate_interest(user_id)
        
        # Get updated user data
        user = await BankOperations.get_user(user_id)
        
        # Calculate totals
        wallet = user.get('balance', 0)
        bank = user.get('bank', 0)
        loan = user.get('loan_amount', 0)
        debt = user.get('permanent_debt', 0)
        credit_score = user.get('credit_score', 700)
        
        # Fixed deposits
        fds = user.get('fixed_deposits', [])
        fd_total = sum(fd['amount'] for fd in fds)
        
        # Investments
        investments = user.get('investments', [])
        inv_total = sum(inv.get('value', 0) for inv in investments)
        
        # Calculate net worth
        total_assets = wallet + bank + fd_total + inv_total
        total_liabilities = loan + debt
        net_worth = total_assets - total_liabilities
        
        # Format message
        message = [
            "🏦 <b>Financial Overview</b>",
            "━" * 30,
            f"💰 <b>Wallet:</b> <code>{BankFormatter.format_currency(wallet)}</code>",
            f"🏛️ <b>Bank Balance:</b> <code>{BankFormatter.format_currency(bank)}</code>"
        ]
        
        if fd_total > 0:
            message.append(f"📅 <b>Fixed Deposits:</b> <code>{BankFormatter.format_currency(fd_total)}</code>")
        
        if inv_total > 0:
            message.append(f"📈 <b>Investments:</b> <code>{BankFormatter.format_currency(inv_total)}</code>")
        
        message.extend([
            "",
            "📊 <b>Summary</b>",
            f"• Total Assets: <code>{BankFormatter.format_currency(total_assets)}</code>",
            f"• Net Worth: <code>{BankFormatter.format_currency(net_worth)}</code>",
            f"• Credit Score: <code>{credit_score}</code>"
        ])
        
        # Add loan info if any
        if loan > 0:
            due_date = user.get('loan_due_date')
            if due_date:
                time_left = (due_date - datetime.utcnow()).total_seconds()
                loan_type = user.get('loan_type', 'normal')
                loan_display = BankFormatter.format_loan_type(loan_type)
                
                message.extend([
                    "",
                    f"{loan_display}",
                    f"• Amount: <code>{BankFormatter.format_currency(loan)}</code>",
                    f"• Due In: {BankFormatter.format_time(time_left)}"
                ])
        
        # Add debt info if any
        if debt > 0:
            message.extend([
                "",
                "🔴 <b>Outstanding Debt</b>",
                f"• Amount: <code>{BankFormatter.format_currency(debt)}</code>",
                f"• Daily Deduction: 10% of wallet balance"
            ])
        
        # Add interest earned if any
        if interest_earned > 0:
            message.extend([
                "",
                f"✨ <b>Interest Earned:</b> +<code>{BankFormatter.format_currency(interest_earned)}</code>"
            ])
        
        # Add premium status if applicable
        if user.get('premium'):
            expiry = user.get('premium_expiry')
            if expiry:
                days_left = (expiry - datetime.utcnow()).days
                message.extend([
                    "",
                    f"💎 <b>Premium Status</b>",
                    f"• Active for {days_left} more days"
                ])
        
        # Create keyboard
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_balance_{user_id}"),
                InlineKeyboardButton("📊 Portfolio", callback_data=f"portfolio_{user_id}")
            ],
            [
                InlineKeyboardButton("🏦 Bank", callback_data=f"bank_menu_{user_id}"),
                InlineKeyboardButton("💳 Loans", callback_data=f"loan_menu_{user_id}")
            ],
            [
                InlineKeyboardButton("📈 Invest", callback_data=f"invest_menu_{user_id}"),
                InlineKeyboardButton("🛡️ Insurance", callback_data=f"insurance_menu_{user_id}")
            ],
            [
                InlineKeyboardButton("📜 History", callback_data=f"history_{user_id}"),
                InlineKeyboardButton("⚙️ Settings", callback_data=f"settings_{user_id}")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "\n".join(message),
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    
    @staticmethod
    async def deposit_command(update: Update, context: CallbackContext) -> None:
        """Deposit money from wallet to bank"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "⚠️ <b>Account Not Found</b>\n\n"
                "Use /balance to create your account first.",
                parse_mode="HTML"
            )
            return
        
        # Check if account is frozen
        if user.get('frozen'):
            await update.message.reply_text(
                "🔒 <b>Account Frozen</b>\n\n"
                "Unlock your account first using /unlockaccount",
                parse_mode="HTML"
            )
            return
        
        # Validate amount
        try:
            amount = int(context.args[0])
            if amount <= 0:
                raise ValueError
        except (IndexError, ValueError):
            await update.message.reply_text(
                "📥 <b>Deposit Funds</b>\n\n"
                "<b>Usage:</b> <code>/deposit &lt;amount&gt;</code>\n"
                "<b>Example:</b> <code>/deposit 5000</code>\n\n"
                f"💼 <b>Wallet Balance:</b> <code>{BankFormatter.format_currency(user.get('balance', 0))}</code>",
                parse_mode="HTML"
            )
            return
        
        # Check sufficient funds
        if user.get('balance', 0) < amount:
            await update.message.reply_text(
                "❌ <b>Insufficient Funds</b>\n\n"
                f"<b>Required:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
                f"<b>Available:</b> <code>{BankFormatter.format_currency(user.get('balance', 0))}</code>",
                parse_mode="HTML"
            )
            return
        
        # Process deposit
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'balance': -amount, 'bank': amount}}
        )
        
        await BankOperations.add_transaction(
            user_id,
            'deposit',
            -amount,
            "Bank deposit"
        )
        
        # Get updated balance
        updated_user = await BankOperations.get_user(user_id)
        
        await update.message.reply_text(
            "✅ <b>Deposit Successful</b>\n\n"
            f"💰 <b>Amount:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
            f"💼 <b>New Wallet:</b> <code>{BankFormatter.format_currency(updated_user.get('balance', 0))}</code>\n"
            f"🏛️ <b>New Bank Balance:</b> <code>{BankFormatter.format_currency(updated_user.get('bank', 0))}</code>\n\n"
            f"✨ <b>Daily Interest:</b> {BANK_CFG['interest_rates']['premium']*100 if user.get('premium') else BANK_CFG['interest_rates']['regular']*100}%",
            parse_mode="HTML"
        )
    
    @staticmethod
    async def withdraw_command(update: Update, context: CallbackContext) -> None:
        """Withdraw money from bank to wallet"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "⚠️ <b>Account Not Found</b>\n\n"
                "Use /balance to create your account first.",
                parse_mode="HTML"
            )
            return
        
        # Check if account is frozen
        if user.get('frozen'):
            await update.message.reply_text(
                "🔒 <b>Account Frozen</b>\n\n"
                "Unlock your account first using /unlockaccount",
                parse_mode="HTML"
            )
            return
        
        # Validate amount
        try:
            amount = int(context.args[0])
            if amount <= 0:
                raise ValueError
        except (IndexError, ValueError):
            await update.message.reply_text(
                "📤 <b>Withdraw Funds</b>\n\n"
                "<b>Usage:</b> <code>/withdraw &lt;amount&gt;</code>\n"
                "<b>Example:</b> <code>/withdraw 5000</code>\n\n"
                f"🏛️ <b>Bank Balance:</b> <code>{BankFormatter.format_currency(user.get('bank', 0))}</code>",
                parse_mode="HTML"
            )
            return
        
        # Check sufficient bank balance
        if user.get('bank', 0) < amount:
            await update.message.reply_text(
                "❌ <b>Insufficient Bank Balance</b>\n\n"
                f"<b>Required:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
                f"<b>Available:</b> <code>{BankFormatter.format_currency(user.get('bank', 0))}</code>",
                parse_mode="HTML"
            )
            return
        
        # Process withdrawal
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'bank': -amount, 'balance': amount}}
        )
        
        await BankOperations.add_transaction(
            user_id,
            'withdrawal',
            amount,
            "Bank withdrawal"
        )
        
        # Get updated balance
        updated_user = await BankOperations.get_user(user_id)
        
        await update.message.reply_text(
            "✅ <b>Withdrawal Successful</b>\n\n"
            f"💰 <b>Amount:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
            f"💼 <b>New Wallet:</b> <code>{BankFormatter.format_currency(updated_user.get('balance', 0))}</code>\n"
            f"🏛️ <b>New Bank Balance:</b> <code>{BankFormatter.format_currency(updated_user.get('bank', 0))}</code>",
            parse_mode="HTML"
        )
    
    @staticmethod
    async def get_loan_command(update: Update, context: CallbackContext) -> None:
        """Apply for a loan"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "⚠️ <b>Account Not Found</b>\n\n"
                "Use /balance to create your account first.",
                parse_mode="HTML"
            )
            return
        
        # Check if account is frozen
        if user.get('frozen'):
            await update.message.reply_text(
                "🔒 <b>Account Frozen</b>\n\n"
                "Unlock your account first using /unlockaccount",
                parse_mode="HTML"
            )
            return
        
        # Check for existing debt
        if user.get('permanent_debt', 0) > 0:
            await update.message.reply_text(
                "❌ <b>Outstanding Debt</b>\n\n"
                "You have outstanding permanent debt that must be cleared before taking a new loan.\n\n"
                f"<b>Current Debt:</b> <code>{BankFormatter.format_currency(user.get('permanent_debt', 0))}</code>\n\n"
                "Use /cleardebt to clear your debt first.",
                parse_mode="HTML"
            )
            return
        
        # Check for existing loan
        existing_loan = user.get('loan_amount', 0)
        if existing_loan > 0:
            due_date = user.get('loan_due_date')
            loan_type = user.get('loan_type', 'normal')
            
            if due_date:
                time_left = (due_date - datetime.utcnow()).total_seconds()
                loan_display = BankFormatter.format_loan_type(loan_type)
                
                await update.message.reply_text(
                    f"⚠️ <b>Active Loan Found</b>\n\n"
                    f"{loan_display}\n"
                    f"<b>Amount:</b> <code>{BankFormatter.format_currency(existing_loan)}</code>\n"
                    f"<b>Due In:</b> {BankFormatter.format_time(time_left)}\n\n"
                    "You must repay your current loan before taking a new one.\n"
                    "Use /repayloan to repay.",
                    parse_mode="HTML"
                )
            return
        
        # Get loan amount
        try:
            amount = int(context.args[0])
            if amount <= 0:
                raise ValueError
        except (IndexError, ValueError):
            # Show loan information
            credit_score = user.get('credit_score', 700)
            is_premium = user.get('premium', False)
            
            max_loan = BANK_CFG['loan_limits']['premium'] if is_premium else BANK_CFG['loan_limits']['regular']
            
            # Determine interest rate based on credit score
            if credit_score >= 800:
                interest_rate = 5
            elif credit_score >= 700:
                interest_rate = 8
            else:
                interest_rate = BANK_CFG['interest_rates']['loan'] * 100
            
            await update.message.reply_text(
                "💳 <b>Loan Application</b>\n\n"
                "<b>Usage:</b> <code>/getloan &lt;amount&gt;</code>\n\n"
                f"📊 <b>Your Credit Score:</b> <code>{credit_score}</code>\n"
                f"💰 <b>Maximum Loan:</b> <code>{BankFormatter.format_currency(max_loan)}</code>\n"
                f"📈 <b>Interest Rate:</b> <code>{interest_rate}%</code>\n"
                f"⏳ <b>Repayment Period:</b> {BANK_CFG['loan_durations']['regular']} days\n\n"
                "<b>Example:</b> <code>/getloan 50000</code>",
                parse_mode="HTML"
            )
            return
        
        # Validate loan amount
        credit_score = user.get('credit_score', 700)
        is_premium = user.get('premium', False)
        max_loan = BANK_CFG['loan_limits']['premium'] if is_premium else BANK_CFG['loan_limits']['regular']
        
        if amount > max_loan:
            await update.message.reply_text(
                "❌ <b>Loan Limit Exceeded</b>\n\n"
                f"<b>Requested:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
                f"<b>Maximum Allowed:</b> <code>{BankFormatter.format_currency(max_loan)}</code>\n\n"
                f"Premium users can borrow up to {BankFormatter.format_currency(BANK_CFG['loan_limits']['premium'])}",
                parse_mode="HTML"
            )
            return
        
        # Calculate interest
        if credit_score >= 800:
            interest_rate = 0.05
        elif credit_score >= 700:
            interest_rate = 0.08
        else:
            interest_rate = BANK_CFG['interest_rates']['loan']
        
        interest = int(amount * interest_rate)
        total_payable = amount + interest
        
        # Set due date
        due_date = datetime.utcnow() + timedelta(days=BANK_CFG['loan_durations']['regular'])
        
        # Process loan
        await user_collection.update_one(
            {'id': user_id},
            {
                '$inc': {'balance': amount},
                '$set': {
                    'loan_amount': total_payable,
                    'loan_due_date': due_date,
                    'loan_type': 'normal'
                }
            }
        )
        
        await BankOperations.add_transaction(
            user_id,
            'loan_disbursed',
            amount,
            f"Loan ({int(interest_rate * 100)}% interest)"
        )
        
        # Update credit score slightly for taking a loan
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'credit_score': -5}}
        )
        
        await update.message.reply_text(
            "✅ <b>Loan Approved</b>\n\n"
            f"💰 <b>Amount Received:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
            f"📈 <b>Interest:</b> <code>{BankFormatter.format_currency(interest)}</code>\n"
            f"💳 <b>Total Repayment:</b> <code>{BankFormatter.format_currency(total_payable)}</code>\n"
            f"⏳ <b>Repayment Due:</b> {due_date.strftime('%d %b %Y')}\n\n"
            "⚠️ <b>Important:</b>\n"
            "• Late payment penalty: 20%\n"
            "• Use /repayloan to repay early\n"
            "• Default may lead to asset seizure",
            parse_mode="HTML"
        )
    
    @staticmethod
    async def emergency_loan_command(update: Update, context: CallbackContext) -> None:
        """Apply for emergency loan"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "⚠️ <b>Account Not Found</b>\n\n"
                "Use /balance to create your account first.",
                parse_mode="HTML"
            )
            return
        
        # Check if account is frozen
        if user.get('frozen'):
            await update.message.reply_text(
                "🔒 <b>Account Frozen</b>\n\n"
                "Unlock your account first using /unlockaccount",
                parse_mode="HTML"
            )
            return
        
        # Check emergency loan limit
        emergency_count = user.get('emergency_loan_count', 0)
        if emergency_count >= 3:
            await update.message.reply_text(
                "❌ <b>Emergency Loan Limit Reached</b>\n\n"
                "You have reached the maximum limit of 3 emergency loans.\n"
                "Clear your existing loans to be eligible again.",
                parse_mode="HTML"
            )
            return
        
        # Get loan amount
        try:
            amount = int(context.args[0])
            if amount <= 0 or amount > BANK_CFG['loan_limits']['emergency']:
                raise ValueError
        except (IndexError, ValueError):
            remaining_loans = 3 - emergency_count
            await update.message.reply_text(
                "⚡ <b>Emergency Loan</b>\n\n"
                "<b>Usage:</b> <code>/emergencyloan &lt;amount&gt;</code>\n\n"
                f"💰 <b>Maximum Amount:</b> <code>{BankFormatter.format_currency(BANK_CFG['loan_limits']['emergency'])}</code>\n"
                f"📈 <b>Interest Rate:</b> 15%\n"
                f"⏳ <b>Repayment Period:</b> {BANK_CFG['loan_durations']['emergency']} days\n"
                f"⚠️ <b>Late Penalty:</b> 30%\n\n"
                f"📊 <b>Emergency Loans Used:</b> {emergency_count}/3\n"
                f"🔄 <b>Remaining:</b> {remaining_loans}\n\n"
                "<b>Example:</b> <code>/emergencyloan 10000</code>",
                parse_mode="HTML"
            )
            return
        
        # Calculate interest
        interest = int(amount * BANK_CFG['interest_rates']['emergency_loan'])
        total_payable = amount + interest
        
        # Set due date
        due_date = datetime.utcnow() + timedelta(days=BANK_CFG['loan_durations']['emergency'])
        
        # Update existing loan if any
        existing_loan = user.get('loan_amount', 0)
        new_total = existing_loan + total_payable
        
        # Process emergency loan
        await user_collection.update_one(
            {'id': user_id},
            {
                '$inc': {
                    'balance': amount,
                    'emergency_loan_count': 1
                },
                '$set': {
                    'loan_amount': new_total,
                    'loan_due_date': due_date,
                    'loan_type': 'emergency'
                }
            }
        )
        
        await BankOperations.add_transaction(
            user_id,
            'emergency_loan',
            amount,
            "Emergency loan (15% interest)"
        )
        
        # Update credit score
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'credit_score': -10}}
        )
        
        remaining_loans = 2 - emergency_count
        
        await update.message.reply_text(
            "⚡ <b>Emergency Loan Approved</b>\n\n"
            f"💰 <b>Amount Received:</b> <code>{BankFormatter.format_currency(amount)}</code>\n"
            f"📈 <b>Interest:</b> <code>{BankFormatter.format_currency(interest)}</code>\n"
            f"💳 <b>Total Repayment:</b> <code>{BankFormatter.format_currency(total_payable)}</code>\n"
            f"⏳ <b>Repayment Due:</b> {due_date.strftime('%d %b %Y')}\n\n"
            f"📊 <b>Emergency Loans Used:</b> {emergency_count + 1}/3\n"
            f"🔄 <b>Remaining:</b> {remaining_loans}\n\n"
            "⚠️ <b>Important:</b>\n"
            "• Higher penalty of 30% for late payment\n"
            "• Combined with existing loans if any",
            parse_mode="HTML"
        )
    
    @staticmethod
    async def repay_loan_command(update: Update, context: CallbackContext) -> None:
        """Repay active loan"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        if not user:
            await update.message.reply_text(
                "⚠️ <b>Account Not Found</b>\n\n"
                "Use /balance to create your account first.",
                parse_mode="HTML"
            )
            return
        
        # Check if account is frozen
        if user.get('frozen'):
            await update.message.reply_text(
                "🔒 <b>Account Frozen</b>\n\n"
                "Unlock your account first using /unlockaccount",
                parse_mode="HTML"
            )
            return
        
        # Check for active loan
        loan_amount = user.get('loan_amount', 0)
        if loan_amount <= 0:
            await update.message.reply_text(
                "ℹ️ <b>No Active Loan</b>\n\n"
                "You don't have any active loans to repay.",
                parse_mode="HTML"
            )
            return
        
        # Check sufficient balance
        balance = user.get('balance', 0)
        if balance < loan_amount:
            await update.message.reply_text(
                "❌ <b>Insufficient Funds</b>\n\n"
                f"<b>Required:</b> <code>{BankFormatter.format_currency(loan_amount)}</code>\n"
                f"<b>Available:</b> <code>{BankFormatter.format_currency(balance)}</code>\n\n"
                "Deposit more funds or wait for daily reward.",
                parse_mode="HTML"
            )
            return
        
        loan_type = user.get('loan_type', 'normal')
        
        # Process repayment
        update_data = {
            '$inc': {'balance': -loan_amount},
            '$set': {
                'loan_amount': 0,
                'loan_due_date': None,
                'loan_type': None
            }
        }
        
        # Reduce emergency loan count if applicable
        if loan_type == 'emergency':
            emergency_count = user.get('emergency_loan_count', 0)
            if emergency_count > 0:
                update_data['$inc']['emergency_loan_count'] = -1
        
        await user_collection.update_one(
            {'id': user_id},
            update_data
        )
        
        # Add to loan history
        await user_collection.update_one(
            {'id': user_id},
            {'$push': {'loan_history': {
                'amount': loan_amount,
                'date': datetime.utcnow(),
                'type': loan_type,
                'status': 'repaid'
            }}}
        )
        
        # Update credit score positively
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'credit_score': 20}}
        )
        
        await BankOperations.add_transaction(
            user_id,
            'loan_repayment',
            -loan_amount,
            f"{loan_type.capitalize()} loan repaid"
        )
        
        # Prepare response
        message = [
            "✅ <b>Loan Repaid Successfully</b>",
            "",
            f"💰 <b>Amount Paid:</b> <code>{BankFormatter.format_currency(loan_amount)}</code>",
            f"📊 <b>New Balance:</b> <code>{BankFormatter.format_currency(balance - loan_amount)}</code>",
            f"✨ <b>Credit Score:</b> +20 points",
            ""
        ]
        
        if loan_type == 'emergency':
            new_count = max(0, user.get('emergency_loan_count', 0) - 1)
            message.append(f"⚡ <b>Emergency Loans:</b> {new_count}/3 used")
        
        await update.message.reply_text(
            "\n".join(message),
            parse_mode="HTML"
        )
    
    @staticmethod
    async def daily_reward_command(update: Update, context: CallbackContext) -> None:
        """Claim daily reward"""
        if not update.effective_user:
            return
        
        user_id = update.effective_user.id
        user = await BankOperations.get_user(user_id)
        
        # Initialize user if not exists
        if not user:
            await BankOperations.init_user(user_id)
            user = await BankOperations.get_user(user_id)
        
        # Check daily cooldown
        last_daily = user.get('last_daily')
        now = datetime.utcnow()
        
        if last_daily and (now - last_daily).total_seconds() < 86400:
            next_claim = last_daily + timedelta(days=1)
            time_left = (next_claim - now).total_seconds()
            
            await update.message.reply_text(
                "⏳ <b>Daily Reward Already Claimed</b>\n\n"
                f"🕒 <b>Next Claim In:</b> {BankFormatter.format_time(time_left)}\n\n"
                f"📅 <b>Next Available:</b> {next_claim.strftime('%d %b %Y, %I:%M %p')}",
                parse_mode="HTML"
            )
            return
        
        # Calculate daily amount
        if user.get('premium'):
            base_amount = BANK_CFG['daily']['premium_reward']
        else:
            base_amount = BANK_CFG['daily']['regular_reward']
        
        # Check for debt deduction
        debt = user.get('permanent_debt', 0)
        actual_amount = base_amount
        
        if debt > 0:
            deduction = int(base_amount * BANK_CFG['daily']['debt_deduction'])
            deduction = min(deduction, debt)
            actual_amount = base_amount - deduction
            new_debt = debt - deduction
            
            update_data = {
                '$inc': {'balance': actual_amount},
                '$set': {
                    'last_daily': now,
                    'permanent_debt': max(0, new_debt)
                }
            }
            
            message = [
                "💰 <b>Daily Reward (with Debt Deduction)</b>",
                "",
                f"🎁 <b>Base Reward:</b> <code>{BankFormatter.format_currency(base_amount)}</code>",
                f"💸 <b>Debt Deduction:</b> <code>-{BankFormatter.format_currency(deduction)}</code>",
                f"✅ <b>Amount Received:</b> <code>{BankFormatter.format_currency(actual_amount)}</code>",
                "",
                f"🔴 <b>Remaining Debt:</b> <code>{BankFormatter.format_currency(new_debt)}</code>"
            ]
            
            if new_debt <= 0:
                message.append("\n🎉 <b>Congratulations! Debt Cleared!</b>")
        else:
            update_data = {
                '$inc': {
                    'balance': actual_amount,
                    'user_xp': 10
                },
                '$set': {'last_daily': now}
            }
            
            message = [
                "💰 <b>Daily Reward Claimed</b>",
                "",
                f"✅ <b>Amount Received:</b> <code>{BankFormatter.format_currency(actual_amount)}</code>",
                f"✨ <b>XP Earned:</b> +10"
            ]
        
        # Update user
        await user_collection.update_one(
            {'id': user_id},
            update_data
        )
        
        # Add transaction
        await BankOperations.add_transaction(
            user_id,
            'daily_reward',
            actual_amount,
            f"Daily reward{' (debt deducted)' if debt > 0 else ''}"
        )
        
        await update.message.reply_text(
            "\n".join(message),
            parse_mode="HTML"
        )


# Background Tasks
async def check_loans_task() -> None:
    """Background task to check and process overdue loans"""
    while True:
        try:
            async with loan_check_lock:
                now = datetime.utcnow()
                
                async for user in user_collection.find({
                    'loan_amount': {'$gt': 0},
                    'loan_due_date': {'$lt': now}
                }):
                    # Process overdue loan (simplified for brevity)
                    # This should include the full loan collection logic
                    pass
                    
        except Exception as e:
            logger.error(f"Error in check_loans_task: {e}")
        
        await asyncio.sleep(3600)  # Check every hour


async def check_fixed_deposits_task() -> None:
    """Background task to check and process matured fixed deposits"""
    while True:
        try:
            now = datetime.utcnow()
            
            async for user in user_collection.find({
                'fixed_deposits': {'$exists': True, '$ne': []}
            }):
                # Process matured FDs
                pass
                
        except Exception as e:
            logger.error(f"Error in check_fixed_deposits_task: {e}")
        
        await asyncio.sleep(3600)


async def startup_tasks() -> None:
    """Initialize all background tasks"""
    asyncio.create_task(check_loans_task())
    asyncio.create_task(check_fixed_deposits_task())
    logger.info("Banking system background tasks started")


# Callback Query Handler
async def callback_query_handler(update: Update, context: CallbackContext) -> None:
    """Handle all callback queries"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Parse callback data
    if data.startswith('refresh_balance_'):
        target_id = int(data.split('_')[-1])
        if user_id != target_id:
            await query.answer("This is not your account!", show_alert=True)
            return
        
        # Refresh balance logic
        await BankCommands.balance_command(update, context)
    
    elif data.startswith('portfolio_'):
        target_id = int(data.split('_')[-1])
        if user_id != target_id:
            await query.answer("This is not your account!", show_alert=True)
            return
        
        # Show portfolio
        user = await BankOperations.get_user(user_id)
        if not user:
            await query.edit_message_text(
                "⚠️ Account not found. Use /balance first.",
                parse_mode="HTML"
            )
            return
        
        # Portfolio display logic
        pass
    
    # Add more callback handlers as needed


# Command Handlers Setup
def setup_handlers():
    """Setup all command handlers"""
    
    # Basic Commands
    application.add_handler(CommandHandler("bal", BankCommands.balance_command))
    application.add_handler(CommandHandler("balance", BankCommands.balance_command))
    application.add_handler(CommandHandler("deposit", BankCommands.deposit_command))
    application.add_handler(CommandHandler("withdraw", BankCommands.withdraw_command))
    application.add_handler(CommandHandler("daily", BankCommands.daily_reward_command))
    application.add_handler(CommandHandler("cclaim", BankCommands.daily_reward_command))
    
    # Loan Commands
    application.add_handler(CommandHandler("getloan", BankCommands.get_loan_command))
    application.add_handler(CommandHandler("loan", BankCommands.get_loan_command))
    application.add_handler(CommandHandler("emergencyloan", BankCommands.emergency_loan_command))
    application.add_handler(CommandHandler("repayloan", BankCommands.repay_loan_command))
    application.add_handler(CommandHandler("repay", BankCommands.repay_loan_command))
    
    # Fixed Deposit Commands
    # Add handlers for /fixeddeposit, /breakfd, etc.
    
    # Investment Commands
    # Add handlers for /investstock, /portfolio, /sellinvest, etc.
    
    # Security Commands
    # Add handlers for /setpin, /lockaccount, /unlockaccount, etc.
    
    # Premium Commands
    # Add handler for /buypremium
    
    # Miscellaneous Commands
    # Add handlers for /txhistory, /userlevel, /leaders, etc.
    
    # Callback Query Handler
    application.add_handler(CallbackQueryHandler(callback_query_handler))


# Startup
async def post_init(application):
    """Initialize banking system on startup"""
    await startup_tasks()
    setup_handlers()
    logger.info("Banking system initialized successfully")


# Attach to application
application.post_init = post_init