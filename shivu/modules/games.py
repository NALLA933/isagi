import math
import asyncio
import random
import time
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, List
from pathlib import Path

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext

from shivu import application, user_collection


@dataclass(frozen=True)
class GameConfig:
    cooldown: int = 5
    riddle_timeout: int = 15
    default_token_reward: int = 1
    stour_entry_fee: int = 300
    stour_success_rate: float = 0.1
    basket_base_win_rate: float = 0.20
    dart_bullseye_rate: float = 0.1
    dart_hit_rate: float = 0.20
    gamble_win_rate: float = 0.20
    coinflip_multiplier: int = 2
    dice_multiplier: int = 2
    gamble_multiplier: int = 2
    basket_multiplier: int = 2
    dart_hit_multiplier: int = 2
    dart_bullseye_multiplier: int = 4


class GameType(Enum):
    COINFLIP = "sbet"
    DICE = "roll"
    GAMBLE = "gamble"
    BASKET = "basket"
    DART = "dart"
    CONTRACT = "stour"
    RIDDLE = "riddle"


@dataclass
class GameResult:
    won: bool
    amount_changed: int
    tokens_gained: int = 0
    message: str = ""
    display_outcome: str | None = None


@dataclass
class PendingRiddle:
    answer: str
    expires_at: float
    message_id: int
    chat_id: int
    question: str
    reward: int = 1


@dataclass
class GameState:
    cooldowns: Dict[int, datetime] = field(default_factory=dict)
    riddles: Dict[int, PendingRiddle] = field(default_factory=dict)
    stats: Dict[int, Dict[str, int]] = field(default_factory=dict)

    def check_cooldown(self, user_id: int) -> float | None:
        if last := self.cooldowns.get(user_id):
            elapsed = (datetime.utcnow() - last).total_seconds()
            if elapsed < CONFIG.cooldown:
                return CONFIG.cooldown - elapsed
        return None

    def set_cooldown(self, user_id: int):
        self.cooldowns[user_id] = datetime.utcnow()

    def record_play(self, user_id: int, game: str):
        if user_id not in self.stats:
            self.stats[user_id] = {}
        self.stats[user_id][game] = self.stats[user_id].get(game, 0) + 1


CONFIG = GameConfig()
game_state = GameState()

EXPLORE_ACTIONS = [
    "explored a dungeon", "ventured into a dark forest", "discovered ancient ruins",
    "infiltrated an elvish village", "raided a goblin nest", "survived an orc den"
]

GAME_EMOJIS = {
    GameType.COINFLIP: "🪙", GameType.DICE: "🎲", GameType.GAMBLE: "🎰",
    GameType.BASKET: "🏀", GameType.DART: "🎯", GameType.CONTRACT: "🤝"
}

GAME_NAMES = {
    'sbet': '🪙 Coin Flip', 'roll': '🎲 Dice', 'gamble': '🎰 Gamble',
    'basket': '🏀 Basketball', 'dart': '🎯 Darts', 'stour': '🤝 Contract', 'riddle': '🧩 Riddle'
}


class GameLogger:
    LOG_CHANNEL = -1003018573623  # Your channel ID
    
    @staticmethod
    async def log_to_channel(game_log: str):
        """Send game log to Telegram channel"""
        try:
            await application.bot.send_message(
                chat_id=GameLogger.LOG_CHANNEL,
                text=game_log,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Failed to send log to channel: {e}")
    
    @staticmethod
    def format_game_log(
        user_id: int,
        username: str,
        first_name: str,
        game_type: str,
        bet_amount: int,
        result: str,
        win_amount: int,
        balance_before: int,
        balance_after: int,
        tokens_before: int,
        tokens_after: int,
        details: str = ""
    ) -> str:
        """Format game log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        date = datetime.now().strftime("%Y-%m-%d")
        
        result_emoji = "✅" if result == "WIN" else "❌"
        result_color = "#27ae60" if result == "WIN" else "#e74c3c"
        
        user_link = f'<a href="tg://user?id={user_id}">{first_name}</a>'
        if username:
            user_link += f" (@{username})"
        
        log_message = (
            f"<b>🎮 GAME LOG - {date} {timestamp}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>👤 Player:</b> {user_link}\n"
            f"<b>🎯 Game:</b> {GAME_NAMES.get(game_type, game_type)}\n"
            f"<b>💰 Bet:</b> <code>{bet_amount:,}</code> coins\n"
            f"<b>📊 Result:</b> <span style='color:{result_color}'>{result_emoji} {result}</span>\n"
        )
        
        if win_amount > 0:
            log_message += f"<b>🏆 Win Amount:</b> <code>+{win_amount:,}</code> coins\n"
        
        log_message += (
            f"<b>💼 Balance:</b> <code>{balance_before:,}</code> → <code>{balance_after:,}</code>\n"
        )
        
        if tokens_before != tokens_after:
            log_message += f"<b>🎫 Tokens:</b> <code>{tokens_before}</code> → <code>{tokens_after}</code>\n"
        
        if details:
            log_message += f"<b>📝 Details:</b> {details}\n"
        
        log_message += "━━━━━━━━━━━━━━━━━━━━"
        
        return log_message
    
    @staticmethod
    async def log_console(
        user_id: int,
        username: str,
        game_type: str,
        bet_amount: int,
        result: str,
        win_amount: int
    ):
        """Print colored log to console"""
        result_color = "\033[92m" if result == "WIN" else "\033[91m"
        reset_color = "\033[0m"
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"{timestamp} [{game_type.upper()}] {result_color}{result}{reset_color} - "
              f"User: {user_id} (@{username}) - "
              f"Bet: {bet_amount:,} - Win: {win_amount:,}")


class UserDB:
    @staticmethod
    async def get(user_id: int) -> dict | None:
        try:
            return await user_collection.find_one({'id': user_id})
        except Exception:
            return None

    @staticmethod
    async def ensure(user_id: int, first_name: str = None, username: str = None) -> dict:
        if doc := await UserDB.get(user_id):
            updates = {}
            if username and username != doc.get('username'):
                updates['username'] = username
            if first_name and first_name != doc.get('first_name'):
                updates['first_name'] = first_name
            if updates:
                await user_collection.update_one({'id': user_id}, {'$set': updates})
            return doc

        new_user = {
            'id': user_id,
            'first_name': first_name or 'Unknown',
            'username': username,
            'balance': 0,
            'tokens': 0,
            'characters': [],
            'created_at': datetime.utcnow()
        }
        await user_collection.insert_one(new_user)
        return new_user

    @staticmethod
    async def change_balance(user_id: int, delta: int) -> dict | None:
        await user_collection.update_one({'id': user_id}, {'$inc': {'balance': delta}}, upsert=True)
        return await UserDB.get(user_id)

    @staticmethod
    async def change_tokens(user_id: int, delta: int) -> dict | None:
        await user_collection.update_one({'id': user_id}, {'$inc': {'tokens': delta}}, upsert=True)
        return await UserDB.get(user_id)


class GameUI:
    @staticmethod
    def play_again(command: str, args: str = "") -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Play Again", callback_data=f"games:repeat:{command}:{args or '_'}")
        ]])

    @staticmethod
    def menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🪙 Coin Flip", callback_data="games:info:sbet"),
             InlineKeyboardButton("🎲 Dice Roll", callback_data="games:info:roll")],
            [InlineKeyboardButton("🎰 Gamble", callback_data="games:info:gamble"),
             InlineKeyboardButton("🏀 Basketball", callback_data="games:info:basket")],
            [InlineKeyboardButton("🎯 Darts", callback_data="games:info:dart"),
             InlineKeyboardButton("🤝 Contract", callback_data="games:info:stour")],
            [InlineKeyboardButton("🧩 Riddle", callback_data="games:info:riddle")]
        ])

    @staticmethod
    def format_result(result: GameResult, emoji: str, user_name: str) -> str:
        status = "✅ <b>WIN</b>" if result.won else "❌ <b>LOSE</b>"
        msg = f"<b>{emoji} Game Result</b>\n{status}\n"
        if result.display_outcome:
            msg += f"<blockquote>Outcome: <b>{result.display_outcome}</b></blockquote>\n"
        msg += f"<blockquote expandable>{result.message}</blockquote>"
        if result.tokens_gained > 0:
            msg += f"\n<blockquote>🎁 Bonus: <b>+{result.tokens_gained}</b> token(s)</blockquote>"
        return msg


class GameLogic:
    @staticmethod
    def coinflip(guess: str, amount: int) -> GameResult:
        outcome = random.choice(['heads', 'tails'])
        won = outcome == guess
        if won:
            win = amount * CONFIG.coinflip_multiplier
            return GameResult(True, win, 0, f"You won <b>{win:,}</b> coins", outcome.upper())
        return GameResult(False, 0, 0, f"You lost <b>{amount:,}</b> coins", outcome.upper())

    @staticmethod
    def dice_roll(choice: str, amount: int) -> GameResult:
        dice = random.randint(1, 6)
        result = 'odd' if dice % 2 else 'even'
        won = result == choice
        if won:
            win = amount * CONFIG.dice_multiplier
            return GameResult(True, win, 0, f"Rolled <b>{dice}</b> ({result})\nYou won <b>{win:,}</b> coins", f"🎲 {dice}")
        return GameResult(False, 0, 0, f"Rolled <b>{dice}</b> ({result})\nYou lost <b>{amount:,}</b> coins", f"🎲 {dice}")

    @staticmethod
    def gamble(pick: str, amount: int) -> GameResult:
        won = random.random() < CONFIG.gamble_win_rate
        if won:
            win = amount * CONFIG.gamble_multiplier
            display = random.choice(['L', 'R'])
            return GameResult(True, win, 0, f"You won <b>{win:,}</b> coins", "LEFT" if display == 'L' else "RIGHT")
        display = 'R' if pick == 'l' else 'L'
        return GameResult(False, 0, 0, f"You lost <b>{amount:,}</b> coins", "LEFT" if display == 'L' else "RIGHT")

    @staticmethod
    def basketball(amount: int) -> GameResult:
        win_chance = min(0.6, CONFIG.basket_base_win_rate + math.log1p(amount) / 50)
        won = random.random() < win_chance
        if won:
            win = amount * CONFIG.basket_multiplier
            return GameResult(True, win, 0, f"Perfect shot! You scored <b>{win:,}</b> coins")
        return GameResult(False, 0, 0, f"Missed! You lost <b>{amount:,}</b> coins")

    @staticmethod
    def darts(amount: int) -> GameResult:
        roll = random.random()
        if roll < CONFIG.dart_bullseye_rate:
            win = amount * CONFIG.dart_bullseye_multiplier
            return GameResult(True, win, 0, f"Bullseye! You won <b>{win:,}</b> coins", "🎯 BULLSEYE")
        elif roll < (CONFIG.dart_bullseye_rate + CONFIG.dart_hit_rate):
            win = amount * CONFIG.dart_hit_multiplier
            return GameResult(True, win, 0, f"Good hit! You won <b>{win:,}</b> coins", "TARGET HIT")
        return GameResult(False, 0, 0, f"Missed! You lost <b>{amount:,}</b> coins", "MISS")

    @staticmethod
    def contract() -> GameResult:
        if random.random() < CONFIG.stour_success_rate:
            reward_type = random.choice(["coins", "tokens"])
            if reward_type == "coins":
                reward = random.randint(100, 600)
                return GameResult(True, reward, 0, f"Contract completed! You earned <b>{reward:,}</b> coins")
            tokens = random.randint(1, 3)
            return GameResult(True, 0, tokens, f"Contract completed! You received <b>{tokens}</b> token(s)")
        return GameResult(False, 0, 0, f"Contract failed! You lost <b>{CONFIG.stour_entry_fee:,}</b> coins")

    @staticmethod
    def generate_riddle() -> tuple[str, str]:
        a, b = random.randint(2, 50), random.randint(1, 50)
        op = random.choice(['+', '-', '*'])
        ans = a + b if op == '+' else (a - b if op == '-' else a * b)
        return f"{a} {op} {b}", str(ans)


async def get_msg(update: Update):
    return update.callback_query.message if update.callback_query else update.message


async def reply(update: Update, text: str, markup=None):
    msg = await get_msg(update)
    return await msg.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def check_cooldown(update: Update, user_id: int) -> bool:
    if remaining := game_state.check_cooldown(user_id):
        await reply(update, f"<b>⏱ Cooldown Active</b>\n<blockquote>Wait {remaining:.1f}s before playing again</blockquote>")
        return True
    return False


async def validate_amount(update: Update, amount: int, user_id: int) -> bool:
    if amount <= 0:
        await reply(update, "<b>❌ Invalid Amount</b>\n<blockquote>Amount must be positive</blockquote>")
        return False
    if not (user := await UserDB.get(user_id)) or user.get('balance', 0) < amount:
        await reply(update, "<b>💰 Insufficient Balance</b>\n<blockquote>You don't have enough coins</blockquote>")
        return False
    return True


async def process_game(update: Update, context: CallbackContext, game_type: GameType, 
                      amount: int, result: GameResult, extra: str = ""):
    user_id = update.effective_user.id
    user = await UserDB.get(user_id)
    
    # Store balance and tokens before the game
    balance_before = user.get('balance', 0)
    tokens_before = user.get('tokens', 0)
    
    # Process the game result
    if result.won and result.amount_changed > 0:
        await UserDB.change_balance(user_id, result.amount_changed)
    if result.tokens_gained > 0:
        await UserDB.change_tokens(user_id, result.tokens_gained)
    
    game_state.record_play(user_id, game_type.value)
    game_state.set_cooldown(user_id)
    
    emoji = GAME_EMOJIS.get(game_type, "🎮")
    msg = GameUI.format_result(result, emoji, user.get('first_name', 'Player'))
    
    updated = await UserDB.get(user_id)
    balance_after = updated.get('balance', 0)
    tokens_after = updated.get('tokens', 0)
    
    msg += f"\n<b>Balance:</b> <code>{balance_after:,}</code> coins"
    
    await reply(update, msg, GameUI.play_again(game_type.value, extra))
    
    # LOGGING - Send to channel and console
    result_str = "WIN" if result.won else "LOSE"
    win_amount = result.amount_changed if result.won else 0
    
    # Console log
    await GameLogger.log_console(
        user_id=user_id,
        username=user.get('username', 'N/A'),
        game_type=game_type.value,
        bet_amount=amount,
        result=result_str,
        win_amount=win_amount
    )
    
    # Channel log
    log_message = GameLogger.format_game_log(
        user_id=user_id,
        username=user.get('username'),
        first_name=user.get('first_name', 'Unknown'),
        game_type=game_type.value,
        bet_amount=amount,
        result=result_str,
        win_amount=win_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        details=result.display_outcome or result.message
    )
    
    await GameLogger.log_to_channel(log_message)


async def sbet(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    try:
        amount, guess = int(context.args[0]), context.args[1].lower()
    except (IndexError, ValueError):
        await reply(update, "<b>📖 Usage</b>\n<blockquote><code>/sbet &lt;amount&gt; heads|tails</code>\n<i>Example: /sbet 100 heads</i></blockquote>")
        return
    
    guess = 'heads' if guess in ('h', 'head', 'heads') else ('tails' if guess in ('t', 'tail', 'tails') else None)
    if not guess:
        await reply(update, "<b>❌ Invalid Choice</b>\n<blockquote>Must be 'heads' or 'tails'</blockquote>")
        return
    
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    
    await UserDB.change_balance(user_id, -amount)
    result = GameLogic.coinflip(guess, amount)
    await process_game(update, context, GameType.COINFLIP, amount, result, f"{amount}:{guess}")


async def roll_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    try:
        amount, choice = int(context.args[0]), context.args[1].lower()
    except (IndexError, ValueError):
        await reply(update, "<b>📖 Usage</b>\n<blockquote><code>/roll &lt;amount&gt; odd|even</code>\n<i>Example: /roll 50 odd</i></blockquote>")
        return
    
    choice = 'odd' if choice in ('o', 'odd') else ('even' if choice in ('e', 'even') else None)
    if not choice:
        await reply(update, "<b>❌ Invalid Choice</b>\n<blockquote>Must be 'odd' or 'even'</blockquote>")
        return
    
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    
    await UserDB.change_balance(user_id, -amount)
    result = GameLogic.dice_roll(choice, amount)
    await process_game(update, context, GameType.DICE, amount, result, f"{amount}:{choice}")


async def gamble(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    try:
        amount, pick = int(context.args[0]), context.args[1].lower()
    except (IndexError, ValueError):
        await reply(update, "<b>📖 Usage</b>\n<blockquote><code>/gamble &lt;amount&gt; l|r</code>\n<i>Example: /gamble 100 l</i></blockquote>")
        return
    
    if pick not in ('l', 'r', 'left', 'right'):
        await reply(update, "<b>❌ Invalid Choice</b>\n<blockquote>Must be 'l' or 'r'</blockquote>")
        return
    
    pick = 'l' if pick.startswith('l') else 'r'
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    
    await UserDB.change_balance(user_id, -amount)
    result = GameLogic.gamble(pick, amount)
    await process_game(update, context, GameType.GAMBLE, amount, result, f"{amount}:{pick}")


async def basket(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await reply(update, "<b>📖 Usage</b>\n<blockquote><code>/basket &lt;amount&gt;</code>\n<i>Example: /basket 75</i></blockquote>")
        return
    
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    
    await UserDB.change_balance(user_id, -amount)
    result = GameLogic.basketball(amount)
    await process_game(update, context, GameType.BASKET, amount, result, str(amount))


async def dart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await reply(update, "<b>📖 Usage</b>\n<blockquote><code>/dart &lt;amount&gt;</code>\n<i>Example: /dart 50</i></blockquote>")
        return
    
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    
    await UserDB.change_balance(user_id, -amount)
    result = GameLogic.darts(amount)
    await process_game(update, context, GameType.DART, amount, result, str(amount))


async def stour(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, CONFIG.stour_entry_fee, user_id):
        return
    
    await UserDB.change_balance(user_id, -CONFIG.stour_entry_fee)
    result = GameLogic.contract()
    await process_game(update, context, GameType.CONTRACT, CONFIG.stour_entry_fee, result)


async def riddle(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await check_cooldown(update, user_id):
        return
    
    question, answer = GameLogic.generate_riddle()
    msg = await get_msg(update)
    text = f"<b>🧩 Riddle Time</b>\n<blockquote expandable>Solve: <b>{question}</b>\nTime: <code>{CONFIG.riddle_timeout}s</code> | Reward: <code>{CONFIG.default_token_reward}</code> token(s)</blockquote>\n<i>Reply with the number</i>"
    sent = await msg.reply_text(text, parse_mode="HTML")
    
    riddle_data = PendingRiddle(answer, time.time() + CONFIG.riddle_timeout, sent.message_id, update.effective_chat.id, question)
    game_state.riddles[user_id] = riddle_data
    game_state.set_cooldown(user_id)
    game_state.record_play(user_id, GameType.RIDDLE.value)
    
    async def expire():
        await asyncio.sleep(CONFIG.riddle_timeout)
        if pending := game_state.riddles.get(user_id):
            if time.time() >= pending.expires_at:
                game_state.riddles.pop(user_id, None)
                try:
                    await application.bot.send_message(pending.chat_id, f"<b>⏳ Time's Up</b>\n<blockquote>Answer was <b>{answer}</b></blockquote>", parse_mode="HTML")
                    
                    # LOG: Riddle timeout
                    log_message = f"<b>🧩 RIDDLE TIMEOUT</b>\n👤 User ID: {user_id}\n❓ Question: {question}\n⏰ Time Limit: {CONFIG.riddle_timeout}s"
                    await GameLogger.log_to_channel(log_message)
                    
                except Exception:
                    pass
    
    asyncio.create_task(expire())


async def riddle_answer(update: Update, context: CallbackContext):
    # Check if effective_user exists
    if not update.effective_user:
        return
    
    user_id = update.effective_user.id
    
    # Also check if there's a pending riddle for this user
    if not (pending := game_state.riddles.get(user_id)):
        return
    
    # Check if chat exists and matches
    if not update.effective_chat or update.effective_chat.id != pending.chat_id:
        return
    
    # Check if there's message text
    if not update.message or not (text := (update.message.text or "").strip()):
        return
    
    # Check if riddle is expired
    if time.time() > pending.expires_at:
        game_state.riddles.pop(user_id, None)
        return
    
    # Get user data for logging
    user = await UserDB.get(user_id)
    tokens_before = user.get('tokens', 0) if user else 0
    
    # Process answer
    if text == pending.answer:
        await UserDB.change_tokens(user_id, pending.reward)
        user_after = await UserDB.get(user_id)
        tokens_after = user_after.get('tokens', 0)
        
        await update.message.reply_text(
            f"<b>✅ Correct</b>\n<blockquote>Earned <b>{pending.reward}</b> token(s)\nTotal: <code>{tokens_after}</code></blockquote>",
            parse_mode="HTML"
        )
        
        # LOG: Riddle solved successfully
        log_message = GameLogger.format_game_log(
            user_id=user_id,
            username=user.get('username') if user else None,
            first_name=user.get('first_name', 'Unknown') if user else 'Unknown',
            game_type='riddle',
            bet_amount=0,
            result="WIN",
            win_amount=pending.reward,
            balance_before=user.get('balance', 0) if user else 0,
            balance_after=user_after.get('balance', 0) if user_after else 0,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            details=f"Solved: {pending.question} = {pending.answer}"
        )
        await GameLogger.log_to_channel(log_message)
        
    else:
        await update.message.reply_text(
            f"<b>❌ Wrong</b>\n<blockquote>Answer was <b>{pending.answer}</b></blockquote>",
            parse_mode="HTML"
        )
        
        # LOG: Riddle failed
        log_message = GameLogger.format_game_log(
            user_id=user_id,
            username=user.get('username') if user else None,
            first_name=user.get('first_name', 'Unknown') if user else 'Unknown',
            game_type='riddle',
            bet_amount=0,
            result="LOSE",
            win_amount=0,
            balance_before=user.get('balance', 0) if user else 0,
            balance_after=user.get('balance', 0) if user else 0,
            tokens_before=tokens_before,
            tokens_after=tokens_before,
            details=f"Failed: {pending.question} ≠ {text}"
        )
        await GameLogger.log_to_channel(log_message)
    
    # Remove riddle from pending
    game_state.riddles.pop(user_id, None)


async def games_menu(update: Update, context: CallbackContext):
    text = f"<b>🎮 Games Hub</b>\n<blockquote expandable><b>Available Games:</b>\n🪙 Coin Flip • 🎲 Dice Roll\n🎰 Gamble • 🏀 Basketball\n🎯 Darts • 🤝 Contract\n🧩 Riddle</blockquote>\n<i>Click below to learn more</i>"
    await reply(update, text, GameUI.menu())


async def game_stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDB.get(user_id)
    stats = game_state.stats.get(user_id, {})
    
    if not stats:
        await reply(update, "<b>📊 No Statistics</b>\n<blockquote>You haven't played yet\nUse /games to start</blockquote>")
        return
    
    total = sum(stats.values())
    text = f"<b>📊 Statistics</b>\n<b>Player:</b> {update.effective_user.first_name}\n<blockquote>Balance: <code>{user.get('balance', 0):,}</code> coins\nTokens: <code>{user.get('tokens', 0)}</code>\nGames: <code>{total}</code></blockquote>\n<b>Breakdown:</b>\n"
    
    for game, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        name = GAME_NAMES.get(game, game)
        pct = (count / total) * 100
        text += f"<blockquote>{name}: <code>{count}</code> ({pct:.1f}%)</blockquote>\n"
    
    await reply(update, text)


async def leaderboard(update: Update, context: CallbackContext):
    try:
        top = await user_collection.find().sort('balance', -1).limit(10).to_list(length=10)
        if not top:
            await reply(update, "<b>🏆 No Players</b>\n<blockquote>Be the first to play</blockquote>")
            return
        
        header = "https://files.catbox.moe/i8x33x.jpg"
        footer = "https://files.catbox.moe/33yrky.jpg"
        text = f'<a href="{header}">&#8203;</a>\n<b>🏆 Top Players</b>\n'
        medals = ["🥇", "🥈", "🥉"]
        
        for i, p in enumerate(top):
            medal = medals[i] if i < 3 else f"<b>{i+1}.</b>"
            name = f'<a href="tg://user?id={p["id"]}">@{p.get("username")}</a>' if p.get('username') else f'<a href="tg://user?id={p["id"]}">{p.get("first_name", "Unknown")}</a>'
            text += f"<blockquote expandable>{medal} {name}\n<code>{p.get('balance', 0):,}</code> coins • <code>{p.get('tokens', 0)}</code> tokens</blockquote>\n"
        
        text += f'<a href="{footer}">&#8203;</a><i>Keep playing</i>'
        await reply(update, text)
    except Exception:
        await reply(update, "<b>❌ Error</b>\n<blockquote>Failed to load leaderboard</blockquote>")


async def daily_bonus(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDB.get(user_id)
    
    if last := user.get('last_daily_claim'):
        if (elapsed := datetime.utcnow() - last) < timedelta(hours=24):
            hours_left = 24 - elapsed.total_seconds() / 3600
            await reply(update, f"<b>⏰ Already Claimed</b>\n<blockquote>Come back in <code>{hours_left:.1f}</code> hours</blockquote>")
            return
    
    coins, tokens = random.randint(50, 150), random.randint(0, 2)
    balance_before = user.get('balance', 0)
    tokens_before = user.get('tokens', 0)
    
    await UserDB.change_balance(user_id, coins)
    if tokens > 0:
        await UserDB.change_tokens(user_id, tokens)
    
    await user_collection.update_one({'id': user_id}, {'$set': {'last_daily_claim': datetime.utcnow()}})
    
    text = f"<b>🎁 Daily Bonus</b>\n<blockquote expandable>Coins: <code>+{coins}</code>"
    if tokens > 0:
        text += f"\nTokens: <code>+{tokens}</code>"
    text += "</blockquote>\n<i>Come back tomorrow</i>"
    await reply(update, text)
    
    # LOG: Daily bonus claimed
    user_after = await UserDB.get(user_id)
    log_message = GameLogger.format_game_log(
        user_id=user_id,
        username=user.get('username'),
        first_name=user.get('first_name', 'Unknown'),
        game_type='daily',
        bet_amount=0,
        result="WIN",
        win_amount=coins,
        balance_before=balance_before,
        balance_after=user_after.get('balance', 0),
        tokens_before=tokens_before,
        tokens_after=user_after.get('tokens', 0),
        details=f"Daily Bonus: +{coins} coins, +{tokens} tokens"
    )
    await GameLogger.log_to_channel(log_message)


async def tokens_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDB.ensure(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDB.get(user_id)
    
    text = f"<b>💎 Your Tokens</b>\n<b>Player:</b> {update.effective_user.first_name}\n<blockquote>Tokens: <code>{user.get('tokens', 0)}</code>\nBalance: <code>{user.get('balance', 0):,}</code> coins</blockquote>\n<b>How to Earn:</b>\n<blockquote expandable>🧩 Riddles - Solve math (/riddle)\n🤝 Contracts - Complete missions (/stour)\n🎁 Daily - Claim every 24h (/daily)</blockquote>"
    await reply(update, text)


async def help_games(update: Update, context: CallbackContext):
    text = f"<b>📚 Games Help</b>\n<b>Commands:</b>\n<blockquote expandable><code>/games</code> - Games menu\n<code>/sbet &lt;amt&gt; &lt;h|t&gt;</code> - Coin flip\n<code>/roll &lt;amt&gt; &lt;odd|even&gt;</code> - Dice\n<code>/gamble &lt;amt&gt; &lt;l|r&gt;</code> - Gamble\n<code>/basket &lt;amt&gt;</code> - Basketball\n<code>/dart &lt;amt&gt;</code> - Darts\n<code>/stour</code> - Contract\n<code>/riddle</code> - Riddle\n<code>/gamestats</code> - Statistics\n<code>/tokens</code> - View tokens\n<code>/leaderboard</code> - Rankings\n<code>/daily</code> - Daily bonus</blockquote>\n<b>Tips:</b>\n<blockquote>• Start small\n• Check win rates\n• Claim daily bonus\n• Solve riddles\n• Use Play Again</blockquote>\n<i>Cooldown: {CONFIG.cooldown}s</i>"
    await reply(update, text)


async def games_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    parts = (query.data or "").split(":", 3)
    if len(parts) < 3:
        return
    
    _, action, cmd = parts[:3]
    args = parts[3] if len(parts) > 3 else ""
    
    if action == "repeat":
        context.args = [] if args in ("_", "") else args.split(":")
        handlers = {
            "sbet": sbet, "roll": roll_cmd, "gamble": gamble,
            "basket": basket, "dart": dart, "stour": stour, "riddle": riddle
        }
        if handler := handlers.get(cmd):
            await handler(update, context)
        else:
            await reply(update, "<b>❌ Error</b>\n<blockquote>Unknown command</blockquote>")
    
    elif action == "info":
        info = {
            "sbet": f"<b>🪙 Coin Flip</b>\n<blockquote expandable><b>How to Play:</b> Bet on heads or tails\n<b>Multiplier:</b> <code>{CONFIG.coinflip_multiplier}x</code>\n<b>Win Rate:</b> <code>50%</code>\n\n<b>Usage:</b>\n<code>/sbet &lt;amount&gt; heads|tails</code>\n\n<i>Example: /sbet 100 heads</i></blockquote>",
            "roll": f"<b>🎲 Dice Roll</b>\n<blockquote expandable><b>How to Play:</b> Bet on odd or even\n<b>Multiplier:</b> <code>{CONFIG.dice_multiplier}x</code>\n<b>Win Rate:</b> <code>50%</code>\n\n<b>Usage:</b>\n<code>/roll &lt;amount&gt; odd|even</code>\n\n<i>Example: /roll 50 odd</i></blockquote>",
            "gamble": f"<b>🎰 Gamble</b>\n<blockquote expandable><b>How to Play:</b> Pick left or right\n<b>Multiplier:</b> <code>{CONFIG.gamble_multiplier}x</code>\n<b>Win Rate:</b> <code>{CONFIG.gamble_win_rate*100:.0f}%</code>\n\n<b>Usage:</b>\n<code>/gamble &lt;amount&gt; l|r</code>\n\n<i>Example: /gamble 100 l</i></blockquote>",
            "basket": f"<b>🏀 Basketball</b>\n<blockquote expandable><b>How to Play:</b> Shoot hoops for coins\n<b>Multiplier:</b> <code>{CONFIG.basket_multiplier}x</code>\n<b>Win Rate:</b> <code>35-60%</code>\n\n<b>Usage:</b>\n<code>/basket &lt;amount&gt;</code>\n\n<i>Example: /basket 75</i></blockquote>",
            "dart": f"<b>🎯 Darts</b>\n<blockquote expandable><b>How to Play:</b> Aim for bullseye\n<b>Bullseye:</b> <code>{CONFIG.dart_bullseye_multiplier}x</code> ({CONFIG.dart_bullseye_rate*100:.0f}%)\n<b>Hit:</b> <code>{CONFIG.dart_hit_multiplier}x</code> ({CONFIG.dart_hit_rate*100:.0f}%)\n\n<b>Usage:</b>\n<code>/dart &lt;amount&gt;</code>\n\n<i>Example: /dart 50</i></blockquote>",
            "stour": f"<b>🤝 Contract</b>\n<blockquote expandable><b>How to Play:</b> High risk, high reward\n<b>Entry Fee:</b> <code>{CONFIG.stour_entry_fee}</code> coins\n<b>Success:</b> <code>{CONFIG.stour_success_rate*100:.0f}%</code>\n<b>Rewards:</b> Coins or tokens\n\n<b>Usage:</b>\n<code>/stour</code></blockquote>",
            "riddle": f"<b>🧩 Riddle</b>\n<blockquote expandable><b>How to Play:</b> Solve math problems\n<b>Time Limit:</b> <code>{CONFIG.riddle_timeout}s</code>\n<b>Reward:</b> <code>{CONFIG.default_token_reward}</code> token(s)\n\n<b>Usage:</b>\n<code>/riddle</code></blockquote>"
        }
        await query.message.reply_text(info.get(cmd, "<b>❌ Error</b>\n<blockquote>Game not found</blockquote>"), parse_mode="HTML")


# Admin command to check logs (optional)
async def logs_cmd(update: Update, context: CallbackContext):
    """Admin command to check recent logs"""
    user_id = update.effective_user.id
    # You can add admin check here
    
    text = "📊 <b>Game Logging System Active</b>\n"
    text += f"<blockquote>• Log Channel: <code>{GameLogger.LOG_CHANNEL}</code>\n"
    text += f"• All games are being logged\n"
    text += f"• Format: User + Game + Bet + Result + Balance</blockquote>\n"
    text += "<i>Use /gamestats for personal stats</i>"
    
    await reply(update, text)


application.add_handler(CommandHandler("sbet", sbet, block=False))
application.add_handler(CommandHandler("roll", roll_cmd, block=False))
application.add_handler(CommandHandler("gamble", gamble, block=False))
application.add_handler(CommandHandler("basket", basket, block=False))
application.add_handler(CommandHandler("dart", dart, block=False))
application.add_handler(CommandHandler("stour", stour, block=False))
application.add_handler(CommandHandler("riddle", riddle, block=False))
application.add_handler(CommandHandler("games", games_menu, block=False))
application.add_handler(CommandHandler("gamestats", game_stats, block=False))
application.add_handler(CommandHandler("tokens", tokens_cmd, block=False))
application.add_handler(CommandHandler("leaderboard", leaderboard, block=False))
application.add_handler(CommandHandler("daily", daily_bonus, block=False))
application.add_handler(CommandHandler("helpgames", help_games, block=False))
application.add_handler(CommandHandler("logs", logs_cmd, block=False))  # Optional admin command
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, riddle_answer, block=False))
application.add_handler(CallbackQueryHandler(games_callback, pattern=r"^games:", block=False))