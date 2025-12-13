import asyncio
import random
import time
import logging
import json
from typing import List, Dict, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext, ContextTypes
from telegram.error import TelegramError
from shivu import application, user_collection, collection
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AI Assistant Configuration
AI_ENABLED = True  # Set to False to disable AI features
AI_SUGGESTIONS_ENABLED = True  # AI fusion suggestions
AI_MARKET_ANALYSIS = True  # AI market trend analysis
AI_PREDICTION_MODEL = True  # AI success prediction

class FusionAI:
    """AI Assistant for fusion management and predictions"""
    
    @staticmethod
    def analyze_fusion_potential(r1: str, r2: str, user_history: Dict) -> Dict:
        """Analyze fusion combination and provide AI insights"""
        r1_norm = norm_rarity(r1)
        r2_norm = norm_rarity(r2)
        
        # Check if it's a special combination
        combo_key = tuple(sorted([r1_norm, r2_norm]))
        is_special = combo_key in SPECIAL_FUSIONS
        
        # Calculate base success rate
        stones = 0
        pity = user_history.get('fusion_pity', 0)
        base_rate = calc_rate(r1_norm, r2_norm, stones, pity)
        
        # Get expected outcomes
        expected_outcomes = FusionAI.get_expected_outcomes(r1_norm, r2_norm)
        
        # AI recommendation
        recommendation = FusionAI.get_recommendation(r1_norm, r2_norm, base_rate, user_history)
        
        # Calculate investment value
        cost = calc_cost(r1_norm, r2_norm)
        value_score = FusionAI.calculate_value_score(expected_outcomes, cost)
        
        return {
            'is_special_combo': is_special,
            'base_success_rate': base_rate,
            'expected_outcomes': expected_outcomes,
            'recommendation': recommendation,
            'value_score': value_score,
            'cost': cost,
            'suggested_stones': FusionAI.suggest_stone_count(base_rate, cost),
            'risk_level': FusionAI.get_risk_level(base_rate, cost)
        }
    
    @staticmethod
    def get_expected_outcomes(r1: str, r2: str) -> List[Tuple[str, float]]:
        """Get expected outcome distribution"""
        combo_key = tuple(sorted([r1, r2]))
        
        if combo_key in SPECIAL_FUSIONS:
            return SPECIAL_FUSIONS[combo_key]
        
        # Simulate multiple outcomes
        tier1 = get_tier(r1)
        tier2 = get_tier(r2)
        max_tier = max(tier1, tier2)
        
        outcomes = {}
        for _ in range(100):
            result = get_result_rarity(r1, r2)
            outcomes[result] = outcomes.get(result, 0) + 1
        
        # Convert to percentages and sort
        total = sum(outcomes.values())
        result_list = [(rarity, count/total) for rarity, count in outcomes.items()]
        result_list.sort(key=lambda x: x[1], reverse=True)
        
        return result_list[:5]  # Top 5 outcomes
    
    @staticmethod
    def get_recommendation(r1: str, r2: str, success_rate: float, user_history: Dict) -> str:
        """Get AI recommendation for the fusion"""
        combo_key = tuple(sorted([r1, r2]))
        tier1 = get_tier(r1)
        tier2 = get_tier(r2)
        
        # Check for special combinations
        if combo_key in SPECIAL_FUSIONS:
            outcomes = SPECIAL_FUSIONS[combo_key]
            top_outcome = outcomes[0]
            
            if top_outcome[1] >= 0.50 and top_outcome[0] in ["🏵 Mythic", "🎐 Celestial"]:
                return f"🌟 EXCELLENT! This combo has {top_outcome[1]*100:.0f}% chance for {top_outcome[0]}!"
            elif top_outcome[1] >= 0.40:
                return f"✨ GREAT! High chance ({top_outcome[1]*100:.0f}%) for {top_outcome[0]}"
            else:
                return f"👍 GOOD! Best outcome: {top_outcome[0]} ({top_outcome[1]*100:.0f}%)"
        
        # Seasonal opposites
        r1_cat = get_rarity_categories(r1)
        r2_cat = get_rarity_categories(r2)
        
        if 'seasonal' in r1_cat and 'seasonal' in r2_cat and r1 != r2:
            return "🔥 HOT COMBO! Opposite seasons = High Mythic chance!"
        
        if 'holiday' in r1_cat and 'holiday' in r2_cat and r1 != r2:
            return "🎉 FESTIVE POWER! Holiday fusion = Celestial/Mythic boost!"
        
        # High tier combination
        if tier1 >= 6 and tier2 >= 6:
            return "💎 PREMIUM FUSION! Two high-tier = Excellent results!"
        
        # Success rate based
        if success_rate >= 0.70:
            return "✅ HIGH SUCCESS! Very safe fusion"
        elif success_rate >= 0.50:
            return "⚖️ BALANCED! Moderate risk, good reward"
        elif success_rate >= 0.30:
            return "⚠️ RISKY! Consider using fusion stones"
        else:
            return "🚨 HIGH RISK! Use 2-3 stones recommended"
    
    @staticmethod
    def calculate_value_score(outcomes: List[Tuple[str, float]], cost: int) -> float:
        """Calculate investment value score (0-100)"""
        # Weight outcomes by tier and probability
        total_value = 0
        for rarity, chance in outcomes:
            tier = get_tier(rarity)
            # Higher tiers are exponentially more valuable
            tier_value = tier ** 2.5
            total_value += tier_value * chance
        
        # Normalize against cost
        cost_factor = min(cost / 1000, 10)
        score = (total_value / cost_factor) * 10
        
        return min(max(score, 0), 100)
    
    @staticmethod
    def suggest_stone_count(success_rate: float, cost: int) -> int:
        """AI suggests optimal stone count"""
        if success_rate >= 0.70:
            return 0  # No stones needed
        elif success_rate >= 0.50:
            return 1  # Just a small boost
        elif success_rate >= 0.35:
            return 2  # Moderate boost needed
        else:
            return 3  # Maximum boost recommended
    
    @staticmethod
    def get_risk_level(success_rate: float, cost: int) -> str:
        """Determine risk level with emoji"""
        if success_rate >= 0.70:
            return "🟢 LOW RISK"
        elif success_rate >= 0.50:
            return "🟡 MEDIUM RISK"
        elif success_rate >= 0.35:
            return "🟠 HIGH RISK"
        else:
            return "🔴 VERY HIGH RISK"
    
    @staticmethod
    def get_best_fusions(characters: List[Dict], user_history: Dict, limit: int = 5) -> List[Dict]:
        """AI analyzes all possible fusions and returns best options"""
        if len(characters) < 2:
            return []
        
        fusion_scores = []
        
        # Analyze all possible pairs
        for i in range(len(characters)):
            for j in range(i + 1, len(characters)):
                c1 = characters[i]
                c2 = characters[j]
                
                r1 = norm_rarity(c1.get('rarity'))
                r2 = norm_rarity(c2.get('rarity'))
                
                analysis = FusionAI.analyze_fusion_potential(r1, r2, user_history)
                
                fusion_scores.append({
                    'char1': c1,
                    'char2': c2,
                    'analysis': analysis,
                    'score': analysis['value_score']
                })
        
        # Sort by score and return top options
        fusion_scores.sort(key=lambda x: x['score'], reverse=True)
        return fusion_scores[:limit]
    
    @staticmethod
    def predict_success_with_stones(r1: str, r2: str, stones: int, pity: int) -> Dict:
        """Predict success rate with different stone counts"""
        predictions = {}
        
        for stone_count in range(0, 4):
            rate = calc_rate(r1, r2, stone_count, pity)
            predictions[stone_count] = {
                'rate': rate,
                'cost_increase': stone_count * 100,  # Stones cost 100 each
                'efficiency': rate / (1 + stone_count * 0.1)  # Rate vs cost efficiency
            }
        
        return predictions

RARITY_MAP = {
    "common": "🟢 Common", "rare": "🟣 Rare", "legendary": "🟡 Legendary",
    "special": "💮 Special Edition", "neon": "💫 Neon", "manga": "✨ Manga",
    "cosplay": "🎭 Cosplay", "celestial": "🎐 Celestial", "premium": "🔮 Premium Edition",
    "erotic": "💋 Erotic", "summer": "🌤 Summer", "winter": "☃️ Winter",
    "monsoon": "☔️ Monsoon", "valentine": "💝 Valentine", "halloween": "🎃 Halloween",
    "christmas": "🎄 Christmas", "mythic": "🏵 Mythic",
    "amv": "🎥 AMV", "tiny": "👼 Tiny"
}

TIERS = {
    "🟢 Common": 1, "🟣 Rare": 2, "🟡 Legendary": 3, "💮 Special Edition": 4,
    "💫 Neon": 5, "✨ Manga": 5, "🎭 Cosplay": 5, "🎐 Celestial": 6,
    "🔮 Premium Edition": 6, "💋 Erotic": 6, "🌤 Summer": 4, "☃️ Winter": 4,
    "☔️ Monsoon": 4, "💝 Valentine": 5, "🎃 Halloween": 5, "🎄 Christmas": 5,
    "🏵 Mythic": 7, "🎥 AMV": 5, "👼 Tiny": 4
}

# Categorize rarities
SEASONAL_RARITIES = {"🌤 Summer", "☃️ Winter", "☔️ Monsoon"}
HOLIDAY_RARITIES = {"💝 Valentine", "🎃 Halloween", "🎄 Christmas"}
SPECIAL_RARITIES = {"💮 Special Edition", "💫 Neon", "✨ Manga", "🎭 Cosplay", "🎐 Celestial", "🔮 Premium Edition", "💋 Erotic"}
CREATIVE_RARITIES = {"🎥 AMV", "👼 Tiny"}
BASE_RARITIES = {"🟢 Common", "🟣 Rare", "🟡 Legendary"}
ULTIMATE_RARITIES = {"🏵 Mythic"}

# Special fusion combinations with chances
SPECIAL_FUSIONS = {
    # Seasonal opposites create powerful results
    ("🌤 Summer", "☃️ Winter"): [
        (0.40, "🏵 Mythic"),  # Opposite seasons = Mythic
        (0.30, "🎐 Celestial"),  # Balance of hot/cold
        (0.20, "💫 Neon"),
        (0.10, "🟡 Legendary")
    ],
    ("🌤 Summer", "☔️ Monsoon"): [
        (0.35, "🎐 Celestial"),  # Water + Heat = Steam/Sky
        (0.30, "💫 Neon"),
        (0.25, "🔮 Premium Edition"),
        (0.10, "🟡 Legendary")
    ],
    ("☃️ Winter", "☔️ Monsoon"): [
        (0.40, "🎐 Celestial"),  # Cold + Water = Ice/Snow power
        (0.30, "💫 Neon"),
        (0.20, "💮 Special Edition"),
        (0.10, "🟣 Rare")
    ],
    
    # Same seasons amplify
    ("🌤 Summer", "🌤 Summer"): [
        (0.50, "🔮 Premium Edition"),  # Double heat
        (0.30, "💫 Neon"),
        (0.15, "🎐 Celestial"),
        (0.05, "🏵 Mythic")
    ],
    ("☃️ Winter", "☃️ Winter"): [
        (0.50, "🔮 Premium Edition"),  # Double cold
        (0.30, "💫 Neon"),
        (0.15, "🎐 Celestial"),
        (0.05, "🏵 Mythic")
    ],
    ("☔️ Monsoon", "☔️ Monsoon"): [
        (0.50, "🎐 Celestial"),  # Double water
        (0.30, "💫 Neon"),
        (0.15, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    
    # Holiday combinations
    ("💝 Valentine", "🎃 Halloween"): [
        (0.45, "🏵 Mythic"),  # Love + Fear = Ultimate
        (0.30, "🎐 Celestial"),
        (0.20, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    ("💝 Valentine", "🎄 Christmas"): [
        (0.40, "🎐 Celestial"),  # Love + Joy = Heaven
        (0.35, "💫 Neon"),
        (0.20, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    ("🎃 Halloween", "🎄 Christmas"): [
        (0.40, "🏵 Mythic"),  # Spooky + Jolly = Chaos
        (0.30, "🎐 Celestial"),
        (0.25, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    
    # Holiday + Seasonal
    ("💝 Valentine", "🌤 Summer"): [
        (0.45, "💫 Neon"),  # Hot love
        (0.30, "🔮 Premium Edition"),
        (0.20, "🎐 Celestial"),
        (0.05, "🏵 Mythic")
    ],
    ("💝 Valentine", "☃️ Winter"): [
        (0.40, "🎐 Celestial"),  # Cold love = Eternal
        (0.35, "💫 Neon"),
        (0.20, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    ("🎃 Halloween", "☃️ Winter"): [
        (0.45, "🏵 Mythic"),  # Spooky cold = Ultimate fear
        (0.30, "🎐 Celestial"),
        (0.20, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    ("🎃 Halloween", "☔️ Monsoon"): [
        (0.40, "🎐 Celestial"),  # Dark water
        (0.35, "💫 Neon"),
        (0.20, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    ("🎄 Christmas", "☃️ Winter"): [
        (0.50, "🏵 Mythic"),  # Perfect match!
        (0.30, "🎐 Celestial"),
        (0.15, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    
    # Creative combinations
    ("🎥 AMV", "✨ Manga"): [
        (0.50, "🎐 Celestial"),  # Animation + Art
        (0.30, "💫 Neon"),
        (0.15, "🏵 Mythic"),
        (0.05, "🔮 Premium Edition")
    ],
    ("🎥 AMV", "🎭 Cosplay"): [
        (0.45, "💫 Neon"),  # Video + Performance
        (0.35, "🎐 Celestial"),
        (0.15, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    ("✨ Manga", "🎭 Cosplay"): [
        (0.45, "💫 Neon"),  # Art + Performance
        (0.30, "🎐 Celestial"),
        (0.20, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    ("👼 Tiny", "🏵 Mythic"): [
        (0.60, "🏵 Mythic"),  # Tiny power = Still mythic
        (0.25, "🎐 Celestial"),
        (0.10, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    
    # Erotic combinations
    ("💋 Erotic", "💝 Valentine"): [
        (0.55, "🏵 Mythic"),  # Passion + Love = Ultimate
        (0.25, "🎐 Celestial"),
        (0.15, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    ("💋 Erotic", "🌤 Summer"): [
        (0.50, "🎐 Celestial"),  # Hot passion
        (0.30, "💫 Neon"),
        (0.15, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    ("💋 Erotic", "☃️ Winter"): [
        (0.45, "🎐 Celestial"),  # Contrast
        (0.30, "💫 Neon"),
        (0.20, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    
    # Neon combinations
    ("💫 Neon", "💫 Neon"): [
        (0.55, "🎐 Celestial"),  # Double glow
        (0.25, "🏵 Mythic"),
        (0.15, "🔮 Premium Edition"),
        (0.05, "💫 Neon")
    ],
    ("💫 Neon", "🎭 Cosplay"): [
        (0.45, "🎐 Celestial"),  # Glow + Performance
        (0.30, "🔮 Premium Edition"),
        (0.20, "🏵 Mythic"),
        (0.05, "💫 Neon")
    ],
    
    # Premium combinations
    ("🔮 Premium Edition", "🔮 Premium Edition"): [
        (0.60, "🏵 Mythic"),  # Double premium
        (0.25, "🎐 Celestial"),
        (0.10, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    ("🔮 Premium Edition", "💫 Neon"): [
        (0.50, "🏵 Mythic"),
        (0.30, "🎐 Celestial"),
        (0.15, "💫 Neon"),
        (0.05, "🔮 Premium Edition")
    ],
    
    # Celestial combinations
    ("🎐 Celestial", "🎐 Celestial"): [
        (0.70, "🏵 Mythic"),  # Double heaven
        (0.20, "🎐 Celestial"),
        (0.08, "💫 Neon"),
        (0.02, "🔮 Premium Edition")
    ],
    ("🎐 Celestial", "💫 Neon"): [
        (0.55, "🏵 Mythic"),
        (0.30, "🎐 Celestial"),
        (0.12, "💫 Neon"),
        (0.03, "🔮 Premium Edition")
    ],
    ("🎐 Celestial", "🔮 Premium Edition"): [
        (0.60, "🏵 Mythic"),
        (0.25, "🎐 Celestial"),
        (0.12, "💫 Neon"),
        (0.03, "🔮 Premium Edition")
    ],
    
    # Mythic combinations (stays mythic or slight downgrades)
    ("🏵 Mythic", "🏵 Mythic"): [
        (0.95, "🏵 Mythic"),  # Almost guaranteed
        (0.04, "🎐 Celestial"),
        (0.01, "💫 Neon")
    ],
    ("🏵 Mythic", "🎐 Celestial"): [
        (0.80, "🏵 Mythic"),
        (0.15, "🎐 Celestial"),
        (0.05, "💫 Neon")
    ],
    
    # Base rarity progressions
    ("🟡 Legendary", "🟡 Legendary"): [
        (0.70, "💮 Special Edition"),
        (0.20, "🟡 Legendary"),
        (0.08, "💫 Neon"),
        (0.02, "🎐 Celestial")
    ],
    ("💮 Special Edition", "💮 Special Edition"): [
        (0.70, "💫 Neon"),
        (0.20, "💮 Special Edition"),
        (0.08, "🎐 Celestial"),
        (0.02, "🏵 Mythic")
    ],
    
    # Cross-category powerful combos
    ("🏵 Mythic", "💝 Valentine"): [
        (0.85, "🏵 Mythic"),  # Love at max level
        (0.10, "🎐 Celestial"),
        (0.05, "💫 Neon")
    ],
    ("🏵 Mythic", "🌤 Summer"): [
        (0.80, "🏵 Mythic"),
        (0.12, "🎐 Celestial"),
        (0.08, "💫 Neon")
    ],
    ("🏵 Mythic", "☃️ Winter"): [
        (0.80, "🏵 Mythic"),
        (0.12, "🎐 Celestial"),
        (0.08, "💫 Neon")
    ],
    
    # Tiny special cases
    ("👼 Tiny", "👼 Tiny"): [
        (0.50, "💮 Special Edition"),  # Tiny power doubles
        (0.30, "💫 Neon"),
        (0.15, "🎐 Celestial"),
        (0.05, "🏵 Mythic")
    ],
    ("👼 Tiny", "💫 Neon"): [
        (0.45, "🎐 Celestial"),  # Tiny glow
        (0.35, "💫 Neon"),
        (0.15, "🔮 Premium Edition"),
        (0.05, "🏵 Mythic")
    ],
    
    # Common combos for progression
    ("🟢 Common", "🟢 Common"): [
        (0.60, "🟢 Common"),
        (0.30, "🟣 Rare"),
        (0.08, "🟡 Legendary"),
        (0.02, "💮 Special Edition")
    ],
    ("🟣 Rare", "🟣 Rare"): [
        (0.50, "🟣 Rare"),
        (0.35, "🟡 Legendary"),
        (0.12, "💮 Special Edition"),
        (0.03, "💫 Neon")
    ],
    ("🟢 Common", "🟣 Rare"): [
        (0.55, "🟣 Rare"),
        (0.30, "🟡 Legendary"),
        (0.12, "🟢 Common"),
        (0.03, "💮 Special Edition")
    ],
    ("🟣 Rare", "🟡 Legendary"): [
        (0.45, "🟡 Legendary"),
        (0.35, "💮 Special Edition"),
        (0.15, "🟣 Rare"),
        (0.05, "💫 Neon")
    ],
    ("🟢 Common", "🟡 Legendary"): [
        (0.50, "🟣 Rare"),
        (0.30, "🟡 Legendary"),
        (0.15, "🟢 Common"),
        (0.05, "💮 Special Edition")
    ]
}

COSTS = {1: 500, 2: 1000, 3: 2000, 4: 3500, 5: 5000, 6: 7500, 7: 10000}
BASE_RATES = {0: 0.70, 1: 0.55, 2: 0.40, 3: 0.30}
STONE_BOOST = 0.15
COOLDOWN = 1800
SESSION_EXPIRE = 300
CHARS_PER_PAGE = 8

sessions = {}

def norm_rarity(r: str) -> str:
    if r in TIERS:
        return r
    return RARITY_MAP.get(r.lower().replace(" ", ""), "🟢 Common")

def get_tier(r: str) -> int:
    return TIERS.get(norm_rarity(r), 1)

def calc_cost(r1: str, r2: str) -> int:
    avg = (get_tier(r1) + get_tier(r2)) // 2
    return COSTS.get(avg, 1000)

def calc_rate(r1: str, r2: str, stones: int, pity: int) -> float:
    diff = abs(get_tier(r1) - get_tier(r2))
    base = BASE_RATES.get(min(diff, 3), 0.30)
    stone_bonus = min(stones, 3) * STONE_BOOST
    pity_bonus = min(pity, 5) * 0.05
    return min(base + stone_bonus + pity_bonus, 0.95)

def get_result_rarity(r1: str, r2: str) -> str:
    """
    Advanced fusion system with 1000+ logical possibilities
    Checks special combinations first, then falls back to tier-based logic
    """
    
    # Normalize inputs
    r1_norm = norm_rarity(r1)
    r2_norm = norm_rarity(r2)
    
    # Create sorted tuple for lookup (order doesn't matter)
    combo_key = tuple(sorted([r1_norm, r2_norm]))
    
    # Check for special predefined combinations
    if combo_key in SPECIAL_FUSIONS:
        outcomes = SPECIAL_FUSIONS[combo_key]
        roll = random.random()
        cumulative = 0.0
        
        for chance, rarity in outcomes:
            cumulative += chance
            if roll <= cumulative:
                return rarity
    
    # If no special combo found, check for reverse order (shouldn't happen with sorted, but safety)
    reverse_key = (combo_key[1], combo_key[0])
    if reverse_key in SPECIAL_FUSIONS:
        outcomes = SPECIAL_FUSIONS[reverse_key]
        roll = random.random()
        cumulative = 0.0
        
        for chance, rarity in outcomes:
            cumulative += chance
            if roll <= cumulative:
                return rarity
    
    # Category-based special logic for undefined combinations
    r1_categories = get_rarity_categories(r1_norm)
    r2_categories = get_rarity_categories(r2_norm)
    
    # Cross-seasonal fusion (not predefined)
    if 'seasonal' in r1_categories and 'seasonal' in r2_categories and r1_norm != r2_norm:
        # Different seasons have high chance for celestial/mythic
        roll = random.random()
        if roll < 0.35:
            return "🏵 Mythic"
        elif roll < 0.65:
            return "🎐 Celestial"
        elif roll < 0.85:
            return "💫 Neon"
        else:
            return "🔮 Premium Edition"
    
    # Holiday + Seasonal (not predefined)
    if 'holiday' in r1_categories and 'seasonal' in r2_categories:
        roll = random.random()
        if roll < 0.40:
            return "🎐 Celestial"
        elif roll < 0.70:
            return "💫 Neon"
        elif roll < 0.90:
            return "🔮 Premium Edition"
        else:
            return "🏵 Mythic"
    
    # Two different holidays (not predefined)
    if 'holiday' in r1_categories and 'holiday' in r2_categories and r1_norm != r2_norm:
        roll = random.random()
        if roll < 0.45:
            return "🏵 Mythic"
        elif roll < 0.75:
            return "🎐 Celestial"
        elif roll < 0.95:
            return "💫 Neon"
        else:
            return "🔮 Premium Edition"
    
    # Creative + Special (not predefined)
    if 'creative' in r1_categories and 'special' in r2_categories:
        roll = random.random()
        if roll < 0.45:
            return "🎐 Celestial"
        elif roll < 0.75:
            return "💫 Neon"
        elif roll < 0.90:
            return "🔮 Premium Edition"
        else:
            return "🏵 Mythic"
    
    # Ultimate + anything (not predefined)
    if 'ultimate' in r1_categories or 'ultimate' in r2_categories:
        roll = random.random()
        if roll < 0.75:
            return "🏵 Mythic"
        elif roll < 0.90:
            return "🎐 Celestial"
        else:
            return "💫 Neon"
    
    # High tier special rarities together
    if 'special' in r1_categories and 'special' in r2_categories:
        tier1 = get_tier(r1_norm)
        tier2 = get_tier(r2_norm)
        avg_tier = (tier1 + tier2) / 2
        
        if avg_tier >= 6:  # Both high tier
            roll = random.random()
            if roll < 0.50:
                return "🏵 Mythic"
            elif roll < 0.80:
                return "🎐 Celestial"
            else:
                return "💫 Neon"
    
    # Random luck - 5% chance for completely random high-tier rarity
    if random.random() < 0.05:
        lucky_pool = ["🏵 Mythic", "🎐 Celestial", "💫 Neon", "🔮 Premium Edition", "💋 Erotic"]
        return random.choice(lucky_pool)
    
    # Fallback to tier-based system for standard combinations
    tier1 = get_tier(r1_norm)
    tier2 = get_tier(r2_norm)
    max_tier = max(tier1, tier2)
    min_tier = min(tier1, tier2)
    
    # If tiers are very different, bias towards middle
    tier_diff = abs(tier1 - tier2)
    
    if tier_diff >= 3:  # Large gap
        roll = random.random()
        if roll < 0.50:
            result_tier = (tier1 + tier2) // 2
        elif roll < 0.80:
            result_tier = max_tier
        else:
            result_tier = min(max_tier + 1, 7)
    else:  # Normal tier progression
        roll = random.random()
        if roll < 0.50:
            result_tier = max_tier
        elif roll < 0.80:
            result_tier = min(max_tier + 1, 7)
        else:
            result_tier = min(max_tier + 2, 7)
    
    # Get all rarities of result tier
    candidates = [r for r, t in TIERS.items() if t == result_tier]
    
    if not candidates:
        return "🏵 Mythic"
    
    # Weight candidates based on categories
    weighted_candidates = []
    for candidate in candidates:
        weight = 1
        cand_categories = get_rarity_categories(candidate)
        
        # If input rarities share category with candidate, increase weight
        if any(cat in cand_categories for cat in r1_categories):
            weight += 2
        if any(cat in cand_categories for cat in r2_categories):
            weight += 2
        
        weighted_candidates.extend([candidate] * weight)
    
    return random.choice(weighted_candidates) if weighted_candidates else random.choice(candidates)


def get_rarity_categories(rarity: str) -> set:
    """Return which categories a rarity belongs to"""
    categories = set()
    
    if rarity in SEASONAL_RARITIES:
        categories.add('seasonal')
    if rarity in HOLIDAY_RARITIES:
        categories.add('holiday')
    if rarity in SPECIAL_RARITIES:
        categories.add('special')
    if rarity in CREATIVE_RARITIES:
        categories.add('creative')
    if rarity in BASE_RARITIES:
        categories.add('base')
    if rarity in ULTIMATE_RARITIES:
        categories.add('ultimate')
    
    return categories

async def check_cooldown(uid: int) -> Tuple[bool, int]:
    try:
        user = await user_collection.find_one({'id': uid}, {'last_fusion': 1})
        if user and 'last_fusion' in user:
            elapsed = time.time() - user['last_fusion']
            if elapsed < COOLDOWN:
                return False, int(COOLDOWN - elapsed)
        return True, 0
    except Exception as e:
        logger.error(f"Cooldown check error: {e}")
        return True, 0

async def set_cooldown(uid: int):
    try:
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'last_fusion': time.time()}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Set cooldown error: {e}")

async def get_user_safe(uid: int) -> Dict:
    try:
        user = await user_collection.find_one({'id': uid})
        return user or {}
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return {}

async def atomic_balance_deduct(uid: int, amount: int) -> bool:
    try:
        result = await user_collection.update_one(
            {'id': uid, 'balance': {'$gte': amount}},
            {'$inc': {'balance': -amount}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Balance deduct error: {e}")
        return False

async def atomic_stone_use(uid: int, amount: int) -> bool:
    try:
        result = await user_collection.update_one(
            {'id': uid, 'fusion_stones': {'$gte': amount}},
            {'$inc': {'fusion_stones': -amount}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Stone use error: {e}")
        return False

async def atomic_char_swap(uid: int, remove_ids: List[str], add_char: Dict) -> bool:
    try:
        user = await user_collection.find_one({'id': uid})
        if not user:
            return False
        
        chars = user.get('characters', [])
        new_chars = []
        removed_count = 0
        
        for c in chars:
            if c.get('id') in remove_ids and removed_count < len(remove_ids):
                removed_count += 1
                continue
            new_chars.append(c)
        
        if removed_count != len(remove_ids):
            return False
        
        new_chars.append(add_char)
        
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'characters': new_chars}}
        )
        return True
    except Exception as e:
        logger.error(f"Char swap error: {e}")
        return False

async def atomic_char_remove(uid: int, remove_ids: List[str]) -> bool:
    try:
        user = await user_collection.find_one({'id': uid})
        if not user:
            return False
        
        chars = user.get('characters', [])
        new_chars = []
        removed_count = 0
        
        for c in chars:
            if c.get('id') in remove_ids and removed_count < len(remove_ids):
                removed_count += 1
                continue
            new_chars.append(c)
        
        if removed_count != len(remove_ids):
            return False
        
        await user_collection.update_one(
            {'id': uid},
            {'$set': {'characters': new_chars}}
        )
        return True
    except Exception as e:
        logger.error(f"Char remove error: {e}")
        return False

async def log_fusion(uid: int, c1_name: str, c2_name: str, success: bool, result_name: str = None):
    try:
        entry = {
            'time': time.time(),
            'c1': c1_name,
            'c2': c2_name,
            'success': success,
            'result': result_name or 'failed'
        }
        
        await user_collection.update_one(
            {'id': uid},
            {
                '$push': {
                    'fusion_history': {
                        '$each': [entry],
                        '$slice': -20
                    }
                },
                '$inc': {
                    'fusion_total': 1,
                    'fusion_success': 1 if success else 0,
                    'fusion_pity': 0 if success else 1
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"Log fusion error: {e}")

def cleanup_sessions():
    now = time.time()
    expired = [k for k, v in sessions.items() if now - v.get('created', now) > SESSION_EXPIRE]
    for k in expired:
        del sessions[k]

async def fuse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        
        can_use, remaining = await check_cooldown(uid)
        if not can_use:
            await update.message.reply_text(
                f"⏱️ cooldown active\nwait {remaining//60}m {remaining%60}s"
            )
            return
        
        user = await get_user_safe(uid)
        chars = user.get('characters', [])
        
        if len(chars) < 2:
            await update.message.reply_text("❌ need at least 2 characters\nuse /grab")
            return
        
        cleanup_sessions()
        
        page = 0
        sessions[uid] = {
            'step': 1,
            'owner': uid,
            'page': page,
            'created': time.time()
        }
        
        await show_char_page(update.message, uid, chars, page, 1, context)
        
    except Exception as e:
        logger.error(f"Fuse cmd error: {e}")
        await update.message.reply_text("⚠️ error occurred")

async def show_char_page(message, uid: int, chars: List[Dict], page: int, step: int, context: ContextTypes.DEFAULT_TYPE, is_edit: bool = False):
    try:
        start = page * CHARS_PER_PAGE
        end = start + CHARS_PER_PAGE
        page_chars = chars[start:end]
        
        if not page_chars:
            text = "❌ no characters on this page"
            if is_edit:
                try:
                    await message.edit_text(text)
                except Exception:
                    await message.reply_text(text)
            else:
                await message.reply_text(text)
            return
        
        buttons = []
        for c in page_chars:
            char_name = c.get('name', 'unknown')
            # Truncate name to avoid callback_data exceeding 64 bytes
            display_name = char_name[:10] if len(char_name) > 10 else char_name
            char_id = str(c.get('id', ''))[:20]  # Ensure ID isn't too long
            
            buttons.append([InlineKeyboardButton(
                f"{norm_rarity(c.get('rarity', 'common'))} {display_name}",
                callback_data=f"fs{step}_{char_id}"
            )])
        
        nav_btns = []
        if page > 0:
            nav_btns.append(InlineKeyboardButton("◀️ prev", callback_data=f"fp{step}_{page-1}"))
        if end < len(chars):
            nav_btns.append(InlineKeyboardButton("next ▶️", callback_data=f"fp{step}_{page+1}"))
        
        if nav_btns:
            buttons.append(nav_btns)
        
        buttons.append([InlineKeyboardButton("❌ cancel", callback_data="fc")])
        
        text = f"⚗️ select character {step}/2\npage {page+1}/{(len(chars)-1)//CHARS_PER_PAGE+1}"
        
        if is_edit:
            try:
                await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except TelegramError as te:
                error_str = str(te).lower()
                if "message can't be edited" in error_str or "message is not modified" in error_str:
                    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
                else:
                    logger.error(f"Edit error: {te}")
                    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Show char page error: {e}")
        try:
            text = f"⚗️ select character {step}/2"
            cancel_button = InlineKeyboardMarkup([[InlineKeyboardButton("❌ cancel", callback_data="fc")]])
            if is_edit:
                await message.edit_text(text, reply_markup=cancel_button)
            else:
                await message.reply_text(text, reply_markup=cancel_button)
        except Exception as inner_e:
            logger.error(f"Fallback error: {inner_e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    
    try:
        if data == "fc":
            sessions.pop(uid, None)
            await query.answer()
            try:
                await query.edit_message_text("❌ cancelled")
            except Exception:
                await query.message.reply_text("❌ cancelled")
            return
        
        # Shop and buy actions don't need active session
        if data == "fshop" or data.startswith("fb_"):
            await query.answer()
            # Continue to shop/buy handlers below
        else:
            # Other actions need session validation
            session = sessions.get(uid)
            if not session or session.get('owner') != uid:
                await query.answer("❌ not your session", show_alert=True)
                return
            await query.answer()
        
        if data.startswith("fp"):
            parts = data[2:].split('_')
            if len(parts) < 2:
                await query.answer("❌ invalid data", show_alert=True)
                return
            
            session = sessions.get(uid)
            step = int(parts[0])
            page = int(parts[1])
            
            session['page'] = page
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            
            await show_char_page(query.message, uid, chars, page, step, context, is_edit=True)
            return
        
        if data.startswith("fs1_"):
            cid = data[4:]
            session = sessions.get(uid)
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            char1 = next((c for c in chars if str(c.get('id')) == cid), None)
            
            if not char1:
                await query.edit_message_text("❌ character not found")
                sessions.pop(uid, None)
                return
            
            sessions[uid].update({
                'step': 2,
                'c1': cid,
                'c1_data': char1,
                'stones': 0,
                'page': 0
            })
            
            # Don't delete, just edit or send new message
            try:
                await query.edit_message_text(
                    f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                )
                msg = query.message
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")
                # Send new message with character 1 media
                try:
                    media_url = char1.get('img_url', '')
                    # Check if AMV (video)
                    if char1.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                        msg = await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=media_url,
                            caption=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                        )
                    else:
                        msg = await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=media_url,
                            caption=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                        )
                except Exception as e2:
                    logger.warning(f"Could not send media: {e2}")
                    msg = await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ {norm_rarity(char1.get('rarity'))} {char1.get('name')}\n\nselecting second character..."
                    )
            
            await asyncio.sleep(0.5)
            await show_char_page(msg, uid, chars, 0, 2, context, is_edit=False)
            return
        
        if data.startswith("fs2_"):
            cid = data[4:]
            session = sessions.get(uid)
            user = await get_user_safe(uid)
            chars = user.get('characters', [])
            char2 = next((c for c in chars if str(c.get('id')) == cid), None)
            
            if not char2:
                await query.edit_message_text("❌ character not found")
                sessions.pop(uid, None)
                return
            
            # Check if user selected the same character
            if cid == session.get('c1'):
                await query.answer("❌ cannot select the same character", show_alert=True)
                return
            
            session['c2'] = cid
            session['c2_data'] = char2
            
            # Edit current message instead of deleting
            try:
                await query.edit_message_text(
                    f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                )
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")
            
            # Send confirmation with character 2 media
            try:
                media_url = char2.get('img_url', '')
                # Check if AMV (video)
                if char2.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=media_url,
                        caption=f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=media_url,
                        caption=f"✅ {norm_rarity(char2.get('rarity'))} {char2.get('name')}\n\npreparing fusion..."
                    )
            except Exception as e:
                logger.warning(f"Could not send media: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"✅ {char2.get('name')}\n\npreparing..."
                )
            
            await asyncio.sleep(0.5)
            # Use context.bot to send confirmation
            await show_confirm(query.message.chat_id, uid, context)
            return
        
        if data.startswith("fst_"):
            stones_str = data[4:]
            if not stones_str.isdigit():
                await query.answer("❌ invalid stone count", show_alert=True)
                return
            
            session = sessions.get(uid)
            stones = int(stones_str)
            user = await get_user_safe(uid)
            user_stones = user.get('fusion_stones', 0)
            
            if user_stones < stones:
                await query.answer(f"❌ need {stones} stones (have {user_stones})", show_alert=True)
                return
            
            session['stones'] = stones
            
            # Just update the message text, don't send new confirmation
            await query.answer(f"✅ Using {stones} stones", show_alert=False)
            
            # Update the existing message with new stone selection
            await update_confirm_message(query, uid, context)
            return
        
        if data == "fconf":
            session = sessions.get(uid)
            await execute_fusion(query, uid, context)
            return
        
        if data == "fshop":
            await show_shop(query, uid)
            return
        
        if data == "fai":
            # Show AI insights
            await show_ai_insights(query, uid, context)
            return
        
        if data == "fback":
            # Go back to fusion confirmation from AI insights
            session = sessions.get(uid)
            if session:
                await show_confirm(query.message.chat_id, uid, context)
            return
        
        if data.startswith("fb_"):
            amount_str = data[3:]
            if not amount_str.isdigit():
                await query.answer("❌ invalid amount", show_alert=True)
                return
            
            amount = int(amount_str)
            prices = {1: 100, 5: 450, 10: 850, 20: 1600}
            cost = prices.get(amount, 0)
            
            if cost == 0:
                await query.answer("❌ invalid purchase", show_alert=True)
                return
            
            if not await atomic_balance_deduct(uid, cost):
                user = await get_user_safe(uid)
                await query.answer(f"❌ need {cost:,} coins (have {user.get('balance', 0):,})", show_alert=True)
                return
            
            await user_collection.update_one(
                {'id': uid},
                {'$inc': {'fusion_stones': amount}},
                upsert=True
            )
            
            await query.answer(f"✅ bought {amount} stones!", show_alert=True)
            await show_shop(query, uid)
            return
            
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        await query.answer("⚠️ error occurred", show_alert=True)

async def update_confirm_message(query, uid: int, context: ContextTypes.DEFAULT_TYPE):
    """Update only the confirmation text without resending images"""
    try:
        session = sessions.get(uid)
        if not session:
            await query.answer("❌ session expired", show_alert=True)
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        if not c1 or not c2:
            await query.answer("❌ character data missing", show_alert=True)
            return
        
        stones = session.get('stones', 0)
        
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        result_r = get_result_rarity(r1, r2)
        cost = calc_cost(r1, r2)
        
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        user_stones = user.get('fusion_stones', 0)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        
        buttons = []
        stone_btns = []
        for i in range(1, 4):
            if user_stones >= i:
                stone_btns.append(InlineKeyboardButton(
                    f"{'✅' if stones == i else '💎'} {i}",
                    callback_data=f"fst_{i}"
                ))
        
        if stone_btns:
            if len(stone_btns) > 1:
                buttons.append(stone_btns[:2])
                if len(stone_btns) > 2:
                    buttons.append([stone_btns[2]])
            else:
                buttons.append(stone_btns)
        
        fuse_text = "✅ fuse" if bal >= cost else "❌ insufficient"
        fuse_callback = "fconf" if bal >= cost else "fc"
        
        buttons.extend([
            [InlineKeyboardButton(fuse_text, callback_data=fuse_callback)],
            [
                InlineKeyboardButton("💎 buy stones", callback_data="fshop"),
                InlineKeyboardButton("❌ cancel", callback_data="fc")
            ]
        ])
        
        pity_text = f' (+{pity*5}% pity)' if pity > 0 else ''
        stone_text = f' (+{stones*15}%)' if stones else ''
        
        caption = (
            f"⚗️ fusion preview\n\n"
            f"1️⃣ {r1} {c1.get('name')}\n"
            f"     ×\n"
            f"2️⃣ {r2} {c2.get('name')}\n"
            f"     ‖\n"
            f"     ⬇️\n"
            f"✨ {result_r}\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"success: {rate*100:.0f}%{pity_text}\n"
            f"cost: {cost:,} 💰\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}{stone_text}"
        )
        
        # Just edit the existing message text and buttons
        try:
            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except TelegramError as e:
            error_str = str(e).lower()
            if "message is not modified" in error_str:
                # Message is the same, just ignore
                pass
            else:
                logger.warning(f"Could not update confirm message: {e}")
                
    except Exception as e:
        logger.error(f"Update confirm message error: {e}", exc_info=True)

async def show_confirm(chat_id: int, uid: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        session = sessions.get(uid)
        if not session:
            await context.bot.send_message(chat_id=chat_id, text="❌ session expired")
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        if not c1 or not c2:
            await context.bot.send_message(chat_id=chat_id, text="❌ character data missing")
            sessions.pop(uid, None)
            return
        
        stones = session.get('stones', 0)
        
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        result_r = get_result_rarity(r1, r2)
        cost = calc_cost(r1, r2)
        
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        user_stones = user.get('fusion_stones', 0)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        
        # AI Analysis
        ai_analysis = None
        if AI_ENABLED:
            ai_analysis = FusionAI.analyze_fusion_potential(r1, r2, user)
            session['ai_analysis'] = ai_analysis  # Store for later use
        
        buttons = []
        
        # AI Insight button at the top if special combo
        if ai_analysis and ai_analysis['is_special_combo']:
            buttons.append([InlineKeyboardButton("🤖 AI Insights", callback_data="fai")])
        
        stone_btns = []
        for i in range(1, 4):
            if user_stones >= i:
                stone_btns.append(InlineKeyboardButton(
                    f"{'✅' if stones == i else '💎'} {i}",
                    callback_data=f"fst_{i}"
                ))
        
        if stone_btns:
            if len(stone_btns) > 1:
                buttons.append(stone_btns[:2])
                if len(stone_btns) > 2:
                    buttons.append([stone_btns[2]])
            else:
                buttons.append(stone_btns)
        
        fuse_text = "✅ fuse" if bal >= cost else "❌ insufficient"
        fuse_callback = "fconf" if bal >= cost else "fc"
        
        buttons.extend([
            [InlineKeyboardButton(fuse_text, callback_data=fuse_callback)],
            [
                InlineKeyboardButton("💎 buy stones", callback_data="fshop"),
                InlineKeyboardButton("❌ cancel", callback_data="fc")
            ]
        ])
        
        pity_text = f' (+{pity*5}% pity)' if pity > 0 else ''
        stone_text = f' (+{stones*15}%)' if stones else ''
        
        # Add AI recommendation to caption
        ai_text = ""
        if ai_analysis:
            ai_text = f"\n🤖 AI: {ai_analysis['recommendation']}\n"
            if ai_analysis['is_special_combo']:
                ai_text += "⭐ SPECIAL COMBO DETECTED!\n"
        
        caption = (
            f"⚗️ fusion preview\n\n"
            f"1️⃣ {r1} {c1.get('name')}\n"
            f"     ×\n"
            f"2️⃣ {r2} {c2.get('name')}\n"
            f"     ‖\n"
            f"     ⬇️\n"
            f"✨ {result_r}\n"
            f"{ai_text}"
            f"━━━━━━━━━━━━━━\n"
            f"success: {rate*100:.0f}%{pity_text}\n"
            f"cost: {cost:,} 💰\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}{stone_text}"
        )
        
        # Send both character images/videos as a media group
        try:
            media_list = []
            
            # Character 1
            media1_url = c1.get('img_url', '')
            if c1.get('rarity', '').lower() == 'amv' or media1_url.endswith(('.mp4', '.mov', '.avi')):
                media_list.append(InputMediaVideo(media=media1_url, caption=f"1️⃣ {r1} {c1.get('name')}"))
            else:
                media_list.append(InputMediaPhoto(media=media1_url, caption=f"1️⃣ {r1} {c1.get('name')}"))
            
            # Character 2
            media2_url = c2.get('img_url', '')
            if c2.get('rarity', '').lower() == 'amv' or media2_url.endswith(('.mp4', '.mov', '.avi')):
                media_list.append(InputMediaVideo(media=media2_url, caption=f"2️⃣ {r2} {c2.get('name')}"))
            else:
                media_list.append(InputMediaPhoto(media=media2_url, caption=f"2️⃣ {r2} {c2.get('name')}"))
            
            # Send media group
            await context.bot.send_media_group(
                chat_id=chat_id,
                media=media_list
            )
            
            # Send confirmation message with buttons
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        except Exception as e:
            logger.warning(f"Could not send media group in confirm: {e}")
            # Fallback to single image
            try:
                media_url = c1.get('img_url', '')
                if c1.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=media_url,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=media_url,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
            except Exception as e2:
                logger.warning(f"Could not send single media: {e2}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            
    except Exception as e:
        logger.error(f"Show confirm error: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="⚠️ error preparing fusion")

async def execute_fusion(query, uid: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        session = sessions.get(uid)
        if not session:
            await query.edit_message_text("❌ session expired")
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        if not c1 or not c2:
            await query.edit_message_text("❌ character data missing")
            sessions.pop(uid, None)
            return
        
        stones = session.get('stones', 0)
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        cost = calc_cost(r1, r2)
        
        # Deduct balance
        if not await atomic_balance_deduct(uid, cost):
            await query.edit_message_text("❌ insufficient balance")
            sessions.pop(uid, None)
            return
        
        # Deduct stones if used
        if stones > 0 and not await atomic_stone_use(uid, stones):
            # Refund balance
            await user_collection.update_one({'id': uid}, {'$inc': {'balance': cost}})
            await query.edit_message_text("❌ insufficient stones (refunded)")
            sessions.pop(uid, None)
            return
        
        # Animate fusion process
        animation_frames = ['⚡', '🌀', '✨', '💫', '🔮']
        for i, frame in enumerate(animation_frames):
            try:
                await query.edit_message_text(f"{frame} fusing... {(i+1)*20}%")
                await asyncio.sleep(0.8)
            except Exception as e:
                logger.warning(f"Animation frame error: {e}")
        
        # Calculate success
        user = await get_user_safe(uid)
        pity = user.get('fusion_pity', 0)
        rate = calc_rate(r1, r2, stones, pity)
        success = random.random() < rate
        
        if success:
            result_r = get_result_rarity(r1, r2)
            
            # Find matching rarity in database (handle both formats)
            result_rarity_raw = None
            for key, value in RARITY_MAP.items():
                if value == result_r:
                    result_rarity_raw = key
                    break
            
            # Try both formats
            match_query = {'$or': [
                {'rarity': result_r},
                {'rarity': result_rarity_raw} if result_rarity_raw else {'rarity': result_r}
            ]}
            
            new_chars = await collection.aggregate([
                {'$match': match_query},
                {'$sample': {'size': 1}}
            ]).to_list(length=1)
            
            if new_chars:
                new_char = new_chars[0]
                
                # Swap characters atomically
                if not await atomic_char_swap(uid, [session['c1'], session['c2']], new_char):
                    # Refund on failure
                    await user_collection.update_one(
                        {'id': uid},
                        {'$inc': {'balance': cost, 'fusion_stones': stones}}
                    )
                    await query.edit_message_text("❌ fusion failed (refunded)")
                    sessions.pop(uid, None)
                    return
                
                await log_fusion(uid, c1.get('name'), c2.get('name'), True, new_char.get('name'))
                
                try:
                    media_url = new_char.get('img_url', '')
                    # Check if result is AMV (video)
                    if new_char.get('rarity', '').lower() == 'amv' or media_url.endswith(('.mp4', '.mov', '.avi')):
                        await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=media_url,
                            caption=(
                                f"✨ success!\n\n"
                                f"{result_r}\n"
                                f"{new_char.get('name')}\n"
                                f"{new_char.get('anime', 'unknown')}\n"
                                f"id: {new_char.get('id')}"
                            )
                        )
                    else:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=media_url,
                            caption=(
                                f"✨ success!\n\n"
                                f"{result_r}\n"
                                f"{new_char.get('name')}\n"
                                f"{new_char.get('anime', 'unknown')}\n"
                                f"id: {new_char.get('id')}"
                            )
                        )
                except Exception as e:
                    logger.warning(f"Could not send success media: {e}")
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✨ success!\n\n{result_r}\n{new_char.get('name')}"
                    )
                
                await query.edit_message_text("✅ fusion complete!")
            else:
                # Refund if no character found
                await user_collection.update_one(
                    {'id': uid},
                    {'$inc': {'balance': cost, 'fusion_stones': stones}}
                )
                await query.edit_message_text("❌ no result available (refunded)")
        else:
            # Failure - remove both characters
            if not await atomic_char_remove(uid, [session['c1'], session['c2']]):
                # Refund on error
                await user_collection.update_one(
                    {'id': uid},
                    {'$inc': {'balance': cost, 'fusion_stones': stones}}
                )
                await query.edit_message_text("❌ fusion error (refunded)")
                sessions.pop(uid, None)
                return
            
            await log_fusion(uid, c1.get('name'), c2.get('name'), False)
            await query.edit_message_text(
                f"💔 failed\n\nlost:\n{c1.get('name')}\n{c2.get('name')}\n\npity: +5%"
            )
        
        await set_cooldown(uid)
        sessions.pop(uid, None)
        
    except Exception as e:
        logger.error(f"Execute fusion error: {e}", exc_info=True)
        try:
            await query.edit_message_text("⚠️ fusion error occurred")
        except Exception:
            await query.message.reply_text("⚠️ fusion error occurred")
        sessions.pop(uid, None)

async def show_shop(query, uid: int):
    """Display detailed AI analysis of the fusion"""
    try:
        session = sessions.get(uid)
        if not session or 'ai_analysis' not in session:
            await query.answer("❌ No AI analysis available", show_alert=True)
            return
        
        ai_analysis = session['ai_analysis']
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        
        # Build detailed insight message
        insights = "🤖 AI FUSION ANALYSIS\n\n"
        insights += f"📊 Combo: {r1} + {r2}\n\n"
        
        # Special combo indicator
        if ai_analysis['is_special_combo']:
            insights += "⭐ SPECIAL COMBINATION!\n"
            insights += "This is a predefined powerful combo\n\n"
        
        # Expected outcomes
        insights += "🎯 Expected Outcomes:\n"
        for rarity, chance in ai_analysis['expected_outcomes']:
            bar_length = int(chance * 20)
            bar = "█" * bar_length + "░" * (20 - bar_length)
            insights += f"{rarity}\n{bar} {chance*100:.1f}%\n"
        
        insights += f"\n💡 Recommendation:\n{ai_analysis['recommendation']}\n\n"
        
        # Value analysis
        insights += f"📈 Value Score: {ai_analysis['value_score']:.1f}/100\n"
        insights += f"{ai_analysis['risk_level']}\n\n"
        
        # Stone recommendation
        if ai_analysis['suggested_stones'] > 0:
            insights += f"💎 AI suggests: {ai_analysis['suggested_stones']} stone(s)\n"
            insights += f"This boosts success by {ai_analysis['suggested_stones']*15}%\n\n"
        else:
            insights += "💎 No stones needed for this combo\n\n"
        
        # Cost analysis
        insights += f"💰 Cost: {ai_analysis['cost']:,} coins\n"
        
        # Back button
        buttons = [[InlineKeyboardButton("⬅️ Back to Fusion", callback_data="fback")]]
        
        await query.edit_message_text(
            insights,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        logger.error(f"Show AI insights error: {e}", exc_info=True)
        await query.answer("⚠️ Error loading insights", show_alert=True)


async def show_best_fusions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI analyzes user's characters and suggests best fusion combinations"""
    try:
        uid = update.effective_user.id
        
        if not AI_SUGGESTIONS_ENABLED:
            await update.message.reply_text("🤖 AI suggestions are currently disabled")
            return
        
        user = await get_user_safe(uid)
        chars = user.get('characters', [])
        
        if len(chars) < 2:
            await update.message.reply_text("❌ Need at least 2 characters for AI analysis")
            return
        
        # Show processing message
        processing_msg = await update.message.reply_text("🤖 AI analyzing all possible fusions...")
        
        # Get AI recommendations
        best_fusions = FusionAI.get_best_fusions(chars, user, limit=5)
        
        if not best_fusions:
            await processing_msg.edit_text("❌ No fusion combinations found")
            return
        
        # Build recommendation message
        msg = "🤖 AI TOP FUSION RECOMMENDATIONS\n\n"
        msg += f"Analyzed {len(chars)} characters\n"
        msg += f"Found {len(best_fusions)} best combinations:\n\n"
        
        for idx, fusion in enumerate(best_fusions, 1):
            c1 = fusion['char1']
            c2 = fusion['char2']
            analysis = fusion['analysis']
            
            r1 = norm_rarity(c1.get('rarity'))
            r2 = norm_rarity(c2.get('rarity'))
            
            msg += f"{idx}. {r1} {c1.get('name')} + {r2} {c2.get('name')}\n"
            msg += f"   Value: {analysis['value_score']:.0f}/100 | {analysis['risk_level']}\n"
            
            if analysis['expected_outcomes']:
                top_outcome = analysis['expected_outcomes'][0]
                msg += f"   Best: {top_outcome[0]} ({top_outcome[1]*100:.0f}%)\n"
            
            msg += "\n"
        
        msg += "Use /fuse to start fusion with your chosen pair!"
        
        await processing_msg.edit_text(msg)
        
    except Exception as e:
        logger.error(f"Show best fusions error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Error during AI analysis")


async def ai_predict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show AI prediction for current fusion session"""
    try:
        uid = update.effective_user.id
        session = sessions.get(uid)
        
        if not session or 'c1_data' not in session or 'c2_data' not in session:
            await update.message.reply_text("❌ No active fusion session\nUse /fuse first")
            return
        
        c1 = session.get('c1_data')
        c2 = session.get('c2_data')
        user = await get_user_safe(uid)
        
        r1 = norm_rarity(c1.get('rarity'))
        r2 = norm_rarity(c2.get('rarity'))
        pity = user.get('fusion_pity', 0)
        
        # Get predictions for different stone counts
        predictions = FusionAI.predict_success_with_stones(r1, r2, 0, pity)
        
        msg = "🤖 AI SUCCESS PREDICTION\n\n"
        msg += f"Fusion: {r1} + {r2}\n\n"
        
        for stones, pred in predictions.items():
            rate = pred['rate']
            cost = pred['cost_increase']
            
            msg += f"💎 {stones} Stone(s):\n"
            msg += f"  Success: {rate*100:.1f}%\n"
            msg += f"  Cost: +{cost:,} 💰\n"
            msg += f"  Efficiency: {pred['efficiency']*100:.1f}%\n\n"
        
        # AI recommendation
        best_stones = max(predictions.items(), key=lambda x: x[1]['efficiency'])[0]
        msg += f"💡 AI Recommends: {best_stones} stone(s)\n"
        msg += "This gives best value for success rate!"
        
        await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"AI predict error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Error during prediction")
    try:
        user = await get_user_safe(uid)
        bal = user.get('balance', 0)
        stones = user.get('fusion_stones', 0)
        
        buttons = [
            [
                InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"),
                InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")
            ],
            [
                InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"),
                InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")
            ],
            [InlineKeyboardButton("⬅️ back", callback_data="fc")]
        ]
        
        shop_text = (
            f"💎 stone shop\n\n"
            f"balance: {bal:,} 💰\n"
            f"stones: {stones}\n\n"
            f"1 = 100 💰\n"
            f"5 = 450 💰 (10% off)\n"
            f"10 = 850 💰 (15% off)\n"
            f"20 = 1600 💰 (20% off)\n\n"
            f"+15% success per stone (max 3)"
        )
        
        await query.edit_message_text(
            shop_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Show shop error: {e}", exc_info=True)
        try:
            await query.answer("⚠️ error loading shop", show_alert=True)
        except Exception:
            pass

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        user = await get_user_safe(uid)
        chars = user.get('characters', [])
        
        can_use, remaining = await check_cooldown(uid)
        status = "ready ✅" if can_use else f"cooldown {remaining//60}m {remaining%60}s"
        
        pity = user.get('fusion_pity', 0)
        total = user.get('fusion_total', 0)
        success = user.get('fusion_success', 0)
        rate = (success / total * 100) if total > 0 else 0
        
        info_text = (
            f"⚗️ fusion stats\n\n"
            f"balance: {user.get('balance', 0):,} 💰\n"
            f"stones: {user.get('fusion_stones', 0)} 💎\n"
            f"characters: {len(chars)}\n"
            f"status: {status}\n\n"
            f"total fusions: {total}\n"
            f"success rate: {rate:.1f}%\n"
            f"pity bonus: +{pity*5}%\n\n"
            f"/fuse - start fusion\n"
            f"/buystone - shop"
        )
        
        await update.message.reply_text(info_text)
    except Exception as e:
        logger.error(f"Info cmd error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ error occurred")

async def buystone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = update.effective_user.id
        user = await get_user_safe(uid)
        
        buttons = [
            [
                InlineKeyboardButton("💎 1 - 100", callback_data="fb_1"),
                InlineKeyboardButton("💎 5 - 450", callback_data="fb_5")
            ],
            [
                InlineKeyboardButton("💎 10 - 850", callback_data="fb_10"),
                InlineKeyboardButton("💎 20 - 1600", callback_data="fb_20")
            ],
            [InlineKeyboardButton("❌ close", callback_data="fc")]
        ]
        
        shop_text = (
            f"💎 stone shop\n\n"
            f"balance: {user.get('balance', 0):,} 💰\n"
            f"stones: {user.get('fusion_stones', 0)}\n\n"
            f"1 = 100 💰\n"
            f"5 = 450 💰 (save 50)\n"
            f"10 = 850 💰 (save 150)\n"
            f"20 = 1600 💰 (save 400)"
        )
        
        await update.message.reply_text(
            shop_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        logger.error(f"Buystone cmd error: {e}", exc_info=True)
        await update.message.reply_text("⚠️ error occurred")

# Register handlers
application.add_handler(CommandHandler(['fuse', 'fusion'], fuse_cmd, block=False))
application.add_handler(CommandHandler(['fusioninfo', 'finfo'], info_cmd, block=False))
application.add_handler(CommandHandler(['buystone', 'buystones'], buystone_cmd, block=False))
application.add_handler(CommandHandler(['bestfusions', 'aisuggestions', 'aifuse'], show_best_fusions, block=False))
application.add_handler(CommandHandler(['aipredict', 'predict'], ai_predict_cmd, block=False))
application.add_handler(CallbackQueryHandler(callback_handler, pattern='^f', block=False))