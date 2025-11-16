import asyncio
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

OWNER_ID = 5147822244

class Config:
    TIMEOUT = 60
    MIN_BET = 10
    MAX_BET = 10000
    ANIM_DELAY = 0.8
    COOLDOWN = 5

class Move(Enum):
    ROCK = "🪨"
    PAPER = "📄"
    SCISSORS = "✂️"
    
    def beats(self, other):
        return {Move.ROCK: Move.SCISSORS, Move.PAPER: Move.ROCK, Move.SCISSORS: Move.PAPER}[self] == other

class Game:
    def __init__(self, p1_id, p1_name, p2_id, p2_name, bet, chat_id):
        self.p1_id = p1_id
        self.p1_name = p1_name
        self.p2_id = p2_id
        self.p2_name = p2_name
        self.bet = bet
        self.chat_id = chat_id
        self.p1_move = None
        self.p2_move = None
        self.msg_id = 0
        self.expires = (datetime.utcnow() + timedelta(seconds=Config.TIMEOUT)).timestamp()
        self.accepted = False
    
    def winner(self):
        if not (self.p1_move and self.p2_move):
            return None
        if self.p1_move == self.p2_move:
            return None
        return self.p1_id if self.p1_move.beats(self.p2_move) else self.p2_id

class State:
    def __init__(self):
        self.games = {}
        self.user_map = {}
        self.cooldowns = {}
    
    def add(self, game):
        key = f"{game.chat_id}:{game.p1_id}"
        self.games[key] = game
        self.user_map[game.p1_id] = key
        self.user_map[game.p2_id] = key
        return key
    
    def get(self, user_id):
        key = self.user_map.get(user_id)
        return self.games.get(key) if key else None
    
    def remove(self, game):
        key = f"{game.chat_id}:{game.p1_id}"
        self.games.pop(key, None)
        self.user_map.pop(game.p1_id, None)
        self.user_map.pop(game.p2_id, None)
    
    def has_game(self, user_id):
        return user_id in self.user_map
    
    def check_cooldown(self, uid):
        last = self.cooldowns.get(uid)
        if not last:
            return False, 0
        elapsed = (datetime.utcnow() - last).total_seconds()
        if elapsed >= Config.COOLDOWN:
            self.cooldowns.pop(uid, None)
            return False, 0
        return True, Config.COOLDOWN - elapsed
    
    def set_cooldown(self, uid):
        self.cooldowns[uid] = datetime.utcnow()

state = State()

async def get_user(uid):
    return await user_collection.find_one({'id': uid})

async def has_coins(uid, amount):
    user = await get_user(uid)
    return user and user.get('balance', 0) >= amount

async def transfer(from_id, to_id, amount):
    await user_collection.update_one({'id': from_id}, {'$inc': {'balance': -amount}})
    await user_collection.update_one({'id': to_id}, {'$inc': {'balance': amount}})

async def refund(uid1, uid2, amount):
    await user_collection.update_one({'id': uid1}, {'$inc': {'balance': amount}})
    await user_collection.update_one({'id': uid2}, {'$inc': {'balance': amount}})

async def update_stats(uid, win, tie):
    key = 'rps_ties' if tie else ('rps_wins' if win else 'rps_losses')
    await user_collection.update_one({'id': uid}, {'$inc': {key: 1}}, upsert=True)

def challenge_kb(key):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ ᴀᴄᴄᴇᴘᴛ", callback_data=f"rps:accept:{key}"),
        InlineKeyboardButton("❌ ᴅᴇᴄʟɪɴᴇ", callback_data=f"rps:decline:{key}")
    ]])

def move_kb(key):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🪨 ʀᴏᴄᴋ", callback_data=f"rps:move:{key}:rock"),
        InlineKeyboardButton("📄 ᴘᴀᴘᴇʀ", callback_data=f"rps:move:{key}:paper"),
        InlineKeyboardButton("✂️ ꜱᴄɪꜱꜱᴏʀꜱ", callback_data=f"rps:move:{key}:scissors")
    ]])

def msg_challenge(g):
    return (
        f"<blockquote>🎮 <b>ʀᴏᴄᴋ ᴘᴀᴘᴇʀ ꜱᴄɪꜱꜱᴏʀꜱ</b>\n\n"
        f"<b>ᴄʜᴀʟʟᴇɴɢᴇʀ:</b> {g.p1_name}\n"
        f"<b>ᴏᴘᴘᴏɴᴇɴᴛ:</b> {g.p2_name}\n"
        f"<b>ʙᴇᴛ:</b> 💰 {g.bet} ᴄᴏɪɴꜱ\n\n"
        f"⏱ <i>{Config.TIMEOUT}ꜱ ᴛᴏ ᴀᴄᴄᴇᴘᴛ</i></blockquote>"
    )

def msg_waiting(g):
    s1 = "✅" if g.p1_move else "⏳"
    s2 = "✅" if g.p2_move else "⏳"
    return (
        f"<blockquote>🎮 <b>ɢᴀᴍᴇ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ</b>\n\n"
        f"{s1} {g.p1_name}\n"
        f"{s2} {g.p2_name}\n\n"
        f"💰 <b>ʙᴇᴛ:</b> {g.bet} ᴄᴏɪɴꜱ</blockquote>"
    )

def msg_anim(frame):
    emojis = ["🤜", "🤛", "✊"]
    e = emojis[frame % 3]
    return f"<blockquote><b>ʀᴏᴄᴋ... ᴘᴀᴘᴇʀ... ꜱᴄɪꜱꜱᴏʀꜱ...</b>\n\n<b>{e}     {e}</b></blockquote>"

def msg_result(g, winner_id):
    c1 = g.p1_move.value
    c2 = g.p2_move.value
    
    if winner_id is None:
        result = "🤝 <b>ɪᴛ'ꜱ ᴀ ᴛɪᴇ!</b>"
        subtitle = "ʙᴇᴛꜱ ʀᴇꜰᴜɴᴅᴇᴅ"
    else:
        winner = g.p1_name if winner_id == g.p1_id else g.p2_name
        result = f"🏆 <b>{winner} ᴡɪɴꜱ!</b>"
        subtitle = f"💰 +{g.bet * 2} ᴄᴏɪɴꜱ"
    
    return (
        f"<blockquote>{result}\n\n"
        f"<b>{g.p1_name}:</b> {c1}\n"
        f"<b>{g.p2_name}:</b> {c2}\n\n"
        f"<i>{subtitle}</i></blockquote>"
    )

async def animate(g, context):
    try:
        for i in range(3):
            await context.bot.edit_message_text(
                chat_id=g.chat_id,
                message_id=g.msg_id,
                text=msg_anim(i),
                parse_mode='HTML'
            )
            await asyncio.sleep(Config.ANIM_DELAY)
        
        winner_id = g.winner()
        
        if winner_id is None:
            await refund(g.p1_id, g.p2_id, g.bet)
            await update_stats(g.p1_id, False, True)
            await update_stats(g.p2_id, False, True)
        else:
            loser_id = g.p2_id if winner_id == g.p1_id else g.p1_id
            await transfer(loser_id, winner_id, g.bet * 2)
            await update_stats(winner_id, True, False)
            await update_stats(loser_id, False, False)
        
        await context.bot.edit_message_text(
            chat_id=g.chat_id,
            message_id=g.msg_id,
            text=msg_result(g, winner_id),
            parse_mode='HTML'
        )
        
        state.remove(g)
    except Exception:
        state.remove(g)

async def rps_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    
    on_cd, wait = state.check_cooldown(uid)
    if on_cd:
        await update.message.reply_text(
            f"<blockquote>⌛ ᴡᴀɪᴛ {wait:.1f}ꜱ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if state.has_game(uid):
        await update.message.reply_text(
            "<blockquote>❌ ʏᴏᴜ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "<blockquote>📖 <b>ᴜꜱᴀɢᴇ:</b> ʀᴇᴘʟʏ ᴛᴏ ᴜꜱᴇʀ ᴡɪᴛʜ\n"
            "<code>/rps &lt;amount&gt;</code>\n\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/rps 100</code></blockquote>",
            parse_mode='HTML'
        )
        return
    
    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "<blockquote>❌ ɪɴᴠᴀʟɪᴅ ᴀᴍᴏᴜɴᴛ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if bet < Config.MIN_BET or bet > Config.MAX_BET:
        await update.message.reply_text(
            f"<blockquote>❌ ʙᴇᴛ: {Config.MIN_BET}-{Config.MAX_BET}</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if not await has_coins(uid, bet):
        await update.message.reply_text(
            "<blockquote>💰 ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴄᴏɪɴꜱ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "<blockquote>❌ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴜꜱᴇʀ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    opp_id = update.message.reply_to_message.from_user.id
    opp_name = update.message.reply_to_message.from_user.first_name
    
    if opp_id == uid:
        await update.message.reply_text(
            "<blockquote>❌ ᴄᴀɴ'ᴛ ᴘʟᴀʏ ʏᴏᴜʀꜱᴇʟꜰ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if state.has_game(opp_id):
        await update.message.reply_text(
            "<blockquote>❌ ᴜꜱᴇʀ ɪɴ ᴀ ɢᴀᴍᴇ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if not await has_coins(opp_id, bet):
        await update.message.reply_text(
            "<blockquote>❌ ᴜꜱᴇʀ ɴᴏ ᴄᴏɪɴꜱ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    game = Game(uid, name, opp_id, opp_name, bet, update.effective_chat.id)
    key = state.add(game)
    
    msg = await update.message.reply_text(
        msg_challenge(game),
        parse_mode='HTML',
        reply_markup=challenge_kb(key)
    )
    
    game.msg_id = msg.message_id
    
    async def expire():
        await asyncio.sleep(Config.TIMEOUT)
        if state.has_game(uid):
            g = state.get(uid)
            if g and not g.accepted:
                state.remove(g)
                try:
                    await context.bot.edit_message_text(
                        chat_id=g.chat_id,
                        message_id=g.msg_id,
                        text="<blockquote>⏰ ᴇxᴘɪʀᴇᴅ</blockquote>",
                        parse_mode='HTML'
                    )
                except Exception:
                    pass
    
    asyncio.create_task(expire())
    state.set_cooldown(uid)

async def rps_stats(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await update.message.reply_text(
            "<blockquote>❌ ɴᴏ ᴅᴀᴛᴀ ꜰᴏᴜɴᴅ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    wins = user.get('rps_wins', 0)
    losses = user.get('rps_losses', 0)
    ties = user.get('rps_ties', 0)
    total = wins + losses + ties
    wr = (wins / total * 100) if total > 0 else 0
    
    await update.message.reply_text(
        f"<blockquote>📊 <b>ʀᴘꜱ ꜱᴛᴀᴛꜱ</b>\n\n"
        f"<b>ᴘʟᴀʏᴇʀ:</b> {update.effective_user.first_name}\n"
        f"💰 <b>ʙᴀʟᴀɴᴄᴇ:</b> {user.get('balance', 0)}\n\n"
        f"🎮 <b>ᴛᴏᴛᴀʟ:</b> {total}\n"
        f"🏆 <b>ᴡɪɴꜱ:</b> {wins}\n"
        f"💔 <b>ʟᴏꜱꜱᴇꜱ:</b> {losses}\n"
        f"🤝 <b>ᴛɪᴇꜱ:</b> {ties}\n"
        f"📈 <b>ᴡɪɴ ʀᴀᴛᴇ:</b> {wr:.1f}%</blockquote>",
        parse_mode='HTML'
    )

async def rps_help(update: Update, context: CallbackContext):
    await update.message.reply_text(
        f"<blockquote>🎮 <b>ʀᴏᴄᴋ ᴘᴀᴘᴇʀ ꜱᴄɪꜱꜱᴏʀꜱ</b>\n\n"
        f"<b>ʜᴏᴡ ᴛᴏ ᴘʟᴀʏ:</b>\n"
        f"1️⃣ ʀᴇᴘʟʏ: <code>/rps &lt;amount&gt;</code>\n"
        f"2️⃣ ᴛʜᴇʏ ᴀᴄᴄᴇᴘᴛ\n"
        f"3️⃣ ʙᴏᴛʜ ᴄʜᴏᴏꜱᴇ ᴍᴏᴠᴇ\n"
        f"4️⃣ ᴡᴀᴛᴄʜ ᴀɴɪᴍᴀᴛɪᴏɴ\n"
        f"5️⃣ ᴡɪɴɴᴇʀ ᴛᴀᴋᴇꜱ ᴀʟʟ\n\n"
        f"<b>ʀᴜʟᴇꜱ:</b>\n"
        f"🪨 ʀᴏᴄᴋ ʙᴇᴀᴛꜱ ✂️\n"
        f"📄 ᴘᴀᴘᴇʀ ʙᴇᴀᴛꜱ 🪨\n"
        f"✂️ ꜱᴄɪꜱꜱᴏʀꜱ ʙᴇᴀᴛꜱ 📄\n\n"
        f"<b>ᴄᴏᴍᴍᴀɴᴅꜱ:</b>\n"
        f"• <code>/rps &lt;amount&gt;</code>\n"
        f"• <code>/rpsstats</code>\n"
        f"• <code>/rpshelp</code>\n\n"
        f"💰 ʙᴇᴛ: {Config.MIN_BET}-{Config.MAX_BET}</blockquote>",
        parse_mode='HTML'
    )

async def rps_config(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "<blockquote><b>ᴏᴡɴᴇʀ ᴄᴏɴꜰɪɢ:</b>\n"
            f"<code>/rpsconfig timeout {Config.TIMEOUT}</code>\n"
            f"<code>/rpsconfig minbet {Config.MIN_BET}</code>\n"
            f"<code>/rpsconfig maxbet {Config.MAX_BET}</code>\n"
            f"<code>/rpsconfig cooldown {Config.COOLDOWN}</code>\n"
            f"<code>/rpsconfig animdelay {Config.ANIM_DELAY}</code></blockquote>",
            parse_mode='HTML'
        )
        return
    
    setting = context.args[0].lower()
    try:
        value = float(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "<blockquote>❌ ɪɴᴠᴀʟɪᴅ ᴠᴀʟᴜᴇ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if setting == 'timeout':
        Config.TIMEOUT = int(value)
    elif setting == 'minbet':
        Config.MIN_BET = int(value)
    elif setting == 'maxbet':
        Config.MAX_BET = int(value)
    elif setting == 'cooldown':
        Config.COOLDOWN = int(value)
    elif setting == 'animdelay':
        Config.ANIM_DELAY = value
    else:
        await update.message.reply_text(
            "<blockquote>❌ ᴜɴᴋɴᴏᴡɴ ꜱᴇᴛᴛɪɴɢ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text(
        f"<blockquote>✅ {setting} = {value}</blockquote>",
        parse_mode='HTML'
    )

async def rps_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    if len(data) < 3:
        return
    
    _, action, key = data[:3]
    uid = query.from_user.id
    
    game = state.get(uid)
    if not game:
        await query.edit_message_text(
            "<blockquote>❌ ɢᴀᴍᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ</blockquote>",
            parse_mode='HTML'
        )
        return
    
    if action == 'accept':
        if uid != game.p2_id:
            await query.answer("❌ ɴᴏᴛ ꜰᴏʀ ʏᴏᴜ", show_alert=True)
            return
        
        if not await has_coins(game.p1_id, game.bet):
            state.remove(game)
            await query.edit_message_text(
                "<blockquote>❌ ᴄʜᴀʟʟᴇɴɢᴇʀ ɴᴏ ᴄᴏɪɴꜱ</blockquote>",
                parse_mode='HTML'
            )
            return
        
        if not await has_coins(game.p2_id, game.bet):
            state.remove(game)
            await query.edit_message_text(
                "<blockquote>❌ ʏᴏᴜ ɴᴏ ᴄᴏɪɴꜱ</blockquote>",
                parse_mode='HTML'
            )
            return
        
        await user_collection.update_one({'id': game.p1_id}, {'$inc': {'balance': -game.bet}})
        await user_collection.update_one({'id': game.p2_id}, {'$inc': {'balance': -game.bet}})
        
        game.accepted = True
        
        await query.edit_message_text(
            msg_waiting(game),
            parse_mode='HTML',
            reply_markup=move_kb(key)
        )
    
    elif action == 'decline':
        if uid != game.p2_id:
            await query.answer("❌ ɴᴏᴛ ꜰᴏʀ ʏᴏᴜ", show_alert=True)
            return
        
        state.remove(game)
        await query.edit_message_text(
            "<blockquote>❌ ᴅᴇᴄʟɪɴᴇᴅ</blockquote>",
            parse_mode='HTML'
        )
    
    elif action == 'move':
        if not game.accepted:
            await query.answer("❌ ɢᴀᴍᴇ ɴᴏᴛ ᴀᴄᴄᴇᴘᴛᴇᴅ", show_alert=True)
            return
        
        if uid not in (game.p1_id, game.p2_id):
            await query.answer("❌ ɴᴏᴛ ʏᴏᴜʀ ɢᴀᴍᴇ", show_alert=True)
            return
        
        if len(data) < 4:
            return
        
        move_str = data[3]
        move_map = {'rock': Move.ROCK, 'paper': Move.PAPER, 'scissors': Move.SCISSORS}
        move = move_map.get(move_str)
        
        if not move:
            return
        
        if uid == game.p1_id:
            if game.p1_move:
                await query.answer("❌ ᴀʟʀᴇᴀᴅʏ ᴄʜᴏꜱᴇ", show_alert=True)
                return
            game.p1_move = move
            await query.answer(f"✅ {move.value}")
        else:
            if game.p2_move:
                await query.answer("❌ ᴀʟʀᴇᴀᴅʏ ᴄʜᴏꜱᴇ", show_alert=True)
                return
            game.p2_move = move
            await query.answer(f"✅ {move.value}")
        
        if game.p1_move and game.p2_move:
            await query.edit_message_text(msg_waiting(game), parse_mode='HTML')
            await animate(game, context)
        else:
            await query.edit_message_text(
                msg_waiting(game),
                parse_mode='HTML',
                reply_markup=move_kb(key)
            )

application.add_handler(CommandHandler("rps", rps_cmd, block=False))
application.add_handler(CommandHandler("rpsstats", rps_stats, block=False))
application.add_handler(CommandHandler("rpshelp", rps_help, block=False))
application.add_handler(CommandHandler("rpsconfig", rps_config, block=False))
application.add_handler(CallbackQueryHandler(rps_callback, pattern=r"^rps:", block=False))