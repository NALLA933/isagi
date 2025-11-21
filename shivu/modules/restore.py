import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from shivu import application, user_collection

logger = logging.getLogger(__name__)

class AttackType(Enum):
    FIRE = "fire"
    ICE = "ice"

@dataclass
class Player:
    user_id: int
    hp: int
    max_hp: int
    mana: int
    max_mana: int
    attack: int
    defense: int
    
@dataclass
class Enemy:
    name: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    reward_coins: int
    reward_tokens: int

class BattleConfig:
    FIRE_COST = 30
    FIRE_DAMAGE = 25
    ICE_COST = 25
    ICE_DAMAGE = 20
    HEALTH_POTION_COST = 20
    HEALTH_POTION_HEAL = 30
    MANA_POTION_RESTORE = 40
    DEFEND_MULTIPLIER = 2
    BATTLE_TIMEOUT = 300  # 5 minutes
    
    # Video URLs
    FIRE_VIDEO = "https://files.catbox.moe/y3zz0k.mp4"
    ICE_VIDEO = "https://files.catbox.moe/tm5iwt.mp4"

class BattleState:
    def __init__(self):
        self.active_battles: Dict[int, 'Battle'] = {}
        
    def start_battle(self, user_id: int, player: Player, enemy: Enemy) -> 'Battle':
        battle = Battle(player, enemy)
        self.active_battles[user_id] = battle
        return battle
    
    def get_battle(self, user_id: int) -> Optional['Battle']:
        return self.active_battles.get(user_id)
    
    def end_battle(self, user_id: int):
        self.active_battles.pop(user_id, None)

class Battle:
    def __init__(self, player: Player, enemy: Enemy):
        self.player = player
        self.enemy = enemy
        self.is_defending = False
        self.turn_count = 0
        self.started_at = datetime.utcnow()
        self.battle_log = []
        
    def add_log(self, message: str):
        self.battle_log.append(message)
        if len(self.battle_log) > 5:
            self.battle_log.pop(0)
    
    def is_over(self) -> Tuple[bool, bool]:
        """Returns (is_over, player_won)"""
        if self.player.hp <= 0:
            return True, False
        if self.enemy.hp <= 0:
            return True, True
        if (datetime.utcnow() - self.started_at).seconds > BattleConfig.BATTLE_TIMEOUT:
            return True, False
        return False, False

battle_state = BattleState()

def generate_enemy(difficulty: str = "normal") -> Enemy:
    """Generate random enemy based on difficulty"""
    enemies = {
        "easy": [
            {"name": "🐺 Wolf", "hp": 50, "attack": 10, "defense": 5, "coins": 50, "tokens": 1},
            {"name": "🦇 Bat", "hp": 40, "attack": 8, "defense": 3, "coins": 40, "tokens": 1},
        ],
        "normal": [
            {"name": "👹 Goblin", "hp": 80, "attack": 15, "defense": 8, "coins": 100, "tokens": 2},
            {"name": "🧟 Zombie", "hp": 90, "attack": 12, "defense": 10, "coins": 120, "tokens": 2},
            {"name": "🐉 Baby Dragon", "hp": 100, "attack": 18, "defense": 12, "coins": 150, "tokens": 3},
        ],
        "hard": [
            {"name": "⚔️ Dark Knight", "hp": 150, "attack": 25, "defense": 15, "coins": 300, "tokens": 5},
            {"name": "🐲 Dragon", "hp": 200, "attack": 30, "defense": 20, "coins": 500, "tokens": 8},
            {"name": "👑 Boss", "hp": 250, "attack": 35, "defense": 25, "coins": 800, "tokens": 10},
        ]
    }
    
    enemy_list = enemies.get(difficulty, enemies["normal"])
    enemy_data = random.choice(enemy_list)
    
    return Enemy(
        name=enemy_data["name"],
        hp=enemy_data["hp"],
        max_hp=enemy_data["hp"],
        attack=enemy_data["attack"],
        defense=enemy_data["defense"],
        reward_coins=enemy_data["coins"],
        reward_tokens=enemy_data["tokens"]
    )

def create_battle_keyboard(user_id: int, battle: Battle) -> InlineKeyboardMarkup:
    """Create battle control keyboard"""
    over, won = battle.is_over()
    
    if over:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 New Battle", callback_data=f"rpg:start:{user_id}")]
        ])
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"🔥 Fire ({BattleConfig.FIRE_COST} mana)", 
                callback_data=f"rpg:attack:fire:{user_id}"
            ),
            InlineKeyboardButton(
                f"❄️ Ice ({BattleConfig.ICE_COST} mana)", 
                callback_data=f"rpg:attack:ice:{user_id}"
            )
        ],
        [
            InlineKeyboardButton("🛡️ Defend", callback_data=f"rpg:defend:{user_id}"),
            InlineKeyboardButton(
                f"💚 Health Potion ({BattleConfig.HEALTH_POTION_COST} mana)", 
                callback_data=f"rpg:potion:health:{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"💙 Mana Potion", 
                callback_data=f"rpg:potion:mana:{user_id}"
            ),
            InlineKeyboardButton("❌ Forfeit", callback_data=f"rpg:forfeit:{user_id}")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def format_battle_status(battle: Battle) -> str:
    """Format battle status message"""
    p = battle.player
    e = battle.enemy
    
    # Player stats bars
    hp_bar = create_bar(p.hp, p.max_hp, 10, "█", "░")
    mana_bar = create_bar(p.mana, p.max_mana, 10, "█", "░")
    
    # Enemy stats bar
    enemy_hp_bar = create_bar(e.hp, e.max_hp, 10, "█", "░")
    
    status = f"""
<b>⚔️ BATTLE IN PROGRESS ⚔️</b>

<b>{e.name}</b>
❤️ HP: {enemy_hp_bar} {e.hp}/{e.max_hp}
⚔️ ATK: {e.attack} | 🛡️ DEF: {e.defense}

━━━━━━━━━━━━━━━━
<b>👤 YOUR STATS</b>
❤️ HP: {hp_bar} {p.hp}/{p.max_hp}
💙 Mana: {mana_bar} {p.mana}/{p.max_mana}
⚔️ ATK: {p.attack} | 🛡️ DEF: {p.defense}
"""
    
    if battle.is_defending:
        status += "\n🛡️ <b>DEFENDING</b> (Defense x2)"
    
    if battle.battle_log:
        status += "\n\n<b>📜 Battle Log:</b>"
        for log in battle.battle_log[-3:]:
            status += f"\n• {log}"
    
    return status

def create_bar(current: int, maximum: int, length: int, filled: str, empty: str) -> str:
    """Create a visual bar"""
    percentage = max(0, min(1, current / maximum))
    filled_length = int(length * percentage)
    return filled * filled_length + empty * (length - filled_length)

async def perform_attack(battle: Battle, attack_type: AttackType) -> Tuple[str, Optional[str]]:
    """Perform an attack and return (message, video_url)"""
    p = battle.player
    e = battle.enemy
    
    if attack_type == AttackType.FIRE:
        if p.mana < BattleConfig.FIRE_COST:
            return "❌ Not enough mana for Fire Attack!", None
        p.mana -= BattleConfig.FIRE_COST
        damage = max(1, (p.attack + BattleConfig.FIRE_DAMAGE) - e.defense)
        e.hp = max(0, e.hp - damage)
        battle.add_log(f"🔥 Fire Attack dealt {damage} damage!")
        return f"🔥 Fire Attack dealt <b>{damage}</b> damage!", BattleConfig.FIRE_VIDEO
    
    else:  # ICE
        if p.mana < BattleConfig.ICE_COST:
            return "❌ Not enough mana for Ice Attack!", None
        p.mana -= BattleConfig.ICE_COST
        damage = max(1, (p.attack + BattleConfig.ICE_DAMAGE) - e.defense)
        e.hp = max(0, e.hp - damage)
        battle.add_log(f"❄️ Ice Attack dealt {damage} damage!")
        return f"❄️ Ice Attack dealt <b>{damage}</b> damage!", BattleConfig.ICE_VIDEO

async def enemy_turn(battle: Battle) -> str:
    """Enemy attacks the player"""
    e = battle.enemy
    p = battle.player
    
    defense_mult = BattleConfig.DEFEND_MULTIPLIER if battle.is_defending else 1
    damage = max(1, e.attack - (p.defense * defense_mult))
    p.hp = max(0, p.hp - damage)
    
    battle.is_defending = False
    battle.add_log(f"👹 {e.name} dealt {damage} damage!")
    
    return f"👹 <b>{e.name}</b> attacks for <b>{damage}</b> damage!"

async def rpg_start(update: Update, context: CallbackContext):
    """Start a new RPG battle"""
    user_id = update.effective_user.id
    
    # Check if already in battle
    if battle_state.get_battle(user_id):
        await update.message.reply_text(
            "⚠️ You're already in a battle! Use the buttons to continue or forfeit.",
            parse_mode="HTML"
        )
        return
    
    # Get or create user
    user_doc = await user_collection.find_one({'id': user_id})
    if not user_doc:
        user_doc = {
            'id': user_id,
            'first_name': update.effective_user.first_name,
            'username': update.effective_user.username,
            'balance': 0,
            'tokens': 0
        }
        await user_collection.insert_one(user_doc)
    
    # Parse difficulty
    difficulty = "normal"
    if context.args:
        arg = context.args[0].lower()
        if arg in ["easy", "normal", "hard"]:
            difficulty = arg
    
    # Create player and enemy
    player = Player(
        user_id=user_id,
        hp=100,
        max_hp=100,
        mana=100,
        max_mana=100,
        attack=20,
        defense=10
    )
    
    enemy = generate_enemy(difficulty)
    
    # Start battle
    battle = battle_state.start_battle(user_id, player, enemy)
    
    status = format_battle_status(battle)
    keyboard = create_battle_keyboard(user_id, battle)
    
    await update.message.reply_text(
        status,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def rpg_callback(update: Update, context: CallbackContext):
    """Handle RPG button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    action = data[1]
    user_id = int(data[-1])
    
    # Verify user
    if update.effective_user.id != user_id:
        await query.answer("⚠️ This isn't your battle!", show_alert=True)
        return
    
    battle = battle_state.get_battle(user_id)
    
    # Handle new battle start
    if action == "start":
        if battle:
            await query.answer("⚠️ Already in battle!", show_alert=True)
            return
        
        # Simulate command context for starting battle
        update.message = query.message
        await rpg_start(update, context)
        return
    
    if not battle:
        await query.message.edit_text(
            "❌ No active battle found. Start a new one with /rpg",
            parse_mode="HTML"
        )
        return
    
    # Check if battle is over
    over, won = battle.is_over()
    if over:
        await query.answer("⚠️ Battle is already over!", show_alert=True)
        return
    
    message = ""
    video_url = None
    
    # Handle actions
    if action == "attack":
        attack_type = AttackType(data[2])
        message, video_url = await perform_attack(battle, attack_type)
        
        # Check if enemy defeated
        over, won = battle.is_over()
        if not over:
            # Enemy turn
            enemy_msg = await enemy_turn(battle)
            message += f"\n{enemy_msg}"
    
    elif action == "defend":
        battle.is_defending = True
        battle.add_log("🛡️ Defending!")
        message = "🛡️ You brace for defense!"
        # Enemy turn
        enemy_msg = await enemy_turn(battle)
        message += f"\n{enemy_msg}"
    
    elif action == "potion":
        potion_type = data[2]
        if potion_type == "health":
            if battle.player.mana < BattleConfig.HEALTH_POTION_COST:
                await query.answer("❌ Not enough mana!", show_alert=True)
                return
            battle.player.mana -= BattleConfig.HEALTH_POTION_COST
            heal = min(BattleConfig.HEALTH_POTION_HEAL, battle.player.max_hp - battle.player.hp)
            battle.player.hp += heal
            battle.add_log(f"💚 Healed {heal} HP!")
            message = f"💚 Healed <b>{heal}</b> HP!"
            # Enemy turn
            enemy_msg = await enemy_turn(battle)
            message += f"\n{enemy_msg}"
        else:  # mana
            restore = min(BattleConfig.MANA_POTION_RESTORE, battle.player.max_mana - battle.player.mana)
            battle.player.mana += restore
            battle.add_log(f"💙 Restored {restore} mana!")
            message = f"💙 Restored <b>{restore}</b> mana!"
            # Enemy turn
            enemy_msg = await enemy_turn(battle)
            message += f"\n{enemy_msg}"
    
    elif action == "forfeit":
        battle_state.end_battle(user_id)
        await query.message.edit_text(
            "🏳️ You forfeited the battle!",
            parse_mode="HTML"
        )
        return
    
    # Check battle end
    over, won = battle.is_over()
    
    if over:
        battle_state.end_battle(user_id)
        
        if won:
            # Award rewards
            await user_collection.update_one(
                {'id': user_id},
                {
                    '$inc': {
                        'balance': battle.enemy.reward_coins,
                        'tokens': battle.enemy.reward_tokens
                    }
                }
            )
            
            result_msg = f"""
<b>🎉 VICTORY! 🎉</b>

You defeated <b>{battle.enemy.name}</b>!

<b>Rewards:</b>
💰 Coins: +{battle.enemy.reward_coins}
🎫 Tokens: +{battle.enemy.reward_tokens}

{message}
"""
        else:
            result_msg = f"""
<b>💀 DEFEATED 💀</b>

You were defeated by <b>{battle.enemy.name}</b>!

{message}

Better luck next time!
"""
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 New Battle", callback_data=f"rpg:start:{user_id}")]
        ])
        
        await query.message.edit_text(result_msg, reply_markup=keyboard, parse_mode="HTML")
    else:
        # Update battle status
        status = format_battle_status(battle)
        if message:
            status += f"\n\n<b>⚡ Action:</b>\n{message}"
        
        keyboard = create_battle_keyboard(user_id, battle)
        
        # If video, send it first then update message
        if video_url:
            try:
                await query.message.reply_video(
                    video=video_url,
                    caption=f"{'🔥 Fire Attack!' if 'fire' in video_url else '❄️ Ice Attack!'}",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error sending video: {e}")
        
        await query.message.edit_text(
            status,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

async def rpg_status(update: Update, context: CallbackContext):
    """Check current battle status"""
    user_id = update.effective_user.id
    battle = battle_state.get_battle(user_id)
    
    if not battle:
        await update.message.reply_text(
            "❌ You're not in a battle!\n\nStart one with: <code>/rpg [easy|normal|hard]</code>",
            parse_mode="HTML"
        )
        return
    
    status = format_battle_status(battle)
    keyboard = create_battle_keyboard(user_id, battle)
    
    await update.message.reply_text(
        status,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Register handlers
application.add_handler(CommandHandler("rpg", rpg_start))
application.add_handler(CommandHandler("battle", rpg_start))
application.add_handler(CommandHandler("bstatus", rpg_status))
application.add_handler(CallbackQueryHandler(rpg_callback, pattern="^rpg:"))

logger.info("🎮 RPG Battle System loaded successfully!")