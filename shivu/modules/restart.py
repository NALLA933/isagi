import asyncio
import math
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from telegram.error import BadRequest
from shivu import application, user_collection

class Element(Enum):
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    WATER = "water"
    EARTH = "earth"
    WIND = "wind"
    DARK = "dark"
    LIGHT = "light"
    NORMAL = "normal"

ELEMENTAL_CHART = {
    Element.FIRE: {Element.ICE: 1.5, Element.EARTH: 1.25, Element.WATER: 0.5},
    Element.ICE: {Element.WIND: 1.5, Element.WATER: 1.25, Element.FIRE: 0.5},
    Element.WATER: {Element.FIRE: 1.5, Element.EARTH: 1.25, Element.LIGHTNING: 0.5},
    Element.LIGHTNING: {Element.WATER: 1.5, Element.WIND: 1.25, Element.EARTH: 0.5},
    Element.EARTH: {Element.LIGHTNING: 1.5, Element.FIRE: 1.25, Element.WIND: 0.5},
    Element.WIND: {Element.EARTH: 1.5, Element.ICE: 1.25, Element.LIGHTNING: 0.5},
    Element.DARK: {Element.LIGHT: 1.5},
    Element.LIGHT: {Element.DARK: 1.5},
}

SMALLCAPS_MAP = {c: v for c, v in zip('abcdefghijklmnopqrstuvwxyz', 'ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ')}
BATTLE_TIMEOUT = 120
MAX_AI_BATTLES_PER_DAY = 20
MAX_PVP_BATTLES_PER_DAY = 30

def sc(text: str) -> str:
    return ''.join(SMALLCAPS_MAP.get(c.lower(), c) for c in text)

@dataclass
class AttackData:
    name: str
    element: Element
    mana_cost: int
    base_damage: int
    accuracy: int
    crit_bonus: float
    unlock_level: int
    emoji: str
    description: str
    effect: Optional[str] = None
    effect_chance: int = 0

ATTACKS = {
    "punch": AttackData("Punch", Element.NORMAL, 0, 15, 100, 0, 1, "👊", "Basic attack"),
    "slash": AttackData("Slash", Element.NORMAL, 10, 25, 95, 0.05, 1, "⚔️", "Swift blade strike"),
    "fireball": AttackData("Fireball", Element.FIRE, 25, 35, 90, 0.05, 1, "🔥", "Fire ball", "burn", 25),
    "flame_burst": AttackData("Flame Burst", Element.FIRE, 40, 55, 85, 0.1, 8, "💥", "Explosive fire", "burn", 35),
    "inferno": AttackData("Inferno", Element.FIRE, 70, 90, 75, 0.15, 18, "🌋", "Devastating flames", "burn", 50),
    "ice_shard": AttackData("Ice Shard", Element.ICE, 20, 30, 95, 0.03, 1, "❄️", "Sharp ice", "freeze", 15),
    "blizzard": AttackData("Blizzard", Element.ICE, 45, 60, 80, 0.08, 10, "🌨️", "Freezing storm", "freeze", 30),
    "spark": AttackData("Spark", Element.LIGHTNING, 22, 32, 92, 0.08, 3, "⚡", "Electric jolt", "stun", 20),
    "thunderbolt": AttackData("Thunderbolt", Element.LIGHTNING, 50, 70, 82, 0.12, 12, "🌩️", "Lightning", "stun", 35),
    "aqua_jet": AttackData("Aqua Jet", Element.WATER, 18, 28, 98, 0.02, 5, "💧", "High-speed water"),
    "tidal_wave": AttackData("Tidal Wave", Element.WATER, 55, 75, 78, 0.1, 14, "🌊", "Crushing wave"),
    "rock_throw": AttackData("Rock Throw", Element.EARTH, 20, 30, 90, 0.05, 7, "🪨", "Boulder throw"),
    "earthquake": AttackData("Earthquake", Element.EARTH, 60, 80, 75, 0.08, 16, "🏔️", "Ground quake", "stun", 25),
}

@dataclass
class StatusEffect:
    name: str
    emoji: str
    duration: int
    damage_per_turn: int
    stat_modifier: Dict[str, float]
    prevents_action: bool
    description: str

STATUS_EFFECTS = {
    "burn": StatusEffect("Burn", "🔥", 3, 8, {"defense": 0.85}, False, "Fire damage"),
    "freeze": StatusEffect("Freeze", "🧊", 2, 0, {"speed": 0.5}, False, "Slowed"),
    "stun": StatusEffect("Stun", "💫", 1, 0, {}, True, "Cannot act"),
    "regen": StatusEffect("Regen", "💚", 3, -15, {}, False, "Healing"),
    "shield": StatusEffect("Shield", "🛡️", 2, 0, {"defense": 1.5}, False, "Defense up"),
    "might": StatusEffect("Might", "💪", 3, 0, {"attack": 1.3}, False, "Attack up"),
    "haste": StatusEffect("Haste", "⚡", 2, 0, {"speed": 1.5}, False, "Speed up"),
}

@dataclass
class ActiveEffect:
    effect_name: str
    turns_remaining: int
    source: str

@dataclass
class PlayerStats:
    user_id: int
    username: str
    hp: int = 200
    max_hp: int = 200
    mana: int = 150
    max_mana: int = 150
    attack: int = 30
    defense: int = 20
    speed: int = 15
    accuracy: int = 95
    crit_chance: float = 0.1
    level: int = 1
    rank: str = "F"
    rank_emoji: str = "🔰"
    xp: int = 0
    element_affinity: Element = Element.NORMAL
    active_effects: List[ActiveEffect] = field(default_factory=list)
    is_defending: bool = False
    combo_counter: int = 0

@dataclass
class BattleMessage:
    text: str
    is_critical: bool = False

class Battle:
    def __init__(self, p1: PlayerStats, p2: PlayerStats, is_pvp: bool = False):
        self.player1 = p1
        self.player2 = p2
        self.is_pvp = is_pvp
        self.current_turn = 1 if p1.speed >= p2.speed else 2
        self.turn_count = 0
        self.started_at = datetime.utcnow()
        self.last_action = datetime.utcnow()
        self.battle_log: List[str] = []
    
    def get_current_player(self) -> PlayerStats:
        return self.player1 if self.current_turn == 1 else self.player2
    
    def get_opponent(self) -> PlayerStats:
        return self.player2 if self.current_turn == 1 else self.player1
    
    def add_log(self, msg: str):
        self.battle_log.append(msg)
        if len(self.battle_log) > 5:
            self.battle_log.pop(0)
    
    def process_turn_effects(self, player: PlayerStats) -> List[str]:
        messages = []
        expired = []
        
        for i, effect in enumerate(player.active_effects):
            eff_data = STATUS_EFFECTS.get(effect.effect_name)
            if not eff_data:
                continue
            
            if eff_data.damage_per_turn != 0:
                if eff_data.damage_per_turn > 0:
                    player.hp = max(0, player.hp - eff_data.damage_per_turn)
                    messages.append(f"{eff_data.emoji} -{eff_data.damage_per_turn} HP")
                else:
                    heal = abs(eff_data.damage_per_turn)
                    player.hp = min(player.max_hp, player.hp + heal)
                    messages.append(f"{eff_data.emoji} +{heal} HP")
            
            effect.turns_remaining -= 1
            if effect.turns_remaining <= 0:
                expired.append(i)
        
        for i in reversed(expired):
            player.active_effects.pop(i)
        
        return messages
    
    def get_effective_stats(self, player: PlayerStats) -> Dict[str, float]:
        stats = {"attack": player.attack, "defense": player.defense, "speed": player.speed}
        
        for effect in player.active_effects:
            eff_data = STATUS_EFFECTS.get(effect.effect_name)
            if eff_data:
                for stat, mult in eff_data.stat_modifier.items():
                    if stat in stats:
                        stats[stat] *= mult
        
        if player.is_defending:
            stats["defense"] *= 2.0
        
        return stats
    
    def can_act(self, player: PlayerStats) -> Tuple[bool, Optional[str]]:
        for effect in player.active_effects:
            eff_data = STATUS_EFFECTS.get(effect.effect_name)
            if eff_data and eff_data.prevents_action:
                return False, f"{eff_data.emoji} {player.username} is stunned!"
        return True, None
    
    def switch_turn(self):
        self.current_turn = 2 if self.current_turn == 1 else 1
        self.turn_count += 1
        self.player1.is_defending = False
        self.player2.is_defending = False
        self.last_action = datetime.utcnow()
    
    def is_inactive(self) -> bool:
        return (datetime.utcnow() - self.last_action).total_seconds() > BATTLE_TIMEOUT
    
    def is_over(self) -> Tuple[bool, Optional[int]]:
        if self.player1.hp <= 0:
            return True, 2
        if self.player2.hp <= 0:
            return True, 1
        return False, None

class BattleManager:
    def __init__(self):
        self.active_battles: Dict[str, Battle] = {}
        self.pending_challenges: Dict[int, Dict] = {}
    
    def battle_id(self, u1: int, u2: int) -> str:
        return f"{min(u1, u2)}_{max(u1, u2)}"
    
    def start(self, p1: PlayerStats, p2: PlayerStats, pvp: bool = False) -> Battle:
        bid = self.battle_id(p1.user_id, p2.user_id)
        battle = Battle(p1, p2, pvp)
        self.active_battles[bid] = battle
        return battle
    
    def get(self, uid: int) -> Optional[Battle]:
        for b in self.active_battles.values():
            if b.player1.user_id == uid or b.player2.user_id == uid:
                return b
        return None
    
    def end(self, u1: int, u2: int):
        self.active_battles.pop(self.battle_id(u1, u2), None)
    
    def challenge(self, cid: int, tid: int, cname: str):
        self.pending_challenges[tid] = {
            'challenger_id': cid, 'challenger_name': cname,
            'timestamp': datetime.utcnow()
        }
    
    def get_challenge(self, tid: int) -> Optional[Dict]:
        return self.pending_challenges.get(tid)
    
    def remove_challenge(self, tid: int):
        self.pending_challenges.pop(tid, None)

battle_manager = BattleManager()

# Helper functions
def calc_level(xp: int) -> int:
    return min(max(1, math.floor(math.sqrt(max(xp, 0) / 100)) + 1), 100)

def calc_rank(level: int) -> Tuple[str, str]:
    ranks = [(10, "F", "🔰"), (20, "E", "🥉"), (30, "D", "🥈"), (40, "C", "🥇"), 
             (50, "B", "💎"), (60, "A", "👑"), (75, "S", "⭐"), (100, "SSS", "✨")]
    for lim, r, e in ranks:
        if level <= lim:
            return r, e
    return "SSS", "✨"

def get_unlocked_attacks(level: int) -> List[str]:
    return [name for name, data in ATTACKS.items() if data.unlock_level <= level]

def create_hp_bar(current: int, maximum: int, length: int = 10) -> str:
    pct = max(0, min(1, current / maximum))
    filled = int(length * pct)
    color = "🟩" if pct > 0.6 else "🟨" if pct > 0.3 else "🟥"
    bar = "█" * filled + "░" * (length - filled)
    return f"{color} {bar}"

def create_mp_bar(current: int, maximum: int, length: int = 10) -> str:
    pct = max(0, min(1, current / maximum))
    filled = int(length * pct)
    bar = "█" * filled + "░" * (length - filled)
    return f"🔵 {bar}"

async def get_user(uid: int):
    try:
        return await user_collection.find_one({'id': uid})
    except:
        return None

async def check_battle_limits(uid: int, is_pvp: bool) -> Tuple[bool, str]:
    doc = await get_user(uid)
    if not doc:
        return True, ""
    
    today = datetime.utcnow().date()
    battle_data = doc.get('battle_data', {})
    last_reset = battle_data.get('last_reset')
    
    if last_reset:
        last_date = datetime.fromisoformat(last_reset).date()
        if last_date != today:
            battle_data = {'ai_battles': 0, 'pvp_battles': 0, 'last_reset': today.isoformat()}
    else:
        battle_data = {'ai_battles': 0, 'pvp_battles': 0, 'last_reset': today.isoformat()}
    
    current = battle_data.get('pvp_battles' if is_pvp else 'ai_battles', 0)
    max_battles = MAX_PVP_BATTLES_PER_DAY if is_pvp else MAX_AI_BATTLES_PER_DAY
    
    if current >= max_battles:
        return False, f"❌ {sc('daily limit reached!')} ({current}/{max_battles})"
    
    return True, ""

async def increment_battle_count(uid: int, is_pvp: bool):
    doc = await get_user(uid)
    if not doc:
        return
    
    today = datetime.utcnow().date()
    battle_data = doc.get('battle_data', {})
    key = 'pvp_battles' if is_pvp else 'ai_battles'
    battle_data[key] = battle_data.get(key, 0) + 1
    battle_data['last_reset'] = today.isoformat()
    
    try:
        await user_collection.update_one({'id': uid}, {'$set': {'battle_data': battle_data}}, upsert=True)
    except:
        pass

async def load_player(uid: int, uname: str) -> PlayerStats:
    doc = await get_user(uid)
    
    if not doc:
        doc = {'id': uid, 'username': uname, 'user_xp': 0, 'element_affinity': 'normal'}
    
    xp = doc.get('user_xp', 0)
    level = calc_level(xp)
    rank, rank_emoji = calc_rank(level)
    mult = 1 + (level - 1) * 0.12
    
    affinity_str = doc.get('element_affinity', 'normal')
    try:
        affinity = Element[affinity_str.upper()]
    except:
        affinity = Element.NORMAL
    
    return PlayerStats(
        user_id=uid, username=uname[:16],
        hp=int(200 * mult), max_hp=int(200 * mult),
        mana=int(150 * mult), max_mana=int(150 * mult),
        attack=int(30 * mult), defense=int(20 * mult), speed=int(15 * mult),
        accuracy=min(98, 90 + level // 5), crit_chance=0.1 + (level * 0.005),
        level=level, rank=rank, rank_emoji=rank_emoji, xp=xp, element_affinity=affinity
    )

async def save_progress(uid: int, xp: int, coins: int):
    try:
        await user_collection.update_one({'id': uid}, {'$inc': {'user_xp': xp, 'balance': coins}}, upsert=True)
    except:
        pass

def calc_elemental_multiplier(atk_element: Element, def_element: Element) -> Tuple[float, str]:
    chart = ELEMENTAL_CHART.get(atk_element, {})
    mult = chart.get(def_element, 1.0)
    effectiveness = "super" if mult > 1.0 else "not very" if mult < 1.0 else None
    return mult, effectiveness

def perform_attack(battle: Battle, attack_name: str) -> BattleMessage:
    attacker = battle.get_current_player()
    defender = battle.get_opponent()
    
    attack = ATTACKS.get(attack_name)
    if not attack:
        return BattleMessage("❌ Invalid attack!")
    
    if attacker.mana < attack.mana_cost:
        return BattleMessage(f"❌ Not enough mana! Need {attack.mana_cost} MP")
    
    if attack.unlock_level > attacker.level:
        return BattleMessage(f"🔒 Unlock at level {attack.unlock_level}!")
    
    attacker.mana -= attack.mana_cost
    
    if random.randint(1, 100) > attack.accuracy:
        battle.add_log(f"💨 {attacker.username}: MISSED")
        return BattleMessage(f"💨 {attacker.username}'s {attack.name} missed!")
    
    atk_eff = battle.get_effective_stats(attacker)
    def_eff = battle.get_effective_stats(defender)
    
    base_dmg = attack.base_damage + atk_eff["attack"]
    damage = max(5, int(base_dmg - def_eff["defense"] * 0.5))
    
    elem_mult, effectiveness = calc_elemental_multiplier(attack.element, defender.element_affinity)
    damage = int(damage * elem_mult)
    
    is_crit = random.random() < (attacker.crit_chance + attack.crit_bonus)
    if is_crit:
        damage = int(damage * 1.75)
        attacker.combo_counter += 1
    else:
        attacker.combo_counter = 0
    
    defender.hp = max(0, defender.hp - damage)
    
    effect_msg = ""
    if attack.effect and random.randint(1, 100) <= attack.effect_chance:
        has_effect = any(e.effect_name == attack.effect for e in defender.active_effects)
        if not has_effect:
            eff_data = STATUS_EFFECTS.get(attack.effect)
            if eff_data:
                defender.active_effects.append(ActiveEffect(attack.effect, eff_data.duration, attacker.username))
                effect_msg = f" [{eff_data.emoji} {attack.effect}!]"
    
    crit_text = " 💥CRIT!" if is_crit else ""
    eff_text = " ⚡SUPER!" if effectiveness == "super" else " 🛡️Not very!" if effectiveness == "not very" else ""
    combo_text = f" 🔥x{attacker.combo_counter}" if attacker.combo_counter >= 2 else ""
    
    msg = f"{attack.emoji} {attacker.username} used {attack.name}!\n➤ {damage} DMG{crit_text}{eff_text}{combo_text}{effect_msg}"
    battle.add_log(f"{attack.emoji} {attacker.username}: {damage}{crit_text}")
    
    return BattleMessage(msg, is_crit)

def perform_defend(battle: Battle) -> BattleMessage:
    player = battle.get_current_player()
    player.is_defending = True
    mana_regen = min(20, player.max_mana - player.mana)
    player.mana += mana_regen
    battle.add_log(f"🛡️ {player.username}: DEFEND")
    return BattleMessage(f"🛡️ {player.username} is defending!\n➤ Defense x2, +{mana_regen} MP")

def perform_heal(battle: Battle) -> BattleMessage:
    player = battle.get_current_player()
    if player.mana < 30:
        return BattleMessage("❌ Need 30 MP!")
    
    player.mana -= 30
    heal_amount = 40 + (player.level * 3)
    actual_heal = min(heal_amount, player.max_hp - player.hp)
    player.hp += actual_heal
    battle.add_log(f"💚 {player.username}: +{actual_heal} HP")
    return BattleMessage(f"💚 {player.username} healed!\n➤ +{actual_heal} HP")

def perform_buff(battle: Battle, buff_type: str) -> BattleMessage:
    player = battle.get_current_player()
    
    costs = {"might": 35, "shield": 30, "haste": 40, "regen": 45}
    cost = costs.get(buff_type, 30)
    
    if player.mana < cost:
        return BattleMessage(f"❌ Need {cost} MP!")
    
    has_buff = any(e.effect_name == buff_type for e in player.active_effects)
    if has_buff:
        return BattleMessage(f"❌ Already have {buff_type}!")
    
    player.mana -= cost
    eff_data = STATUS_EFFECTS.get(buff_type)
    
    if eff_data:
        player.active_effects.append(ActiveEffect(buff_type, eff_data.duration, player.username))
        battle.add_log(f"{eff_data.emoji} {player.username}: {buff_type.upper()}")
        return BattleMessage(f"{eff_data.emoji} {player.username} used {buff_type.title()}!\n➤ {eff_data.description} for {eff_data.duration} turns")
    
    return BattleMessage("❌ Invalid buff!")

async def ai_turn(battle: Battle) -> BattleMessage:
    await asyncio.sleep(0.5)
    
    ai = battle.player2
    
    hp_pct = ai.hp / ai.max_hp
    mp_pct = ai.mana / ai.max_mana
    
    if hp_pct < 0.25 and ai.mana >= 30:
        return perform_heal(battle)
    
    if mp_pct < 0.2:
        return perform_defend(battle)
    
    if random.random() < 0.15 and ai.mana >= 35:
        buffs = ["might", "shield", "haste"]
        available = [b for b in buffs if not any(e.effect_name == b for e in ai.active_effects)]
        if available:
            return perform_buff(battle, random.choice(available))
    
    available_attacks = [(name, data) for name, data in ATTACKS.items()
                        if data.unlock_level <= ai.level and ai.mana >= data.mana_cost]
    
    if not available_attacks:
        return perform_defend(battle)
    
    # Prefer higher damage attacks
    weights = [data.base_damage for _, data in available_attacks]
    chosen = random.choices(available_attacks, weights=weights, k=1)[0][0]
    return perform_attack(battle, chosen)

def format_effects(effects: List[ActiveEffect]) -> str:
    if not effects:
        return ""
    parts = []
    for e in effects:
        eff = STATUS_EFFECTS.get(e.effect_name)
        if eff:
            parts.append(f"{eff.emoji}{e.turns_remaining}")
    return " ".join(parts)

def format_battle_ui(battle: Battle, action_msg: str = None) -> str:
    p1, p2 = battle.player1, battle.player2
    
    t1 = "▶" if battle.current_turn == 1 else "○"
    t2 = "▶" if battle.current_turn == 2 else "○"
    
    p1_eff = format_effects(p1.active_effects)
    p2_eff = format_effects(p2.active_effects)
    
    p1_def = " 🛡️" if p1.is_defending else ""
    p2_def = " 🛡️" if p2.is_defending else ""
    
    panel = f"""<b>⚔️ {sc('battle arena')} ⚔️</b>
━━━━━━━━━━━━━━━━━━━━

{t1} <b>{sc(p1.username)}</b> {p1.rank_emoji} Lv.{p1.level}{p1_def}
{create_hp_bar(p1.hp, p1.max_hp)} <code>{p1.hp}/{p1.max_hp}</code>
{create_mp_bar(p1.mana, p1.max_mana)} <code>{p1.mana}/{p1.max_mana}</code>
{p1_eff}

<b>━━━━━━ VS ━━━━━━</b>

{t2} <b>{sc(p2.username if battle.is_pvp else 'ai warrior')}</b> {p2.rank_emoji} Lv.{p2.level}{p2_def}
{create_hp_bar(p2.hp, p2.max_hp)} <code>{p2.hp}/{p2.max_hp}</code>
{create_mp_bar(p2.mana, p2.max_mana)} <code>{p2.mana}/{p2.max_mana}</code>
{p2_eff}

━━━━━━━━━━━━━━━━━━━━
<b>📜 {sc('battle log')}</b>"""
    
    for log in battle.battle_log[-3:]:
        panel += f"\n• {log}"
    
    if action_msg:
        panel += f"\n\n<b>➤ {action_msg}</b>"
    
    panel += f"\n\n<i>Turn {battle.turn_count + 1}</i>"
    
    return panel

def create_attack_keyboard(battle: Battle, uid: int) -> InlineKeyboardMarkup:
    player = battle.get_current_player()
    unlocked = get_unlocked_attacks(player.level)
    
    keyboard = []
    row = []
    
    for name in unlocked[:12]:  # Limit to first 12 attacks
        atk = ATTACKS[name]
        can_use = player.mana >= atk.mana_cost
        emoji = atk.emoji if can_use else "✗"
        btn = InlineKeyboardButton(emoji, callback_data=f"bat_atk_{name}_{uid}")
        row.append(btn)
        
        if len(row) >= 4:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # Action buttons
    keyboard.append([
        InlineKeyboardButton("🛡️", callback_data=f"bat_def_{uid}"),
        InlineKeyboardButton("💚", callback_data=f"bat_heal_{uid}"),
        InlineKeyboardButton("📖", callback_data=f"bat_skill_{uid}"),
    ])
    
    keyboard.append([InlineKeyboardButton(f"🏳️ {sc('forfeit')}", callback_data=f"bat_ff_{uid}")])
    
    return InlineKeyboardMarkup(keyboard)

def create_skills_keyboard(battle: Battle, uid: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(f"💪 {sc('might')} (35MP)", callback_data=f"bat_might_{uid}"),
         InlineKeyboardButton(f"🛡️ {sc('shield')} (30MP)", callback_data=f"bat_shield_{uid}")],
        [InlineKeyboardButton(f"⚡ {sc('haste')} (40MP)", callback_data=f"bat_haste_{uid}"),
         InlineKeyboardButton(f"💚 {sc('regen')} (45MP)", callback_data=f"bat_regen_{uid}")],
        [InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"bat_back_{uid}")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_battle_end(message, battle: Battle, winner: Optional[int]):
    if not winner:
        battle_manager.end(battle.player1.user_id, battle.player2.user_id)
        try:
            await message.edit_text(f"⏰ {sc('battle cancelled!')}", parse_mode="HTML")
        except:
            pass
        return
    
    battle_manager.end(battle.player1.user_id, battle.player2.user_id)
    
    winner_p = battle.player1 if winner == 1 else battle.player2
    loser_p = battle.player2 if winner == 1 else battle.player1
    
    base_xp = 100 if battle.is_pvp else 60
    winner_xp = int(base_xp * (1 + max(0, loser_p.level - winner_p.level) * 0.2))
    loser_xp = int(base_xp * 0.35) if battle.is_pvp else 0
    
    winner_coins = 200 + (winner_p.level * 20) + random.randint(50, 150)
    loser_coins = winner_coins // 3 if battle.is_pvp else 0
    
    # Check for XP boost
    try:
        from shivu.modules.up import get_active_boosts
        boosts = await get_active_boosts(winner_p.user_id)
        for boost in boosts:
            if boost['type'] == 'exp_boost':
                bonus = int(winner_xp * (boost['value'] / 100))
                winner_xp += bonus
            elif boost['type'] == 'coin_boost':
                bonus = int(winner_coins * (boost['value'] / 100))
                winner_coins += bonus
    except:
        pass
    
    await save_progress(winner_p.user_id, winner_xp, winner_coins)
    if battle.is_pvp:
        await save_progress(loser_p.user_id, loser_xp, loser_coins)
    
    result = f"""<b>⚔️ {sc('battle complete!')} ⚔️</b>
━━━━━━━━━━━━━━━━━━━━

<b>🏆 {sc('winner:')}</b> {winner_p.username}
<b>💀 {sc('defeated:')}</b> {loser_p.username if battle.is_pvp else 'AI'}

<b>🎁 {sc('rewards')}</b>
<b>{winner_p.username}:</b> +{winner_xp} XP, +{winner_coins} 💰"""
    
    if battle.is_pvp and loser_xp > 0:
        result += f"\n<b>{loser_p.username}:</b> +{loser_xp} XP, +{loser_coins} 💰"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"⚔️ {sc('new battle')}", callback_data=f"rpg_menu_{winner_p.user_id}")]])
    
    try:
        await message.edit_text(result, reply_markup=kb, parse_mode="HTML")
    except:
        pass

async def rpg_start(update: Update, context: CallbackContext):
    user = update.effective_user
    msg = update.message
    
    existing = battle_manager.get(user.id)
    if existing:
        await msg.reply_text(f"⚠️ {sc('already in battle! use /rpgforfeit to quit')}", parse_mode="HTML")
        return
    
    # Handle PVP challenge
    if msg.reply_to_message and msg.reply_to_message.from_user.id != user.id:
        target = msg.reply_to_message.from_user
        
        if target.is_bot:
            await msg.reply_text(f"❌ {sc('cannot challenge bots!')}", parse_mode="HTML")
            return
        
        can_battle, limit_msg = await check_battle_limits(user.id, True)
        if not can_battle:
            await msg.reply_text(limit_msg, parse_mode="HTML")
            return
        
        can_battle_target, limit_msg_target = await check_battle_limits(target.id, True)
        if not can_battle_target:
            await msg.reply_text(f"❌ {target.first_name} {limit_msg_target}", parse_mode="HTML")
            return
        
        battle_manager.challenge(user.id, target.id, user.first_name)
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ {sc('accept')}", callback_data=f"rpg_acc_{user.id}_{target.id}"),
             InlineKeyboardButton(f"❌ {sc('decline')}", callback_data=f"rpg_dec_{user.id}_{target.id}")]
        ])
        
        await msg.reply_text(
            f"<b>⚔️ {sc('battle challenge!')} ⚔️</b>\n\n<b>{target.first_name}</b>, you've been challenged by <b>{user.first_name}</b>!",
            reply_markup=kb, parse_mode="HTML"
        )
        return
    
    # Handle PVE battle
    can_battle, limit_msg = await check_battle_limits(user.id, False)
    if not can_battle:
        await msg.reply_text(limit_msg, parse_mode="HTML")
        return
    
    await increment_battle_count(user.id, False)
    
    p1 = await load_player(user.id, user.first_name)
    ai_level = max(1, p1.level + random.randint(-2, 2))
    ai_mult = 1 + (ai_level - 1) * 0.1
    rank, emoji = calc_rank(ai_level)
    
    p2 = PlayerStats(
        user_id=0, username="AI",
        hp=int(180 * ai_mult), max_hp=int(180 * ai_mult),
        mana=int(140 * ai_mult), max_mana=int(140 * ai_mult),
        attack=int(28 * ai_mult), defense=int(18 * ai_mult), speed=int(14 * ai_mult),
        level=ai_level, rank=rank, rank_emoji=emoji,
        element_affinity=random.choice(list(Element))
    )
    
    battle = battle_manager.start(p1, p2, False)
    
    panel = format_battle_ui(battle)
    kb = create_attack_keyboard(battle, user.id)
    
    try:
        battle_msg = await msg.reply_text(panel, reply_markup=kb, parse_mode="HTML")
        
        if battle.current_turn == 2:
            await asyncio.sleep(1)
            result = await ai_turn(battle)
            
            effect_msgs = battle.process_turn_effects(battle.player2)
            for em in effect_msgs:
                battle.add_log(em)
            
            battle.switch_turn()
            
            over, winner = battle.is_over()
            if over:
                await handle_battle_end(battle_msg, battle, winner)
            else:
                panel = format_battle_ui(battle, result.text)
                kb = create_attack_keyboard(battle, user.id)
                await battle_msg.edit_text(panel, reply_markup=kb, parse_mode="HTML")
    except Exception:
        battle_manager.end(p1.user_id, p2.user_id)

async def rpg_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data_parts = query.data.split("_")
    
    if len(data_parts) < 2:
        await query.answer(sc("invalid action!"), show_alert=True)
        return
    
    action = data_parts[1]
    await query.answer()
    
    # Handle menu
    if action == "menu":
        uid = int(data_parts[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your button!"), show_alert=True)
            return
        
        doc = await get_user(uid)
        battle_data = doc.get('battle_data', {}) if doc else {}
        ai_count = battle_data.get('ai_battles', 0)
        pvp_count = battle_data.get('pvp_battles', 0)
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⚔️ {sc('start pve')} ({ai_count}/{MAX_AI_BATTLES_PER_DAY})", callback_data=f"rpg_pve_{uid}")],
            [InlineKeyboardButton(f"📊 {sc('view stats')}", callback_data=f"rpg_stats_{uid}")],
            [InlineKeyboardButton(f"🛒 {sc('battle shop')}", callback_data=f"bshop_home_{uid}")]
        ])
        
        try:
            await query.message.edit_text(
                f"""<b>⚔️ {sc('rpg battle system')} ⚔️</b>

{sc('daily limits:')}
• AI: {ai_count}/{MAX_AI_BATTLES_PER_DAY}
• PVP: {pvp_count}/{MAX_PVP_BATTLES_PER_DAY}

{sc('select an option:')}""",
                reply_markup=kb, parse_mode="HTML"
            )
        except:
            pass
        return
    
    # Handle PVE start
    if action == "pve":
        uid = int(data_parts[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your button!"), show_alert=True)
            return
        
        can_battle, limit_msg = await check_battle_limits(uid, False)
        if not can_battle:
            await query.answer(limit_msg, show_alert=True)
            return
        
        # Create a fake message object for rpg_start
        update.message = query.message
        update.message.reply_to_message = None
        await rpg_start(update, context)
        return
    
    # Handle stats view
    if action == "stats":
        uid = int(data_parts[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your stats!"), show_alert=True)
            return
        
        player = await load_player(uid, update.effective_user.first_name)
        doc = await get_user(uid)
        balance = doc.get('balance', 0) if doc else 0
        unlocked = get_unlocked_attacks(player.level)
        
        stats_text = f"""<b>📊 {sc('player statistics')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('profile')}</b>
• Name: {player.username}
• Level: {player.level} {player.rank_emoji}
• Rank: {player.rank}

<b>{sc('combat stats')}</b>
• HP: {player.max_hp}
• Mana: {player.max_mana}
• Attack: {player.attack}
• Defense: {player.defense}
• Speed: {player.speed}
• Crit: {player.crit_chance*100:.1f}%

<b>{sc('inventory')}</b>
• 💰 Coins: {balance:,}

<b>{sc('attacks unlocked:')}</b> {len(unlocked)}/{len(ATTACKS)}"""
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"rpg_menu_{uid}")]])
        try:
            await query.message.edit_text(stats_text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    # Handle challenge accept
    if action == "acc":
        cid, tid = int(data_parts[2]), int(data_parts[3])
        
        if update.effective_user.id != tid:
            await query.answer(sc("not your challenge!"), show_alert=True)
            return
        
        challenge = battle_manager.get_challenge(tid)
        if not challenge:
            try:
                await query.message.edit_text(f"⚠️ {sc('challenge expired!')}", parse_mode="HTML")
            except:
                pass
            return
        
        await increment_battle_count(cid, True)
        await increment_battle_count(tid, True)
        
        battle_manager.remove_challenge(tid)
        
        p1 = await load_player(cid, challenge['challenger_name'])
        p2 = await load_player(tid, update.effective_user.first_name)
        
        battle = battle_manager.start(p1, p2, True)
        
        first_player_id = p1.user_id if battle.current_turn == 1 else p2.user_id
        panel = format_battle_ui(battle)
        kb = create_attack_keyboard(battle, first_player_id)
        
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            battle_manager.end(p1.user_id, p2.user_id)
        return
    
    # Handle challenge decline
    if action == "dec":
        tid = int(data_parts[3])
        
        if update.effective_user.id != tid:
            await query.answer(sc("not your challenge!"), show_alert=True)
            return
        
        battle_manager.remove_challenge(tid)
        try:
            await query.message.edit_text(f"❌ {sc('challenge declined!')}", parse_mode="HTML")
        except:
            pass
        return
    
    # Battle actions
    uid = int(data_parts[-1]) if len(data_parts) > 2 else 0
    
    if update.effective_user.id != uid:
        await query.answer(sc("not your turn!"), show_alert=True)
        return
    
    battle = battle_manager.get(uid)
    
    if not battle:
        try:
            await query.message.edit_text(f"❌ {sc('no active battle!')}", parse_mode="HTML")
        except:
            pass
        return
    
    if battle.is_inactive():
        battle_manager.end(battle.player1.user_id, battle.player2.user_id)
        try:
            await query.message.edit_text(f"⏰ {sc('battle timed out!')}", parse_mode="HTML")
        except:
            pass
        return
    
    is_p1 = uid == battle.player1.user_id
    is_turn = (battle.current_turn == 1 and is_p1) or (battle.current_turn == 2 and not is_p1)
    
    if not is_turn:
        await query.answer(sc("not your turn!"), show_alert=True)
        return
    
    over, winner = battle.is_over()
    if over:
        await handle_battle_end(query.message, battle, winner)
        return
    
    current = battle.get_current_player()
    can_act, block_msg = battle.can_act(current)
    
    if not can_act:
        battle.add_log(block_msg)
        battle.switch_turn()
        
        effect_msgs = battle.process_turn_effects(current)
        for msg in effect_msgs:
            battle.add_log(msg)
        
        over, winner = battle.is_over()
        if over:
            await handle_battle_end(query.message, battle, winner)
            return
        
        if not battle.is_pvp and battle.current_turn == 2:
            ai_result = await ai_turn(battle)
            
            ai_effect_msgs = battle.process_turn_effects(battle.player2)
            for msg in ai_effect_msgs:
                battle.add_log(msg)
            
            battle.switch_turn()
            
            over, winner = battle.is_over()
            if over:
                await handle_battle_end(query.message, battle, winner)
                return
        
        panel = format_battle_ui(battle)
        next_id = battle.player1.user_id if battle.current_turn == 1 else battle.player2.user_id
        kb = create_attack_keyboard(battle, next_id)
        
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    result = None
    
    # Handle back button
    if action == "back":
        panel = format_battle_ui(battle)
        kb = create_attack_keyboard(battle, uid)
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    # Handle skill menu
    if action == "skill":
        panel = format_battle_ui(battle)
        panel += f"\n\n<b>{sc('select a skill:')}</b>"
        kb = create_skills_keyboard(battle, uid)
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    # Handle attacks
    if action == "atk":
        atk_name = data_parts[2]
        result = perform_attack(battle, atk_name)
        
        if "Not enough" in result.text or "Unlock" in result.text or "Invalid" in result.text:
            await query.answer(result.text, show_alert=True)
            return
    
    elif action == "def":
        result = perform_defend(battle)
    
    elif action == "heal":
        result = perform_heal(battle)
        if "Need" in result.text:
            await query.answer(result.text, show_alert=True)
            return
    
    elif action in ["might", "shield", "haste", "regen"]:
        result = perform_buff(battle, action)
        if "Need" in result.text or "Already" in result.text:
            await query.answer(result.text, show_alert=True)
            return
    
    elif action == "ff":
        battle_manager.end(battle.player1.user_id, battle.player2.user_id)
        try:
            await query.message.edit_text(
                f"<b>🏳️ {sc('battle forfeited')} 🏳️</b>\n\n{current.username} {sc('gave up!')}",
                parse_mode="HTML"
            )
        except:
            pass
        return
    
    if not result:
        return
    
    # Process turn effects
    effect_msgs = battle.process_turn_effects(current)
    for msg in effect_msgs:
        battle.add_log(msg)
    
    battle.switch_turn()
    
    over, winner = battle.is_over()
    if over:
        await handle_battle_end(query.message, battle, winner)
        return
    
    # AI turn for PVE
    if not battle.is_pvp and battle.current_turn == 2:
        panel = format_battle_ui(battle, result.text)
        try:
            await query.message.edit_text(panel, parse_mode="HTML")
        except:
            pass
        
        await asyncio.sleep(0.5)
        ai_result = await ai_turn(battle)
        
        ai_effect_msgs = battle.process_turn_effects(battle.player2)
        for msg in ai_effect_msgs:
            battle.add_log(msg)
        
        battle.switch_turn()
        
        over, winner = battle.is_over()
        if over:
            await handle_battle_end(query.message, battle, winner)
            return
        
        result = ai_result
    
    panel = format_battle_ui(battle, result.text if result else None)
    next_id = battle.player1.user_id if battle.current_turn == 1 else battle.player2.user_id
    kb = create_attack_keyboard(battle, next_id)
    
    try:
        await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
    except BadRequest:
        pass
    except Exception:
        battle_manager.end(battle.player1.user_id, battle.player2.user_id)

async def rpg_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    doc = await get_user(user.id)
    battle_data = doc.get('battle_data', {}) if doc else {}
    ai_count = battle_data.get('ai_battles', 0)
    pvp_count = battle_data.get('pvp_battles', 0)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚔️ {sc('start pve')} ({ai_count}/{MAX_AI_BATTLES_PER_DAY})", callback_data=f"rpg_pve_{user.id}")],
        [InlineKeyboardButton(f"📊 {sc('view stats')}", callback_data=f"rpg_stats_{user.id}")],
        [InlineKeyboardButton(f"🛒 {sc('battle shop')}", callback_data=f"bshop_home_{user.id}")]
    ])
    
    await update.message.reply_text(
        f"""<b>⚔️ {sc('rpg battle system')} ⚔️</b>

{sc('daily limits:')}
• AI: {ai_count}/{MAX_AI_BATTLES_PER_DAY}
• PVP: {pvp_count}/{MAX_PVP_BATTLES_PER_DAY}

{sc('select an option:')}""",
        reply_markup=kb, parse_mode="HTML"
    )

async def rpg_stats_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    player = await load_player(user.id, user.first_name)
    doc = await get_user(user.id)
    balance = doc.get('balance', 0) if doc else 0
    unlocked = get_unlocked_attacks(player.level)
    
    stats_text = f"""<b>📊 {sc('player statistics')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('profile')}</b>
• Name: {player.username}
• Level: {player.level} {player.rank_emoji}
• Rank: {player.rank}

<b>{sc('combat stats')}</b>
• HP: {player.max_hp}
• Mana: {player.max_mana}
• Attack: {player.attack}
• Defense: {player.defense}
• Speed: {player.speed}
• Crit: {player.crit_chance*100:.1f}%

<b>{sc('inventory')}</b>
• 💰 Coins: {balance:,}

<b>{sc('attacks unlocked:')}</b> {len(unlocked)}/{len(ATTACKS)}"""
    
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def rpg_forfeit_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    battle = battle_manager.get(uid)
    
    if not battle:
        await update.message.reply_text(f"❌ {sc('not in a battle!')}", parse_mode="HTML")
        return
    
    battle_manager.end(battle.player1.user_id, battle.player2.user_id)
    await update.message.reply_text(f"<b>🏳️ {sc('battle forfeited')} 🏳️</b>", parse_mode="HTML")

async def rpg_help(update: Update, context: CallbackContext):
    text = f"""<b>⚔️ {sc('rpg battle guide')} ⚔️</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('commands')}</b>
• /rpg - Start PVE battle
• /rpg (reply) - Challenge player
• /rpgmenu - Main menu
• /rpgstats - View stats
• /rpgforfeit - Quit battle
• /rpghelp - This guide

<b>{sc('daily limits')}</b>
• AI: {MAX_AI_BATTLES_PER_DAY}/day
• PVP: {MAX_PVP_BATTLES_PER_DAY}/day

<b>{sc('combat')}</b>
• Higher speed = first turn
• Crits deal 75% more damage
• Defending restores 20 MP
• Use elemental advantages!

<b>{sc('tips')}</b>
• Level up to unlock attacks
• Buy items from /bshop
• Stack combos for bonus damage"""
    
    await update.message.reply_text(text, parse_mode="HTML")

# Register handlers
application.add_handler(CommandHandler("rpg", rpg_start, block=False))
application.add_handler(CommandHandler("battle", rpg_start, block=False))
application.add_handler(CommandHandler("rpgmenu", rpg_menu, block=False))
application.add_handler(CommandHandler("rpgstats", rpg_stats_cmd, block=False))
application.add_handler(CommandHandler("rpgforfeit", rpg_forfeit_cmd, block=False))
application.add_handler(CommandHandler("rpghelp", rpg_help, block=False))
application.add_handler(CallbackQueryHandler(rpg_callback, pattern="^rpg_", block=False))
application.add_handler(CallbackQueryHandler(rpg_callback, pattern="^bat_", block=False))