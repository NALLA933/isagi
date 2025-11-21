import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

class AttackType(Enum):
    FIRE = ("fire", 30, 35, "https://files.catbox.moe/y3zz0k.mp4")
    ICE = ("ice", 25, 28, "https://files.catbox.moe/tm5iwt.mp4")
    LIGHTNING = ("lightning", 35, 40, None)
    WATER = ("water", 20, 25, None)
    EARTH = ("earth", 22, 30, None)
    WIND = ("wind", 28, 32, None)
    DARK = ("dark", 40, 45, None)
    LIGHT = ("light", 38, 42, None)
    NORMAL = ("normal", 15, 20, None)
    
    def __init__(self, name: str, mana_cost: int, base_damage: int, video_url: Optional[str]):
        self.attack_name = name
        self.mana_cost = mana_cost
        self.base_damage = base_damage
        self.video_url = video_url

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
    xp: int = 0
    unlocked_attacks: List[str] = field(default_factory=lambda: ["normal", "fire", "ice"])
    
@dataclass
class BattleStats:
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    attacks_used: int = 0
    potions_used: int = 0
    defends_used: int = 0

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
        self.waiting_for_video = False
        
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
            if battle.player1.user_id == user1_id or battle.player2.user_id == user1_id:
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

def create_bar(current: int, maximum: int, length: int = 10) -> str:
    percentage = max(0, min(1, current / maximum))
    filled_length = int(length * percentage)
    bar = "█" * filled_length + "░" * (length - filled_length)
    
    if percentage > 0.6:
        return f"<code>{bar}</code>"
    elif percentage > 0.3:
        return f"<code>{bar}</code>"
    else:
        return f"<code>{bar}</code>"

def get_level_from_xp(xp: int) -> int:
    return 1 + int(xp / 100)

def calculate_xp_reward(level_diff: int, won: bool) -> int:
    base_xp = 50 if won else 20
    multiplier = 1.0 + (level_diff * 0.1)
    return int(base_xp * max(0.5, multiplier))

async def load_player_stats(user_id: int, username: str) -> PlayerStats:
    user_doc = await user_collection.find_one({'id': user_id})
    
    if not user_doc:
        user_doc = {
            'id': user_id,
            'username': username,
            'balance': 0,
            'tokens': 0,
            'rpg_level': 1,
            'rpg_xp': 0,
            'rpg_unlocked': ["normal", "fire", "ice"]
        }
        await user_collection.insert_one(user_doc)
    
    level = user_doc.get('rpg_level', 1)
    xp = user_doc.get('rpg_xp', 0)
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
        xp=xp,
        unlocked_attacks=unlocked
    )

async def save_player_progress(user_id: int, xp_gained: int, coins_gained: int, level_up: bool = False):
    update_data = {
        '$inc': {
            'rpg_xp': xp_gained,
            'balance': coins_gained
        }
    }
    
    if level_up:
        current_user = await user_collection.find_one({'id': user_id})
        new_level = get_level_from_xp(current_user.get('rpg_xp', 0) + xp_gained)
        update_data['$set'] = {'rpg_level': new_level}
    
    await user_collection.update_one({'id': user_id}, update_data)

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
                to_smallcaps("waiting for opponent..."), 
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
        btn_text = f"{name.upper()} ({attack.mana_cost}m)"
        callback = f"rpg:atk:{name}:{current_user_id}"
        
        if current_player.mana < attack.mana_cost:
            btn_text = f"✗ {btn_text}"
        
        button = InlineKeyboardButton(to_smallcaps(btn_text), callback_data=callback)
        
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
            to_smallcaps("defend"), 
            callback_data=f"rpg:defend:{current_user_id}"
        ),
        InlineKeyboardButton(
            to_smallcaps(f"heal (20m)"), 
            callback_data=f"rpg:heal:{current_user_id}"
        )
    ]
    keyboard.append(action_row)
    
    utility_row = [
        InlineKeyboardButton(
            to_smallcaps("mana potion"), 
            callback_data=f"rpg:mana:{current_user_id}"
        ),
        InlineKeyboardButton(
            to_smallcaps("forfeit"), 
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
    
    turn_indicator_1 = "▶" if battle.current_turn == 1 else " "
    turn_indicator_2 = "▶" if battle.current_turn == 2 else " "
    
    defend_status_1 = to_smallcaps(" [defending]") if battle.p1_defending else ""
    defend_status_2 = to_smallcaps(" [defending]") if battle.p2_defending else ""
    
    panel = f"""
<b>{to_smallcaps('═══ battle arena ═══')}</b>

<b>{turn_indicator_1} {to_smallcaps('player 1')}</b> {to_smallcaps(f'| lvl {p1.level}')}{defend_status_1}
<b>{to_smallcaps(p1.username)}</b>
{to_smallcaps('hp')}: {p1_hp_bar} <code>{p1.hp}/{p1.max_hp}</code>
{to_smallcaps('mana')}: {p1_mana_bar} <code>{p1.mana}/{p1.max_mana}</code>
{to_smallcaps(f'atk: {p1.attack} | def: {p1.defense} | spd: {p1.speed}')}

<b>{'━' * 30}</b>

<b>{turn_indicator_2} {to_smallcaps('player 2')}</b> {to_smallcaps(f'| lvl {p2.level}')}{defend_status_2}
<b>{to_smallcaps(p2.username if battle.is_pvp else 'bot warrior')}</b>
{to_smallcaps('hp')}: {p2_hp_bar} <code>{p2.hp}/{p2.max_hp}</code>
{to_smallcaps('mana')}: {p2_mana_bar} <code>{p2.mana}/{p2.max_mana}</code>
{to_smallcaps(f'atk: {p2.attack} | def: {p2.defense} | spd: {p2.speed}')}

<b>{to_smallcaps('═══ battle log ═══')}</b>
"""
    
    if battle.battle_log:
        for log in battle.battle_log[-4:]:
            panel += f"\n{to_smallcaps('›')} {log}"
    else:
        panel += f"\n{to_smallcaps('› battle started!')}"
    
    panel += f"\n\n<b>{to_smallcaps(f'turn: {battle.turn_count}')}</b>"
    
    return panel

async def perform_attack(
    battle: Battle, 
    attacker: PlayerStats, 
    defender: PlayerStats,
    attack_type: AttackType,
    attacker_num: int
) -> Tuple[str, Optional[str], int]:
    
    if attacker.mana < attack_type.mana_cost:
        return to_smallcaps(f"{attacker.username} doesn't have enough mana!"), None, 0
    
    attacker.mana -= attack_type.mana_cost
    
    attacker_stats = battle.p1_stats if attacker_num == 1 else battle.p2_stats
    defender_stats = battle.p2_stats if attacker_num == 1 else battle.p1_stats
    
    is_defending = battle.p2_defending if attacker_num == 1 else battle.p1_defending
    defense_mult = 2.0 if is_defending else 1.0
    
    base_damage = attack_type.base_damage + attacker.attack
    defense_reduction = int(defender.defense * defense_mult)
    final_damage = max(5, base_damage - defense_reduction)
    
    crit_chance = 0.15 + (attacker.speed * 0.01)
    is_crit = random.random() < crit_chance
    
    if is_crit:
        final_damage = int(final_damage * 1.5)
    
    defender.hp = max(0, defender.hp - final_damage)
    
    attacker_stats.attacks_used += 1
    attacker_stats.total_damage_dealt += final_damage
    defender_stats.total_damage_taken += final_damage
    
    crit_text = to_smallcaps(" [critical hit!]") if is_crit else ""
    message = to_smallcaps(f"{attacker.username} used {attack_type.attack_name} attack! dealt {final_damage} damage{crit_text}")
    
    battle.add_log(message)
    
    return message, attack_type.video_url, final_damage

async def bot_ai_turn(battle: Battle):
    bot = battle.player2
    player = battle.player1
    
    await asyncio.sleep(1.5)
    
    if bot.hp < bot.max_hp * 0.3 and bot.mana >= 20:
        heal_amount = min(30, bot.max_hp - bot.hp)
        bot.hp += heal_amount
        bot.mana -= 20
        battle.add_log(to_smallcaps(f"bot used healing potion! restored {heal_amount} hp"))
        return
    
    if bot.mana < 40:
        restore = min(40, bot.max_mana - bot.mana)
        bot.mana += restore
        battle.add_log(to_smallcaps(f"bot used mana potion! restored {restore} mana"))
        return
    
    if random.random() < 0.2:
        battle.p2_defending = True
        battle.p2_stats.defends_used += 1
        battle.add_log(to_smallcaps("bot is defending!"))
        return
    
    available_attacks = [
        AttackType.NORMAL, AttackType.FIRE, AttackType.ICE,
        AttackType.LIGHTNING, AttackType.WATER
    ]
    available_attacks = [atk for atk in available_attacks if bot.mana >= atk.mana_cost]
    
    if not available_attacks:
        available_attacks = [AttackType.NORMAL]
    
    chosen_attack = random.choice(available_attacks)
    
    await perform_attack(battle, bot, player, chosen_attack, 2)

async def rpg_start(update: Update, context: CallbackContext):
    user = update.effective_user
    message = update.message
    
    existing_battle = battle_manager.get_battle(user.id)
    if existing_battle:
        await message.reply_text(
            to_smallcaps("you're already in a battle! finish it first or forfeit."),
            parse_mode="HTML"
        )
        return
    
    if message.reply_to_message and message.reply_to_message.from_user.id != user.id:
        target_user = message.reply_to_message.from_user
        
        if target_user.is_bot:
            await message.reply_text(
                to_smallcaps("you can't challenge a bot to pvp!"),
                parse_mode="HTML"
            )
            return
        
        existing_challenge = battle_manager.get_challenge(target_user.id)
        if existing_challenge:
            await message.reply_text(
                to_smallcaps("this player already has a pending challenge!"),
                parse_mode="HTML"
            )
            return
        
        battle_manager.add_challenge(user.id, target_user.id, user.first_name)
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    to_smallcaps("accept"), 
                    callback_data=f"rpg:accept:{user.id}:{target_user.id}"
                ),
                InlineKeyboardButton(
                    to_smallcaps("decline"), 
                    callback_data=f"rpg:decline:{user.id}:{target_user.id}"
                )
            ]
        ])
        
        await message.reply_text(
            to_smallcaps(f"{target_user.first_name}, {user.first_name} challenges you to a battle!\n\naccept or decline within 60 seconds."),
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    player1 = await load_player_stats(user.id, user.first_name)
    
    bot_level = max(1, player1.level + random.randint(-1, 1))
    bot_stat_mult = 1 + (bot_level - 1) * 0.1
    
    player2 = PlayerStats(
        user_id=0,
        username="bot",
        hp=int(120 * bot_stat_mult),
        max_hp=int(120 * bot_stat_mult),
        mana=int(120 * bot_stat_mult),
        max_mana=int(120 * bot_stat_mult),
        attack=int(20 * bot_stat_mult),
        defense=int(12 * bot_stat_mult),
        speed=int(8 * bot_stat_mult),
        level=bot_level,
        unlocked_attacks=["normal", "fire", "ice", "lightning", "water"]
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
        await query.answer(to_smallcaps("wait for your turn!"), show_alert=True)
        return
    
    if action == "menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                to_smallcaps("start pve battle"), 
                callback_data=f"rpg:start_pve:{update.effective_user.id}"
            )],
            [InlineKeyboardButton(
                to_smallcaps("view stats"), 
                callback_data=f"rpg:stats:{update.effective_user.id}"
            )]
        ])
        
        await query.message.edit_text(
            to_smallcaps("rpg battle system\n\nchoose an option:"),
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    if action == "start_pve":
        user_id = int(data[2])
        if update.effective_user.id != user_id:
            await query.answer(to_smallcaps("not your button!"), show_alert=True)
            return
        
        update.message = query.message
        update.message.from_user = update.effective_user
        await rpg_start(update, context)
        return
    
    if action == "accept":
        challenger_id = int(data[2])
        target_id = int(data[3])
        
        if update.effective_user.id != target_id:
            await query.answer(to_smallcaps("this challenge isn't for you!"), show_alert=True)
            return
        
        challenge = battle_manager.get_challenge(target_id)
        if not challenge:
            await query.message.edit_text(
                to_smallcaps("challenge expired!"),
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
            await query.answer(to_smallcaps("this challenge isn't for you!"), show_alert=True)
            return
        
        battle_manager.remove_challenge(target_id)
        
        await query.message.edit_text(
            to_smallcaps("challenge declined!"),
            parse_mode="HTML"
        )
        return
    
    if action == "stats":
        user_id = int(data[2])
        if update.effective_user.id != user_id:
            await query.answer(to_smallcaps("not your stats!"), show_alert=True)
            return
        
        player = await load_player_stats(user_id, update.effective_user.first_name)
        user_doc = await user_collection.find_one({'id': user_id})
        
        balance = user_doc.get('balance', 0)
        tokens = user_doc.get('tokens', 0)
        xp_to_next = 100 - (player.xp % 100)
        
        stats_text = f"""
<b>{to_smallcaps('═══ your stats ═══')}</b>

<b>{to_smallcaps(player.username)}</b>
{to_smallcaps(f'level: {player.level}')}
{to_smallcaps(f'xp: {player.xp} ({xp_to_next} to next level)')}

{to_smallcaps(f'hp: {player.max_hp}')}
{to_smallcaps(f'mana: {player.max_mana}')}
{to_smallcaps(f'attack: {player.attack}')}
{to_smallcaps(f'defense: {player.defense}')}
{to_smallcaps(f'speed: {player.speed}')}

{to_smallcaps(f'balance: {balance} coins')}
{to_smallcaps(f'tokens: {tokens}')}

<b>{to_smallcaps('unlocked attacks:')}</b>
{to_smallcaps(', '.join(player.unlocked_attacks))}
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                to_smallcaps("back"), 
                callback_data=f"rpg:menu:{user_id}"
            )]
        ])
        
        await query.message.edit_text(
            stats_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    user_id = int(data[-1])
    
    if update.effective_user.id != user_id:
        await query.answer(to_smallcaps("not your turn!"), show_alert=True)
        return
    
    battle = battle_manager.get_battle(user_id)
    
    if not battle:
        await query.message.edit_text(
            to_smallcaps("battle not found! start a new one with /rpg"),
            parse_mode="HTML"
        )
        return
    
    is_player1 = user_id == battle.player1.user_id
    current_player = battle.player1 if is_player1 else battle.player2
    opponent = battle.player2 if is_player1 else battle.player1
    player_num = 1 if is_player1 else 2
    
    is_turn = (battle.current_turn == 1 and is_player1) or (battle.current_turn == 2 and not is_player1)
    
    if not is_turn:
        await query.answer(to_smallcaps("wait for your turn!"), show_alert=True)
        return
    
    over, winner = battle.is_over()
    if over:
        await query.answer(to_smallcaps("battle is already over!"), show_alert=True)
        return
    
    action_message = ""
    video_url = None
    
    if action == "atk":
        attack_name = data[2]
        
        try:
            attack_type = None
            for atk in AttackType:
                if atk.attack_name == attack_name:
                    attack_type = atk
                    break
            
            if not attack_type:
                await query.answer(to_smallcaps("invalid attack!"), show_alert=True)
                return
            
            if attack_name not in current_player.unlocked_attacks:
                await query.answer(to_smallcaps("attack not unlocked!"), show_alert=True)
                return
            
            action_message, video_url, damage = await perform_attack(
                battle, current_player, opponent, attack_type, player_num
            )
            
            if damage == 0:
                await query.answer(action_message, show_alert=True)
                return
            
        except Exception as e:
            await query.answer(to_smallcaps(f"error: {str(e)}"), show_alert=True)
            return
    
    elif action == "defend":
        if is_player1:
            battle.p1_defending = True
            battle.p1_stats.defends_used += 1
        else:
            battle.p2_defending = True
            battle.p2_stats.defends_used += 1
        
        action_message = to_smallcaps(f"{current_player.username} is defending!")
        battle.add_log(action_message)
    
    elif action == "heal":
        if current_player.mana < 20:
            await query.answer(to_smallcaps("not enough mana!"), show_alert=True)
            return
        
        heal_amount = min(30, current_player.max_hp - current_player.hp)
        current_player.hp += heal_amount
        current_player.mana -= 20
        
        stats = battle.p1_stats if is_player1 else battle.p2_stats
        stats.potions_used += 1
        
        action_message = to_smallcaps(f"{current_player.username} used healing potion! restored {heal_amount} hp")
        battle.add_log(action_message)
    
    elif action == "mana":
        restore_amount = min(40, current_player.max_mana - current_player.mana)
        current_player.mana += restore_amount
        
        stats = battle.p1_stats if is_player1 else battle.p2_stats
        stats.potions_used += 1
        
        action_message = to_smallcaps(f"{current_player.username} used mana potion! restored {restore_amount} mana")
        battle.add_log(action_message)
    
    elif action == "forfeit":
        battle_manager.end_battle(battle.player1.user_id, battle.player2.user_id)
        
        await query.message.edit_text(
            to_smallcaps(f"{current_player.username} forfeited the battle!"),
            parse_mode="HTML"
        )
        return
    
    battle.switch_turn()
    
    over, winner = battle.is_over()
    
    if over:
        await handle_battle_end(query.message, battle, winner)
        return
    
    if video_url:
        try:
            await query.message.reply_video(
                video=video_url,
                caption=action_message,
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    if not battle.is_pvp and battle.current_turn == 2:
        await bot_ai_turn(battle)
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
    
    winner_xp = calculate_xp_reward(level_diff, True)
    loser_xp = calculate_xp_reward(level_diff, False)
    
    base_coins = 100 if battle.is_pvp else 50
    winner_coins = base_coins + (winner_player.level * 10) + random.randint(20, 50)
    loser_coins = base_coins // 2
    
    winner_old_level = winner_player.level
    loser_old_level = loser_player.level
    
    await save_player_progress(winner_player.user_id, winner_xp, winner_coins)
    
    if battle.is_pvp:
        await save_player_progress(loser_player.user_id, loser_xp, loser_coins)
    
    winner_new_data = await user_collection.find_one({'id': winner_player.user_id})
    winner_new_level = get_level_from_xp(winner_new_data.get('rpg_xp', 0))
    
    level_up_msg = ""
    if winner_new_level > winner_old_level:
        level_up_msg = to_smallcaps(f"\n\nlevel up! {winner_old_level} → {winner_new_level}")
        
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
            level_up_msg += to_smallcaps(f"\nnew attacks unlocked: {', '.join(new_attacks)}")
    
    result_text = f"""
<b>{to_smallcaps('═══ battle ended ═══')}</b>

<b>{to_smallcaps('winner:')}</b> {winner_player.username}
<b>{to_smallcaps('loser:')}</b> {loser_player.username}

<b>{to_smallcaps('═══ battle stats ═══')}</b>

<b>{to_smallcaps(winner_player.username)}</b>
{to_smallcaps(f'damage dealt: {winner_stats.total_damage_dealt}')}
{to_smallcaps(f'damage taken: {winner_stats.total_damage_taken}')}
{to_smallcaps(f'attacks used: {winner_stats.attacks_used}')}
{to_smallcaps(f'potions used: {winner_stats.potions_used}')}
{to_smallcaps(f'defends used: {winner_stats.defends_used}')}

<b>{to_smallcaps(loser_player.username)}</b>
{to_smallcaps(f'damage dealt: {loser_stats.total_damage_dealt}')}
{to_smallcaps(f'damage taken: {loser_stats.total_damage_taken}')}
{to_smallcaps(f'attacks used: {loser_stats.attacks_used}')}
{to_smallcaps(f'potions used: {loser_stats.potions_used}')}
{to_smallcaps(f'defends used: {loser_stats.defends_used}')}

<b>{to_smallcaps('═══ rewards ═══')}</b>

<b>{to_smallcaps(winner_player.username)}</b>
{to_smallcaps(f'xp gained: +{winner_xp}')}
{to_smallcaps(f'coins gained: +{winner_coins}')}
{level_up_msg}
"""
    
    if battle.is_pvp:
        result_text += f"""

<b>{to_smallcaps(loser_player.username)}</b>
{to_smallcaps(f'xp gained: +{loser_xp}')}
{to_smallcaps(f'coins gained: +{loser_coins}')}
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            to_smallcaps("new battle"), 
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
            to_smallcaps("start pve battle"), 
            callback_data=f"rpg:start_pve:{user.id}"
        )],
        [InlineKeyboardButton(
            to_smallcaps("view stats"), 
            callback_data=f"rpg:stats:{user.id}"
        )]
    ])
    
    await update.message.reply_text(
        to_smallcaps("rpg battle system\n\nchoose an option:"),
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def rpg_help(update: Update, context: CallbackContext):
    help_text = f"""
<b>{to_smallcaps('═══ rpg battle system ═══')}</b>

<b>{to_smallcaps('commands:')}</b>
{to_smallcaps('/rpg - start pve battle')}
{to_smallcaps('/rpg (reply) - challenge player to pvp')}
{to_smallcaps('/rpgmenu - open rpg menu')}
{to_smallcaps('/rpgstats - view your stats')}
{to_smallcaps('/rpghelp - show this help')}

<b>{to_smallcaps('attacks:')}</b>
{to_smallcaps('normal (15 mana) - unlocked at start')}
{to_smallcaps('fire (30 mana) - unlocked at start')}
{to_smallcaps('ice (25 mana) - unlocked at start')}
{to_smallcaps('lightning (35 mana) - unlocked at level 3')}
{to_smallcaps('water (20 mana) - unlocked at level 5')}
{to_smallcaps('earth (22 mana) - unlocked at level 7')}
{to_smallcaps('wind (28 mana) - unlocked at level 10')}
{to_smallcaps('dark (40 mana) - unlocked at level 15')}
{to_smallcaps('light (38 mana) - unlocked at level 20')}

<b>{to_smallcaps('actions:')}</b>
{to_smallcaps('defend - double your defense for one turn')}
{to_smallcaps('heal (20 mana) - restore 30 hp')}
{to_smallcaps('mana potion - restore 40 mana')}

<b>{to_smallcaps('tips:')}</b>
{to_smallcaps('• higher speed = more critical hits')}
{to_smallcaps('• defending reduces damage taken')}
{to_smallcaps('• gain xp and coins from battles')}
{to_smallcaps('• level up to unlock new attacks')}
{to_smallcaps('• challenge friends for pvp battles')}
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode="HTML"
    )

async def rpg_stats_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    player = await load_player_stats(user.id, user.first_name)
    user_doc = await user_collection.find_one({'id': user.id})
    
    balance = user_doc.get('balance', 0) if user_doc else 0
    tokens = user_doc.get('tokens', 0) if user_doc else 0
    xp_to_next = 100 - (player.xp % 100)
    
    stats_text = f"""
<b>{to_smallcaps('═══ your stats ═══')}</b>

<b>{to_smallcaps(player.username)}</b>
{to_smallcaps(f'level: {player.level}')}
{to_smallcaps(f'xp: {player.xp} ({xp_to_next} to next level)')}

{to_smallcaps(f'hp: {player.max_hp}')}
{to_smallcaps(f'mana: {player.max_mana}')}
{to_smallcaps(f'attack: {player.attack}')}
{to_smallcaps(f'defense: {player.defense}')}
{to_smallcaps(f'speed: {player.speed}')}

{to_smallcaps(f'balance: {balance} coins')}
{to_smallcaps(f'tokens: {tokens}')}

<b>{to_smallcaps('unlocked attacks:')}</b>
{to_smallcaps(', '.join(player.unlocked_attacks))}
"""
    
    await update.message.reply_text(
        stats_text,
        parse_mode="HTML"
    )

application.add_handler(CommandHandler("rpg", rpg_start))
application.add_handler(CommandHandler("battle", rpg_start))
application.add_handler(CommandHandler("rpgmenu", rpg_menu))
application.add_handler(CommandHandler("rpgstats", rpg_stats_cmd))
application.add_handler(CommandHandler("rpghelp", rpg_help))
application.add_handler(CallbackQueryHandler(rpg_callback, pattern="^rpg:"))