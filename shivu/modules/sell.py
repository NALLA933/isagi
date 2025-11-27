from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from datetime import datetime, timedelta
from bson import ObjectId
from shivu import application, db, user_collection
import asyncio
from typing import Optional, Dict, List, Tuple
from collections import defaultdict
import hashlib
import json

collection = db['anime_characters_lol']
sell_listings = db['sell_listings']
sell_history = db['sell_history']
user_preferences = db['user_preferences']
price_analytics = db['price_analytics']
market_notifications = db['market_notifications']

MIN_PRICE = 100
MAX_PRICE = 1000000
MARKET_FEE = 0.05
PREMIUM_FEE = 0.03
MAX_LISTINGS_PER_USER = 10
MAX_PREMIUM_LISTINGS = 25
CACHE_TIMEOUT = 300
BATCH_SIZE = 100
PRICE_HISTORY_DAYS = 30

cache_store: Dict[str, tuple] = {}
search_index: Dict[str, List] = defaultdict(list)
active_searches: Dict[int, dict] = {}

class MarketAnalytics:
    @staticmethod
    async def track_price(char_id: str, price: int, rarity: str):
        await price_analytics.update_one(
            {"char_id": char_id},
            {
                "$push": {
                    "prices": {
                        "$each": [{"price": price, "date": datetime.utcnow()}],
                        "$slice": -50
                    }
                },
                "$set": {"rarity": rarity, "last_updated": datetime.utcnow()}
            },
            upsert=True
        )
    
    @staticmethod
    async def get_price_stats(char_id: str) -> Dict:
        data = await price_analytics.find_one({"char_id": char_id})
        if not data or not data.get("prices"):
            return {}
        
        prices = [p["price"] for p in data["prices"]]
        return {
            "avg": sum(prices) // len(prices),
            "min": min(prices),
            "max": max(prices),
            "recent": prices[-1] if prices else 0,
            "sales": len(prices)
        }
    
    @staticmethod
    async def get_market_trends(rarity: str = None) -> Dict:
        pipeline = [
            {"$match": {"sold_at": {"$gte": datetime.utcnow() - timedelta(days=7)}}},
            {"$group": {
                "_id": "$character_anime",
                "total_sales": {"$sum": 1},
                "avg_price": {"$avg": "$price"},
                "total_volume": {"$sum": "$price"}
            }},
            {"$sort": {"total_volume": -1}},
            {"$limit": 10}
        ]
        
        return await sell_history.aggregate(pipeline).to_list(10)

class SearchEngine:
    @staticmethod
    def create_search_key(text: str) -> str:
        return text.lower().strip()
    
    @staticmethod
    async def build_index():
        listings = await sell_listings.find({}).to_list(1000)
        search_index.clear()
        
        for listing in listings:
            char = listing["character"]
            lid = str(listing["_id"])
            
            name_key = SearchEngine.create_search_key(char.get("name", ""))
            anime_key = SearchEngine.create_search_key(char.get("anime", ""))
            
            if name_key:
                search_index[name_key].append(lid)
            if anime_key:
                search_index[anime_key].append(lid)
        
        return len(listings)
    
    @staticmethod
    async def search(query: str, filters: Dict = None) -> List:
        query_key = SearchEngine.create_search_key(query)
        listing_ids = set()
        
        for key, ids in search_index.items():
            if query_key in key:
                listing_ids.update(ids)
        
        if not listing_ids:
            return []
        
        results = await sell_listings.find(
            {"_id": {"$in": [ObjectId(lid) for lid in listing_ids]}}
        ).to_list(100)
        
        if filters:
            if "min_price" in filters:
                results = [r for r in results if r["price"] >= filters["min_price"]]
            if "max_price" in filters:
                results = [r for r in results if r["price"] <= filters["max_price"]]
            if "rarity" in filters:
                results = [r for r in results if r["character"].get("rarity") == filters["rarity"]]
        
        return results

class NotificationSystem:
    @staticmethod
    async def subscribe_price_alert(user_id: int, char_id: str, target_price: int):
        await market_notifications.update_one(
            {"user_id": user_id},
            {
                "$addToSet": {
                    "price_alerts": {
                        "char_id": char_id,
                        "target_price": target_price,
                        "created": datetime.utcnow()
                    }
                }
            },
            upsert=True
        )
    
    @staticmethod
    async def check_alerts(char_id: str, current_price: int, bot):
        alerts = await market_notifications.find({
            "price_alerts.char_id": char_id,
            "price_alerts.target_price": {"$gte": current_price}
        }).to_list(100)
        
        for alert_doc in alerts:
            user_id = alert_doc["user_id"]
            matching_alerts = [
                a for a in alert_doc["price_alerts"]
                if a["char_id"] == char_id and a["target_price"] >= current_price
            ]
            
            for alert in matching_alerts:
                try:
                    await bot.send_message(
                        user_id,
                        f"🔔 <b>ᴘʀɪᴄᴇ ᴀʟᴇʀᴛ!</b>\n\n"
                        f"<blockquote>ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʏᴏᴜ'ʀᴇ ᴡᴀᴛᴄʜɪɴɢ ɪs ɴᴏᴡ ᴀᴠᴀɪʟᴀʙʟᴇ!\n\n"
                        f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{current_price:,}</code> ɢᴏʟᴅ\n"
                        f"🎯 <b>ʏᴏᴜʀ ᴛᴀʀɢᴇᴛ:</b> <code>{alert['target_price']:,}</code> ɢᴏʟᴅ</blockquote>\n\n"
                        f"💡 ᴜsᴇ /market ᴛᴏ ᴠɪᴇᴡ",
                        parse_mode="HTML"
                    )
                except:
                    pass
            
            await market_notifications.update_one(
                {"user_id": user_id},
                {"$pull": {"price_alerts": {"char_id": char_id}}}
            )

async def get_cached_user(bot, user_id: int) -> Optional[str]:
    cache_key = f"user_{user_id}"
    if cache_key in cache_store:
        data, timestamp = cache_store[cache_key]
        if datetime.utcnow().timestamp() - timestamp < CACHE_TIMEOUT:
            return data
    
    try:
        user = await bot.get_chat(user_id)
        username = user.first_name[:15]
        cache_store[cache_key] = (username, datetime.utcnow().timestamp())
        return username
    except:
        return "Unknown"

async def is_premium_user(user_id: int) -> bool:
    user_data = await user_collection.find_one({"id": user_id}, {"premium": 1})
    return user_data.get("premium", False) if user_data else False

async def validate_listing_ownership(user_id: int, char_id: str) -> tuple:
    user_data = await user_collection.find_one({"id": user_id}, {"characters": 1})
    if not user_data:
        return False, None, "⚠️ <b>ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ғᴏᴜɴᴅ ɪɴ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</b>"
    
    char_to_sell = next((c for c in user_data.get("characters", []) if str(c.get("id", c.get("_id"))) == char_id), None)
    
    if not char_to_sell:
        return False, None, f"⚠️ <b>ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n<blockquote>ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ: <code>{char_id}</code>\n\n💡 ᴜsᴇ /collection ᴛᴏ ᴠɪᴇᴡ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>"
    
    return True, char_to_sell, None

async def check_listing_limits(user_id: int) -> tuple:
    is_premium = await is_premium_user(user_id)
    max_listings = MAX_PREMIUM_LISTINGS if is_premium else MAX_LISTINGS_PER_USER
    
    user_listings = await sell_listings.count_documents({"seller_id": user_id})
    if user_listings >= max_listings:
        return False, f"⚠️ <b>ʟɪsᴛɪɴɢ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ</b>\n\n<blockquote>📦 <b>ᴍᴀx ʟɪsᴛɪɴɢs:</b> {user_listings}/{max_listings}\n\n{'⭐ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀ ʟɪᴍɪᴛ' if is_premium else '💡 ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ ғᴏʀ 25 sʟᴏᴛs'}</blockquote>"
    return True, None

def format_time_ago(timestamp: datetime) -> str:
    time_diff = datetime.utcnow() - timestamp
    seconds = int(time_diff.total_seconds())
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"

def create_listing_caption(listing: dict, seller_name: str, is_own: bool, page: int, total: int, stats: Dict = None) -> str:
    char = listing["character"]
    price = listing["price"]
    fee = int(price * MARKET_FEE)
    final_price = price - fee
    time_str = format_time_ago(listing.get("listed_at", datetime.utcnow()))
    
    caption = f"{'📦 <b>ʏᴏᴜʀ ʟɪsᴛɪɴɢ</b>' if is_own else '🏪 <b>ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ</b>'}\n\n"
    
    caption += (
        f"<blockquote expandable>"
        f"🎭 <b>ɴᴀᴍᴇ:</b> <code>{char.get('name', 'Unknown')}</code>\n"
        f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char.get('anime', 'Unknown')}</code>\n"
        f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char.get('rarity', 'Unknown')}\n"
        f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
        f"</blockquote>\n\n"
        f"<blockquote>"
        f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
        f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
        f"👁️ <b>ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}\n"
        f"⏰ <b>ʟɪsᴛᴇᴅ:</b> {time_str}"
        f"</blockquote>\n\n"
    )
    
    if stats:
        caption += (
            f"<blockquote expandable>"
            f"📊 <b>ᴍᴀʀᴋᴇᴛ ᴀɴᴀʟʏᴛɪᴄs:</b>\n"
            f"📈 <b>ᴀᴠɢ ᴘʀɪᴄᴇ:</b> <code>{stats.get('avg', 0):,}</code>\n"
            f"📉 <b>ᴍɪɴ-ᴍᴀx:</b> <code>{stats.get('min', 0):,}</code> - <code>{stats.get('max', 0):,}</code>\n"
            f"🔄 <b>ᴛᴏᴛᴀʟ sᴀʟᴇs:</b> {stats.get('sales', 0)}"
            f"</blockquote>\n\n"
        )
    
    if is_own:
        caption += (
            f"<blockquote>"
            f"💵 <b>ʏᴏᴜ'ʟʟ ʀᴇᴄᴇɪᴠᴇ:</b> <code>{final_price:,}</code> ɢᴏʟᴅ\n"
            f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ({int(MARKET_FEE*100)}%)"
            f"</blockquote>\n\n"
        )
    
    caption += f"📖 <b>ᴘᴀɢᴇ:</b> {page+1}/{total}"
    return caption

def create_navigation_buttons(listing: dict, page: int, total: int, is_own: bool, show_analytics: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    
    if is_own:
        buttons.append([InlineKeyboardButton("🗑️ ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ", callback_data=f"market_remove_{listing['_id']}")])
    else:
        row = [InlineKeyboardButton("💳 ʙᴜʏ ɴᴏᴡ", callback_data=f"bi_{listing['_id']}")]
        if show_analytics:
            row.append(InlineKeyboardButton("📊 ᴀɴᴀʟʏᴛɪᴄs", callback_data=f"stats_{listing['_id']}"))
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton("🔔 ᴘʀɪᴄᴇ ᴀʟᴇʀᴛ", callback_data=f"alert_{listing['_id']}"),
        InlineKeyboardButton("👤 sᴇʟʟᴇʀ ɪɴғᴏ", callback_data=f"seller_{listing['seller_id']}")
    ])
    
    if total > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"market_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"• {page+1}/{total} •", callback_data="market_pageinfo"))
        if page < total - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"market_page_{page+1}"))
        buttons.append(nav)
    
    buttons.append([
        InlineKeyboardButton("🔍 sᴇᴀʀᴄʜ", callback_data="market_search"),
        InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="market_refresh")
    ])
    
    return InlineKeyboardMarkup(buttons)

async def sell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>ɪɴᴄᴏʀʀᴇᴄᴛ ᴜsᴀɢᴇ</b>\n\n"
            "<b>ғᴏʀᴍᴀᴛ:</b> <code>/sell [character_id] [price]</code>\n\n"
            "<blockquote><b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/sell 12345 5000</code>\n\n"
            f"💰 <b>ᴘʀɪᴄᴇ ʀᴀɴɢᴇ:</b> {MIN_PRICE:,} - {MAX_PRICE:,}\n"
            f"💸 <b>sᴛᴀɴᴅᴀʀᴅ ғᴇᴇ:</b> {int(MARKET_FEE*100)}%\n"
            f"⭐ <b>ᴘʀᴇᴍɪᴜᴍ ғᴇᴇ:</b> {int(PREMIUM_FEE*100)}%</blockquote>",
            parse_mode="HTML"
        )
        return
    
    try:
        char_id = context.args[0]
        price = int(context.args[1])
        
        if price < MIN_PRICE or price > MAX_PRICE:
            await update.message.reply_text(
                f"⚠️ <b>ɪɴᴠᴀʟɪᴅ ᴘʀɪᴄᴇ ʀᴀɴɢᴇ</b>\n\n"
                f"<blockquote>ᴘʀɪᴄᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ:\n"
                f"<b>{MIN_PRICE:,}</b> - <b>{MAX_PRICE:,}</b> ɢᴏʟᴅ</blockquote>",
                parse_mode="HTML"
            )
            return
        
        valid, char_to_sell, error = await validate_listing_ownership(user_id, char_id)
        if not valid:
            await update.message.reply_text(error, parse_mode="HTML")
            return
        
        if await sell_listings.find_one({"seller_id": user_id, "character.id": char_to_sell.get("id", char_to_sell.get("_id"))}):
            await update.message.reply_text(
                "⚠️ <b>ᴀʟʀᴇᴀᴅʏ ʟɪsᴛᴇᴅ</b>\n\n"
                "<blockquote>ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ɪs ᴀʟʀᴇᴀᴅʏ ᴏɴ ᴛʜᴇ ᴍᴀʀᴋᴇᴛ\n\n"
                "💡 ᴜsᴇ /unsell ᴛᴏ ʀᴇᴍᴏᴠᴇ ɪᴛ ғɪʀsᴛ</blockquote>",
                parse_mode="HTML"
            )
            return
        
        can_list, error = await check_listing_limits(user_id)
        if not can_list:
            await update.message.reply_text(error, parse_mode="HTML")
            return
        
        is_premium = await is_premium_user(user_id)
        
        stats = await MarketAnalytics.get_price_stats(char_id)
        price_suggestion = ""
        if stats and stats.get("avg"):
            avg = stats["avg"]
            if price > avg * 1.2:
                price_suggestion = f"\n\n💡 <i>ᴀᴠɢ ᴍᴀʀᴋᴇᴛ ᴘʀɪᴄᴇ: {avg:,} ɢᴏʟᴅ</i>"
        
        await sell_listings.insert_one({
            "seller_id": user_id,
            "character": char_to_sell,
            "price": price,
            "listed_at": datetime.utcnow(),
            "views": 0,
            "is_premium": is_premium
        })
        
        await user_collection.update_one({"id": user_id}, {"$pull": {"characters": char_to_sell}})
        
        await MarketAnalytics.track_price(char_id, price, char_to_sell.get("rarity", "Unknown"))
        
        asyncio.create_task(SearchEngine.build_index())
        
        fee_rate = PREMIUM_FEE if is_premium else MARKET_FEE
        fee = int(price * fee_rate)
        you_get = price - fee
        
        await update.message.reply_text(
            f"✅ <b>sᴜᴄᴄᴇssғᴜʟʟʏ ʟɪsᴛᴇᴅ!</b>\n\n"
            f"<blockquote expandable>🎭 <b>ɴᴀᴍᴇ:</b> <code>{char_to_sell.get('name', 'Unknown')}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char_to_sell.get('anime', 'Unknown')}</code>\n"
            f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char_to_sell.get('rarity', 'Unknown')}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{char_id}</code></blockquote>\n\n"
            f"<blockquote>💰 <b>ʟɪsᴛᴇᴅ ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
            f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ɢᴏʟᴅ ({int(fee_rate*100)}%{'⭐' if is_premium else ''})\n"
            f"💵 <b>ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇ:</b> <code>{you_get:,}</code> ɢᴏʟᴅ</blockquote>{price_suggestion}\n\n"
            f"📊 ᴠɪᴇᴡ ʏᴏᴜʀ ʟɪsᴛɪɴɢs: /mymarket",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ <b>ɪɴᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀᴍᴀᴛ</b>\n\n<blockquote>ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ</blockquote>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>ᴇʀʀᴏʀ:</b>\n\n<blockquote><code>{str(e)}</code></blockquote>", parse_mode="HTML")

async def unsell(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <b>ɪɴᴄᴏʀʀᴇᴄᴛ ᴜsᴀɢᴇ</b>\n\n"
            "<b>ғᴏʀᴍᴀᴛ:</b> <code>/unsell [character_id]</code>\n\n"
            "<blockquote><b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/unsell 12345</code>\n\n"
            "💡 ᴜsᴇ /mymarket ᴛᴏ sᴇᴇ ʏᴏᴜʀ ʟɪsᴛɪɴɢs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    try:
        listing = await sell_listings.find_one({"seller_id": user_id, "character.id": context.args[0]})
        
        if not listing:
            await update.message.reply_text(
                f"⚠️ <b>ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ</b>\n\n"
                f"<blockquote>ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢ ғᴏʀ ɪᴅ: <code>{context.args[0]}</code></blockquote>",
                parse_mode="HTML"
            )
            return
        
        await user_collection.update_one({"id": user_id}, {"$push": {"characters": listing["character"]}}, upsert=True)
        await sell_listings.delete_one({"_id": listing["_id"]})
        
        asyncio.create_task(SearchEngine.build_index())
        
        await update.message.reply_text(
            f"✅ <b>ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ</b>\n\n"
            f"<blockquote>🎭 <b>{listing['character'].get('name', 'Unknown')}</b>\n"
            f"ʀᴇᴛᴜʀɴᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ\n\n"
            f"👁️ <b>ᴛᴏᴛᴀʟ ᴠɪᴇᴡs:</b> {listing.get('views', 0):,}</blockquote>",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ <b>ᴇʀʀᴏʀ:</b>\n\n<blockquote><code>{str(e)}</code></blockquote>", parse_mode="HTML")

async def market(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    sort_by = context.args[0] if context.args else "recent"
    sort_options = {
        "recent": ("listed_at", -1),
        "price_low": ("price", 1),
        "price_high": ("price", -1),
        "popular": ("views", -1)
    }
    
    sort_field, sort_order = sort_options.get(sort_by, ("listed_at", -1))
    
    listings = await sell_listings.find({}).sort(sort_field, sort_order).limit(200).to_list(length=200)
    
    if not listings:
        await update.message.reply_text(
            "🏪 <b>ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ</b>\n\n"
            "<blockquote>😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴄᴜʀʀᴇɴᴛʟʏ ᴀᴠᴀɪʟᴀʙʟᴇ\n\n"
            "<b>💡 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
            "• /sell - ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            "• /mymarket - ʏᴏᴜʀ ʟɪsᴛɪɴɢs\n"
            "• /msales - ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ\n"
            "• /mtrends - ᴍᴀʀᴋᴇᴛ ᴛʀᴇɴᴅs\n"
            "• /msearch [query] - sᴇᴀʀᴄʜ ᴍᴀʀᴋᴇᴛ</blockquote>",
            parse_mode="HTML"
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = 0
    context.user_data['viewing_mine'] = False
    context.user_data['sort_by'] = sort_by
    await render_market_page(update.message, context, listings, 0, user_id)

async def mymarket(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    listings = await sell_listings.find({"seller_id": user_id}).sort("listed_at", -1).limit(100).to_list(length=100)
    
    if not listings:
        await update.message.reply_text(
            "📦 <b>ʏᴏᴜʀ ʟɪsᴛɪɴɢs</b>\n\n"
            "<blockquote>😔 ʏᴏᴜ ʜᴀᴠᴇ ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs\n\n"
            "💡 ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in listings]
    context.user_data['market_page'] = 0
    context.user_data['viewing_mine'] = True
    await render_market_page(update.message, context, listings, 0, user_id, my_listings=True)

async def msearch(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>ᴍᴀʀᴋᴇᴛ sᴇᴀʀᴄʜ</b>\n\n"
            "<b>ғᴏʀᴍᴀᴛ:</b> <code>/msearch [query]</code>\n\n"
            "<blockquote><b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "• <code>/msearch Naruto</code>\n"
            "• <code>/msearch Goku</code>\n"
            "• <code>/msearch One Piece</code></blockquote>\n\n"
            "💡 ᴀᴅᴠᴀɴᴄᴇᴅ sᴇᴀʀᴄʜ ᴄᴏᴍɪɴɢ sᴏᴏɴ!",
            parse_mode="HTML"
        )
        return
    
    query = " ".join(context.args)
    
    msg = await update.message.reply_text("🔍 <b>sᴇᴀʀᴄʜɪɴɢ ᴍᴀʀᴋᴇᴛ...</b>", parse_mode="HTML")
    
    results = await SearchEngine.search(query)
    
    if not results:
        await msg.edit_text(
            f"🔍 <b>sᴇᴀʀᴄʜ ʀᴇsᴜʟᴛs</b>\n\n"
            f"<blockquote>😔 ɴᴏ ʀᴇsᴜʟᴛs ғᴏᴜɴᴅ ғᴏʀ: <code>{query}</code>\n\n"
            f"💡 ᴛʀʏ ᴅɪғғᴇʀᴇɴᴛ ᴋᴇʏᴡᴏʀᴅs ᴏʀ /market ᴛᴏ ʙʀᴏᴡsᴇ ᴀʟʟ</blockquote>",
            parse_mode="HTML"
        )
        return
    
    context.user_data['market_listings'] = [str(l['_id']) for l in results]
    context.user_data['market_page'] = 0
    context.user_data['viewing_mine'] = False
    context.user_data['search_query'] = query
    
    await msg.delete()
    await render_market_page(update.message, context, results, 0, user_id)

async def mtrends(update: Update, context: CallbackContext):
    trends = await MarketAnalytics.get_market_trends()
    
    if not trends:
        await update.message.reply_text(
            "📈 <b>ᴍᴀʀᴋᴇᴛ ᴛʀᴇɴᴅs</b>\n\n"
            "<blockquote>😔 ɴᴏ ᴛʀᴇɴᴅ ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ ʏᴇᴛ\n\n"
            "💡 ᴄʜᴇᴄᴋ ʙᴀᴄᴋ ᴀғᴛᴇʀ ᴍᴏʀᴇ ᴛʀᴀᴅᴇs!</blockquote>",
            parse_mode="HTML"
        )
        return
    
    text = "📈 <b>ᴛᴏᴘ ᴛʀᴀᴅɪɴɢ ᴀɴɪᴍᴇs</b>\n<i>(ʟᴀsᴛ 7 ᴅᴀʏs)</i>\n\n"
    
    for idx, trend in enumerate(trends, 1):
        text += (
            f"<blockquote expandable>"
            f"<b>{idx}. {trend['_id']}</b>\n"
            f"🔄 <b>sᴀʟᴇs:</b> {trend['total_sales']}\n"
            f"💰 <b>ᴀᴠɢ ᴘʀɪᴄᴇ:</b> <code>{int(trend['avg_price']):,}</code> ɢᴏʟᴅ\n"
            f"📊 <b>ᴠᴏʟᴜᴍᴇ:</b> <code>{int(trend['total_volume']):,}</code> ɢᴏʟᴅ"
            f"</blockquote>\n\n"
        )
    
    active_listings = await sell_listings.count_documents({})
    total_value = await sell_listings.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$price"}}}
    ]).to_list(1)
    
    market_value = total_value[0]["total"] if total_value else 0
    
    text += (
        f"<blockquote>"
        f"📦 <b>ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs:</b> {active_listings:,}\n"
        f"💎 <b>ᴛᴏᴛᴀʟ ᴍᴀʀᴋᴇᴛ ᴠᴀʟᴜᴇ:</b> <code>{market_value:,}</code> ɢᴏʟᴅ"
        f"</blockquote>"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def lists(update: Update, context: CallbackContext):
    listings = await sell_listings.find({}).sort("listed_at", -1).limit(200).to_list(length=200)
    
    if not listings:
        await update.message.reply_text(
            "📋 <b>ᴍᴀʀᴋᴇᴛ ʟɪsᴛɪɴɢs</b>\n\n"
            "<blockquote>😔 ɴᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴄᴜʀʀᴇɴᴛʟʏ ʟɪsᴛᴇᴅ\n\n"
            "💡 ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ʏᴏᴜʀ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
            parse_mode="HTML"
        )
        return
    
    text = f"📋 <b>ᴍᴀʀᴋᴇᴛ ʟɪsᴛɪɴɢs</b>\n\n"
    text += f"<blockquote><b>ᴛᴏᴛᴀʟ ʟɪsᴛɪɴɢs:</b> {len(listings)}/200</blockquote>\n\n"
    
    seller_tasks = [get_cached_user(context.bot, listing["seller_id"]) for listing in listings[:BATCH_SIZE]]
    seller_names = await asyncio.gather(*seller_tasks)
    
    for idx, (listing, seller_name) in enumerate(zip(listings[:BATCH_SIZE], seller_names), 1):
        char = listing["character"]
        price = listing["price"]
        premium_badge = "⭐" if listing.get("is_premium") else ""
        
        text += (
            f"<blockquote expandable>"
            f"<b>{idx}.</b> <code>{char.get('name', 'Unknown')[:20]}</code>\n"
            f"💰 <b>ᴘʀɪᴄᴇ:</b> <code>{price:,}</code> ɢᴏʟᴅ {premium_badge}\n"
            f"👤 <b>sᴇʟʟᴇʀ:</b> {seller_name}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
            f"</blockquote>\n\n"
        )
        
        if len(text) > 3500:
            await update.message.reply_text(text, parse_mode="HTML")
            text = ""
    
    if text:
        await update.message.reply_text(text, parse_mode="HTML")
    
    if len(listings) > BATCH_SIZE:
        await update.message.reply_text(
            f"<blockquote>📊 <b>sʜᴏᴡɪɴɢ:</b> {BATCH_SIZE}/{len(listings)} ʟɪsᴛɪɴɢs\n\n"
            f"💡 ᴜsᴇ /market ᴛᴏ ʙʀᴏᴡsᴇ ᴡɪᴛʜ ɪᴍᴀɢᴇs</blockquote>",
            parse_mode="HTML"
        )

async def render_market_page(message, context, listings, page, user_id, my_listings=False):
    if page >= len(listings):
        return
    
    listing = listings[page]
    char = listing["character"]
    seller_id = listing["seller_id"]
    char_id = char.get("id", char.get("_id"))
    
    await sell_listings.update_one({"_id": listing["_id"]}, {"$inc": {"views": 1}})
    
    seller_name = await get_cached_user(context.bot, seller_id)
    stats = await MarketAnalytics.get_price_stats(str(char_id))
    
    is_video = char.get("rarity") == "🎥 AMV"
    is_own = seller_id == user_id
    
    caption = create_listing_caption(listing, seller_name, is_own, page, len(listings), stats if stats else None)
    markup = create_navigation_buttons(listing, page, len(listings), is_own, show_analytics=bool(stats))
    
    try:
        if is_video:
            await message.reply_video(
                video=char.get("img_url"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
                has_spoiler=True
            )
        else:
            await message.reply_photo(
                photo=char.get("img_url"),
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
                has_spoiler=True
            )
    except BadRequest:
        await message.reply_text(f"{caption}\n\n⚠️ <blockquote>ᴍᴇᴅɪᴀ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ</blockquote>", parse_mode="HTML", reply_markup=markup)

async def msales(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    sales_task = sell_history.find({"seller_id": user_id}).sort("sold_at", -1).limit(10).to_list(10)
    purchases_task = sell_history.find({"buyer_id": user_id}).sort("sold_at", -1).limit(10).to_list(10)
    active_task = sell_listings.count_documents({"seller_id": user_id})
    
    sales, purchases, active_listings = await asyncio.gather(sales_task, purchases_task, active_task)
    
    text = "📊 <b>ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ</b>\n\n"
    
    if sales:
        text += "<blockquote expandable><b>💰 ʀᴇᴄᴇɴᴛ sᴀʟᴇs:</b>\n"
        total_earned = sum(s.get("price", 0) - s.get("fee", 0) for s in sales)
        for idx, s in enumerate(sales[:5], 1):
            net = s.get("price", 0) - s.get("fee", 0)
            text += f"{idx}. <code>{s.get('character_name', 'Unknown')}</code> → <code>{net:,}</code> 💎\n"
        text += f"\n<b>ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ:</b> <code>{total_earned:,}</code> 💰</blockquote>\n\n"
    
    if purchases:
        text += "<blockquote expandable><b>🛒 ʀᴇᴄᴇɴᴛ ᴘᴜʀᴄʜᴀsᴇs:</b>\n"
        total_spent = sum(p.get("price", 0) for p in purchases)
        for idx, p in enumerate(purchases[:5], 1):
            text += f"{idx}. <code>{p.get('character_name', 'Unknown')}</code> → <code>{p.get('price', 0):,}</code> 💎\n"
        text += f"\n<b>ᴛᴏᴛᴀʟ sᴘᴇɴᴛ:</b> <code>{total_spent:,}</code> 💰</blockquote>\n\n"
    
    is_premium = await is_premium_user(user_id)
    max_slots = MAX_PREMIUM_LISTINGS if is_premium else MAX_LISTINGS_PER_USER
    
    text += f"<blockquote><b>📦 ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs:</b> {active_listings}/{max_slots}{'⭐' if is_premium else ''}</blockquote>"
    
    if not sales and not purchases:
        text += "<blockquote>😔 ɴᴏ ᴛʀᴀᴅᴇ ʜɪsᴛᴏʀʏ ʏᴇᴛ\n\n💡 sᴛᴀʀᴛ ᴛʀᴀᴅɪɴɢ ᴡɪᴛʜ /market</blockquote>"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def market_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("market_page_"):
        await query.answer()
        page = int(data.split("_")[2])
        listings = [await sell_listings.find_one({"_id": ObjectId(lid)}) for lid in context.user_data.get('market_listings', [])]
        listings = [l for l in listings if l]
        
        if listings:
            context.user_data['market_page'] = page
            await update_market_display(query, context, listings, page, user_id)
    
    elif data == "market_pageinfo":
        await query.answer("📖 ᴜsᴇ ᴀʀʀᴏᴡs ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ")
    
    elif data == "market_search":
        await query.answer("💡 ᴜsᴇ /msearch [query] ᴛᴏ sᴇᴀʀᴄʜ ᴛʜᴇ ᴍᴀʀᴋᴇᴛ", show_alert=True)
    
    elif data == "market_refresh":
        is_mine = context.user_data.get('viewing_mine', False)
        filter_query = {"seller_id": user_id} if is_mine else {}
        
        listings = await sell_listings.find(filter_query).sort("listed_at", -1).limit(200).to_list(length=200)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
            await query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ")
        else:
            await query.answer("😔 ɴᴏ ʟɪsᴛɪɴɢs", show_alert=True)
    
    elif data.startswith("stats_"):
        listing_id = data.replace("stats_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id)})
        
        if listing:
            char_id = listing["character"].get("id", listing["character"].get("_id"))
            stats = await MarketAnalytics.get_price_stats(str(char_id))
            
            if stats:
                await query.answer(
                    f"📊 ᴀɴᴀʟʏᴛɪᴄs\n"
                    f"ᴀᴠɢ: {stats['avg']:,} | "
                    f"ᴍɪɴ: {stats['min']:,} | "
                    f"ᴍᴀx: {stats['max']:,}\n"
                    f"sᴀʟᴇs: {stats['sales']}",
                    show_alert=True
                )
            else:
                await query.answer("📊 ɴᴏ ᴀɴᴀʟʏᴛɪᴄs ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
    
    elif data.startswith("seller_"):
        seller_id = int(data.replace("seller_", ""))
        
        seller_listings = await sell_listings.count_documents({"seller_id": seller_id})
        seller_sales = await sell_history.count_documents({"seller_id": seller_id})
        seller_name = await get_cached_user(context.bot, seller_id)
        
        await query.answer(
            f"👤 {seller_name}\n"
            f"📦 ᴀᴄᴛɪᴠᴇ: {seller_listings} | "
            f"✅ sᴏʟᴅ: {seller_sales}",
            show_alert=True
        )
    
    elif data.startswith("alert_"):
        listing_id = data.replace("alert_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id)})
        
        if listing:
            char_id = listing["character"].get("id", listing["character"].get("_id"))
            current_price = listing["price"]
            target_price = int(current_price * 0.9)
            
            await NotificationSystem.subscribe_price_alert(user_id, str(char_id), target_price)
            await query.answer(
                f"🔔 ᴘʀɪᴄᴇ ᴀʟᴇʀᴛ sᴇᴛ!\n"
                f"ʏᴏᴜ'ʟʟ ʙᴇ ɴᴏᴛɪғɪᴇᴅ ɪғ ᴘʀɪᴄᴇ ᴅʀᴏᴘs ʙᴇʟᴏᴡ {target_price:,} ɢᴏʟᴅ",
                show_alert=True
            )
    
    elif data.startswith("bi_"):
        listing_id = data.replace("bi_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id)})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴠᴀɪʟᴀʙʟᴇ", show_alert=True)
            return
        
        if listing["seller_id"] == user_id:
            await query.answer("⚠️ ᴄᴀɴ'ᴛ ʙᴜʏ ʏᴏᴜʀ ᴏᴡɴ ʟɪsᴛɪɴɢ", show_alert=True)
            return
        
        user_data = await user_collection.find_one({"id": user_id}, {"balance": 1})
        balance = user_data.get("balance", 0) if user_data else 0
        price = listing["price"]
        
        if balance < price:
            shortage = price - balance
            await query.answer(
                f"⚠️ ɪɴsᴜғғɪᴄɪᴇɴᴛ ʙᴀʟᴀɴᴄᴇ\n\n"
                f"💰 ɴᴇᴇᴅ: {price:,} ɢᴏʟᴅ\n"
                f"💵 ʜᴀᴠᴇ: {balance:,} ɢᴏʟᴅ\n"
                f"📉 sʜᴏʀᴛ: {shortage:,} ɢᴏʟᴅ",
                show_alert=True
            )
            return
        
        char = listing["character"]
        char_id = char.get("id", char.get("_id"))
        is_premium = listing.get("is_premium", False)
        fee_rate = PREMIUM_FEE if is_premium else MARKET_FEE
        fee = int(price * fee_rate)
        seller_gets = price - fee
        
        update_buyer = user_collection.update_one(
            {"id": user_id},
            {"$inc": {"balance": -price}, "$push": {"characters": char}},
            upsert=True
        )
        
        update_seller = user_collection.update_one(
            {"id": listing["seller_id"]},
            {"$inc": {"balance": seller_gets}},
            upsert=True
        )
        
        delete_listing = sell_listings.delete_one({"_id": listing["_id"]})
        
        insert_history = sell_history.insert_one({
            "seller_id": listing["seller_id"],
            "buyer_id": user_id,
            "character_name": char.get("name", "Unknown"),
            "character_anime": char.get("anime", "Unknown"),
            "price": price,
            "fee": fee,
            "sold_at": datetime.utcnow()
        })
        
        await asyncio.gather(update_buyer, update_seller, delete_listing, insert_history)
        
        asyncio.create_task(MarketAnalytics.track_price(str(char_id), price, char.get("rarity", "Unknown")))
        asyncio.create_task(SearchEngine.build_index())
        asyncio.create_task(NotificationSystem.check_alerts(str(char_id), price, context.bot))
        
        try:
            await context.bot.send_message(
                listing["seller_id"],
                f"💰 <b>sᴀʟᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
                f"<blockquote expandable>"
                f"🎭 <b>{char.get('name', 'Unknown')}</b>\n"
                f"📺 {char.get('anime', 'Unknown')}\n"
                f"💫 {char.get('rarity', 'Unknown')}"
                f"</blockquote>\n\n"
                f"<blockquote>"
                f"💵 <b>ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇᴅ:</b> <code>{seller_gets:,}</code> ɢᴏʟᴅ\n"
                f"📉 <b>ᴍᴀʀᴋᴇᴛ ғᴇᴇ:</b> <code>{fee:,}</code> ɢᴏʟᴅ ({int(fee_rate*100)}%{'⭐' if is_premium else ''})\n"
                f"👤 <b>ʙᴜʏᴇʀ:</b> {query.from_user.first_name}"
                f"</blockquote>",
                parse_mode="HTML"
            )
        except:
            pass
        
        success_text = (
            f"✅ <b>ᴘᴜʀᴄʜᴀsᴇ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
            f"<blockquote expandable>"
            f"🎭 <b>ɴᴀᴍᴇ:</b> <code>{char.get('name', 'Unknown')}</code>\n"
            f"📺 <b>ᴀɴɪᴍᴇ:</b> <code>{char.get('anime', 'Unknown')}</code>\n"
            f"💫 <b>ʀᴀʀɪᴛʏ:</b> {char.get('rarity', 'Unknown')}\n"
            f"🆔 <b>ɪᴅ:</b> <code>{char.get('id', char.get('_id', 'N/A'))}</code>"
            f"</blockquote>\n\n"
            f"<blockquote>"
            f"💰 <b>ᴘᴀɪᴅ:</b> <code>{price:,}</code> ɢᴏʟᴅ\n"
            f"💵 <b>ɴᴇᴡ ʙᴀʟᴀɴᴄᴇ:</b> <code>{balance - price:,}</code> ɢᴏʟᴅ"
            f"</blockquote>\n\n"
            f"🎉 ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ!"
        )
        
        try:
            await query.edit_message_caption(
                caption=success_text,
                parse_mode="HTML"
            )
            await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!")
        except BadRequest:
            await query.answer("✨ ᴘᴜʀᴄʜᴀsᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!")
    
    elif data.startswith("market_remove_"):
        listing_id = data.replace("market_remove_", "")
        listing = await sell_listings.find_one({"_id": ObjectId(listing_id), "seller_id": user_id})
        
        if not listing:
            await query.answer("⚠️ ʟɪsᴛɪɴɢ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)
            return
        
        restore_char = user_collection.update_one(
            {"id": user_id},
            {"$push": {"characters": listing["character"]}},
            upsert=True
        )
        delete_list = sell_listings.delete_one({"_id": listing["_id"]})
        
        await asyncio.gather(restore_char, delete_list)
        asyncio.create_task(SearchEngine.build_index())
        
        await query.answer("🔙 ʀᴇᴍᴏᴠᴇᴅ ғʀᴏᴍ ᴍᴀʀᴋᴇᴛ")
        
        is_mine = context.user_data.get('viewing_mine', False)
        filter_query = {"seller_id": user_id} if is_mine else {}
        
        listings = await sell_listings.find(filter_query).sort("listed_at", -1).limit(200).to_list(length=200)
        if listings:
            context.user_data['market_listings'] = [str(l['_id']) for l in listings]
            context.user_data['market_page'] = 0
            await update_market_display(query, context, listings, 0, user_id)
        else:
            try:
                await query.edit_message_caption(
                    caption="<b>📦 ɴᴏ ᴀᴄᴛɪᴠᴇ ʟɪsᴛɪɴɢs</b>\n\n<blockquote>💡 ᴜsᴇ /sell ᴛᴏ ʟɪsᴛ ᴄʜᴀʀᴀᴄᴛᴇʀs</blockquote>",
                    parse_mode="HTML"
                )
            except:
                pass
    
    elif data == "market_cancel":
        page = context.user_data.get('market_page', 0)
        listings = [await sell_listings.find_one({"_id": ObjectId(lid)}) for lid in context.user_data.get('market_listings', [])]
        listings = [l for l in listings if l]
        
        if listings:
            await update_market_display(query, context, listings, page, user_id)
        await query.answer("❌ ᴄᴀɴᴄᴇʟʟᴇᴅ")

async def update_market_display(query, context, listings, page, user_id):
    if page >= len(listings):
        return
    
    listing = listings[page]
    char = listing["character"]
    seller_id = listing["seller_id"]
    char_id = char.get("id", char.get("_id"))
    
    seller_name = await get_cached_user(context.bot, seller_id)
    stats = await MarketAnalytics.get_price_stats(str(char_id))
    
    is_video = char.get("rarity") == "🎥 AMV"
    is_own = seller_id == user_id
    
    caption = create_listing_caption(listing, seller_name, is_own, page, len(listings), stats if stats else None)
    markup = create_navigation_buttons(listing, page, len(listings), is_own, show_analytics=bool(stats))
    
    try:
        if is_video:
            await query.edit_message_media(
                media=InputMediaVideo(media=char.get("img_url"), caption=caption, parse_mode="HTML", has_spoiler=True),
                reply_markup=markup
            )
        else:
            await query.edit_message_media(
                media=InputMediaPhoto(media=char.get("img_url"), caption=caption, parse_mode="HTML", has_spoiler=True),
                reply_markup=markup
            )
    except BadRequest:
        try:
            await query.edit_message_caption(caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            pass

async def init_market_system():
    await SearchEngine.build_index()
    
    await sell_listings.create_index([("seller_id", 1)])
    await sell_listings.create_index([("price", 1)])
    await sell_listings.create_index([("listed_at", -1)])
    await sell_listings.create_index([("character.name", "text"), ("character.anime", "text")])
    
    await sell_history.create_index([("seller_id", 1)])
    await sell_history.create_index([("buyer_id", 1)])
    await sell_history.create_index([("sold_at", -1)])
    
    await price_analytics.create_index([("char_id", 1)])
    
    await market_notifications.create_index([("user_id", 1)])
    
    print("✅ Market system initialized with indexes and search engine")

asyncio.create_task(init_market_system())

application.add_handler(CommandHandler("sell", sell, block=False))
application.add_handler(CommandHandler("unsell", unsell, block=False))
application.add_handler(CommandHandler("market", market, block=False))
application.add_handler(CommandHandler("mymarket", mymarket, block=False))
application.add_handler(CommandHandler("msales", msales, block=False))
application.add_handler(CommandHandler("msearch", msearch, block=False))
application.add_handler(CommandHandler("mtrends", mtrends, block=False))
application.add_handler(CommandHandler("lists", lists, block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^market_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^bi_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^cf_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^stats_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^seller_", block=False))
application.add_handler(CallbackQueryHandler(market_callback, pattern=r"^alert_", block=False))