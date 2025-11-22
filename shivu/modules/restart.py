import asyncio
import math
import random
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from telegram.error import BadRequest, TimedOut, NetworkError
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
    Element.FIRE: {Element.ICE: 1.5, Element.EARTH: 1.25, Element.WATER: 0.5, Element.FIRE: 0.75},
    Element.ICE: {Element.WIND: 1.5, Element.WATER: 1.25, Element.FIRE: 0.5, Element.ICE: 0.75},
    Element.WATER: {Element.FIRE: 1.5, Element.EARTH: 1.25, Element.LIGHTNING: 0.5, Element.WATER: 0.75},
    Element.LIGHTNING: {Element.WATER: 1.5, Element.WIND: 1.25, Element.EARTH: 0.5, Element.LIGHTNING: 0.75},
    Element.EARTH: {Element.LIGHTNING: 1.5, Element.FIRE: 1.25, Element.WIND: 0.5, Element.EARTH: 0.75},
    Element.WIND: {Element.EARTH: 1.5, Element.ICE: 1.25, Element.LIGHTNING: 0.5, Element.WIND: 0.75},
    Element.DARK: {Element.LIGHT: 1.5, Element.NORMAL: 1.25, Element.DARK: 0.5},
    Element.LIGHT: {Element.DARK: 1.5, Element.NORMAL: 1.25, Element.LIGHT: 0.5},
    Element.NORMAL: {}
}

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
    animation_url: str
    description: str
    effect: Optional[str] = None
    effect_chance: int = 0

ATTACKS = {
    "punch": AttackData("Punch", Element.NORMAL, 0, 15, 100, 0, 1, "👊", 
        "https://files.catbox.moe/k3dhbe.mp4", "Basic attack"),
    "slash": AttackData("Slash", Element.NORMAL, 10, 25, 95, 0.05, 1, "⚔️",
        "https://files.catbox.moe/k3dhbe.mp4", "Swift blade strike"),
    
    "fireball": AttackData("Fireball", Element.FIRE, 25, 35, 90, 0.05, 1, "🔥",
        "https://files.catbox.moe/y3zz0k.mp4", "Launches a ball of fire", "burn", 25),
    "flame_burst": AttackData("Flame Burst", Element.FIRE, 40, 55, 85, 0.1, 8, "💥",
        "https://files.catbox.moe/y3zz0k.mp4", "Explosive fire damage", "burn", 35),
    "inferno": AttackData("Inferno", Element.FIRE, 70, 90, 75, 0.15, 18, "🌋",
        "https://files.catbox.moe/y3zz0k.mp4", "Devastating flames", "burn", 50),
    
    "ice_shard": AttackData("Ice Shard", Element.ICE, 20, 30, 95, 0.03, 1, "❄️",
        "https://files.catbox.moe/tm5iwt.mp4", "Sharp ice projectile", "freeze", 15),
    "blizzard": AttackData("Blizzard", Element.ICE, 45, 60, 80, 0.08, 10, "🌨️",
        "https://files.catbox.moe/tm5iwt.mp4", "Freezing storm", "freeze", 30),
    "absolute_zero": AttackData("Absolute Zero", Element.ICE, 75, 95, 70, 0.12, 20, "💠",
        "https://files.catbox.moe/tm5iwt.mp4", "Ultimate frost", "freeze", 45),
    
    "spark": AttackData("Spark", Element.LIGHTNING, 22, 32, 92, 0.08, 3, "⚡",
        "https://files.catbox.moe/8qdw3g.mp4", "Quick electric jolt", "stun", 20),
    "thunderbolt": AttackData("Thunderbolt", Element.LIGHTNING, 50, 70, 82, 0.12, 12, "🌩️",
        "https://files.catbox.moe/8qdw3g.mp4", "Powerful lightning", "stun", 35),
    "divine_thunder": AttackData("Divine Thunder", Element.LIGHTNING, 80, 100, 72, 0.18, 22, "⛈️",
        "https://files.catbox.moe/8qdw3g.mp4", "Heavenly wrath", "stun", 50),
    
    "aqua_jet": AttackData("Aqua Jet", Element.WATER, 18, 28, 98, 0.02, 5, "💧",
        "https://files.catbox.moe/6y2mxf.mp4", "High-speed water", "wet", 40),
    "tidal_wave": AttackData("Tidal Wave", Element.WATER, 55, 75, 78, 0.1, 14, "🌊",
        "https://files.catbox.moe/6y2mxf.mp4", "Crushing wave", "wet", 60),
    "tsunami": AttackData("Tsunami", Element.WATER, 85, 105, 68, 0.15, 24, "🌀",
        "https://files.catbox.moe/6y2mxf.mp4", "Oceanic devastation", "wet", 80),
    
    "rock_throw": AttackData("Rock Throw", Element.EARTH, 20, 30, 90, 0.05, 7, "🪨",
        "https://files.catbox.moe/htgbeh.mp4", "Hurls a boulder"),
    "earthquake": AttackData("Earthquake", Element.EARTH, 60, 80, 75, 0.08, 16, "🏔️",
        "https://files.catbox.moe/htgbeh.mp4", "Ground-shaking quake", "stun", 25),
    "meteor": AttackData("Meteor", Element.EARTH, 90, 115, 65, 0.2, 26, "☄️",
        "https://files.catbox.moe/htgbeh.mp4", "Falling star strike", "burn", 40),
    
    "gust": AttackData("Gust", Element.WIND, 15, 25, 100, 0.1, 10, "💨",
        "https://files.catbox.moe/1yxz13.mp4", "Swift wind strike"),
    "cyclone": AttackData("Cyclone", Element.WIND, 50, 65, 85, 0.12, 17, "🌪️",
        "https://files.catbox.moe/1yxz13.mp4", "Spinning vortex", "bleed", 30),
    "tempest": AttackData("Tempest", Element.WIND, 85, 100, 70, 0.18, 27, "🌬️",
        "https://files.catbox.moe/1yxz13.mp4", "Ultimate storm", "bleed", 45),
    
    "shadow_bolt": AttackData("Shadow Bolt", Element.DARK, 35, 45, 88, 0.1, 15, "🌑",
        "https://files.catbox.moe/gjhnew.mp4", "Dark energy blast", "curse", 25),
    "void_strike": AttackData("Void Strike", Element.DARK, 65, 85, 78, 0.15, 21, "🕳️",
        "https://files.catbox.moe/gjhnew.mp4", "Nothingness damage", "curse", 40),
    "oblivion": AttackData("Oblivion", Element.DARK, 95, 120, 60, 0.22, 28, "⬛",
        "https://files.catbox.moe/gjhnew.mp4", "Ultimate darkness", "curse", 55),
    
    "holy_ray": AttackData("Holy Ray", Element.LIGHT, 30, 40, 92, 0.08, 20, "✨",
        "https://files.catbox.moe/u9bfjl.mp4", "Divine light beam", "blind", 20),
    "radiance": AttackData("Radiance", Element.LIGHT, 60, 80, 82, 0.12, 23, "🌟",
        "https://files.catbox.moe/u9bfjl.mp4", "Brilliant burst", "blind", 35),
    "divine_judgment": AttackData("Divine Judgment", Element.LIGHT, 100, 130, 55, 0.25, 30, "👼",
        "https://files.catbox.moe/u9bfjl.mp4", "Heaven's wrath", "blind", 50),
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
    "burn": StatusEffect("Burn", "🔥", 3, 8, {"defense": 0.85}, False, "Takes fire damage"),
    "freeze": StatusEffect("Freeze", "🧊", 2, 0, {"speed": 0.5}, False, "Slowed movement"),
    "stun": StatusEffect("Stun", "💫", 1, 0, {}, True, "Cannot act"),
    "poison": StatusEffect("Poison", "🤢", 4, 12, {}, False, "Losing HP over time"),
    "bleed": StatusEffect("Bleed", "🩸", 3, 10, {"attack": 0.9}, False, "Bleeding out"),
    "curse": StatusEffect("Curse", "💀", 3, 5, {"attack": 0.8, "defense": 0.8}, False, "Weakened"),
    "blind": StatusEffect("Blind", "😵", 2, 0, {}, False, "Reduced accuracy"),
    "wet": StatusEffect("Wet", "💦", 2, 0, {"defense": 0.9}, False, "Vulnerable to lightning"),
    "regen": StatusEffect("Regen", "💚", 3, -15, {}, False, "Healing over time"),
    "shield": StatusEffect("Shield", "🛡️", 2, 0, {"defense": 1.5}, False, "Defense boosted"),
    "might": StatusEffect("Might", "💪", 3, 0, {"attack": 1.3}, False, "Attack boosted"),
    "haste": StatusEffect("Haste", "⚡", 2, 0, {"speed": 1.5}, False, "Speed boosted"),
}

BATTLE_ANIMATIONS = {
    "defend": "https://files.catbox.moe/5drz0h.mp4",
    "heal": "https://files.catbox.moe/ptc7sp.mp4",
    "critical": "https://files.catbox.moe/e19bx6.mp4",
    "victory": "https://files.catbox.moe/iitev2.mp4",
    "defeat": "https://files.catbox.moe/iitev2.mp4",
    "level_up": "https://files.catbox.moe/iitev2.mp4",
    "buff": "https://files.catbox.moe/ptc7sp.mp4",
    "debuff": "https://files.catbox.moe/gjhnew.mp4",
    "miss": "https://files.catbox.moe/1yxz13.mp4",
    "dodge": "https://files.catbox.moe/1yxz13.mp4",
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

BATTLE_TIMEOUT = 90
MAX_BATTLE_DURATION = 900
MAX_AI_BATTLES_PER_DAY = 20
MAX_PVP_BATTLES_PER_DAY = 30

def sc(text: str) -> str:
    return ''.join(SMALLCAPS_MAP.get(c, c) for c in text)

def calc_level(xp: int) -> int:
    return min(max(1, math.floor(math.sqrt(max(xp, 0) / 100)) + 1), 100)

def calc_rank(level: int) -> Tuple[str, str]:
    ranks = [
        (10, "F", "🔰"), (20, "E", "🥉"), (30, "D", "🥈"), 
        (40, "C", "🥇"), (50, "B", "💎"), (60, "A", "👑"),
        (75, "S", "⭐"), (90, "SS", "🌟"), (100, "SSS", "✨")
    ]
    for lim, r, e in ranks:
        if level <= lim:
            return r, e
    return "SSS", "✨"

def calc_xp_needed(level: int) -> int:
    return (level ** 2) * 100

def get_unlocked_attacks(level: int) -> List[str]:
    return [name for name, data in ATTACKS.items() if data.unlock_level <= level]

def create_hp_bar(current: int, maximum: int, length: int = 10) -> str:
    pct = max(0, min(1, current / maximum))
    filled = int(length * pct)
    
    if pct > 0.6:
        fill_char = "█"
        color = "🟩"
    elif pct > 0.3:
        fill_char = "▓"
        color = "🟨"
    else:
        fill_char = "▒"
        color = "🟥"
    
    bar = fill_char * filled + "░" * (length - filled)
    return f"{color} {bar}"

def create_mp_bar(current: int, maximum: int, length: int = 10) -> str:
    pct = max(0, min(1, current / maximum))
    filled = int(length * pct)
    
    if pct > 0.5:
        fill_char = "█"
    elif pct > 0.2:
        fill_char = "▓"
    else:
        fill_char = "▒"
    
    bar = fill_char * filled + "░" * (length - filled)
    return f"🔵 {bar}"

def create_xp_bar(current: int, needed: int, length: int = 8) -> str:
    pct = max(0, min(1, current / needed)) if needed > 0 else 0
    filled = int(length * pct)
    bar = "▰" * filled + "▱" * (length - filled)
    return f"⚡ {bar}"

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
class BattleStats:
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    total_healing: int = 0
    attacks_used: int = 0
    skills_used: int = 0
    critical_hits: int = 0
    misses: int = 0
    dodges: int = 0
    effects_applied: int = 0
    max_combo: int = 0

@dataclass
class BattleMessage:
    text: str
    animation_url: Optional[str] = None
    is_critical: bool = False
    is_miss: bool = False
    effectiveness: Optional[str] = None

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
        self.p1_stats = BattleStats()
        self.p2_stats = BattleStats()
        self.is_expired = False
        self.pending_animation: Optional[str] = None
        self.last_damage = 0
        self.last_effectiveness: Optional[str] = None
        
    def get_current_player(self) -> PlayerStats:
        return self.player1 if self.current_turn == 1 else self.player2
    
    def get_opponent(self) -> PlayerStats:
        return self.player2 if self.current_turn == 1 else self.player1
    
    def get_current_stats(self) -> BattleStats:
        return self.p1_stats if self.current_turn == 1 else self.p2_stats
    
    def get_opponent_stats(self) -> BattleStats:
        return self.p2_stats if self.current_turn == 1 else self.p1_stats
    
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
                    messages.append(f"{eff_data.emoji} {player.username}: -{eff_data.damage_per_turn} HP ({effect.effect_name})")
                else:
                    heal = abs(eff_data.damage_per_turn)
                    player.hp = min(player.max_hp, player.hp + heal)
                    messages.append(f"{eff_data.emoji} {player.username}: +{heal} HP (regen)")
            
            effect.turns_remaining -= 1
            if effect.turns_remaining <= 0:
                expired.append(i)
                messages.append(f"✖️ {effect.effect_name} wore off!")
        
        for i in reversed(expired):
            player.active_effects.pop(i)
        
        return messages
    
    def get_effective_stats(self, player: PlayerStats) -> Dict[str, float]:
        stats = {
            "attack": player.attack,
            "defense": player.defense,
            "speed": player.speed,
        }
        
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
                return False, f"{eff_data.emoji} {player.username} is {effect.effect_name}!"
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
        if self.is_expired:
            return True, None
        if self.player1.hp <= 0:
            return True, 2
        if self.player2.hp <= 0:
            return True, 1
        if (datetime.utcnow() - self.started_at).total_seconds() > MAX_BATTLE_DURATION:
            return True, 1 if self.player1.hp > self.player2.hp else 2
        return False, None

class BattleManager:
    def __init__(self):
        self.active_battles: Dict[str, Battle] = {}
        self.pending_challenges: Dict[int, Dict] = {}
        self.cleanup_task = None
        
    def battle_id(self, u1: int, u2: int) -> str:
        return f"{min(u1, u2)}_{max(u1, u2)}"
    
    def start(self, p1: PlayerStats, p2: PlayerStats, pvp: bool = False) -> Battle:
        bid = self.battle_id(p1.user_id, p2.user_id)
        battle = Battle(p1, p2, pvp)
        self.active_battles[bid] = battle
        
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup())
        
        return battle
    
    def get(self, uid: int, uid2: int = None) -> Optional[Battle]:
        if uid2:
            return self.active_battles.get(self.battle_id(uid, uid2))
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
        asyncio.create_task(self._expire_challenge(tid))
    
    async def _expire_challenge(self, tid: int):
        await asyncio.sleep(60)
        self.pending_challenges.pop(tid, None)
    
    def get_challenge(self, tid: int) -> Optional[Dict]:
        return self.pending_challenges.get(tid)
    
    def remove_challenge(self, tid: int):
        self.pending_challenges.pop(tid, None)
    
    async def _cleanup(self):
        while True:
            await asyncio.sleep(30)
            expired = [bid for bid, b in self.active_battles.items() if b.is_inactive()]
            for bid in expired:
                b = self.active_battles.pop(bid, None)
                if b:
                    b.is_expired = True

battle_manager = BattleManager()

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
    
    if is_pvp:
        current = battle_data.get('pvp_battles', 0)
        if current >= MAX_PVP_BATTLES_PER_DAY:
            return False, f"❌ {sc('daily pvp limit reached!')} ({current}/{MAX_PVP_BATTLES_PER_DAY})\n{sc('resets in')} {24 - datetime.utcnow().hour} {sc('hours')}"
    else:
        current = battle_data.get('ai_battles', 0)
        if current >= MAX_AI_BATTLES_PER_DAY:
            return False, f"❌ {sc('daily ai battle limit reached!')} ({current}/{MAX_AI_BATTLES_PER_DAY})\n{sc('resets in')} {24 - datetime.utcnow().hour} {sc('hours')}"
    
    return True, ""

async def increment_battle_count(uid: int, is_pvp: bool):
    doc = await get_user(uid)
    if not doc:
        return
    
    today = datetime.utcnow().date()
    battle_data = doc.get('battle_data', {})
    
    if is_pvp:
        battle_data['pvp_battles'] = battle_data.get('pvp_battles', 0) + 1
    else:
        battle_data['ai_battles'] = battle_data.get('ai_battles', 0) + 1
    
    battle_data['last_reset'] = today.isoformat()
    
    try:
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'battle_data': battle_data}},
            upsert=True
        )
    except:
        pass

async def load_player(uid: int, uname: str) -> PlayerStats:
    doc = await get_user(uid)
    
    if not doc:
        doc = {'id': uid, 'username': uname, 'balance': 0, 'tokens': 0, 
               'user_xp': 0, 'achievements': [], 'element_affinity': 'normal'}
        try:
            await user_collection.insert_one(doc)
        except:
            pass
    
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
        user_id=uid,
        username=uname[:16],
        hp=int(200 * mult),
        max_hp=int(200 * mult),
        mana=int(150 * mult),
        max_mana=int(150 * mult),
        attack=int(30 * mult),
        defense=int(20 * mult),
        speed=int(15 * mult),
        accuracy=min(98, 90 + level // 5),
        crit_chance=0.1 + (level * 0.005),
        level=level,
        rank=rank,
        rank_emoji=rank_emoji,
        xp=xp,
        element_affinity=affinity
    )

async def save_progress(uid: int, xp: int, coins: int, updates: dict = None):
    try:
        update_dict = {'$inc': {'user_xp': xp, 'balance': coins}}
        if updates:
            update_dict['$set'] = updates
        await user_collection.update_one({'id': uid}, update_dict, upsert=True)
    except:
        pass

def calc_elemental_multiplier(atk_element: Element, def_element: Element, defender: PlayerStats) -> Tuple[float, str]:
    mult = 1.0
    effectiveness = None
    
    is_wet = any(e.effect_name == "wet" for e in defender.active_effects)
    if is_wet and atk_element == Element.LIGHTNING:
        mult *= 1.5
        effectiveness = "super"
    
    chart = ELEMENTAL_CHART.get(atk_element, {})
    if def_element in chart:
        type_mult = chart[def_element]
        mult *= type_mult
        if type_mult > 1.0:
            effectiveness = "super"
        elif type_mult < 1.0:
            effectiveness = "not very"
    
    return mult, effectiveness

def perform_attack(battle: Battle, attack_name: str) -> BattleMessage:
    attacker = battle.get_current_player()
    defender = battle.get_opponent()
    atk_stats = battle.get_current_stats()
    def_stats = battle.get_opponent_stats()
    
    attack = ATTACKS.get(attack_name)
    if not attack:
        return BattleMessage("❌ Invalid attack!", None)
    
    if attacker.mana < attack.mana_cost:
        return BattleMessage(f"❌ Not enough mana! Need {attack.mana_cost} MP", None)
    
    if attack.unlock_level > attacker.level:
        return BattleMessage(f"🔒 Unlock at level {attack.unlock_level}!", None)
    
    attacker.mana -= attack.mana_cost
    atk_stats.attacks_used += 1
    
    atk_eff = battle.get_effective_stats(attacker)
    def_eff = battle.get_effective_stats(defender)
    
    accuracy = attack.accuracy
    if any(e.effect_name == "blind" for e in attacker.active_effects):
        accuracy -= 30
    
    if random.randint(1, 100) > accuracy:
        atk_stats.misses += 1
        attacker.combo_counter = 0
        battle.add_log(f"💨 {attacker.username}: MISSED!")
        return BattleMessage(
            f"💨 {attacker.username}'s {attack.name} missed!",
            BATTLE_ANIMATIONS["miss"],
            is_miss=True
        )
    
    dodge_chance = max(0, (def_eff["speed"] - atk_eff["speed"]) * 2)
    if random.randint(1, 100) <= dodge_chance:
        def_stats.dodges += 1
        attacker.combo_counter = 0
        battle.add_log(f"🌀 {defender.username}: DODGED!")
        return BattleMessage(
            f"🌀 {defender.username} dodged the attack!",
            BATTLE_ANIMATIONS["dodge"]
        )
    
    base_dmg = attack.base_damage + atk_eff["attack"]
    defense_reduction = def_eff["defense"] * 0.5
    damage = max(5, int(base_dmg - defense_reduction))
    
    elem_mult, effectiveness = calc_elemental_multiplier(
        attack.element, defender.element_affinity, defender
    )
    damage = int(damage * elem_mult)
    
    crit_chance = attacker.crit_chance + attack.crit_bonus
    is_crit = random.random() < crit_chance
    
    if is_crit:
        damage = int(damage * 1.75)
        atk_stats.critical_hits += 1
        attacker.combo_counter += 1
        atk_stats.max_combo = max(atk_stats.max_combo, attacker.combo_counter)
    else:
        attacker.combo_counter = 0
    
    if attacker.combo_counter >= 2:
        combo_mult = 1 + (attacker.combo_counter * 0.1)
        damage = int(damage * combo_mult)
    
    defender.hp = max(0, defender.hp - damage)
    atk_stats.total_damage_dealt += damage
    def_stats.total_damage_taken += damage
    battle.last_damage = damage
    battle.last_effectiveness = effectiveness
    
    effect_msg = ""
    if attack.effect and random.randint(1, 100) <= attack.effect_chance:
        has_effect = any(e.effect_name == attack.effect for e in defender.active_effects)
        if not has_effect:
            eff_data = STATUS_EFFECTS.get(attack.effect)
            if eff_data:
                defender.active_effects.append(ActiveEffect(
                    attack.effect, eff_data.duration, attacker.username
                ))
                atk_stats.effects_applied += 1
                effect_msg = f" [{eff_data.emoji} {attack.effect}!]"
    
    crit_text = " 💥CRIT!" if is_crit else ""
    eff_text = ""
    if effectiveness == "super":
        eff_text = " ⚡SUPER EFFECTIVE!"
    elif effectiveness == "not very":
        eff_text = " 🛡️Not very effective..."
    
    combo_text = f" 🔥x{attacker.combo_counter}" if attacker.combo_counter >= 2 else ""
    
    msg = f"{attack.emoji} {attacker.username} used {attack.name}!"
    msg += f"\n➤ {damage} DMG{crit_text}{eff_text}{combo_text}{effect_msg}"
    
    battle.add_log(f"{attack.emoji} {attacker.username}: {damage}{crit_text}")
    
    anim = BATTLE_ANIMATIONS["critical"] if is_crit else attack.animation_url
    
    return BattleMessage(msg, anim, is_crit, False, effectiveness)

def perform_defend(battle: Battle) -> BattleMessage:
    player = battle.get_current_player()
    stats = battle.get_current_stats()
    
    player.is_defending = True
    
    mana_regen = min(20, player.max_mana - player.mana)
    player.mana += mana_regen
    
    battle.add_log(f"🛡️ {player.username}: DEFENDING (+{mana_regen} MP)")
    
    return BattleMessage(
        f"🛡️ {player.username} is defending!\n➤ Defense x2, +{mana_regen} MP",
        BATTLE_ANIMATIONS["defend"]
    )

def perform_heal(battle: Battle) -> BattleMessage:
    player = battle.get_current_player()
    stats = battle.get_current_stats()
    
    mana_cost = 30
    if player.mana < mana_cost:
        return BattleMessage(f"❌ Need {mana_cost} MP to heal!", None)
    
    player.mana -= mana_cost
    
    heal_amount = 40 + (player.level * 3)
    actual_heal = min(heal_amount, player.max_hp - player.hp)
    player.hp += actual_heal
    stats.total_healing += actual_heal
    
    battle.add_log(f"💚 {player.username}: +{actual_heal} HP")
    
    return BattleMessage(
        f"💚 {player.username} healed!\n➤ +{actual_heal} HP (Cost: {mana_cost} MP)",
        BATTLE_ANIMATIONS["heal"]
    )

def perform_mana_restore(battle: Battle) -> BattleMessage:
    player = battle.get_current_player()
    
    restore = 50 + (player.level * 2)
    actual_restore = min(restore, player.max_mana - player.mana)
    player.mana += actual_restore
    
    battle.add_log(f"💙 {player.username}: +{actual_restore} MP")
    
    return BattleMessage(
        f"💙 {player.username} focused!\n➤ +{actual_restore} MP",
        BATTLE_ANIMATIONS["buff"]
    )

def perform_buff(battle: Battle, buff_type: str) -> BattleMessage:
    player = battle.get_current_player()
    
    buff_costs = {"might": 35, "shield": 30, "haste": 40, "regen": 45}
    cost = buff_costs.get(buff_type, 30)
    
    if player.mana < cost:
        return BattleMessage(f"❌ Need {cost} MP!", None)
    
    has_buff = any(e.effect_name == buff_type for e in player.active_effects)
    if has_buff:
        return BattleMessage(f"❌ Already have {buff_type}!", None)
    
    player.mana -= cost
    eff_data = STATUS_EFFECTS.get(buff_type)
    
    if eff_data:
        player.active_effects.append(ActiveEffect(buff_type, eff_data.duration, player.username))
        battle.add_log(f"{eff_data.emoji} {player.username}: {buff_type.upper()}!")
        
        return BattleMessage(
            f"{eff_data.emoji} {player.username} used {buff_type.title()}!\n➤ {eff_data.description} for {eff_data.duration} turns",
            BATTLE_ANIMATIONS["buff"]
        )
    
    return BattleMessage("❌ Invalid buff!", None)

async def ai_turn(battle: Battle) -> BattleMessage:
    await asyncio.sleep(0.8)
    
    ai = battle.player2
    player = battle.player1
    
    hp_pct = ai.hp / ai.max_hp
    mp_pct = ai.mana / ai.max_mana
    
    if hp_pct < 0.25 and ai.mana >= 30:
        return perform_heal(battle)
    
    if mp_pct < 0.2:
        return perform_mana_restore(battle)
    
    if hp_pct < 0.4 and random.random() < 0.3:
        return perform_defend(battle)
    
    if random.random() < 0.15 and ai.mana >= 35:
        buffs = ["might", "shield", "haste"]
        available = [b for b in buffs if not any(e.effect_name == b for e in ai.active_effects)]
        if available:
            return perform_buff(battle, random.choice(available))
    
    available_attacks = [
        (name, data) for name, data in ATTACKS.items()
        if data.unlock_level <= ai.level and ai.mana >= data.mana_cost
    ]
    
    if not available_attacks:
        return perform_mana_restore(battle)
    
    best_attacks = []
    for name, data in available_attacks:
        mult, _ = calc_elemental_multiplier(data.element, player.element_affinity, player)
        if mult > 1.0:
            best_attacks.append((name, data, mult))
    
    if player.hp / player.max_hp < 0.3:
        available_attacks.sort(key=lambda x: x[1].base_damage, reverse=True)
        return perform_attack(battle, available_attacks[0][0])
    
    if best_attacks and random.random() < 0.6:
        chosen = random.choice(best_attacks)[0]
    else:
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
    
    p2_name = p2.username if battle.is_pvp else "ᴀɪ ᴡᴀʀʀɪᴏʀ"
    
    combo_display = ""
    if p1.combo_counter >= 2:
        combo_display = f"\n🔥 {sc('combo')} x{p1.combo_counter}!"
    elif p2.combo_counter >= 2:
        combo_display = f"\n🔥 {sc('combo')} x{p2.combo_counter}!"
    
    panel = f"""<b>⚔️ {sc('battle arena')} ⚔️</b>
━━━━━━━━━━━━━━━━━━━━

{t1} <b>{sc(p1.username)}</b> {p1.rank_emoji} Lv.{p1.level}{p1_def}
{create_hp_bar(p1.hp, p1.max_hp)} <code>{p1.hp}/{p1.max_hp}</code>
{create_mp_bar(p1.mana, p1.max_mana)} <code>{p1.mana}/{p1.max_mana}</code>
⚔️{int(battle.get_effective_stats(p1)['attack'])} 🛡️{int(battle.get_effective_stats(p1)['defense'])} ⚡{int(battle.get_effective_stats(p1)['speed'])}
{p1_eff}

<b>━━━━━━ VS ━━━━━━</b>

{t2} <b>{sc(p2_name)}</b> {p2.rank_emoji} Lv.{p2.level}{p2_def}
{create_hp_bar(p2.hp, p2.max_hp)} <code>{p2.hp}/{p2.max_hp}</code>
{create_mp_bar(p2.mana, p2.max_mana)} <code>{p2.mana}/{p2.max_mana}</code>
⚔️{int(battle.get_effective_stats(p2)['attack'])} 🛡️{int(battle.get_effective_stats(p2)['defense'])} ⚡{int(battle.get_effective_stats(p2)['speed'])}
{p2_eff}
{combo_display}
━━━━━━━━━━━━━━━━━━━━
<b>📜 {sc('battle log')}</b>"""
    
    if battle.battle_log:
        for log in battle.battle_log[-4:]:
            panel += f"\n• {log}"
    else:
        panel += f"\n• {sc('battle started!')}"
    
    if action_msg:
        panel += f"\n\n<b>➤ {action_msg}</b>"
    
    panel += f"\n\n<i>Turn {battle.turn_count + 1}</i>"
    
    return panel

def create_attack_keyboard(battle: Battle, uid: int) -> InlineKeyboardMarkup:
    player = battle.get_current_player()
    unlocked = get_unlocked_attacks(player.level)
    
    elements = {
        "basic": ["punch", "slash"],
        "fire": ["fireball", "flame_burst", "inferno"],
        "ice": ["ice_shard", "blizzard", "absolute_zero"],
        "lightning": ["spark", "thunderbolt", "divine_thunder"],
        "water": ["aqua_jet", "tidal_wave", "tsunami"],
        "earth": ["rock_throw", "earthquake", "meteor"],
        "wind": ["gust", "cyclone", "tempest"],
        "dark": ["shadow_bolt", "void_strike", "oblivion"],
        "light": ["holy_ray", "radiance", "divine_judgment"],
    }
    
    available = {}
    for elem, attacks in elements.items():
        avail = [a for a in attacks if a in unlocked]
        if avail:
            available[elem] = avail
    
    keyboard = []
    row = []
    
    for elem, attacks in available.items():
        best = max(attacks, key=lambda a: ATTACKS[a].base_damage)
        atk = ATTACKS[best]
        
        can_use = player.mana >= atk.mana_cost
        emoji = atk.emoji if can_use else "✗"
        
        btn = InlineKeyboardButton(emoji, callback_data=f"btl_atk_{best}_{uid}")
        row.append(btn)
        
        if len(row) >= 5:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton("🛡️", callback_data=f"btl_def_{uid}"),
        InlineKeyboardButton("💚", callback_data=f"btl_heal_{uid}"),
        InlineKeyboardButton("💙", callback_data=f"btl_mana_{uid}"),
        InlineKeyboardButton("📖", callback_data=f"btl_skills_{uid}"),
    ])
    
    keyboard.append([
        InlineKeyboardButton(f"🏳️ {sc('forfeit')}", callback_data=f"btl_forfeit_{uid}")
    ])
    
    return InlineKeyboardMarkup(keyboard)

def create_skills_keyboard(battle: Battle, uid: int) -> InlineKeyboardMarkup:
    player = battle.get_current_player()
    
    keyboard = [
        [
            InlineKeyboardButton(f"💪 {sc('might')} (35)", callback_data=f"btl_buff_might_{uid}"),
            InlineKeyboardButton(f"🛡️ {sc('shield')} (30)", callback_data=f"btl_buff_shield_{uid}"),
        ],
        [
            InlineKeyboardButton(f"⚡ {sc('haste')} (40)", callback_data=f"btl_buff_haste_{uid}"),
            InlineKeyboardButton(f"💚 {sc('regen')} (45)", callback_data=f"btl_buff_regen_{uid}"),
        ],
        [InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"btl_back_{uid}")]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def create_waiting_keyboard(player_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"⏳ {sc('waiting for')} {player_name}...", callback_data="btl_wait")
    ]])

def create_end_keyboard(winner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚔️ {sc('new battle')}", callback_data=f"btl_menu_{winner_id}")]
    ])

async def handle_battle_end(message, battle: Battle, winner: Optional[int]):
    if not winner:
        battle_manager.end(battle.player1.user_id, battle.player2.user_id)
        try:
            await message.edit_text(f"⏰ {sc('battle cancelled due to inactivity!')}", parse_mode="HTML")
        except:
            pass
        return
    
    battle_manager.end(battle.player1.user_id, battle.player2.user_id)
    
    winner_p = battle.player1 if winner == 1 else battle.player2
    loser_p = battle.player2 if winner == 1 else battle.player1
    winner_stats = battle.p1_stats if winner == 1 else battle.p2_stats
    loser_stats = battle.p2_stats if winner == 1 else battle.p1_stats
    
    level_diff = max(0, loser_p.level - winner_p.level)
    base_xp = 100 if battle.is_pvp else 60
    xp_mult = 1.0 + (level_diff * 0.2) + (winner_stats.critical_hits * 0.05) + (winner_stats.max_combo * 0.1)
    winner_xp = int(base_xp * xp_mult)
    loser_xp = int(base_xp * 0.35) if battle.is_pvp else 0
    
    base_coins = 200 if battle.is_pvp else 100
    winner_coins = base_coins + (winner_p.level * 20) + random.randint(50, 150)
    loser_coins = base_coins // 3 if battle.is_pvp else 0
    
    old_level = winner_p.level
    await save_progress(winner_p.user_id, winner_xp, winner_coins)
    
    if battle.is_pvp:
        await save_progress(loser_p.user_id, loser_xp, loser_coins)
    
    new_doc = await user_collection.find_one({'id': winner_p.user_id})
    new_xp = new_doc.get('user_xp', 0) if new_doc else 0
    new_level = calc_level(new_xp)
    new_rank, new_rank_emoji = calc_rank(new_level)
    
    level_up_text = ""
    if new_level > old_level:
        level_up_text = f"""

<b>🎉 {sc('level up!')} 🎉</b>
{old_level} ➤ {new_level} {new_rank_emoji}"""
        
        old_attacks = set(get_unlocked_attacks(old_level))
        new_attacks = set(get_unlocked_attacks(new_level))
        unlocked = new_attacks - old_attacks
        
        if unlocked:
            attack_names = [ATTACKS[a].name for a in unlocked]
            level_up_text += f"\n<b>{sc('new attacks:')}</b> {', '.join(attack_names)}"
    
    loser_name = loser_p.username if battle.is_pvp else "AI"
    
    result = f"""<b>⚔️ {sc('battle complete!')} ⚔️</b>
━━━━━━━━━━━━━━━━━━━━

<b>🏆 {sc('winner:')}</b> {winner_p.username}
<b>💀 {sc('defeated:')}</b> {loser_name}

<b>📊 {sc('battle statistics')}</b>
━━━━━━━━━━━━━━━━━━━━

<b>{winner_p.username}</b>
• Damage: {winner_stats.total_damage_dealt}
• Crits: {winner_stats.critical_hits}
• Max Combo: {winner_stats.max_combo}
• Healed: {winner_stats.total_healing}
• Misses: {winner_stats.misses}
• Dodges: {winner_stats.dodges}

<b>{loser_name}</b>
• Damage: {loser_stats.total_damage_dealt}
• Crits: {loser_stats.critical_hits}
• Max Combo: {loser_stats.max_combo}
• Healed: {loser_stats.total_healing}
• Misses: {loser_stats.misses}
• Dodges: {loser_stats.dodges}

<b>🎁 {sc('rewards')}</b>
━━━━━━━━━━━━━━━━━━━━
<b>{winner_p.username}:</b> +{winner_xp} XP, +{winner_coins} 💰"""

    if battle.is_pvp and loser_xp > 0:
        result += f"\n<b>{loser_p.username}:</b> +{loser_xp} XP, +{loser_coins} 💰"
    
    result += level_up_text
    
    try:
        await message.edit_text(
            result,
            reply_markup=create_end_keyboard(winner_p.user_id),
            parse_mode="HTML"
        )
    except:
        pass

async def rpg_start(update: Update, context: CallbackContext):
    user = update.effective_user
    msg = update.message
    
    existing = battle_manager.get(user.id)
    if existing and not existing.is_expired:
        await msg.reply_text(f"⚠️ {sc('already in battle! use /rpgforfeit to quit')}", parse_mode="HTML")
        return
    
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
        
        if battle_manager.get_challenge(target.id):
            await msg.reply_text(f"⚠️ {sc('player has pending challenge!')}", parse_mode="HTML")
            return
        
        battle_manager.challenge(user.id, target.id, user.first_name)
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"✅ {sc('accept')}", callback_data=f"btl_accept_{user.id}_{target.id}"),
                InlineKeyboardButton(f"❌ {sc('decline')}", callback_data=f"btl_decline_{user.id}_{target.id}")
            ]
        ])
        
        await msg.reply_text(
            f"""<b>⚔️ {sc('battle challenge!')} ⚔️</b>

<b>{target.first_name}</b>, you have been challenged by <b>{user.first_name}</b>!

<i>60 seconds to respond</i>""",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return
    
    can_battle, limit_msg = await check_battle_limits(user.id, False)
    if not can_battle:
        await msg.reply_text(limit_msg, parse_mode="HTML")
        return
    
    await increment_battle_count(user.id, False)
    
    p1 = await load_player(user.id, user.first_name)
    
    ai_level = max(1, p1.level + random.randint(-2, 2))
    ai_rank, ai_emoji = calc_rank(ai_level)
    ai_mult = 1 + (ai_level - 1) * 0.1
    ai_element = random.choice(list(Element))
    
    p2 = PlayerStats(
        user_id=0,
        username="AI",
        hp=int(180 * ai_mult),
        max_hp=int(180 * ai_mult),
        mana=int(140 * ai_mult),
        max_mana=int(140 * ai_mult),
        attack=int(28 * ai_mult),
        defense=int(18 * ai_mult),
        speed=int(14 * ai_mult),
        accuracy=88,
        crit_chance=0.08 + (ai_level * 0.003),
        level=ai_level,
        rank=ai_rank,
        rank_emoji=ai_emoji,
        xp=0,
        element_affinity=ai_element
    )
    
    battle = battle_manager.start(p1, p2, False)
    
    panel = format_battle_ui(battle)
    kb = create_attack_keyboard(battle, user.id) if battle.current_turn == 1 else create_waiting_keyboard("AI")
    
    try:
        battle_msg = await msg.reply_text(panel, reply_markup=kb, parse_mode="HTML")
        
        if battle.current_turn == 2:
            await asyncio.sleep(1)
            result = await ai_turn(battle)
            
            if result.animation_url:
                try:
                    await msg.reply_animation(result.animation_url, caption=result.text, parse_mode="HTML")
                except:
                    pass
            
            battle.switch_turn()
            
            over, winner = battle.is_over()
            if over:
                await handle_battle_end(battle_msg, battle, winner)
            else:
                panel = format_battle_ui(battle)
                kb = create_attack_keyboard(battle, user.id)
                await battle_msg.edit_text(panel, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        battle_manager.end(p1.user_id, p2.user_id)
        await msg.reply_text(f"❌ {sc('failed to start battle!')}", parse_mode="HTML")

async def rpg_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data.split("_")
    action = data[1] if len(data) > 1 else None
    
    if action == "wait":
        await query.answer(sc("waiting for opponent..."), show_alert=False)
        return
    
    await query.answer()
    
    if action == "menu":
        uid = int(data[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your button!"), show_alert=True)
            return
        
        doc = await get_user(uid)
        battle_data = doc.get('battle_data', {}) if doc else {}
        ai_count = battle_data.get('ai_battles', 0)
        pvp_count = battle_data.get('pvp_battles', 0)
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⚔️ {sc('start pve battle')} ({ai_count}/{MAX_AI_BATTLES_PER_DAY})", callback_data=f"btl_startpve_{uid}")],
            [InlineKeyboardButton(f"📊 {sc('view stats')}", callback_data=f"btl_stats_{uid}")],
            [InlineKeyboardButton(f"📖 {sc('attack list')}", callback_data=f"btl_attacks_{uid}")],
            [InlineKeyboardButton(f"🏆 {sc('leaderboard')}", callback_data=f"btl_lb_{uid}")],
            [InlineKeyboardButton(f"🛒 {sc('battle shop')}", callback_data=f"btl_shop_{uid}")]
        ])
        
        try:
            await query.message.edit_text(
                f"""<b>⚔️ {sc('rpg battle system')} ⚔️</b>

{sc('daily limits:')}
• AI Battles: {ai_count}/{MAX_AI_BATTLES_PER_DAY}
• PVP Battles: {pvp_count}/{MAX_PVP_BATTLES_PER_DAY}

{sc('select an option:')}""",
                reply_markup=kb, parse_mode="HTML"
            )
        except:
            pass
        return
    
    if action == "startpve":
        uid = int(data[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your button!"), show_alert=True)
            return
        
        can_battle, limit_msg = await check_battle_limits(uid, False)
        if not can_battle:
            await query.answer(limit_msg, show_alert=True)
            return
        
        await increment_battle_count(uid, False)
        
        update.message = query.message
        update.message.reply_to_message = None
        await rpg_start(update, context)
        return
    
    if action == "accept":
        cid, tid = int(data[2]), int(data[3])
        
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
        
        can_battle_c, _ = await check_battle_limits(cid, True)
        can_battle_t, _ = await check_battle_limits(tid, True)
        
        if not can_battle_c or not can_battle_t:
            await query.answer(sc("daily limit reached for one of the players!"), show_alert=True)
            return
        
        await increment_battle_count(cid, True)
        await increment_battle_count(tid, True)
        
        battle_manager.remove_challenge(tid)
        
        p1 = await load_player(cid, challenge['challenger_name'])
        p2 = await load_player(tid, update.effective_user.first_name)
        
        battle = battle_manager.start(p1, p2, True)
        
        first_player_id = p1.user_id if battle.current_turn == 1 else p2.user_id
        first_player_name = p1.username if battle.current_turn == 1 else p2.username
        panel = format_battle_ui(battle)
        kb = create_attack_keyboard(battle, first_player_id)
        
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            battle_manager.end(p1.user_id, p2.user_id)
        return
    
    if action == "decline":
        tid = int(data[3])
        
        if update.effective_user.id != tid:
            await query.answer(sc("not your challenge!"), show_alert=True)
            return
        
        battle_manager.remove_challenge(tid)
        try:
            await query.message.edit_text(f"❌ {sc('challenge declined!')}", parse_mode="HTML")
        except:
            pass
        return
    
    if action == "stats":
        uid = int(data[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your stats!"), show_alert=True)
            return
        
        player = await load_player(uid, update.effective_user.first_name)
        doc = await user_collection.find_one({'id': uid})
        
        balance = doc.get('balance', 0) if doc else 0
        tokens = doc.get('tokens', 0) if doc else 0
        battle_data = doc.get('battle_data', {}) if doc else {}
        
        unlocked = get_unlocked_attacks(player.level)
        current_xp = player.xp
        progress = current_xp % ((player.level) ** 2 * 100) if player.level > 1 else current_xp
        next_lvl_xp = calc_xp_needed(player.level) - calc_xp_needed(player.level - 1) if player.level > 1 else 100
        
        stats_text = f"""<b>📊 {sc('player statistics')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('profile')}</b>
• Name: {player.username}
• Level: {player.level} {player.rank_emoji}
• Rank: {player.rank}
• Element: {player.element_affinity.value.title()}

<b>{sc('experience')}</b>
{create_xp_bar(progress, next_lvl_xp)} {progress}/{next_lvl_xp}
• Total XP: {current_xp}

<b>{sc('combat stats')}</b>
• HP: {player.max_hp}
• Mana: {player.max_mana}
• Attack: {player.attack}
• Defense: {player.defense}
• Speed: {player.speed}
• Crit: {player.crit_chance*100:.1f}%
• Accuracy: {player.accuracy}%

<b>{sc('daily battles')}</b>
• AI: {battle_data.get('ai_battles', 0)}/{MAX_AI_BATTLES_PER_DAY}
• PVP: {battle_data.get('pvp_battles', 0)}/{MAX_PVP_BATTLES_PER_DAY}

<b>{sc('inventory')}</b>
• 💰 Coins: {balance}
• 🎫 Tokens: {tokens}

<b>{sc('attacks unlocked:')}</b> {len(unlocked)}/{len(ATTACKS)}"""
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"btl_menu_{uid}")]
        ])
        
        try:
            await query.message.edit_text(stats_text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "attacks":
        uid = int(data[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not yours!"), show_alert=True)
            return
        
        player = await load_player(uid, update.effective_user.first_name)
        unlocked = get_unlocked_attacks(player.level)
        
        text = f"<b>📖 {sc('attack compendium')} 📖</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        by_element = {}
        for name, atk in ATTACKS.items():
            elem = atk.element.value
            if elem not in by_element:
                by_element[elem] = []
            status = "✓" if name in unlocked else f"🔒Lv.{atk.unlock_level}"
            by_element[elem].append(f"{atk.emoji} {atk.name} ({atk.mana_cost}MP) - DMG:{atk.base_damage} {status}")
        
        for elem, attacks in by_element.items():
            text += f"<b>{elem.upper()}</b>\n"
            text += "\n".join(attacks[:3])
            if len(attacks) > 3:
                text += f"\n<i>+{len(attacks)-3} more...</i>"
            text += "\n\n"
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"btl_menu_{uid}")]
        ])
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "lb":
        uid = int(data[2])
        
        try:
            top = await user_collection.find().sort('user_xp', -1).limit(10).to_list(length=10)
        except:
            top = []
        
        text = f"<b>🏆 {sc('leaderboard')} 🏆</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, doc in enumerate(top):
            uname = doc.get('username', doc.get('first_name', 'Unknown'))[:12]
            xp = doc.get('user_xp', 0)
            lvl = calc_level(xp)
            rank, emoji = calc_rank(lvl)
            
            medal = medals[i] if i < 3 else f"{i+1}."
            text += f"{medal} <b>{uname}</b> {emoji} Lv.{lvl} • {xp} XP\n"
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"btl_menu_{uid}")]
        ])
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "shop":
        uid = int(data[2])
        if update.effective_user.id != uid:
            await query.answer(sc("not your shop!"), show_alert=True)
            return
        
        text = f"""<b>🛒 {sc('battle shop')} 🛒</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('coming soon!')}</b>

{sc('purchase items to boost your battles:')}
• HP Potions
• Mana Potions
• Element Crystals
• Stat Boosters
• Special Abilities

<i>{sc('check back later for updates!')}</i>"""
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"◀️ {sc('back')}", callback_data=f"btl_menu_{uid}")]
        ])
        
        try:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    uid = int(data[-1]) if len(data) > 2 else 0
    
    if update.effective_user.id != uid:
        await query.answer(sc("not your turn!"), show_alert=True)
        return
    
    battle = battle_manager.get(uid)
    
    if not battle:
        try:
            await query.message.edit_text(f"❌ {sc('no active battle! use /rpg to start')}", parse_mode="HTML")
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
            
            if ai_result.animation_url:
                try:
                    await query.message.reply_animation(ai_result.animation_url, caption=ai_result.text, parse_mode="HTML")
                except:
                    pass
            
            battle.switch_turn()
            
            over, winner = battle.is_over()
            if over:
                await handle_battle_end(query.message, battle, winner)
                return
        
        panel = format_battle_ui(battle)
        next_id = battle.player1.user_id if battle.current_turn == 1 else battle.player2.user_id
        next_name = battle.player1.username if battle.current_turn == 1 else battle.player2.username
        
        if battle.is_pvp:
            kb = create_attack_keyboard(battle, next_id)
        else:
            kb = create_attack_keyboard(battle, next_id) if battle.current_turn == 1 else create_waiting_keyboard("AI")
        
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    result = None
    
    if action == "back":
        panel = format_battle_ui(battle)
        kb = create_attack_keyboard(battle, uid)
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "skills":
        panel = format_battle_ui(battle)
        panel += f"\n\n<b>{sc('select a skill:')}</b>"
        kb = create_skills_keyboard(battle, uid)
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        return
    
    if action == "atk":
        atk_name = data[2]
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
    
    elif action == "mana":
        result = perform_mana_restore(battle)
    
    elif action == "buff":
        buff_type = data[2]
        result = perform_buff(battle, buff_type)
        if "Need" in result.text or "Already" in result.text or "Invalid" in result.text:
            await query.answer(result.text, show_alert=True)
            return
    
    elif action == "forfeit":
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
    
    if result.animation_url:
        try:
            await query.message.reply_animation(result.animation_url, caption=result.text, parse_mode="HTML")
        except:
            pass
    
    effect_msgs = battle.process_turn_effects(current)
    for msg in effect_msgs:
        battle.add_log(msg)
    
    battle.switch_turn()
    
    over, winner = battle.is_over()
    if over:
        await handle_battle_end(query.message, battle, winner)
        return
    
    if not battle.is_pvp and battle.current_turn == 2:
        opponent_name = battle.player2.username
        panel = format_battle_ui(battle, result.text)
        kb = create_waiting_keyboard(opponent_name)
        
        try:
            await query.message.edit_text(panel, reply_markup=kb, parse_mode="HTML")
        except:
            pass
        
        ai_result = await ai_turn(battle)
        
        if ai_result.animation_url:
            try:
                await query.message.reply_animation(ai_result.animation_url, caption=ai_result.text, parse_mode="HTML")
            except:
                pass
        
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
    next_name = battle.player1.username if battle.current_turn == 1 else battle.player2.username
    
    if battle.is_pvp:
        kb = create_attack_keyboard(battle, next_id)
    else:
        kb = create_attack_keyboard(battle, next_id) if battle.current_turn == 1 else create_waiting_keyboard("AI")
    
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
        [InlineKeyboardButton(f"⚔️ {sc('start pve battle')} ({ai_count}/{MAX_AI_BATTLES_PER_DAY})", callback_data=f"btl_startpve_{user.id}")],
        [InlineKeyboardButton(f"📊 {sc('view stats')}", callback_data=f"btl_stats_{user.id}")],
        [InlineKeyboardButton(f"📖 {sc('attack list')}", callback_data=f"btl_attacks_{user.id}")],
        [InlineKeyboardButton(f"🏆 {sc('leaderboard')}", callback_data=f"btl_lb_{user.id}")],
        [InlineKeyboardButton(f"🛒 {sc('battle shop')}", callback_data=f"btl_shop_{user.id}")]
    ])
    
    await update.message.reply_text(
        f"""<b>⚔️ {sc('rpg battle system')} ⚔️</b>

{sc('daily limits:')}
• AI Battles: {ai_count}/{MAX_AI_BATTLES_PER_DAY}
• PVP Battles: {pvp_count}/{MAX_PVP_BATTLES_PER_DAY}

{sc('select an option:')}""",
        reply_markup=kb, parse_mode="HTML"
    )

async def rpg_stats_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    player = await load_player(user.id, user.first_name)
    doc = await user_collection.find_one({'id': user.id})
    
    balance = doc.get('balance', 0) if doc else 0
    tokens = doc.get('tokens', 0) if doc else 0
    battle_data = doc.get('battle_data', {}) if doc else {}
    
    unlocked = get_unlocked_attacks(player.level)
    current_xp = player.xp
    progress = current_xp % ((player.level) ** 2 * 100) if player.level > 1 else current_xp
    next_lvl_xp = calc_xp_needed(player.level) - calc_xp_needed(player.level - 1) if player.level > 1 else 100
    
    stats_text = f"""<b>📊 {sc('player statistics')} 📊</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('profile')}</b>
• Name: {player.username}
• Level: {player.level} {player.rank_emoji}
• Rank: {player.rank}
• Element: {player.element_affinity.value.title()}

<b>{sc('experience')}</b>
{create_xp_bar(progress, next_lvl_xp)} {progress}/{next_lvl_xp}
• Total XP: {current_xp}

<b>{sc('combat stats')}</b>
• HP: {player.max_hp}
• Mana: {player.max_mana}
• Attack: {player.attack}
• Defense: {player.defense}
• Speed: {player.speed}
• Crit: {player.crit_chance*100:.1f}%
• Accuracy: {player.accuracy}%

<b>{sc('daily battles')}</b>
• AI: {battle_data.get('ai_battles', 0)}/{MAX_AI_BATTLES_PER_DAY}
• PVP: {battle_data.get('pvp_battles', 0)}/{MAX_PVP_BATTLES_PER_DAY}

<b>{sc('inventory')}</b>
• 💰 Coins: {balance}
• 🎫 Tokens: {tokens}

<b>{sc('attacks unlocked:')}</b> {len(unlocked)}/{len(ATTACKS)}"""
    
    await update.message.reply_text(stats_text, parse_mode="HTML")

async def rpg_level_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    doc = await get_user(user.id)
    
    if not doc:
        await update.message.reply_text(f"⚠️ {sc('no data found! start a battle first.')}", parse_mode="HTML")
        return
    
    xp = doc.get('user_xp', 0)
    lvl = calc_level(xp)
    rank, emoji = calc_rank(lvl)
    
    current_lvl_xp = calc_xp_needed(lvl - 1) if lvl > 1 else 0
    next_lvl_xp = calc_xp_needed(lvl)
    progress = xp - current_lvl_xp
    needed = next_lvl_xp - current_lvl_xp
    
    all_unlocks = [(name, data.unlock_level) for name, data in ATTACKS.items()]
    next_unlocks = sorted([u for u in all_unlocks if u[1] > lvl], key=lambda x: x[1])[:3]
    
    unlock_text = ""
    if next_unlocks:
        unlock_text = f"\n\n<b>{sc('upcoming unlocks:')}</b>\n"
        for name, ulvl in next_unlocks:
            atk = ATTACKS[name]
            unlock_text += f"• Lv.{ulvl}: {atk.emoji} {atk.name}\n"
    
    text = f"""<b>📈 {sc('level progress')} 📈</b>
━━━━━━━━━━━━━━━━━━━━

<b>Level {lvl}</b> {emoji} Rank {rank}

{create_xp_bar(progress, needed, 12)}
<code>{progress} / {needed}</code> XP

<b>{sc('total xp:')}</b> {xp}
<b>{sc('xp to next level:')}</b> {needed - progress}{unlock_text}"""
    
    await update.message.reply_text(text, parse_mode="HTML")

async def rpg_forfeit_cmd(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    battle = battle_manager.get(uid)
    
    if not battle:
        await update.message.reply_text(f"❌ {sc('not in a battle!')}", parse_mode="HTML")
        return
    
    battle_manager.end(battle.player1.user_id, battle.player2.user_id)
    
    await update.message.reply_text(
        f"<b>🏳️ {sc('battle forfeited')} 🏳️</b>\n\n{sc('you gave up!')}",
        parse_mode="HTML"
    )

async def rpg_help(update: Update, context: CallbackContext):
    text = f"""<b>⚔️ {sc('rpg battle guide')} ⚔️</b>
━━━━━━━━━━━━━━━━━━━━

<b>{sc('commands')}</b>
• /rpg - Start PVE battle
• /rpg (reply) - Challenge player
• /rpgmenu - Main menu
• /rpgstats - View your stats
• /rpglevel - Level progress
• /rpgforfeit - Quit battle
• /rpghelp - This guide

<b>{sc('daily limits')}</b>
• AI Battles: {MAX_AI_BATTLES_PER_DAY}/day
• PVP Battles: {MAX_PVP_BATTLES_PER_DAY}/day
• Limits reset at 00:00 UTC

<b>{sc('combat basics')}</b>
• Each element has strengths/weaknesses
• 🔥 Fire beats ❄️ Ice, 🌍 Earth
• ❄️ Ice beats 💨 Wind, 💧 Water  
• ⚡ Lightning beats 💧 Water, 💨 Wind
• 💧 Water beats 🔥 Fire, 🌍 Earth
• And more combinations!

<b>{sc('status effects')}</b>
• 🔥 Burn - Damage over time
• 🧊 Freeze - Slowed speed
• 💫 Stun - Skip turn
• 🩸 Bleed - HP drain
• 💀 Curse - Weakened stats
• 😵 Blind - Reduced accuracy

<b>{sc('buffs')}</b>
• 💪 Might - +30% Attack
• 🛡️ Shield - +50% Defense  
• ⚡ Haste - +50% Speed
• 💚 Regen - Heal over time

<b>{sc('tips')}</b>
• Higher speed = first turn + dodge chance
• Consecutive crits build combos
• Defending restores some mana
• Use elemental advantages!
• Unlock stronger attacks as you level up
• Max level is 100!"""
    
    await update.message.reply_text(text, parse_mode="HTML")

application.add_handler(CommandHandler("rpg", rpg_start))
application.add_handler(CommandHandler("battle", rpg_start))
application.add_handler(CommandHandler("rpgmenu", rpg_menu))
application.add_handler(CommandHandler("rpgstats", rpg_stats_cmd))
application.add_handler(CommandHandler("rpglevel", rpg_level_cmd))
application.add_handler(CommandHandler("rpgforfeit", rpg_forfeit_cmd))
application.add_handler(CommandHandler("rpghelp", rpg_help))
application.add_handler(CallbackQueryHandler(rpg_callback, pattern="^btl_"))