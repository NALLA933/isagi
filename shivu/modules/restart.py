import asyncio
import math
import random
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update, InputMediaAnimation, InputMediaVideo
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

class AttackType(Enum):
    FIRE = ("fire", 30, 35, "https://files.catbox.moe/y3zz0k.mp4", "🔥")
    ICE = ("ice", 25, 28, "https://files.catbox.moe/tm5iwt.mp4", "❄️")
    LIGHTNING = ("lightning", 35, 40, "https://i.imgur.com/XoK5gHD.gif", "⚡")
    WATER = ("water", 20, 25, "https://i.imgur.com/wKk7LnD.gif", "💧")
    EARTH = ("earth", 22, 30, "https://i.imgur.com/R9t8KJm.gif", "🌍")
    WIND = ("wind", 28, 32, "https://i.imgur.com/yD9Xm3K.gif", "💨")
    DARK = ("dark", 40, 45, "https://i.imgur.com/7J8FKpL.gif", "🌑")
    LIGHT = ("light", 38, 42, "https://i.imgur.com/mN9pQwX.gif", "✨")
    NORMAL = ("normal", 15, 20, "https://i.imgur.com/KqZ8Rv2.gif", "👊")
    
    def __init__(self, name: str, mana_cost: int, base_damage: int, animation_url: str, emoji: str):
        self.attack_name = name
        self.mana_cost = mana_cost
        self.base_damage = base_damage
        self.animation_url = animation_url
        self.emoji = emoji

BATTLE_ANIMATIONS = {
    "defend": "https://i.imgur.com/xJ9KmPz.gif",
    "heal": "https://i.imgur.com/vR7TnQw.gif",
    "mana": "https://i.imgur.com/bS5HkLp.gif",
    "critical": "https://i.imgur.com/pT4JmNx.gif",
    "victory": "https://i.imgur.com/wQ9XmKp.gif",
    "defeat": "https://i.imgur.com/dL8RnYs.gif",
    "levelup": "https://i.imgur.com/hK3PmVw.gif"
}

SMALLCAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
    'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
    'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
    'y': 'ʏ', 'z': 'ᴢ',
    'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 'H': 'ʜ',
    'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ',
    'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x',
    'Y': 'ʏ', 'Z': 'ᴢ'
}

def to_smallcaps(text: str) -> str:
    return ''.join(SMALLCAPS_MAP.get(c, c) for c in text)

def calculate_level_from_xp(xp: int) -> int:
    return min(math.floor(math.sqrt(max(xp, 0) / 100)) + 1, 100)

def calculate_rank(level: int) -> str:
    ranks = {10: "E", 30: "D", 50: "C", 70: "B", 90: "A", 100: "S"}
    return next((r for lim, r in ranks.items() if level <= lim), "S")

def calculate_xp_needed(level: int) -> int:
    return ((level) ** 2) * 100

@dataclass
class PlayerStats:
    user_id: int
    username: str
    hp: int = 150
    max_hp: int = 150
    mana: int = 150
    max_mana: int = 150
    attack: int = 25
    defense: int = 15
    speed: int = 10
    level: int = 1
    rank: str = "E"
    xp: int = 0
    unlocked_attacks: List[str] = field(default_factory=lambda: ["normal", "fire", "ice"])
    
@dataclass
class BattleStats:
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    attacks_used: int = 0
    potions_used: int = 0
    defends_used: int = 0
    critical_hits: int = 0

class Battle:
    def __init__(self, player1: PlayerStats, player2: PlayerStats, is_pvp: bool = False):
        self.player1 = player1
        self.player2 = player2
        self.is_pvp = is_pvp
        self.current_turn = 1
        self.turn_count = 0
        self.started_at = datetime.utcnow()
        self.battle_log: List[str] = []
        self.p1_defending = False
        self.p2_defending = False
        self.p1_stats = BattleStats()
        self.p2_stats = BattleStats()
        self.last_action = None
        self.last_animation = None
        self.combo_count = 0
        
    def add_log(self, message: str):
        self.battle_log.append(message)
        if len(self.battle_log) > 6:
            self.battle_log.pop(0)
    
    def is_over(self) -> Tuple[bool, Optional[int]]:
        if self.player1.hp <= 0:
            return True, 2
        if self.player2.hp <= 0:
            return True, 1
        if (datetime.utcnow() - self.started_at).seconds > 600:
            return True, 1 if self.player1.hp > self.player2.hp else 2
        return False, None
    
    def switch_turn(self):
        self.current_turn = 2 if self.current_turn == 1 else 1
        self.turn_count += 1
        self.p1_defending = False
        self.p2_defending = False

class BattleManager:
    def __init__(self):
        self.active_battles: Dict[str, Battle] = {}
        self.pending_challenges: Dict[int, Dict] = {}
        
    def create_battle_id(self, user1_id: int, user2_id: int) -> str:
        return f"{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
    
    def start_battle(self, player1: PlayerStats, player2: PlayerStats, is_pvp: bool = False) -> Battle:
        battle_id = self.create_battle_id(player1.user_id, player2.user_id)
        battle = Battle(player1, player2, is_pvp)
        self.active_battles[battle_id] = battle
        return battle
    
    def get_battle(self, user1_id: int, user2_id: int = None) -> Optional[Battle]:
        if user2_id:
            battle_id = self.create_battle_id(user1_id, user2_id)
            return self.active_battles.get(battle_id)
        for battle in self.active_battles.values():
            if battle.player1.user_id == user1_id or battle.player2.user_id == user2_id:
                return battle
        return None
    
    def end_battle(self, user1_id: int, user2_id: int):
        battle_id = self.create_battle_id(user1_id, user2_id)
        self.active_battles.pop(battle_id, None)
    
    def add_challenge(self, challenger_id: int, target_id: int, challenger_name: str):
        self.pending_challenges[target_id] = {
            'challenger_id': challenger_id,
            'challenger_name': challenger_name,
            'timestamp': datetime.utcnow()
        }
        asyncio.create_task(self.clear_challenge_after_timeout(target_id))
    
    async def clear_challenge_after_timeout(self, target_id: int):
        await asyncio.sleep(60)
        self.pending_challenges.pop(target_id, None)
    
    def get_challenge(self, target_id: int) -> Optional[Dict]:
        return self.pending_challenges.get(target_id)
    
    def remove_challenge(self, target_id: int):
        self.pending_challenges.pop(target_id, None)

battle_manager = BattleManager()

async def get_user(user_id: int):
    return await user_collection.find_one({'id': user_id})

def create_bar(current: int, maximum: int, length: int = 10) -> str:
    percentage = max(0, min(1, current / maximum))
    filled_length = int(length * percentage)
    bar = "█" * filled_length + "░" * (length - filled_length)
    return f"<code>{bar}</code>"

async def load_player_stats(user_id: int, username: str) -> PlayerStats:
    user_doc = await get_user(user_id)
    
    if not user_doc:
        user_doc = {
            'id': user_id,
            'username': username,
            'balance': 0,
            'tokens': 0,
            'user_xp': 0,
            'rpg_unlocked': ["normal", "fire", "ice"],
            'achievements': []
        }
        await user_collection.insert_one(user_doc)
    
    xp = user_doc.get('user_xp', 0)
    level = calculate_level_from_xp(xp)
    rank = calculate_rank(level)
    unlocked = user_doc.get('rpg_unlocked', ["normal", "fire", "ice"])
    
    stat_multiplier = 1 + (level - 1) * 0.1
    
    return PlayerStats(
        user_id=user_id,
        username=username,
        hp=int(150 * stat_multiplier),
        max_hp=int(150 * stat_multiplier),
        mana=int(150 * stat_multiplier),
        max_mana=int(150 * stat_multiplier),
        attack=int(25 * stat_multiplier),
        defense=int(15 * stat_multiplier),
        speed=int(10 * stat_multiplier),
        level=level,
        rank=rank,
        xp=xp,
        unlocked_attacks=unlocked
    )

async def save_player_progress(user_id: int, xp_gained: int, coins_gained: int):
    await user_collection.update_one(
        {'id': user_id},
        {
            '$inc': {
                'user_xp': xp_gained,
                'balance': coins_gained
            }
        },
        upsert=True
    )

def create_battle_keyboard(battle: Battle, current_user_id: int) -> InlineKeyboardMarkup:
    over, winner = battle.is_over()
    
    if over:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                to_smallcaps("new battle"), 
                callback_data=f"rpg:menu:{current_user_id}"
            )]
        ])
    
    is_turn = (battle.current_turn == 1 and current_user_id == battle.player1.user_id) or \
              (battle.current_turn == 2 and current_user_id == battle.player2.user_id)
    
    if not is_turn:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                to_smallcaps("⏳ waiting for opponent..."), 
                callback_data="rpg:wait"
            )]
        ])
    
    current_player = battle.player1 if current_user_id == battle.player1.user_id else battle.player2
    
    keyboard = []
    
    attack_row1 = []
    attack_row2 = []
    attack_row3 = []
    
    available_attacks = [
        (AttackType.NORMAL, "normal"),
        (AttackType.FIRE, "fire"),
        (AttackType.ICE, "ice"),
        (AttackType.LIGHTNING, "lightning"),
        (AttackType.WATER, "water"),
        (AttackType.EARTH, "earth"),
        (AttackType.WIND, "wind"),
        (AttackType.DARK, "dark"),
        (AttackType.LIGHT, "light")
    ]
    
    unlocked = current_player.unlocked_attacks
    available = [(atk, name) for atk, name in available_attacks if name in unlocked]
    
    for i, (attack, name) in enumerate(available):
        emoji = attack.emoji
        btn_text = f"{emoji} {name} ({attack.mana_cost}m)"
        callback = f"rpg:atk:{name}:{current_user_id}"
        
        if current_player.mana < attack.mana_cost:
            btn_text = f"✗ {btn_text}"
        
        button = InlineKeyboardButton(btn_text, callback_data=callback)
        
        if i < 3:
            attack_row1.append(button)
        elif i < 6:
            attack_row2.append(button)
        else:
            attack_row3.append(button)
    
    if attack_row1:
        keyboard.append(attack_row1)
    if attack_row2:
        keyboard.append(attack_row2)
    if attack_row3:
        keyboard.append(attack_row3)
    
    action_row = [
        InlineKeyboardButton(
            "🛡 " + to_smallcaps("defend"), 
            callback_data=f"rpg:defend:{current_user_id}"
        ),
        InlineKeyboardButton(
            "💚 " + to_smallcaps(f"heal (20m)"), 
            callback_data=f"rpg:heal:{current_user_id}"
        )
    ]
    keyboard.append(action_row)
    
    utility_row = [
        InlineKeyboardButton(
            "💙 " + to_smallcaps("mana potion"), 
            callback_data=f"rpg:mana:{current_user_id}"
        ),
        InlineKeyboardButton(
            "🏳 " + to_smallcaps("forfeit"), 
            callback_data=f"rpg:forfeit:{current_user_id}"
        )
    ]
    keyboard.append(utility_row)
    
    return InlineKeyboardMarkup(keyboard)

def format_battle_panel(battle: Battle) -> str:
    p1 = battle.player1
    p2 = battle.player2
    
    p1_hp_bar = create_bar(p1.hp, p1.max_hp, 12)
    p1_mana_bar = create_bar(p1.mana, p1.max_mana, 12)
    p2_hp_bar = create_bar(p2.hp, p2.max_hp, 12)
    p2_mana_bar = create_bar(p2.mana, p2.max_mana, 12)
    
    turn_indicator_1 = "▶" if battle.current_turn == 1 else "  "
    turn_indicator_2 = "▶" if battle.current_turn == 2 else "  "
    
    defend_status_1 = " 🛡" if battle.p1_defending else ""
    defend_status_2 = " 🛡" if battle.p2_defending else ""
    
    combo_text = ""
    if battle.combo_count > 1:
        combo_text = f"\n{to_smallcaps(f'combo: x{battle.combo_count}!')}"
    
    panel = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('⚔️ battle arena ⚔️')}</b>
<b>{'═' * 30}</b>

{turn_indicator_1} <b>{to_smallcaps('player 1')}</b> | {to_smallcaps(f'lvl {p1.level}')} | <b>{to_smallcaps(f'rank {p1.rank}')}</b>{defend_status_1}
<b>{to_smallcaps(p1.username[:15])}</b>
{to_smallcaps('hp')}: {p1_hp_bar} <code>{p1.hp}/{p1.max_hp}</code>
{to_smallcaps('mp')}: {p1_mana_bar} <code>{p1.mana}/{p1.max_mana}</code>
{to_smallcaps(f'⚔️ {p1.attack} | 🛡 {p1.defense} | ⚡ {p1.speed}')}

<b>{'━' * 30}</b>

{turn_indicator_2} <b>{to_smallcaps('player 2')}</b> | {to_smallcaps(f'lvl {p2.level}')} | <b>{to_smallcaps(f'rank {p2.rank}')}</b>{defend_status_2}
<b>{to_smallcaps((p2.username if battle.is_pvp else 'ai warrior')[:15])}</b>
{to_smallcaps('hp')}: {p2_hp_bar} <code>{p2.hp}/{p2.max_hp}</code>
{to_smallcaps('mp')}: {p2_mana_bar} <code>{p2.mana}/{p2.max_mana}</code>
{to_smallcaps(f'⚔️ {p2.attack} | 🛡 {p2.defense} | ⚡ {p2.speed}')}

<b>{'═' * 30}</b>
<b>{to_smallcaps('📜 battle log')}</b>
<b>{'═' * 30}</b>
"""
    
    if battle.battle_log:
        for log in battle.battle_log[-4:]:
            panel += f"\n{to_smallcaps('›')} {log}"
    else:
        panel += f"\n{to_smallcaps('› battle started! choose your action')}"
    
    panel += combo_text
    panel += f"\n\n{to_smallcaps(f'turn: {battle.turn_count}')}"
    
    return panel

async def send_animation(message, animation_url: str, caption: str):
    try:
        if animation_url.endswith('.mp4'):
            await message.reply_video(
                video=animation_url,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            await message.reply_animation(
                animation=animation_url,
                caption=caption,
                parse_mode="HTML"
            )
        await asyncio.sleep(1.5)
    except Exception:
        pass

async def perform_attack(
    battle: Battle, 
    attacker: PlayerStats, 
    defender: PlayerStats,
    attack_type: AttackType,
    attacker_num: int,
    message
) -> Tuple[str, int]:
    
    if attacker.mana < attack_type.mana_cost:
        return to_smallcaps(f"{attacker.username} doesn't have enough mana!"), 0
    
    attacker.mana -= attack_type.mana_cost
    
    attacker_stats = battle.p1_stats if attacker_num == 1 else battle.p2_stats
    defender_stats = battle.p2_stats if attacker_num == 1 else battle.p1_stats
    
    is_defending = battle.p2_defending if attacker_num == 1 else battle.p1_defending
    defense_mult = 2.5 if is_defending else 1.0
    
    base_damage = attack_type.base_damage + attacker.attack
    defense_reduction = int(defender.defense * defense_mult)
    final_damage = max(5, base_damage - defense_reduction)
    
    crit_chance = 0.15 + (attacker.speed * 0.008)
    is_crit = random.random() < crit_chance
    
    if is_crit:
        final_damage = int(final_damage * 1.8)
        attacker_stats.critical_hits += 1
        battle.combo_count += 1
        
        await send_animation(
            message,
            BATTLE_ANIMATIONS["critical"],
            f"<b>💥 {to_smallcaps('critical hit!')} 💥</b>"
        )
    else:
        battle.combo_count = 0
    
    defender.hp = max(0, defender.hp - final_damage)
    
    attacker_stats.attacks_used += 1
    attacker_stats.total_damage_dealt += final_damage
    defender_stats.total_damage_taken += final_damage
    
    attack_caption = f"<b>{attack_type.emoji} {to_smallcaps(attacker.username)} {to_smallcaps('used')} {to_smallcaps(attack_type.attack_name)} {to_smallcaps('attack!')}</b>"
    
    await send_animation(message, attack_type.animation_url, attack_caption)
    
    crit_text = to_smallcaps(" [critical hit!]") if is_crit else ""
    damage_text = to_smallcaps(f"dealt {final_damage} damage{crit_text}")
    
    message_text = f"{attack_type.emoji} {to_smallcaps(attacker.username)} → {to_smallcaps(attack_type.attack_name)} | {damage_text}"
    
    battle.add_log(message_text)
    
    return message_text, final_damage

async def bot_ai_turn(battle: Battle, message):
    bot = battle.player2
    player = battle.player1
    
    await asyncio.sleep(1)
    
    if bot.hp < bot.max_hp * 0.25 and bot.mana >= 20:
        heal_amount = min(40, bot.max_hp - bot.hp)
        bot.hp += heal_amount
        bot.mana -= 20
        
        await send_animation(
            message,
            BATTLE_ANIMATIONS["heal"],
            f"<b>💚 {to_smallcaps('ai used healing potion!')}</b>"
        )
        
        battle.add_log(to_smallcaps(f"ai restored {heal_amount} hp"))
        return
    
    if bot.mana < 30:
        restore = min(50, bot.max_mana - bot.mana)
        bot.mana += restore
        
        await send_animation(
            message,
            BATTLE_ANIMATIONS["mana"],
            f"<b>💙 {to_smallcaps('ai used mana potion!')}</b>"
        )
        
        battle.add_log(to_smallcaps(f"ai restored {restore} mana"))
        return
    
    if random.random() < 0.18:
        battle.p2_defending = True
        battle.p2_stats.defends_used += 1
        
        await send_animation(
            message,
            BATTLE_ANIMATIONS["defend"],
            f"<b>🛡 {to_smallcaps('ai is defending!')}</b>"
        )
        
        battle.add_log(to_smallcaps("ai is defending!"))
        return
    
    available_attacks = [
        AttackType.NORMAL, AttackType.FIRE, AttackType.ICE,
        AttackType.LIGHTNING, AttackType.WATER, AttackType.EARTH
    ]
    available_attacks = [atk for atk in available_attacks if bot.mana >= atk.mana_cost]
    
    if not available_attacks:
        available_attacks = [AttackType.NORMAL]
    
    if player.hp < player.max_hp * 0.3:
        strong_attacks = [atk for atk in available_attacks if atk.base_damage > 30]
        chosen_attack = random.choice(strong_attacks if strong_attacks else available_attacks)
    else:
        chosen_attack = random.choice(available_attacks)
    
    await perform_attack(battle, bot, player, chosen_attack, 2, message)

async def rpg_start(update: Update, context: CallbackContext):
    user = update.effective_user
    message = update.message
    
    existing_battle = battle_manager.get_battle(user.id)
    if existing_battle:
        await message.reply_text(
            to_smallcaps("⚠️ you're already in a battle! finish it first or use /rpgforfeit"),
            parse_mode="HTML"
        )
        return
    
    if message.reply_to_message and message.reply_to_message.from_user.id != user.id:
        target_user = message.reply_to_message.from_user
        
        if target_user.is_bot:
            await message.reply_text(
                to_smallcaps("❌ you can't challenge a bot to pvp!"),
                parse_mode="HTML"
            )
            return
        
        existing_challenge = battle_manager.get_challenge(target_user.id)
        if existing_challenge:
            await message.reply_text(
                to_smallcaps("⚠️ this player already has a pending challenge!"),
                parse_mode="HTML"
            )
            return
        
        battle_manager.add_challenge(user.id, target_user.id, user.first_name)
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ " + to_smallcaps("accept"), 
                    callback_data=f"rpg:accept:{user.id}:{target_user.id}"
                ),
                InlineKeyboardButton(
                    "❌ " + to_smallcaps("decline"), 
                    callback_data=f"rpg:decline:{user.id}:{target_user.id}"
                )
            ]
        ])
        
        await message.reply_text(
            f"<b>⚔️ {to_smallcaps('battle challenge')} ⚔️</b>\n\n<b>{target_user.first_name}</b>, {user.first_name} {to_smallcaps('challenges you to a battle!')}\n\n{to_smallcaps('accept or decline within 60 seconds.')}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    player1 = await load_player_stats(user.id, user.first_name)
    
    bot_level = max(1, player1.level + random.randint(-2, 2))
    bot_xp = ((bot_level - 1) ** 2) * 100
    bot_rank = calculate_rank(bot_level)
    bot_stat_mult = 1 + (bot_level - 1) * 0.1
    
    player2 = PlayerStats(
        user_id=0,
        username="ai",
        hp=int(130 * bot_stat_mult),
        max_hp=int(130 * bot_stat_mult),
        mana=int(130 * bot_stat_mult),
        max_mana=int(130 * bot_stat_mult),
        attack=int(22 * bot_stat_mult),
        defense=int(13 * bot_stat_mult),
        speed=int(9 * bot_stat_mult),
        level=bot_level,
        rank=bot_rank,
        xp=bot_xp,
        unlocked_attacks=["normal", "fire", "ice", "lightning", "water", "earth"]
    )
    
    battle = battle_manager.start_battle(player1, player2, is_pvp=False)
    
    panel = format_battle_panel(battle)
    keyboard = create_battle_keyboard(battle, user.id)
    
    await message.reply_text(
        panel,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def rpg_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    action = data[1]
    
    if action == "wait":
        await query.answer(to_smallcaps("⏳ wait for your turn!"), show_alert=True)
        return
    
    if action == "menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⚔️ " + to_smallcaps("start pve battle"), 
                callback_data=f"rpg:start_pve:{update.effective_user.id}"
            )],
            [InlineKeyboardButton(
                "📊 " + to_smallcaps("view stats"), 
                callback_data=f"rpg:stats:{update.effective_user.id}"
            )],
            [InlineKeyboardButton(
                "🏆 " + to_smallcaps("leaderboard"),
                callback_data=f"rpg:leaderboard:{update.effective_user.id}"
            )]
        ])
        
        await query.message.edit_text(
            f"<b>⚔️ {to_smallcaps('rpg battle system')} ⚔️</b>\n\n{to_smallcaps('choose an option:')}",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    if action == "start_pve":
        user_id = int(data[2])
        if update.effective_user.id != user_id:
            await query.answer(to_smallcaps("❌ not your button!"), show_alert=True)
            return
        
        update.message = query.message
        update.message.from_user = update.effective_user
        await rpg_start(update, context)
        return
    
    if action == "accept":
        challenger_id = int(data[2])
        target_id = int(data[3])
        
        if update.effective_user.id != target_id:
            await query.answer(to_smallcaps("❌ this challenge isn't for you!"), show_alert=True)
            return
        
        challenge = battle_manager.get_challenge(target_id)
        if not challenge:
            await query.message.edit_text(
                to_smallcaps("⚠️ challenge expired!"),
                parse_mode="HTML"
            )
            return
        
        battle_manager.remove_challenge(target_id)
        
        player1 = await load_player_stats(challenger_id, challenge['challenger_name'])
        player2 = await load_player_stats(target_id, update.effective_user.first_name)
        
        battle = battle_manager.start_battle(player1, player2, is_pvp=True)
        
        panel = format_battle_panel(battle)
        keyboard = create_battle_keyboard(battle, challenger_id)
        
        await query.message.edit_text(
            panel,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    if action == "decline":
        challenger_id = int(data[2])
        target_id = int(data[3])
        
        if update.effective_user.id != target_id:
            await query.answer(to_smallcaps("❌ this challenge isn't for you!"), show_alert=True)
            return
        
        battle_manager.remove_challenge(target_id)
        
        await query.message.edit_text(
            to_smallcaps("❌ challenge declined!"),
            parse_mode="HTML"
        )
        return
    
    if action == "stats":
        user_id = int(data[2])
        if update.effective_user.id != user_id:
            await query.answer(to_smallcaps("❌ not your stats!"), show_alert=True)
            return
        
        player = await load_player_stats(user_id, update.effective_user.first_name)
        user_doc = await user_collection.find_one({'id': user_id})
        
        balance = user_doc.get('balance', 0)
        tokens = user_doc.get('tokens', 0)
        achievements = user_doc.get('achievements', [])
        
        current_xp = player.xp
        xp_needed = calculate_xp_needed(player.level)
        xp_progress = xp_needed - current_xp
        
        stats_text = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('📊 player stats 📊')}</b>
<b>{'═' * 30}</b>

<b>{to_smallcaps(player.username)}</b>
{to_smallcaps(f'level: {player.level}')}
{to_smallcaps(f'rank: {player.rank}')}
{to_smallcaps(f'xp: {current_xp}')}
{to_smallcaps(f'needed: {xp_progress}')}

<b>{to_smallcaps('combat stats:')}</b>
{to_smallcaps(f'❤️ hp: {player.max_hp}')}
{to_smallcaps(f'💙 mana: {player.max_mana}')}
{to_smallcaps(f'⚔️ attack: {player.attack}')}
{to_smallcaps(f'🛡️ defense: {player.defense}')}
{to_smallcaps(f'⚡ speed: {player.speed}')}

<b>{to_smallcaps('inventory:')}</b>
{to_smallcaps(f'💰 balance: {balance} coins')}
{to_smallcaps(f'🎫 tokens: {tokens}')}
{to_smallcaps(f'🏆 achievements: {len(achievements)}')}

<b>{to_smallcaps('unlocked attacks:')}</b>
{to_smallcaps(', '.join(player.unlocked_attacks))}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "◀ " + to_smallcaps("back"), 
                callback_data=f"rpg:menu:{user_id}"
            )]
        ])
        
        await query.message.edit_text(
            stats_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    if action == "leaderboard":
        user_id = int(data[2])
        
        top_users = await user_collection.find().sort('user_xp', -1).limit(10).to_list(length=10)
        
        leaderboard_text = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('🏆 leaderboard 🏆')}</b>
<b>{'═' * 30}</b>

"""
        
        for idx, user_doc in enumerate(top_users, 1):
            username = user_doc.get('username', user_doc.get('first_name', 'Unknown'))
            xp = user_doc.get('user_xp', 0)
            level = calculate_level_from_xp(xp)
            rank = calculate_rank(level)
            
            medal = ""
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"{idx}."
            
            leaderboard_text += f"{medal} <b>{username[:15]}</b> | {to_smallcaps(f'lvl {level}')} | {to_smallcaps(f'rank {rank}')} | {to_smallcaps(f'xp: {xp}')}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "◀ " + to_smallcaps("back"), 
                callback_data=f"rpg:menu:{user_id}"
            )]
        ])
        
        await query.message.edit_text(
            leaderboard_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    user_id = int(data[-1])
    
    if update.effective_user.id != user_id:
        await query.answer(to_smallcaps("❌ not your turn!"), show_alert=True)
        return
    
    battle = battle_manager.get_battle(user_id)
    
    if not battle:
        await query.message.edit_text(
            to_smallcaps("❌ battle not found! start a new one with /rpg"),
            parse_mode="HTML"
        )
        return
    
    is_player1 = user_id == battle.player1.user_id
    current_player = battle.player1 if is_player1 else battle.player2
    opponent = battle.player2 if is_player1 else battle.player1
    player_num = 1 if is_player1 else 2
    
    is_turn = (battle.current_turn == 1 and is_player1) or (battle.current_turn == 2 and not is_player1)
    
    if not is_turn:
        await query.answer(to_smallcaps("⏳ wait for your turn!"), show_alert=True)
        return
    
    over, winner = battle.is_over()
    if over:
        await query.answer(to_smallcaps("⚠️ battle is already over!"), show_alert=True)
        return
    
    action_message = ""
    
    if action == "atk":
        attack_name = data[2]
        
        try:
            attack_type = None
            for atk in AttackType:
                if atk.attack_name == attack_name:
                    attack_type = atk
                    break
            
            if not attack_type:
                await query.answer(to_smallcaps("❌ invalid attack!"), show_alert=True)
                return
            
            if attack_name not in current_player.unlocked_attacks:
                await query.answer(to_smallcaps("🔒 attack not unlocked!"), show_alert=True)
                return
            
            action_message, damage = await perform_attack(
                battle, current_player, opponent, attack_type, player_num, query.message
            )
            
            if damage == 0:
                await query.answer(action_message, show_alert=True)
                return
            
        except Exception as e:
            await query.answer(to_smallcaps(f"❌ error: {str(e)}"), show_alert=True)
            return
    
    elif action == "defend":
        if is_player1:
            battle.p1_defending = True
            battle.p1_stats.defends_used += 1
        else:
            battle.p2_defending = True
            battle.p2_stats.defends_used += 1
        
        await send_animation(
            query.message,
            BATTLE_ANIMATIONS["defend"],
            f"<b>🛡 {to_smallcaps(f'{current_player.username} is defending!')}</b>"
        )
        
        action_message = to_smallcaps(f"{current_player.username} is defending!")
        battle.add_log(action_message)
    
    elif action == "heal":
        if current_player.mana < 20:
            await query.answer(to_smallcaps("❌ not enough mana!"), show_alert=True)
            return
        
        heal_amount = min(40, current_player.max_hp - current_player.hp)
        current_player.hp += heal_amount
        current_player.mana -= 20
        
        stats = battle.p1_stats if is_player1 else battle.p2_stats
        stats.potions_used += 1
        
        await send_animation(
            query.message,
            BATTLE_ANIMATIONS["heal"],
            f"<b>💚 {to_smallcaps(f'{current_player.username} used healing potion!')}</b>"
        )
        
        action_message = to_smallcaps(f"{current_player.username} restored {heal_amount} hp")
        battle.add_log(action_message)
    
    elif action == "mana":
        restore_amount = min(50, current_player.max_mana - current_player.mana)
        current_player.mana += restore_amount
        
        stats = battle.p1_stats if is_player1 else battle.p2_stats
        stats.potions_used += 1
        
        await send_animation(
            query.message,
            BATTLE_ANIMATIONS["mana"],
            f"<b>💙 {to_smallcaps(f'{current_player.username} used mana potion!')}</b>"
        )
        
        action_message = to_smallcaps(f"{current_player.username} restored {restore_amount} mana")
        battle.add_log(action_message)
    
    elif action == "forfeit":
        battle_manager.end_battle(battle.player1.user_id, battle.player2.user_id)
        
        await query.message.edit_text(
            f"<b>🏳 {to_smallcaps('battle forfeited!')} 🏳</b>\n\n{to_smallcaps(f'{current_player.username} gave up!')}",
            parse_mode="HTML"
        )
        return
    
    battle.switch_turn()
    
    over, winner = battle.is_over()
    
    if over:
        await handle_battle_end(query.message, battle, winner)
        return
    
    if not battle.is_pvp and battle.current_turn == 2:
        await bot_ai_turn(battle, query.message)
        battle.switch_turn()
        
        over, winner = battle.is_over()
        if over:
            await handle_battle_end(query.message, battle, winner)
            return
    
    panel = format_battle_panel(battle)
    
    next_player_id = battle.player1.user_id if battle.current_turn == 1 else battle.player2.user_id
    keyboard = create_battle_keyboard(battle, next_player_id)
    
    try:
        await query.message.edit_text(
            panel,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        pass

async def handle_battle_end(message, battle: Battle, winner: int):
    battle_manager.end_battle(battle.player1.user_id, battle.player2.user_id)
    
    winner_player = battle.player1 if winner == 1 else battle.player2
    loser_player = battle.player2 if winner == 1 else battle.player1
    
    winner_stats = battle.p1_stats if winner == 1 else battle.p2_stats
    loser_stats = battle.p2_stats if winner == 1 else battle.p1_stats
    
    level_diff = abs(winner_player.level - loser_player.level)
    
    base_xp = 80 if battle.is_pvp else 50
    xp_multiplier = 1.0 + (level_diff * 0.15) + (winner_stats.critical_hits * 0.05)
    winner_xp = int(base_xp * xp_multiplier)
    loser_xp = int(base_xp * 0.4) if battle.is_pvp else 0
    
    base_coins = 150 if battle.is_pvp else 80
    winner_coins = base_coins + (winner_player.level * 15) + random.randint(30, 80)
    loser_coins = base_coins // 2 if battle.is_pvp else 0
    
    winner_old_level = winner_player.level
    winner_old_xp = winner_player.xp
    
    await save_player_progress(winner_player.user_id, winner_xp, winner_coins)
    
    if battle.is_pvp:
        await save_player_progress(loser_player.user_id, loser_xp, loser_coins)
    
    winner_new_data = await user_collection.find_one({'id': winner_player.user_id})
    winner_new_xp = winner_new_data.get('user_xp', 0)
    winner_new_level = calculate_level_from_xp(winner_new_xp)
    winner_new_rank = calculate_rank(winner_new_level)
    
    level_up_msg = ""
    level_up_animation = False
    
    if winner_new_level > winner_old_level:
        level_up_animation = True
        level_up_msg = f"\n\n<b>🎉 {to_smallcaps('level up!')} 🎉</b>\n{to_smallcaps(f'{winner_old_level} → {winner_new_level}')}"
        
        if winner_new_rank != winner_player.rank:
            level_up_msg += f"\n<b>{to_smallcaps(f'new rank: {winner_new_rank}')}</b>"
        
        new_attacks = []
        if winner_new_level >= 3 and "lightning" not in winner_player.unlocked_attacks:
            new_attacks.append("lightning")
        if winner_new_level >= 5 and "water" not in winner_player.unlocked_attacks:
            new_attacks.append("water")
        if winner_new_level >= 7 and "earth" not in winner_player.unlocked_attacks:
            new_attacks.append("earth")
        if winner_new_level >= 10 and "wind" not in winner_player.unlocked_attacks:
            new_attacks.append("wind")
        if winner_new_level >= 15 and "dark" not in winner_player.unlocked_attacks:
            new_attacks.append("dark")
        if winner_new_level >= 20 and "light" not in winner_player.unlocked_attacks:
            new_attacks.append("light")
        
        if new_attacks:
            await user_collection.update_one(
                {'id': winner_player.user_id},
                {'$addToSet': {'rpg_unlocked': {'$each': new_attacks}}}
            )
            level_up_msg += f"\n<b>🔓 {to_smallcaps('unlocked:')} {to_smallcaps(', '.join(new_attacks))}</b>"
    
    await send_animation(
        message,
        BATTLE_ANIMATIONS["victory"] if level_up_animation else BATTLE_ANIMATIONS["victory"],
        f"<b>👑 {to_smallcaps(f'{winner_player.username} wins!')} 👑</b>"
    )
    
    if level_up_animation:
        await send_animation(
            message,
            BATTLE_ANIMATIONS["levelup"],
            level_up_msg
        )
    
    result_text = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('⚔️ battle ended ⚔️')}</b>
<b>{'═' * 30}</b>

<b>👑 {to_smallcaps('winner:')}</b> {winner_player.username}
<b>💀 {to_smallcaps('loser:')}</b> {loser_player.username}

<b>{'═' * 30}</b>
<b>{to_smallcaps('📊 battle statistics 📊')}</b>
<b>{'═' * 30}</b>

<b>{to_smallcaps(winner_player.username)}</b>
{to_smallcaps(f'⚔️ damage dealt: {winner_stats.total_damage_dealt}')}
{to_smallcaps(f'🩸 damage taken: {winner_stats.total_damage_taken}')}
{to_smallcaps(f'🎯 attacks used: {winner_stats.attacks_used}')}
{to_smallcaps(f'💥 critical hits: {winner_stats.critical_hits}')}
{to_smallcaps(f'💊 potions used: {winner_stats.potions_used}')}
{to_smallcaps(f'🛡️ defends used: {winner_stats.defends_used}')}

<b>{to_smallcaps(loser_player.username)}</b>
{to_smallcaps(f'⚔️ damage dealt: {loser_stats.total_damage_dealt}')}
{to_smallcaps(f'🩸 damage taken: {loser_stats.total_damage_taken}')}
{to_smallcaps(f'🎯 attacks used: {loser_stats.attacks_used}')}
{to_smallcaps(f'💥 critical hits: {loser_stats.critical_hits}')}
{to_smallcaps(f'💊 potions used: {loser_stats.potions_used}')}
{to_smallcaps(f'🛡️ defends used: {loser_stats.defends_used}')}

<b>{'═' * 30}</b>
<b>{to_smallcaps('🎁 rewards 🎁')}</b>
<b>{'═' * 30}</b>

<b>{to_smallcaps(winner_player.username)}</b>
{to_smallcaps(f'✨ xp gained: +{winner_xp}')}
{to_smallcaps(f'💰 coins gained: +{winner_coins}')}
{level_up_msg}
"""
    
    if battle.is_pvp and loser_xp > 0:
        result_text += f"""

<b>{to_smallcaps(loser_player.username)}</b>
{to_smallcaps(f'✨ xp gained: +{loser_xp}')}
{to_smallcaps(f'💰 coins gained: +{loser_coins}')}
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⚔️ " + to_smallcaps("new battle"), 
            callback_data=f"rpg:menu:{winner_player.user_id}"
        )]
    ])
    
    await message.edit_text(
        result_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def rpg_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "⚔️ " + to_smallcaps("start pve battle"), 
            callback_data=f"rpg:start_pve:{user.id}"
        )],
        [InlineKeyboardButton(
            "📊 " + to_smallcaps("view stats"), 
            callback_data=f"rpg:stats:{user.id}"
        )],
        [InlineKeyboardButton(
            "🏆 " + to_smallcaps("leaderboard"),
            callback_data=f"rpg:leaderboard:{user.id}"
        )]
    ])
    
    await update.message.reply_text(
        f"<b>⚔️ {to_smallcaps('rpg battle system')} ⚔️</b>\n\n{to_smallcaps('choose an option:')}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def rpg_help(update: Update, context: CallbackContext):
    help_text = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('⚔️ rpg battle guide ⚔️')}</b>
<b>{'═' * 30}</b>

<b>{to_smallcaps('commands:')}</b>
{to_smallcaps('/rpg - start pve battle')}
{to_smallcaps('/rpg (reply) - challenge player')}
{to_smallcaps('/rpgmenu - open menu')}
{to_smallcaps('/rpgstats - view stats')}
{to_smallcaps('/rpglevel - check level')}
{to_smallcaps('/rpgforfeit - forfeit battle')}

<b>{to_smallcaps('attack types:')}</b>
👊 {to_smallcaps('normal (15m) - start')}
🔥 {to_smallcaps('fire (30m) - start')}
❄️ {to_smallcaps('ice (25m) - start')}
⚡ {to_smallcaps('lightning (35m) - lvl 3')}
💧 {to_smallcaps('water (20m) - lvl 5')}
🌍 {to_smallcaps('earth (22m) - lvl 7')}
💨 {to_smallcaps('wind (28m) - lvl 10')}
🌑 {to_smallcaps('dark (40m) - lvl 15')}
✨ {to_smallcaps('light (38m) - lvl 20')}

<b>{to_smallcaps('actions:')}</b>
🛡 {to_smallcaps('defend - 2.5x defense')}
💚 {to_smallcaps('heal (20m) - +40 hp')}
💙 {to_smallcaps('mana potion - +50 mp')}

<b>{to_smallcaps('tips:')}</b>
{to_smallcaps('• high speed = more crits')}
{to_smallcaps('• defending blocks damage')}
{to_smallcaps('• combos increase damage')}
{to_smallcaps('• xp levels you up')}
{to_smallcaps('• pvp gives bonus rewards')}
"""
    
    await update.message.reply_text(help_text, parse_mode="HTML")

async def rpg_stats_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    player = await load_player_stats(user.id, user.first_name)
    user_doc = await user_collection.find_one({'id': user.id})
    
    balance = user_doc.get('balance', 0) if user_doc else 0
    tokens = user_doc.get('tokens', 0) if user_doc else 0
    achievements = user_doc.get('achievements', []) if user_doc else []
    
    current_xp = player.xp
    xp_needed = calculate_xp_needed(player.level)
    xp_progress = xp_needed - current_xp
    
    stats_text = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('📊 player stats 📊')}</b>
<b>{'═' * 30}</b>

<b>{to_smallcaps(player.username)}</b>
{to_smallcaps(f'level: {player.level}')}
{to_smallcaps(f'rank: {player.rank}')}
{to_smallcaps(f'xp: {current_xp}')}
{to_smallcaps(f'needed: {xp_progress}')}

<b>{to_smallcaps('combat stats:')}</b>
{to_smallcaps(f'❤️ hp: {player.max_hp}')}
{to_smallcaps(f'💙 mana: {player.max_mana}')}
{to_smallcaps(f'⚔️ attack: {player.attack}')}
{to_smallcaps(f'🛡️ defense: {player.defense}')}
{to_smallcaps(f'⚡ speed: {player.speed}')}

<b>{to_smallcaps('inventory:')}</b>
{to_smallcaps(f'💰 balance: {balance} coins')}
{to_smallcaps(f'🎫 tokens: {tokens}')}
{to_smallcaps(f'🏆 achievements: {len(achievements)}')}

<b>{to_smallcaps('unlocked attacks:')}</b>
{to_smallcaps(', '.join(player.unlocked_attacks))}
"""
    
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def rpg_level_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    user = await get_user(uid)
    
    if not user:
        await update.message.reply_text(to_smallcaps("⚠️ no data found"), parse_mode="HTML")
        return

    xp = user.get('user_xp', 0)
    lvl = calculate_level_from_xp(xp)
    rank = calculate_rank(lvl)
    needed = calculate_xp_needed(lvl) - xp
    achievements = user.get('achievements', [])

    level_text = f"""
<b>{'═' * 30}</b>
<b>{to_smallcaps('level and rank')}</b>
<b>{'═' * 30}</b>

{to_smallcaps(f'level: {lvl}')}
{to_smallcaps(f'rank: {rank}')}
{to_smallcaps(f'xp: {xp}')}
{to_smallcaps(f'needed: {needed}')}
{to_smallcaps(f'achievements: {len(achievements)}')}
"""
    
    await update.message.reply_text(level_text, parse_mode="HTML")

async def rpg_forfeit_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    battle = battle_manager.get_battle(user_id)
    
    if not battle:
        await update.message.reply_text(
            to_smallcaps("❌ you're not in a battle!"),
            parse_mode="HTML"
        )
        return
    
    battle_manager.end_battle(battle.player1.user_id, battle.player2.user_id)
    
    await update.message.reply_text(
        f"<b>🏳 {to_smallcaps('battle forfeited!')} 🏳</b>\n\n{to_smallcaps('you gave up the battle!')}",
        parse_mode="HTML"
    )

application.add_handler(CommandHandler("rpg", rpg_start))
application.add_handler(CommandHandler("battle", rpg_start))
application.add_handler(CommandHandler("rpgmenu", rpg_menu))
application.add_handler(CommandHandler("rpgstats", rpg_stats_cmd))
application.add_handler(CommandHandler("rpglevel", rpg_level_cmd))
application.add_handler(CommandHandler("rpgforfeit", rpg_forfeit_cmd))
application.add_handler(CommandHandler("rpghelp", rpg_help))
application.add_handler(CallbackQueryHandler(rpg_callback, pattern="^rpg:"))