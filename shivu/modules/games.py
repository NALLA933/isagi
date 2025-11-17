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
    BASKET_BASE_WIN_RATE = 0.10
    DART_BULLSEYE_RATE = 0.1
    DART_HIT_RATE = 0.10
    GAMBLE_WIN_RATE = 0.10
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

class GameUI:
    @staticmethod
    def play_again_button(command_name: str, args_text: str = "") -> InlineKeyboardMarkup:
        cb_data = f"games:repeat:{command_name}:{args_text or '_'}"
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Play Again", callback_data=cb_data)]])

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
    def format_result(result: GameResult, game_emoji: str, user_name: str) -> str:
        status = "✅ <b>WIN</b>" if result.won else "❌ <b>LOSE</b>"
        msg = f"<b>{game_emoji} Game Result</b>\n{status}\n"
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
        won = (outcome == guess)
        if won:
            win_amount = amount * GameConfig.COINFLIP_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"You won <b>{win_amount:,}</b> coins", display_outcome=outcome.upper())
        else:
            return GameResult(won=False, amount_changed=0, message=f"You lost <b>{amount:,}</b> coins", display_outcome=outcome.upper())

    @staticmethod
    def dice_roll(choice: str, amount: int) -> GameResult:
        dice = random.randint(1, 6)
        result = 'odd' if dice % 2 else 'even'
        won = (result == choice)
        if won:
            win_amount = amount * GameConfig.DICE_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Rolled <b>{dice}</b> ({result})\nYou won <b>{win_amount:,}</b> coins", display_outcome=f"🎲 {dice}")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Rolled <b>{dice}</b> ({result})\nYou lost <b>{amount:,}</b> coins", display_outcome=f"🎲 {dice}")

    @staticmethod
    def gamble(pick: str, amount: int) -> GameResult:
        won = random.random() < GameConfig.GAMBLE_WIN_RATE
        if won:
            display = random.choice(['L', 'R'])
            win_amount = amount * GameConfig.GAMBLE_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"You won <b>{win_amount:,}</b> coins", display_outcome=f"LEFT" if display == 'L' else "RIGHT")
        else:
            display = 'R' if pick == 'l' else 'L'
            return GameResult(won=False, amount_changed=0, message=f"You lost <b>{amount:,}</b> coins", display_outcome=f"LEFT" if display == 'L' else "RIGHT")

    @staticmethod
    def basketball(amount: int) -> GameResult:
        win_chance = min(0.6, GameConfig.BASKET_BASE_WIN_RATE + math.log1p(amount) / 50)
        won = random.random() < win_chance
        if won:
            win_amount = amount * GameConfig.BASKET_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Perfect shot! You scored <b>{win_amount:,}</b> coins")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Missed! You lost <b>{amount:,}</b> coins")

    @staticmethod
    def darts(amount: int) -> GameResult:
        roll = random.random()
        if roll < GameConfig.DART_BULLSEYE_RATE:
            win_amount = amount * GameConfig.DART_BULLSEYE_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Bullseye! You won <b>{win_amount:,}</b> coins", display_outcome="🎯 BULLSEYE")
        elif roll < (GameConfig.DART_BULLSEYE_RATE + GameConfig.DART_HIT_RATE):
            win_amount = amount * GameConfig.DART_HIT_MULTIPLIER
            return GameResult(won=True, amount_changed=win_amount, message=f"Good hit! You won <b>{win_amount:,}</b> coins", display_outcome="TARGET HIT")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Missed! You lost <b>{amount:,}</b> coins", display_outcome="MISS")

    @staticmethod
    def contract() -> GameResult:
        success = random.random() < GameConfig.STOUR_SUCCESS_RATE
        if success:
            reward_type = random.choice(["coins", "tokens"])
            if reward_type == "coins":
                reward = random.randint(100, 600)
                return GameResult(won=True, amount_changed=reward, message=f"Contract completed! You earned <b>{reward:,}</b> coins")
            else:
                tokens = random.randint(1, 3)
                return GameResult(won=True, amount_changed=0, tokens_gained=tokens, message=f"Contract completed! You received <b>{tokens}</b> token(s)")
        else:
            return GameResult(won=False, amount_changed=0, message=f"Contract failed! You lost <b>{GameConfig.STOUR_ENTRY_FEE:,}</b> coins")

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

async def get_message_object(update: Update):
    if update.callback_query:
        return update.callback_query.message
    return update.message

async def send_reply(update: Update, text: str, reply_markup=None, parse_mode="HTML"):
    msg = await get_message_object(update)
    return await msg.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

async def handle_cooldown(update: Update, user_id: int) -> bool:
    on_cooldown, seconds_left = game_state.check_cooldown(user_id)
    if on_cooldown:
        await send_reply(update, f"<b>⏱ Cooldown Active</b>\n<blockquote>Wait {seconds_left:.1f}s before playing again</blockquote>")
        return True
    return False

async def validate_amount(update: Update, amount: int, user_id: int) -> bool:
    if amount <= 0:
        await send_reply(update, "<b>❌ Invalid Amount</b>\n<blockquote>Amount must be positive</blockquote>")
        return False
    user = await UserDatabase.get_user(user_id)
    if not user or user.get('balance', 0) < amount:
        await send_reply(update, "<b>💰 Insufficient Balance</b>\n<blockquote>You don't have enough coins</blockquote>")
        return False
    return True

async def process_game(update: Update, context: CallbackContext, game_type: GameType, amount: int, result: GameResult, extra_args: str = ""):
    user_id = update.effective_user.id
    user = await UserDatabase.get_user(user_id)
    user_name = user.get('first_name', 'Player')
    
    if result.won and result.amount_changed > 0:
        await UserDatabase.change_balance(user_id, result.amount_changed)
    if result.tokens_gained > 0:
        await UserDatabase.change_tokens(user_id, result.tokens_gained)
    
    game_state.record_play(user_id, game_type.value)
    game_state.set_cooldown(user_id)
    
    game_emojis = {GameType.COINFLIP: "🪙", GameType.DICE: "🎲", GameType.GAMBLE: "🎰", GameType.BASKET: "🏀", GameType.DART: "🎯", GameType.CONTRACT: "🤝"}
    emoji = game_emojis.get(game_type, "🎮")
    formatted_msg = GameUI.format_result(result, emoji, user_name)
    
    updated_user = await UserDatabase.get_user(user_id)
    new_balance = updated_user.get('balance', 0)
    formatted_msg += f"\n<b>Balance:</b> <code>{new_balance:,}</code> coins"
    
    await send_reply(update, formatted_msg, reply_markup=GameUI.play_again_button(game_type.value, extra_args))

async def sbet(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
        guess = context.args[1].lower()
    except (IndexError, ValueError):
        await send_reply(update, "<b>📖 Usage</b>\n<blockquote><code>/sbet &lt;amount&gt; heads|tails</code>\n<i>Example: /sbet 100 heads</i></blockquote>")
        return
    if guess in ('h', 'head', 'heads'):
        guess = 'heads'
    elif guess in ('t', 'tail', 'tails'):
        guess = 'tails'
    else:
        await send_reply(update, "<b>❌ Invalid Choice</b>\n<blockquote>Must be 'heads' or 'tails'</blockquote>")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.coinflip(guess, amount)
    await process_game(update, context, GameType.COINFLIP, amount, result, f"{amount}:{guess}")

async def roll_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
        choice = context.args[1].lower()
    except (IndexError, ValueError):
        await send_reply(update, "<b>📖 Usage</b>\n<blockquote><code>/roll &lt;amount&gt; odd|even</code>\n<i>Example: /roll 50 odd</i></blockquote>")
        return
    if choice in ('o', 'odd'):
        choice = 'odd'
    elif choice in ('e', 'even'):
        choice = 'even'
    else:
        await send_reply(update, "<b>❌ Invalid Choice</b>\n<blockquote>Must be 'odd' or 'even'</blockquote>")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.dice_roll(choice, amount)
    await process_game(update, context, GameType.DICE, amount, result, f"{amount}:{choice}")

async def gamble(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
        pick = context.args[1].lower()
    except (IndexError, ValueError):
        await send_reply(update, "<b>📖 Usage</b>\n<blockquote><code>/gamble &lt;amount&gt; l|r</code>\n<i>Example: /gamble 100 l</i></blockquote>")
        return
    if pick not in ('l', 'r', 'left', 'right'):
        await send_reply(update, "<b>❌ Invalid Choice</b>\n<blockquote>Must be 'l' or 'r'</blockquote>")
        return
    pick = 'l' if pick.startswith('l') else 'r'
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.gamble(pick, amount)
    await process_game(update, context, GameType.GAMBLE, amount, result, f"{amount}:{pick}")

async def basket(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await send_reply(update, "<b>📖 Usage</b>\n<blockquote><code>/basket &lt;amount&gt;</code>\n<i>Example: /basket 75</i></blockquote>")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.basketball(amount)
    await process_game(update, context, GameType.BASKET, amount, result, str(amount))

async def dart(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await send_reply(update, "<b>📖 Usage</b>\n<blockquote><code>/dart &lt;amount&gt;</code>\n<i>Example: /dart 50</i></blockquote>")
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, amount, user_id):
        return
    await UserDatabase.change_balance(user_id, -amount)
    result = GameLogic.darts(amount)
    await process_game(update, context, GameType.DART, amount, result, str(amount))

async def stour(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await validate_amount(update, GameConfig.STOUR_ENTRY_FEE, user_id):
        await send_reply(update, f"<b>💰 Insufficient Balance</b>\n<blockquote>Need at least <code>{GameConfig.STOUR_ENTRY_FEE:,}</code> coins</blockquote>")
        return
    await UserDatabase.change_balance(user_id, -GameConfig.STOUR_ENTRY_FEE)
    result = GameLogic.contract()
    await process_game(update, context, GameType.CONTRACT, GameConfig.STOUR_ENTRY_FEE, result, "")

async def riddle(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if await handle_cooldown(update, user_id):
        return
    question, answer = GameLogic.generate_riddle()
    msg = await get_message_object(update)
    question_text = f"<b>🧩 Riddle Time</b>\n<blockquote expandable>Solve: <b>{question}</b>\nTime: <code>{GameConfig.RIDDLE_TIMEOUT}s</code> | Reward: <code>{GameConfig.DEFAULT_TOKEN_REWARD}</code> token(s)</blockquote>\n<i>Reply with the number</i>"
    sent_msg = await msg.reply_text(question_text, parse_mode="HTML")
    riddle_data = PendingRiddle(answer=answer, expires_at=time.time() + GameConfig.RIDDLE_TIMEOUT, message_id=sent_msg.message_id, chat_id=update.effective_chat.id, question=question)
    game_state.add_riddle(user_id, riddle_data)
    game_state.set_cooldown(user_id)
    game_state.record_play(user_id, GameType.RIDDLE.value)
    
    async def expire_riddle():
        await asyncio.sleep(GameConfig.RIDDLE_TIMEOUT)
        pending = game_state.get_riddle(user_id)
        if pending and time.time() >= pending.expires_at:
            game_state.remove_riddle(user_id)
            try:
                await application.bot.send_message(pending.chat_id, f"<b>⏳ Time's Up</b>\n<blockquote>Answer was <b>{answer}</b></blockquote>", parse_mode="HTML")
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
        return
    if text == pending.answer:
        await UserDatabase.change_tokens(user_id, pending.reward)
        user = await UserDatabase.get_user(user_id)
        new_tokens = user.get('tokens', 0)
        await update.message.reply_text(f"<b>✅ Correct</b>\n<blockquote>Earned <b>{pending.reward}</b> token(s)\nTotal: <code>{new_tokens}</code></blockquote>", parse_mode="HTML")
    else:
        await update.message.reply_text(f"<b>❌ Wrong</b>\n<blockquote>Answer was <b>{pending.answer}</b></blockquote>", parse_mode="HTML")
    game_state.remove_riddle(user_id)

async def games_menu_cmd(update: Update, context: CallbackContext):
    menu_text = f"<b>🎮 Games Hub</b>\n<blockquote expandable><b>Available Games:</b>\n🪙 Coin Flip • 🎲 Dice Roll\n🎰 Gamble • 🏀 Basketball\n🎯 Darts • 🤝 Contract\n🧩 Riddle</blockquote>\n<i>Click below to learn more</i>"
    await send_reply(update, menu_text, reply_markup=GameUI.game_menu())

async def game_stats_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDatabase.get_user(user_id)
    stats = game_state.get_stats(user_id)
    if not stats:
        await send_reply(update, "<b>📊 No Statistics</b>\n<blockquote>You haven't played yet\nUse /games to start</blockquote>")
        return
    total_plays = sum(stats.values())
    stats_text = f"<b>📊 Statistics</b>\n<b>Player:</b> {update.effective_user.first_name}\n<blockquote>Balance: <code>{user.get('balance', 0):,}</code> coins\nTokens: <code>{user.get('tokens', 0)}</code>\nGames: <code>{total_plays}</code></blockquote>\n<b>Breakdown:</b>\n"
    game_names = {'sbet': '🪙 Coin Flip', 'roll': '🎲 Dice', 'gamble': '🎰 Gamble', 'basket': '🏀 Basketball', 'dart': '🎯 Darts', 'stour': '🤝 Contract', 'riddle': '🧩 Riddle'}
    for game, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        game_name = game_names.get(game, game)
        percentage = (count / total_plays) * 100
        stats_text += f"<blockquote>{game_name}: <code>{count}</code> ({percentage:.1f}%)</blockquote>\n"
    await send_reply(update, stats_text)

async def leaderboard_cmd(update: Update, context: CallbackContext):
    try:
        top_players = await user_collection.find().sort('balance', -1).limit(10).to_list(length=10)
        if not top_players:
            await send_reply(update, "<b>🏆 No Players</b>\n<blockquote>Be the first to play</blockquote>")
            return
        header_image = "https://files.catbox.moe/i8x33x.jpg"
        footer_image = "https://files.catbox.moe/33yrky.jpg"
        leaderboard_text = f'<a href="{header_image}">&#8203;</a>\n<b>🏆 Top Players</b>\n'
        medals = ["🥇", "🥈", "🥉"]
        for i, player in enumerate(top_players):
            user_id = player.get('id')
            first_name = player.get('first_name', 'Unknown')
            username = player.get('username', None)
            balance = player.get('balance', 0)
            tokens = player.get('tokens', 0)
            medal = medals[i] if i < 3 else f"<b>{i+1}.</b>"
            if username:
                user_mention = f'<a href="tg://user?id={user_id}">@{username}</a>'
            else:
                user_mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
            balance_formatted = f"{balance:,}"
            leaderboard_text += f"<blockquote expandable>{medal} {user_mention}\n<code>{balance_formatted}</code> coins • <code>{tokens}</code> tokens</blockquote>\n"
        leaderboard_text += f'<a href="{footer_image}">&#8203;</a><i>Keep playing</i>'
        await send_reply(update, leaderboard_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}")
        await send_reply(update, "<b>❌ Error</b>\n<blockquote>Failed to load leaderboard</blockquote>")

async def daily_bonus_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDatabase.get_user(user_id)
    last_claim = user.get('last_daily_claim')
    now = datetime.utcnow()
    if last_claim:
        time_since_claim = now - last_claim
        if time_since_claim < timedelta(hours=24):
            hours_left = 24 - time_since_claim.total_seconds() / 3600
            await send_reply(update, f"<b>⏰ Already Claimed</b>\n<blockquote>Come back in <code>{hours_left:.1f}</code> hours</blockquote>")
            return
    daily_coins = random.randint(50, 150)
    daily_tokens = random.randint(0, 2)
    await UserDatabase.change_balance(user_id, daily_coins)
    if daily_tokens > 0:
        await UserDatabase.change_tokens(user_id, daily_tokens)
    await user_collection.update_one({'id': user_id}, {'$set': {'last_daily_claim': now}})
    bonus_text = f"<b>🎁 Daily Bonus</b>\n<blockquote expandable>Coins: <code>+{daily_coins}</code>"
    if daily_tokens > 0:
        bonus_text += f"\nTokens: <code>+{daily_tokens}</code>"
    bonus_text += "</blockquote>\n<i>Come back tomorrow</i>"
    await send_reply(update, bonus_text)

async def tokens_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    await UserDatabase.ensure_user(user_id, update.effective_user.first_name, update.effective_user.username)
    user = await UserDatabase.get_user(user_id)
    tokens = user.get('tokens', 0)
    balance = user.get('balance', 0)
    tokens_text = f"<b>💎 Your Tokens</b>\n<b>Player:</b> {update.effective_user.first_name}\n<blockquote>Tokens: <code>{tokens}</code>\nBalance: <code>{balance:,}</code> coins</blockquote>\n<b>How to Earn:</b>\n<blockquote expandable>🧩 Riddles - Solve math (/riddle)\n🤝 Contracts - Complete missions (/stour)\n🎁 Daily - Claim every 24h (/daily)</blockquote>"
    await send_reply(update, tokens_text)

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
        game_handlers = {"sbet": sbet, "roll": roll_cmd, "gamble": gamble, "basket": basket, "dart": dart, "stour": stour, "riddle": riddle}
        handler = game_handlers.get(cmd_name)
        if handler:
            await handler(update, context)
        else:
            await send_reply(update, "<b>❌ Error</b>\n<blockquote>Unknown command</blockquote>")
    
    elif action == "info":
        game_info = {
            "sbet": f"<b>🪙 Coin Flip</b>\n<blockquote expandable><b>How to Play:</b> Bet on heads or tails\n<b>Multiplier:</b> <code>{GameConfig.COINFLIP_MULTIPLIER}x</code>\n<b>Win Rate:</b> <code>50%</code>\n\n<b>Usage:</b>\n<code>/sbet &lt;amount&gt; heads|tails</code>\n\n<i>Example: /sbet 100 heads</i></blockquote>",
            "roll": f"<b>🎲 Dice Roll</b>\n<blockquote expandable><b>How to Play:</b> Bet on odd or even\n<b>Multiplier:</b> <code>{GameConfig.DICE_MULTIPLIER}x</code>\n<b>Win Rate:</b> <code>50%</code>\n\n<b>Usage:</b>\n<code>/roll &lt;amount&gt; odd|even</code>\n\n<i>Example: /roll 50 odd</i></blockquote>",
            "gamble": f"<b>🎰 Gamble</b>\n<blockquote expandable><b>How to Play:</b> Pick left or right\n<b>Multiplier:</b> <code>{GameConfig.GAMBLE_MULTIPLIER}x</code>\n<b>Win Rate:</b> <code>{GameConfig.GAMBLE_WIN_RATE*100:.0f}%</code>\n\n<b>Usage:</b>\n<code>/gamble &lt;amount&gt; l|r</code>\n\n<i>Example: /gamble 100 l</i></blockquote>",
            "basket": f"<b>🏀 Basketball</b>\n<blockquote expandable><b>How to Play:</b> Shoot hoops for coins\n<b>Multiplier:</b> <code>{GameConfig.BASKET_MULTIPLIER}x</code>\n<b>Win Rate:</b> <code>35-60%</code>\n\n<b>Usage:</b>\n<code>/basket &lt;amount&gt;</code>\n\n<i>Example: /basket 75</i></blockquote>",
            "dart": f"<b>🎯 Darts</b>\n<blockquote expandable><b>How to Play:</b> Aim for bullseye\n<b>Bullseye:</b> <code>{GameConfig.DART_BULLSEYE_MULTIPLIER}x</code> ({GameConfig.DART_BULLSEYE_RATE*100:.0f}%)\n<b>Hit:</b> <code>{GameConfig.DART_HIT_MULTIPLIER}x</code> ({GameConfig.DART_HIT_RATE*100:.0f}%)\n\n<b>Usage:</b>\n<code>/dart &lt;amount&gt;</code>\n\n<i>Example: /dart 50</i></blockquote>",
            "stour": f"<b>🤝 Contract</b>\n<blockquote expandable><b>How to Play:</b> High risk, high reward\n<b>Entry Fee:</b> <code>{GameConfig.STOUR_ENTRY_FEE}</code> coins\n<b>Success:</b> <code>{GameConfig.STOUR_SUCCESS_RATE*100:.0f}%</code>\n<b>Rewards:</b> Coins or tokens\n\n<b>Usage:</b>\n<code>/stour</code></blockquote>",
            "riddle": f"<b>🧩 Riddle</b>\n<blockquote expandable><b>How to Play:</b> Solve math problems\n<b>Time Limit:</b> <code>{GameConfig.RIDDLE_TIMEOUT}s</code>\n<b>Reward:</b> <code>{GameConfig.DEFAULT_TOKEN_REWARD}</code> token(s)\n\n<b>Usage:</b>\n<code>/riddle</code></blockquote>"
        }
        info_text = game_info.get(cmd_name, "<b>❌ Error</b>\n<blockquote>Game not found</blockquote>")
        await query.message.reply_text(info_text, parse_mode="HTML")

async def help_games_cmd(update: Update, context: CallbackContext):
    help_text = f"<b>📚 Games Help</b>\n<b>Commands:</b>\n<blockquote expandable><code>/games</code> - Games menu\n<code>/sbet &lt;amt&gt; &lt;h|t&gt;</code> - Coin flip\n<code>/roll &lt;amt&gt; &lt;odd|even&gt;</code> - Dice\n<code>/gamble &lt;amt&gt; &lt;l|r&gt;</code> - Gamble\n<code>/basket &lt;amt&gt;</code> - Basketball\n<code>/dart &lt;amt&gt;</code> - Darts\n<code>/stour</code> - Contract\n<code>/riddle</code> - Riddle\n<code>/gamestats</code> - Statistics\n<code>/tokens</code> - View tokens\n<code>/leaderboard</code> - Rankings\n<code>/daily</code> - Daily bonus</blockquote>\n<b>Tips:</b>\n<blockquote>• Start small\n• Check win rates\n• Claim daily bonus\n• Solve riddles\n• Use Play Again</blockquote>\n<i>Cooldown: {GameConfig.COOLDOWN_SECONDS}s</i>"
    await send_reply(update, help_text)

ADMIN_IDS = []

async def admin_give_coins(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await send_reply(update, "<b>Usage:</b> <code>/givecoins &lt;user_id&gt; &lt;amount&gt;</code>")
        return
    await UserDatabase.change_balance(target_id, amount)
    await send_reply(update, f"<b>✅ Success</b>\n<blockquote>Gave <code>{amount:,}</code> coins to user <code>{target_id}</code></blockquote>")
    logger.info(f"Admin {update.effective_user.id} gave {amount} coins to {target_id}")

async def admin_give_tokens(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await send_reply(update, "<b>Usage:</b> <code>/givetokens &lt;user_id&gt; &lt;amount&gt;</code>")
        return
    await UserDatabase.change_tokens(target_id, amount)
    await send_reply(update, f"<b>✅ Success</b>\n<blockquote>Gave <code>{amount}</code> tokens to user <code>{target_id}</code></blockquote>")
    logger.info(f"Admin {update.effective_user.id} gave {amount} tokens to {target_id}")

async def admin_reset_cooldown(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await send_reply(update, "<b>Usage:</b> <code>/resetcooldown &lt;user_id&gt;</code>")
        return
    game_state._cooldowns.pop(target_id, None)
    await send_reply(update, f"<b>✅ Success</b>\n<blockquote>Reset cooldown for user <code>{target_id}</code></blockquote>")
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
    logger.info("✅ All game handlers registered")

register_handlers()

__version__ = "2.0.0"
__author__ = "Enhanced Games Module"
__description__ = "Telegram bot games system"

logger.info(f"Games module v{__version__} loaded")