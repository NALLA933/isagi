from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
from functools import wraps
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest, TimedOut, NetworkError
from telegram.constants import ParseMode, ChatAction

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
shop_collection = db['shop']
shop_history_collection = db['shop_history']

SUDO_USERS = {"8297659126", "8420981179", "5147822244"}

logger = logging.getLogger(__name__)


def typing_action(func):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.message:
            await update.message.chat.send_action(ChatAction.TYPING)
        return await func(update, context, *args, **kwargs)
    return wrapper


class ShopStatus(Enum):
    AVAILABLE = "✅"
    SOLD_OUT = "🚫"
    OWNED = "👑"
    FEATURED = "⭐"


class CacheManager:
    _cache: Dict[str, tuple[Any, float]] = {}
    TTL = 60
    
    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        if key in cls._cache:
            data, timestamp = cls._cache[key]
            if datetime.now(timezone.utc).timestamp() - timestamp < cls.TTL:
                return data
            del cls._cache[key]
        return None
    
    @classmethod
    async def set(cls, key: str, value: Any):
        cls._cache[key] = (value, datetime.now(timezone.utc).timestamp())
    
    @classmethod
    def invalidate(cls, pattern: str = None):
        if pattern:
            keys = [k for k in cls._cache.keys() if pattern in k]
            for k in keys:
                del cls._cache[k]
        else:
            cls._cache.clear()


@dataclass
class Character:
    id: str
    name: str
    anime: str
    img_url: str
    rarity: str
    
    @classmethod
    def from_db(cls, data: dict) -> 'Character':
        return cls(
            id=data.get('id', ''),
            name=data.get('name', 'Unknown'),
            anime=data.get('anime', 'Unknown'),
            img_url=data.get('img_url', ''),
            rarity=data.get('rarity', '')
        )
    
    @property
    def is_video(self) -> bool:
        return self.rarity == "🎥 AMV"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShopItem:
    id: str
    price: int
    original_price: int
    discount: int
    final_price: int
    added_by: int
    added_at: datetime
    limit: Optional[int]
    sold: int
    featured: bool
    views: int
    tags: List[str] = field(default_factory=list)
    
    @classmethod
    def from_db(cls, data: dict) -> 'ShopItem':
        return cls(
            id=data.get('id', ''),
            price=data.get('price', 0),
            original_price=data.get('original_price', 0),
            discount=data.get('discount', 0),
            final_price=data.get('final_price', 0),
            added_by=data.get('added_by', 0),
            added_at=data.get('added_at', datetime.now(timezone.utc)),
            limit=data.get('limit'),
            sold=data.get('sold', 0),
            featured=data.get('featured', False),
            views=data.get('views', 0),
            tags=data.get('tags', [])
        )
    
    @property
    def is_sold_out(self) -> bool:
        return self.limit is not None and self.sold >= self.limit
    
    @property
    def stock_display(self) -> str:
        if self.limit is None:
            return "∞"
        remaining = self.limit - self.sold
        return f"{remaining}/{self.limit}"
    
    @property
    def discount_badge(self) -> str:
        if self.discount >= 50:
            return "🔥 HOT"
        elif self.discount >= 30:
            return "💥 SALE"
        elif self.discount > 0:
            return "🏷️ OFF"
        return ""
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['added_at'] = self.added_at.isoformat()
        return data


@dataclass
class UserData:
    id: int
    balance: int
    characters: List[dict] = field(default_factory=list)
    purchase_count: int = 0
    total_spent: int = 0
    
    @classmethod
    async def fetch(cls, user_id: int) -> 'UserData':
        cache_key = f"user_{user_id}"
        cached = await CacheManager.get(cache_key)
        if cached:
            return cached
        
        data = await user_collection.find_one({"id": user_id})
        if not data:
            user = cls(id=user_id, balance=0, characters=[])
        else:
            user = cls(
                id=data.get('id', user_id),
                balance=data.get('balance', 0),
                characters=data.get('characters', []),
                purchase_count=data.get('purchase_count', 0),
                total_spent=data.get('total_spent', 0)
            )
        
        await CacheManager.set(cache_key, user)
        return user
    
    def owns_character(self, char_id: str) -> bool:
        return any(c.get("id") == char_id for c in self.characters)


class ShopUI:
    
    @staticmethod
    def build_caption(character: Character, shop_item: ShopItem, 
                     page: int, total: int, status: ShopStatus) -> str:
        
        status_icons = {
            ShopStatus.SOLD_OUT: "🚫 SOLD OUT",
            ShopStatus.OWNED: "👑 OWNED",
            ShopStatus.FEATURED: "⭐ FEATURED",
            ShopStatus.AVAILABLE: ""
        }
        
        header = "╔═══════════════════════╗\n"
        header += f"║   🏪 <b>PREMIUM SHOP</b>   ║\n"
        header += "╠═══════════════════════╣\n"
        
        status_text = status_icons.get(status, "")
        if shop_item.featured and status == ShopStatus.AVAILABLE:
            status_text = status_icons[ShopStatus.FEATURED]
        
        if status_text:
            header += f"║ {status_text:^21} ║\n"
            header += "╠═══════════════════════╣\n"
        
        body_lines = [
            f"║",
            f"║ ✨ <b>{character.name[:19]}</b>",
            f"║ 🎭 <code>{character.anime[:19]}</code>",
            f"║"
        ]
        
        if shop_item.discount > 0:
            badge = shop_item.discount_badge
            body_lines.extend([
                f"║ 💰 <s>{shop_item.price:,}</s> → <b>{shop_item.final_price:,}</b>",
                f"║ {badge} <b>{shop_item.discount}%</b> DISCOUNT"
            ])
        else:
            body_lines.append(f"║ 💰 <b>{shop_item.final_price:,}</b> GOLD")
        
        body_lines.extend([
            f"║",
            f"║ 📦 Stock: <code>{shop_item.stock_display}</code>",
            f"║ 👁️ Views: <code>{shop_item.views:,}</code>"
        ])
        
        if shop_item.tags:
            tags_str = " ".join([f"#{tag}" for tag in shop_item.tags[:2]])
            body_lines.append(f"║ 🏷️ {tags_str}")
        
        footer = f"║\n╚═══════════════════════╝\n"
        footer += f"<code>Page {page}/{total}</code>"
        
        return header + "\n".join(body_lines) + footer
    
    @staticmethod
    def build_keyboard(shop_item: ShopItem, status: ShopStatus, 
                      page: int, total_pages: int, user_balance: int) -> InlineKeyboardMarkup:
        keyboard = []
        
        if status == ShopStatus.AVAILABLE:
            can_afford = user_balance >= shop_item.final_price
            buy_text = "💳 BUY NOW" if can_afford else f"💰 Need {shop_item.final_price - user_balance:,}"
            keyboard.append([
                InlineKeyboardButton(
                    buy_text, 
                    callback_data=f"sb9x_{shop_item.id}" if can_afford else "sn4f"
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("🚫 UNAVAILABLE", callback_data="sn4f")
            ])
        
        if total_pages > 1:
            nav_row = []
            if page > 1:
                nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"sp7g_{page-1}"))
            nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="si3n"))
            if page < total_pages:
                nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"sp7g_{page+1}"))
            keyboard.append(nav_row)
        
        keyboard.append([
            InlineKeyboardButton("🏷️ Discounts", callback_data="sf8t_discount"),
            InlineKeyboardButton("⭐ Featured", callback_data="sf8t_featured")
        ])
        
        keyboard.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="sr5h"),
            InlineKeyboardButton("📊 Stats", callback_data="ss2t")
        ])
        
        return InlineKeyboardMarkup(keyboard)


class ShopManager:
    
    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        return str(user_id) in SUDO_USERS
    
    @staticmethod
    async def add_item(char_id: str, price: int, limit: Optional[int] = None,
                      discount: int = 0, featured: bool = False, 
                      added_by: int = 0, tags: List[str] = None) -> tuple[bool, str]:
        
        character = await collection.find_one({"id": char_id})
        if not character:
            return False, "⚠️ Character not found in database"
        
        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            return False, "⚠️ Character already listed in shop"
        
        final_price = int(price * (1 - discount / 100))
        
        shop_data = {
            "id": char_id,
            "price": price,
            "original_price": price,
            "discount": discount,
            "final_price": final_price,
            "added_by": added_by,
            "added_at": datetime.now(timezone.utc),
            "limit": limit,
            "sold": 0,
            "featured": featured,
            "views": 0,
            "tags": tags or []
        }
        
        await shop_collection.insert_one(shop_data)
        CacheManager.invalidate("shop_items")
        
        msg = "╔═══════════════════════╗\n"
        msg += "║  ✅ <b>ADDED TO SHOP</b>  ║\n"
        msg += "╚═══════════════════════╝\n\n"
        msg += f"✨ <b>{character['name']}</b>\n"
        msg += f"💰 <s>{price:,}</s> → <b>{final_price:,}</b> gold\n" if discount > 0 else f"💰 <b>{final_price:,}</b> gold\n"
        msg += f"📦 Stock: {'∞' if not limit else limit}\n"
        if featured:
            msg += "⭐ <b>FEATURED ITEM</b>"
        
        return True, msg
    
    @staticmethod
    async def remove_item(char_id: str) -> tuple[bool, str]:
        result = await shop_collection.delete_one({"id": char_id})
        if result.deleted_count:
            CacheManager.invalidate("shop_items")
            return True, "🗑️ Successfully removed from shop"
        return False, "⚠️ Item not found in shop"
    
    @staticmethod
    async def get_items(filter_type: Optional[str] = None) -> List[dict]:
        cache_key = f"shop_items_{filter_type or 'all'}"
        cached = await CacheManager.get(cache_key)
        if cached:
            return cached
        
        query = {}
        if filter_type == "discount":
            query = {"discount": {"$gt": 0}}
        elif filter_type == "featured":
            query = {"featured": True}
        
        items = await shop_collection.find(query).sort([
            ("featured", -1),
            ("discount", -1),
            ("added_at", -1)
        ]).to_list(None)
        
        await CacheManager.set(cache_key, items)
        return items
    
    @staticmethod
    async def purchase(user_id: int, char_id: str) -> tuple[bool, str]:
        shop_item_data = await shop_collection.find_one({"id": char_id})
        if not shop_item_data:
            return False, "⚠️ Item not found in shop"
        
        shop_item = ShopItem.from_db(shop_item_data)
        character_data = await collection.find_one({"id": char_id})
        character = Character.from_db(character_data)
        user_data = await UserData.fetch(user_id)
        
        if shop_item.is_sold_out:
            return False, "🚫 Item sold out"
        
        if user_data.owns_character(char_id):
            return False, "✅ You already own this character"
        
        if user_data.balance < shop_item.final_price:
            deficit = shop_item.final_price - user_data.balance
            return False, f"⚠️ Insufficient balance\n💰 Need: {deficit:,} more gold\n💳 Balance: {user_data.balance:,}"
        
        async with asyncio.Lock():
            current_item = await shop_collection.find_one({"id": char_id})
            if current_item and current_item.get('limit'):
                if current_item.get('sold', 0) >= current_item['limit']:
                    return False, "🚫 Item just sold out"
            
            await user_collection.update_one(
                {"id": user_id},
                {
                    "$inc": {
                        "balance": -shop_item.final_price,
                        "purchase_count": 1,
                        "total_spent": shop_item.final_price
                    },
                    "$push": {"characters": character_data}
                },
                upsert=True
            )
            
            await shop_collection.update_one(
                {"id": char_id},
                {"$inc": {"sold": 1}}
            )
            
            await shop_history_collection.insert_one({
                "user_id": user_id,
                "character_id": char_id,
                "character_name": character.name,
                "price": shop_item.final_price,
                "discount_applied": shop_item.discount,
                "purchase_date": datetime.now(timezone.utc)
            })
        
        CacheManager.invalidate(f"user_{user_id}")
        CacheManager.invalidate("shop_items")
        
        msg = "╔═══════════════════════╗\n"
        msg += "║ ✨ <b>PURCHASE SUCCESS</b> ║\n"
        msg += "╚═══════════════════════╝\n\n"
        msg += f"🎉 You got <b>{character.name}</b>!\n"
        msg += f"💰 Paid: <b>{shop_item.final_price:,}</b> gold\n"
        msg += f"💳 Remaining: <b>{user_data.balance - shop_item.final_price:,}</b> gold"
        
        return True, msg


@typing_action
async def shop_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    filter_type = context.args[0].lower() if context.args else None
    if filter_type not in [None, "discount", "featured"]:
        filter_type = None
    
    items = await ShopManager.get_items(filter_type)
    
    if not items:
        no_items_msg = "╔═══════════════════════╗\n"
        no_items_msg += "║   🏪 <b>SHOP EMPTY</b>   ║\n"
        no_items_msg += "╚═══════════════════════╝\n\n"
        no_items_msg += "No items available\n"
        no_items_msg += "Check back later!"
        
        await update.message.reply_text(
            no_items_msg,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Refresh", callback_data="sr5h")
            ]])
        )
        return
    
    context.user_data['shop_items'] = [item['id'] for item in items]
    context.user_data['shop_page'] = 1
    context.user_data['shop_filter'] = filter_type
    
    await render_shop_page(update.message, context, user_id, 1)


async def render_shop_page(message, context: CallbackContext, 
                          user_id: int, page: int, edit: bool = False):
    items = context.user_data.get('shop_items', [])
    if not items or page < 1 or page > len(items):
        return
    
    char_id = items[page - 1]
    
    character_data = await collection.find_one({"id": char_id})
    shop_item_data = await shop_collection.find_one({"id": char_id})
    
    if not character_data or not shop_item_data:
        return
    
    character = Character.from_db(character_data)
    shop_item = ShopItem.from_db(shop_item_data)
    user_data = await UserData.fetch(user_id)
    
    await shop_collection.update_one({"id": char_id}, {"$inc": {"views": 1}})
    CacheManager.invalidate("shop_items")
    
    if shop_item.is_sold_out:
        status = ShopStatus.SOLD_OUT
    elif user_data.owns_character(char_id):
        status = ShopStatus.OWNED
    elif shop_item.featured:
        status = ShopStatus.FEATURED
    else:
        status = ShopStatus.AVAILABLE
    
    caption = ShopUI.build_caption(character, shop_item, page, len(items), status)
    keyboard = ShopUI.build_keyboard(shop_item, status, page, len(items), user_data.balance)
    
    context.user_data['shop_page'] = page
    
    try:
        if edit:
            await message.edit_caption(
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        else:
            send_func = message.reply_video if character.is_video else message.reply_photo
            media_param = "video" if character.is_video else "photo"
            await send_func(
                **{media_param: character.img_url},
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
    except (BadRequest, TimedOut, NetworkError) as e:
        logger.error(f"Error rendering shop page: {e}")
        if not edit:
            await message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def shop_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    try:
        if data.startswith("sp7g_"):
            page = int(data.split("_")[1])
            await render_shop_page(query.message, context, user_id, page, edit=True)
        
        elif data == "sr5h":
            page = context.user_data.get('shop_page', 1)
            filter_type = context.user_data.get('shop_filter')
            CacheManager.invalidate("shop_items")
            items = await ShopManager.get_items(filter_type)
            context.user_data['shop_items'] = [item['id'] for item in items]
            await render_shop_page(query.message, context, user_id, page, edit=True)
        
        elif data.startswith("sf8t_"):
            filter_type = data.split("_")[1]
            items = await ShopManager.get_items(filter_type)
            if items:
                context.user_data['shop_items'] = [item['id'] for item in items]
                context.user_data['shop_filter'] = filter_type
                await render_shop_page(query.message, context, user_id, 1, edit=True)
            else:
                await query.answer(f"⚠️ No {filter_type} items available", show_alert=True)
        
        elif data.startswith("sb9x_"):
            char_id = data.split("_", 1)[1]
            success, message = await ShopManager.purchase(user_id, char_id)
            await query.answer(message, show_alert=True)
            if success:
                await asyncio.sleep(1)
                page = context.user_data.get('shop_page', 1)
                await render_shop_page(query.message, context, user_id, page, edit=True)
        
        elif data == "ss2t":
            user_data = await UserData.fetch(user_id)
            stats_msg = f"📊 <b>YOUR STATS</b>\n\n"
            stats_msg += f"💰 Balance: <b>{user_data.balance:,}</b>\n"
            stats_msg += f"🛒 Purchases: <b>{user_data.purchase_count}</b>\n"
            stats_msg += f"💸 Total Spent: <b>{user_data.total_spent:,}</b>\n"
            stats_msg += f"👥 Characters: <b>{len(user_data.characters)}</b>"
            await query.answer(stats_msg, show_alert=True)
        
        elif data == "sn4f":
            await query.answer("⚠️ This item is unavailable", show_alert=False)
        
        elif data == "si3n":
            await query.answer("📄 Use arrow buttons to navigate", show_alert=False)
    
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.answer("⚠️ An error occurred", show_alert=True)


@typing_action
async def shop_add_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await ShopManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n"
            "<code>/sadd &lt;id&gt; &lt;price&gt; [limit] [discount%] [featured] [tags]</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/sadd char123 5000</code>\n"
            "<code>/sadd char123 5000 10 20 yes rare,limited</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    char_id = context.args[0]
    price = int(context.args[1])
    limit = None if len(context.args) < 3 or context.args[2].lower() in ["0", "unlimited"] else int(context.args[2])
    discount = max(0, min(int(context.args[3]), 90)) if len(context.args) >= 4 else 0
    featured = len(context.args) >= 5 and context.args[4].lower() in ["yes", "true", "1"]
    tags = context.args[5].split(",") if len(context.args) >= 6 else []
    
    success, message = await ShopManager.add_item(
        char_id, price, limit, discount, featured, user_id, tags
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


@typing_action
async def shop_remove_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await ShopManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/srm &lt;id&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    char_id = context.args[0]
    success, message = await ShopManager.remove_item(char_id)
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


@typing_action
async def shop_history_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    history = await shop_history_collection.find(
        {"user_id": user_id}
    ).sort("purchase_date", -1).limit(15).to_list(15)
    
    if not history:
        msg = "╔═══════════════════════╗\n"
        msg += "║  📜 <b>NO PURCHASES</b>  ║\n"
        msg += "╚═══════════════════════╝\n\n"
        msg += "You haven't bought\nanything yet!"
        
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return
    
    user_data = await UserData.fetch(user_id)
    
    lines = [
        "╔═══════════════════════╗",
        "║ 📜 <b>PURCHASE HISTORY</b> ║",
        "╚═══════════════════════╝\n"
    ]
    
    for i, record in enumerate(history, 1):
        name = record.get("character_name", "Unknown")
        price = record.get("price", 0)
        discount = record.get("discount_applied", 0)
        
        lines.append(f"<b>{i}.</b> {name[:20]}")
        if discount > 0:
            lines.append(f"   💰 {price:,} <code>({discount}% off)</code>")
        else:
            lines.append(f"   💰 {price:,} gold")
        lines.append("")
    
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🛒 Total Purchases: <b>{user_data.purchase_count}</b>",
        f"💸 Total Spent: <b>{user_data.total_spent:,}</b> gold"
    ])
    
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


application.add_handler(CommandHandler("shop", shop_command, block=False))
application.add_handler(CommandHandler("sadd", shop_add_command, block=False))
application.add_handler(CommandHandler("srm", shop_remove_command, block=False))
application.add_handler(CommandHandler("shist", shop_history_command, block=False))
application.add_handler(CallbackQueryHandler(shop_callback_handler, pattern=r"^s[bfprin][0-9][a-z]", block=False))