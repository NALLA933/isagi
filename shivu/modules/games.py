import math
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CallbackContext
from shivu import application, user_collection
import random
import time

logger = logging.getLogger(__name__)

class GameConfig:
    COOLDOWN_SECONDS = 5
    RIDDLE_TIMEOUT = 15
    DEFAULT_TOKEN_REWARD = 1
    STOUR_ENTRY_FEE = 300
    STOUR_SUCCESS_RATE = 0.1
    BASKET_BASE_WIN_RATE = 0.35
    DART_BULLSEYE_RATE = 0.10
    DART_HIT_RATE = 0.40
    GAMBLE_WIN_RATE = 0.35
    COINFLIP_MULTIPLIER = 2
    DICE_MULTIPLIER = 2
    GAMBLE_MULTIPLIER = 2
    BASKET_MULTIPLIER = 2
    DART_HIT_MULTIPLIER = 2
    DART_BULLSEYE_MULTIPLIER = 4

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
    display_outcome: Optional[str] = None

@dataclass
class PendingRiddle:
    answer: str
    expires_at: float
    message_id: int
    chat_id: int
    question: str
    reward: int = GameConfig.DEFAULT_TOKEN_REWARD

class GameState:
    def __init__(self):
        self._cooldowns: Dict[int, datetime] = {}
        self._riddles: Dict[int, PendingRiddle] = {}
        self._stats: Dict[int, Dict[str, int]] = {}

    def check_cooldown(self, user_id: int) -> Tuple[bool, float]:
        last = self._cooldowns.get(user_id)
        if not last:
            return False, 0.0
        elapsed = (datetime.utcnow() - last).total_seconds()
        if elapsed >= GameConfig.COOLDOWN_SECONDS:
            return False, 0.0
        return True, GameConfig.COOLDOWN_SECONDS - elapsed

    def set_cooldown(self, user_id: int):
        self._cooldowns[user_id] = datetime.utcnow()

    def add_riddle(self, user_id: int, riddle: PendingRiddle):
        self._riddles[user_id] = riddle

    def get_riddle(self, user_id: int) -> Optional[PendingRiddle]:
        return self._riddles.get(user_id)

    def remove_riddle(self, user_id: int):
        self._riddles.pop(user_id, None)

    def record_play(self, user_id: int, game: str):
        if user_id not in self._stats:
            self._stats[user_id] = {}
        self._stats[user_id][game] = self._stats[user_id].get(game, 0) + 1

    def get_stats(self, user_id: int) -> Dict[str, int]:
        return self._stats.get(user_id, {})

game_state = GameState()

class UserDatabase:
    @staticmethod
    async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
        try:
            return await user_collection.find_one({'id': user_id})
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

    @staticmethod
    async def ensure_user(user_id: int, first_name: str = None, username: str = None) -> Dict[str, Any]:
        doc = await UserDatabase.get_user(user_id)
        if doc:
            update = {}
            if username and username != doc.get('username'):
                update['username'] = username
            if first_name and first_name != doc.get('first_name'):
                update['first_name'] = first_name
            if update:
                try:
                    await user_collection.update_one({'id': user_id}, {'$set': update})
                except Exception as e:
                    logger.error(f"Error updating user {user_id}: {e}")
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
        try:
            await user_collection.insert_one(new_user)
            logger.info(f"Created new user: {user_id}")
            return new_user
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")
            return new_user

    @staticmethod
    async def change_balance(user_id: int, delta: int) -> Optional[Dict[str, Any]]:
        try:
            await user_collection.update_one({'id': user_id}, {'$inc': {'balance': delta}}, upsert=True)
            return await UserDatabase.get_user(user_id)
        except Exception as e:
            logger.error(f"Error changing balance for user {user_id}: {e}")
            return None

    @staticmethod
    async def change_tokens(user_id: int, delta: int) -> Optional[Dict[str, Any]]:
        try:
            await user_collection.update_one({'id': user_id}, {'$inc': {'tokens': delta}}, upsert=True)
            return await UserDatabase.get_user(user_id)
        except Exception as e:
            logger.error(f"Error changing tokens for user {user_id}: {e}")
            return None

    @staticmethod
    async def check_and_deduct(user_id: int, amount: int) -> bool:
        user = await UserDatabase.get_user(user_id)
        if not user or user.get('balance', 0) < amount:
            return False
        await UserDatabase.change_balance(user_id, -amount)
        return True

class GameUI:
    @staticmethod
    def play_again_button(command_name: str, args_text: str = "") -> InlineKeyboardMarkup:
        cb_data = f"games:repeat:{command_name}:{args_text or '_'}"
        return InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Again", callback_data=cb_data)]])

    @staticmethod
    def game_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("🪙 Coin Flip", callback_data="games:info:sbet"), InlineKeyboardButton("🎲 Dice Roll", callback_data="games:info:roll")],
            [InlineKeyboardButton("🎰 Gamble", callback_data="games:info:gamble"), InlineKeyboardButton("🏀 Basketball", callback_data="games:info:basket")],
            [InlineKeyboardButton("🎯 Darts", callback_data="games:info:dart"), InlineKeyboardButton("🤝 Contract", callback_data="games:info:stour")],
            [InlineKeyboardButton("🧩 Riddle", callback_data="games:info:riddle")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def format_result(result: GameResult, game_emoji: str) -> str:
        msg = f"{game_emoji} "
        if result.display_outcome:
            msg += f"{result.display_outcome} — "
        msg += result.message
        if result.tokens_gained > 0:
            msg += f"\n🎁 Bonus: +{result.tokens_gained} token(s)!"
        return msg

class GameLogic:
    @staticmethod
    def coinflip(guess: str, amount: int) -> GameResult:
        outcome = random.choice(['heads', 'tails'])
        won = (outcome == guess)
        if won:
            win_amount = amount * GameConfig.COINFLIP_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"You won {win_amount} coins!", display_outcome=outcome)
        else:
            return GameResult(won=False, amount_changed=0, message=f"You lost {amount} coins.", display_outcome=outcome)

    @staticmethod
    def dice_roll(choice: str, amount: int) -> GameResult:
        dice = random.randint(1, 6)
        result = 'odd' if dice % 2 else 'even'
        won = (result == choice)
        if won:
            win_amount = amount * GameConfig.DICE_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Rolled {dice} ({result}) — You won {win_amount} coins!", display_outcome=f"🎲 {dice}")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Rolled {dice} ({result}) — You lost {amount} coins.", display_outcome=f"🎲 {dice}")

    @staticmethod
    def gamble(pick: str, amount: int) -> GameResult:
        won = random.random() < GameConfig.GAMBLE_WIN_RATE
        if won:
            display = random.choice(['l', 'r'])
            win_amount = amount * GameConfig.GAMBLE_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"You won {win_amount} coins!", display_outcome=display.upper())
        else:
            display = 'r' if pick == 'l' else 'l'
            return GameResult(won=False, amount_changed=0, message=f"You lost {amount} coins.", display_outcome=display.upper())

    @staticmethod
    def basketball(amount: int) -> GameResult:
        win_chance = min(0.6, GameConfig.BASKET_BASE_WIN_RATE + math.log1p(amount) / 50)
        won = random.random() < win_chance
        if won:
            win_amount = amount * GameConfig.BASKET_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Swish! You scored {win_amount} coins!")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Missed! You lost {amount} coins.")

    @staticmethod
    def darts(amount: int) -> GameResult:
        roll = random.random()
        if roll < GameConfig.DART_BULLSEYE_RATE:
            win_amount = amount * GameConfig.DART_BULLSEYE_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"🎯 Bullseye! You won {win_amount} coins!", display_outcome="BULLSEYE")
        elif roll < (GameConfig.DART_BULLSEYE_RATE + GameConfig.DART_HIT_RATE):
            win_amount = amount * GameConfig.DART_HIT_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Good hit! You won {win_amount} coins!", display_outcome="HIT")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Missed! You lost {amount} coins.", display_outcome="MISS")

    @staticmethod
    def contract() -> GameResult:
        success = random.random() < GameConfig.STOUR_SUCCESS_RATE
        if success:
            reward_type = random.choice(["coins", "tokens"])
            if reward_type == "coins":
                reward = random.randint(100, 600)
                return GameResult(won=True, amount_changed=reward, message=f"Contract successful! You earned {reward} coins!")
            else:
                tokens = random.randint(1, 3)
                return GameResult(won=True, amount_changed=0, tokens_gained=tokens, message=f"Contract granted you {tokens} token(s)!")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Contract failed! You lost {GameConfig.STOUR_ENTRY_FEE} coins.")

    @staticmethod
    def generate_riddle() -> Tuple[str, str]:
        a = random.randint(2, 50)
        b = random.randint(1, 50)
        op = random.choice(['+', '-', '*'])
        if op == '+':
            ans = a + b
        elif op == '-':
            ans = a - b
        else:
            ans = a * b
        question = f"{a} {op} {b}"
        return question, str(ans)

async def handle_cooldown(update: Update, user_id: int) -> bool:
    on_cooldown, seconds_left = game_state.check_cooldown(user_id)
    if on_cooldown:
        await update.message.reply_text(f"⌛ Please wait {seconds_left:.1f} seconds before playing again.")
        return True
    return False

async def validate_amount(update: Update, amount: int, user_id: int) -> bool:
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be positive.")
        return False
    user = await UserDatabase.get_user(user_id)
    if not user or user.get('balance', 0) < amount:
        await update.message.reply_text("💰 You don't have enough coins.")
        return False
    return True

async def sbet(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
        guess = context.args[1].lower()
    except (IndexError, ValueError):
        await update.message.reply_text("📖 Usage: `/sbet <amount> heads|tails`\nExample: `/sbet 100 heads`", parse_mode="Markdown")
        return
    if guess in ('h', 'head', 'heads'):
        guess = 'heads'
    elif guess in ('t', 'tail', 'tails'):
        guess = 'tails'
    else:
        await update.message.reply_text("❌ Guess must be 'heads' or 'tails'.")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.coinflip(guess, amount)
    if result.won:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    game_state.record_play(user_id, GameType.COINFLIP.value)
    game_state.set_cooldown(user_id)
    await update.message.reply_text(GameUI.format_result(result, "🪙"), reply_markup=GameUI.play_again_button("sbet", f"{amount}:{guess}"))

async def roll_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
        choice = context.args[1].lower()
    except (IndexError, ValueError):
        await update.message.reply_text("📖 Usage: `/roll <amount> odd|even`\nExample: `/roll 50 odd`", parse_mode="Markdown")
        return
    if choice in ('o', 'odd'):
        choice = 'odd'
    elif choice in ('e', 'even'):
        choice = 'even'
    else:
        await update.message.reply_text("❌ Choice must be 'odd' or 'even'.")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.dice_roll(choice, amount)
    if result.won:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    game_state.record_play(user_id, GameType.DICE.value)
    game_state.set_cooldown(user_id)
    await update.message.reply_text(GameUI.format_result(result, "🎲"), reply_markup=GameUI.play_again_button("roll", f"{amount}:{choice}"))

async def gamble(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
        pick = context.args[1].lower()
    except (IndexError, ValueError):
        await update.message.reply_text("📖 Usage: `/gamble <amount> l|r`\nExample: `/gamble 100 l`", parse_mode="Markdown")
        return
    if pick not in ('l', 'r', 'left', 'right'):
        await update.message.reply_text("❌ Choice must be 'l' or 'r'.")
        return
    pick = 'l' if pick.startswith('l') else 'r'
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.gamble(pick, amount)
    if result.won:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    game_state.record_play(user_id, GameType.GAMBLE.value)
    game_state.set_cooldown(user_id)
    await update.message.reply_text(GameUI.format_result(result, "🎰"), reply_markup=GameUI.play_again_button("gamble", f"{amount}:{pick}"))

async def basket(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("📖 Usage: `/basket <amount>`\nExample: `/basket 75`", parse_mode="Markdown")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.basketball(amount)
    if result.won:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    game_state.record_play(user_id, GameType.BASKET.value)
    game_state.set_cooldown(user_id)
    await update.message.reply_text(GameUI.format_result(result, "🏀"), reply_markup=GameUI.play_again_button("basket", str(amount)))

async def dart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("📖 Usage: `/dart <amount>`\nExample: `/dart 50`", parse_mode="Markdown")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.darts(amount)
    if result.won:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    game_state.record_play(user_id, GameType.DART.value)
    game_state.set_cooldown(user_id)
    await update.message.reply_text(GameUI.format_result(result, "🎯"), reply_markup=GameUI.play_again_button("dart", str(amount)))

async def stour(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, GameConfig.STOUR_ENTRY_FEE, user_id):
        await update.message.reply_text(f"💰 You need at least {GameConfig.STOUR_ENTRY_FEE} coins to start a contract.")
        return
    await UserDatabase.change_balance(user_id, -GameConfig.STOUR_ENTRY_FEE)
    result = GameLogic.contract()
    if result.amount_changed > 0:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    if result.tokens_gained > 0:
        await UserDatabase.change_tokens(user_id, result.tokens_gained)
    game_state.record_play(user_id, GameType.CONTRACT.value)
    game_state.set_cooldown(user_id)
    await update.message.reply_text(GameUI.format_result(result, "🤝"), parse_mode="HTML", reply_markup=GameUI.play_again_button("stour", ""))

async def riddle(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    question, answer = GameLogic.generate_riddle()
    question_text = f"🧩 **Riddle Time!**\nSolve: `{question}`\n\n⏱ You have {GameConfig.RIDDLE_TIMEOUT} seconds.\nReply with just the number!"
    msg = await update.message.reply_text(question_text, parse_mode="Markdown")
    riddle_data = PendingRiddle(answer=answer, expires_at=time.time() + GameConfig.RIDDLE_TIMEOUT, message_id=msg.message_id, chat_id=update.effective_chat.id, question=question)
    game_state.add_riddle(user_id, riddle_data)
    game_state.set_cooldown(user_id)
    game_state.record_play(user_id, GameType.RIDDLE.value)
    
    async def expire_riddle():
        await asyncio.sleep(GameConfig.RIDDLE_TIMEOUT)
        pending = game_state.get_riddle(user_id)
        if pending and time.time() >= pending.expires_at:
            game_state.remove_riddle(user_id)
            try:
                await application.bot.send_message(pending.chat_id, f"⏳ Time's up! The correct answer was `{answer}`.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error sending expiry message: {e}")
    
    asyncio.create_task(expire_riddle())

async def riddle_answer_listener(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    pending = game_state.get_riddle(user_id)
    if not pending:
        return
    if update.effective_chat.id != pending.chat_id:
        return
    text = (update.message.text or "").strip()
    if not text:
        return
    if time.time() > pending.expires_at:
        game_state.remove_riddle(user_id)
        await update.message.reply_text("⏳ Riddle expired.")
        return
    if text == pending.answer:
        await UserDatabase.change_tokens(user_id, pending.reward)
        await update.message.reply_text(f"✅ Correct! You earned {pending.reward} token(s)! 🎉", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Wrong! The correct answer was `{pending.answer}`.", parse_mode="Markdown")
    game_state.remove_riddle(user_id)

async def games_menu_cmd(update: Update, context: CallbackContext):
    menu_text = "🎮 **Welcome to the Games Hub!**\n\nChoose a game to play and win coins and tokens!\n\n**Available Games:**\n• 🪙 Coin Flip - Guess heads or tails\n• 🎲 Dice Roll - Bet on odd or even\n• 🎰 Gamble - Pick left or right\n• 🏀 Basketball - Skill-based shooting\n• 🎯 Darts - Aim for the bullseye\n• 🤝 Contract - High risk, high reward\n• 🧩 Riddle - Solve math problems\n\nUse /gamestats to see your statistics!"
    await update.message.reply_text(menu_text, parse_mode="Markdown", reply_markup=GameUI.game_menu())

async def game_stats_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDatabase.get_user(user_id)
    stats = game_state.get_stats(user_id)
    if not stats:
        await update.message.reply_text("📊 You haven't played any games yet!\nUse /games to start playing.")
        return
    total_plays = sum(stats.values())
    stats_text = f"📊 **{update.effective_user.first_name}'s Game Stats**\n\n💰 Balance: {user.get('balance', 0)} coins\n🎁 Tokens: {user.get('tokens', 0)}\n🎮 Total Games Played: {total_plays}\n\n**Games Breakdown:**\n"
    game_names = {'sbet': '🪙 Coin Flip', 'roll': '🎲 Dice Roll', 'gamble': '🎰 Gamble', 'basket': '🏀 Basketball', 'dart': '🎯 Darts', 'stour': '🤝 Contract', 'riddle': '🧩 Riddle'}
    for game, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        game_name = game_names.get(game, game)
        percentage = (count / total_plays) * 100
        stats_text += f"• {game_name}: {count} plays ({percentage:.1f}%)\n"
    await update.message.reply_text(stats_text, parse_mode="Markdown")

async def leaderboard_cmd(update: Update, context: CallbackContext):
    try:
        top_players = await user_collection.find().sort('balance', -1).limit(10).to_list(length=10)
        if not top_players:
            await update.message.reply_text(f"⏰ You've already claimed your daily bonus!\nCome back in {hours_left:.1f} hours.")
            return
    daily_coins = random.randint(50, 150)
    daily_tokens = random.randint(0, 2)
    await UserDatabase.change_balance(user_id, daily_coins)
    if daily_tokens > 0:
        await UserDatabase.change_tokens(user_id, daily_tokens)
    await user_collection.update_one({'id': user_id}, {'$set': {'last_daily_claim': now}})
    bonus_text = f"🎁 **Daily Bonus Claimed!**\n\nYou received:\n💰 {daily_coins} coins\n"
    if daily_tokens > 0:
        bonus_text += f"🎁 {daily_tokens} token(s)\n"
    bonus_text += "\nCome back tomorrow for another bonus!"
    await update.message.reply_text(bonus_text, parse_mode="Markdown")

async def tokens_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDatabase.get_user(user_id)
    tokens = user.get('tokens', 0)
    balance = user.get('balance', 0)
    tokens_text = (
        f"🎁 **{update.effective_user.first_name}'s Tokens**\n\n"
        f"💎 Total Tokens: {tokens}\n"
        f"💰 Balance: {balance:,} coins\n\n"
        f"**How to earn tokens:**\n"
        f"• 🧩 Solve riddles (/riddle)\n"
        f"• 🤝 Complete contracts (/stour)\n"
        f"• 🎁 Daily bonuses (/daily)\n\n"
        f"Keep playing to earn more!"
    )
    await update.message.reply_text(tokens_text, parse_mode="Markdown")

async def games_callback_query(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split(":", 3)
    if len(parts) < 3:
        return
    _, action, cmd_name = parts[:3]
    arg_text = parts[3] if len(parts) > 3 else ""
    if action == "repeat":
        if arg_text == "_" or arg_text == "":
            argv = []
        else:
            argv = arg_text.split(":")
        context.args = argv
        
        effective_message = query.message
        original_update_message = update.message
        update.message = effective_message
        
        game_handlers = {
            "sbet": sbet,
            "roll": roll_cmd,
            "gamble": gamble,
            "basket": basket,
            "dart": dart,
            "stour": stour,
            "riddle": riddle
        }
        handler = game_handlers.get(cmd_name)
        if handler:
            await handler(update, context)
        else:
            await query.message.reply_text("❌ Unknown game command.")
        
        update.message = original_update_message
    elif action == "info":
        game_info = {
            "sbet": f"🪙 **Coin Flip**\n\nBet on heads or tails!\nWin multiplier: {GameConfig.COINFLIP_MULTIPLIER}x\nWin rate: 50%\n\nUsage: `/sbet <amount> heads|tails`\nExample: `/sbet 100 heads`",
            "roll": f"🎲 **Dice Roll**\n\nBet on odd or even!\nWin multiplier: {GameConfig.DICE_MULTIPLIER}x\nWin rate: 50%\n\nUsage: `/roll <amount> odd|even`\nExample: `/roll 50 odd`",
            "gamble": f"🎰 **Gamble**\n\nPick left or right!\nWin multiplier: {GameConfig.GAMBLE_MULTIPLIER}x\nWin rate: {GameConfig.GAMBLE_WIN_RATE*100:.0f}%\n\nUsage: `/gamble <amount> l|r`\nExample: `/gamble 100 l`",
            "basket": f"🏀 **Basketball**\n\nShoot hoops for coins!\nWin multiplier: {GameConfig.BASKET_MULTIPLIER}x\nWin rate: Variable (35-60%)\n\nUsage: `/basket <amount>`\nExample: `/basket 75`",
            "dart": f"🎯 **Darts**\n\nAim for the bullseye!\nBullseye: {GameConfig.DART_BULLSEYE_MULTIPLIER}x ({GameConfig.DART_BULLSEYE_RATE*100:.0f}%)\nHit: {GameConfig.DART_HIT_MULTIPLIER}x ({GameConfig.DART_HIT_RATE*100:.0f}%)\n\nUsage: `/dart <amount>`\nExample: `/dart 50`",
            "stour": f"🤝 **Contract**\n\nHigh risk, high reward!\nEntry fee: {GameConfig.STOUR_ENTRY_FEE} coins\nSuccess rate: {GameConfig.STOUR_SUCCESS_RATE*100:.0f}%\nRewards: Coins or tokens\n\nUsage: `/stour`",
            "riddle": f"🧩 **Riddle**\n\nSolve math problems!\nTime limit: {GameConfig.RIDDLE_TIMEOUT} seconds\nReward: Tokens\n\nUsage: `/riddle`"
        }
        info_text = game_info.get(cmd_name, "❌ Game information not found.")
        await query.message.reply_text(info_text, parse_mode="Markdown")

async def help_games_cmd(update: Update, context: CallbackContext):
    help_text = f"🎮 **Games Help & Commands**\n\n**Available Commands:**\n• `/games` - Show games menu\n• `/sbet <amt> <h|t>` - Coin flip\n• `/roll <amt> <odd|even>` - Dice roll\n• `/gamble <amt> <l|r>` - Gamble game\n• `/basket <amt>` - Basketball\n• `/dart <amt>` - Darts\n• `/stour` - Contract game\n• `/riddle` - Math riddle\n• `/gamestats` - Your statistics\n• `/tokens` - View your tokens\n• `/leaderboard` - Top players\n• `/daily` - Daily bonus\n\n**Tips:**\n• Start with smaller bets to learn\n• Check win rates before playing\n• Claim your daily bonus!\n• Complete riddles for tokens\n\n⏱ Cooldown: {GameConfig.COOLDOWN_SECONDS}s between games"
    await update.message.reply_text(help_text, parse_mode="Markdown")

ADMIN_IDS = []

async def admin_give_coins(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /givecoins <user_id> <amount>")
        return
    await UserDatabase.change_balance(target_id, amount)
    await update.message.reply_text(f"✅ Gave {amount} coins to user {target_id}")
    logger.info(f"Admin {update.effective_user.id} gave {amount} coins to {target_id}")

async def admin_give_tokens(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /givetokens <user_id> <amount>")
        return
    await UserDatabase.change_tokens(target_id, amount)
    await update.message.reply_text(f"✅ Gave {amount} tokens to user {target_id}")
    logger.info(f"Admin {update.effective_user.id} gave {amount} tokens to {target_id}")

async def admin_reset_cooldown(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /resetcooldown <user_id>")
        return
    game_state._cooldowns.pop(target_id, None)
    await update.message.reply_text(f"✅ Reset cooldown for user {target_id}")
    logger.info(f"Admin {update.effective_user.id} reset cooldown for {target_id}")

def register_handlers():
    application.add_handler(CommandHandler("sbet", sbet, block=False))
    application.add_handler(CommandHandler("roll", roll_cmd, block=False))
    application.add_handler(CommandHandler("gamble", gamble, block=False))
    application.add_handler(CommandHandler("basket", basket, block=False))
    application.add_handler(CommandHandler("dart", dart, block=False))
    application.add_handler(CommandHandler("stour", stour, block=False))
    application.add_handler(CommandHandler("riddle", riddle, block=False))
    application.add_handler(CommandHandler("games", games_menu_cmd, block=False))
    application.add_handler(CommandHandler("gamestats", game_stats_cmd, block=False))
    application.add_handler(CommandHandler("tokens", tokens_cmd, block=False))
    application.add_handler(CommandHandler("leaderboard", leaderboard_cmd, block=False))
    application.add_handler(CommandHandler("daily", daily_bonus_cmd, block=False))
    application.add_handler(CommandHandler("helpgames", help_games_cmd, block=False))
    if ADMIN_IDS:
        application.add_handler(CommandHandler("givecoins", admin_give_coins, block=False))
        application.add_handler(CommandHandler("givetokens", admin_give_tokens, block=False))
        application.add_handler(CommandHandler("resetcooldown", admin_reset_cooldown, block=False))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, riddle_answer_listener, block=False))
    application.add_handler(CallbackQueryHandler(games_callback_query, pattern=r"^games:", block=False))
    logger.info("✅ All game handlers registered successfully")

register_handlers()

__version__ = "2.0.0"
__author__ = "Enhanced Games Module"
__description__ = "Comprehensive Telegram bot games system with improved architecture"