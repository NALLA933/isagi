from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

from shivu import application, db, user_collection

collection = db['anime_characters_lol']
shop_collection = db['shop']
shop_history_collection = db['shop_history']

SUDO_USERS = ["8297659126", "8420981179", "5147822244"]


class ShopStatus(Enum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    OWNED = "owned"


@dataclass
class Character:
    id: str
    name: str
    anime: str
    img_url: str
    rarity: str
    
    @classmethod
    def from_db(cls, data: dict):
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
    
    @classmethod
    def from_db(cls, data: dict):
        return cls(
            id=data.get('id', ''),
            price=data.get('price', 0),
            original_price=data.get('original_price', 0),
            discount=data.get('discount', 0),
            final_price=data.get('final_price', 0),
            added_by=data.get('added_by', 0),
            added_at=data.get('added_at', datetime.utcnow()),
            limit=data.get('limit'),
            sold=data.get('sold', 0),
            featured=data.get('featured', False),
            views=data.get('views', 0)
        )
    
    @property
    def is_sold_out(self) -> bool:
        return self.limit is not None and self.sold >= self.limit
    
    @property
    def stock_display(self) -> str:
        if self.limit is None:
            return "∞"
        return f"{self.sold}/{self.limit}"


@dataclass
class UserData:
    id: int
    balance: int
    characters: List[dict] = field(default_factory=list)
    
    @classmethod
    async def fetch(cls, user_id: int):
        data = await user_collection.find_one({"id": user_id})
        if not data:
            return cls(id=user_id, balance=0, characters=[])
        return cls(
            id=data.get('id', user_id),
            balance=data.get('balance', 0),
            characters=data.get('characters', [])
        )
    
    def owns_character(self, char_id: str) -> bool:
        return any(c.get("id") == char_id for c in self.characters)


class ShopUI:
    
    @staticmethod
    def build_caption(character: Character, shop_item: ShopItem, 
                     page: int, total: int, status: ShopStatus) -> str:
        
        status_emoji = {
            ShopStatus.SOLD_OUT: "🚫 SOLD OUT",
            ShopStatus.OWNED: "✅ OWNED",
            ShopStatus.AVAILABLE: "⭐ FEATURED" if shop_item.featured else ""
        }
        
        caption_lines = [
            f"╭─「 🏪 <b>SHOP</b> {status_emoji[status]} 」",
            f"│",
            f"│ ✨ <b>{character.name}</b>",
            f"│ 🎭 <code>{character.anime}</code>",
            f"│"
        ]
        
        if shop_item.discount > 0:
            caption_lines.append(f"│ 💰 <s>{shop_item.price:,}</s> → <b>{shop_item.final_price:,}</b> ɢᴏʟᴅ")
            caption_lines.append(f"│ 🏷️ <b>{shop_item.discount}%</b> OFF")
        else:
            caption_lines.append(f"│ 💰 <b>{shop_item.final_price:,}</b> ɢᴏʟᴅ")
        
        caption_lines.extend([
            f"│",
            f"│ 📦 Stock: <code>{shop_item.stock_display}</code>",
            f"│ 👁️ Views: <code>{shop_item.views:,}</code>",
            f"│",
            f"╰─「 {page}/{total} 」"
        ])
        
        return "\n".join(caption_lines)
    
    @staticmethod
    def build_keyboard(shop_item: ShopItem, status: ShopStatus, 
                      page: int, total_pages: int) -> InlineKeyboardMarkup:
        keyboard = []
        
        if status == ShopStatus.AVAILABLE:
            keyboard.append([
                InlineKeyboardButton("💳 BUY NOW", callback_data=f"shop_buy_{shop_item.id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("🚫 UNAVAILABLE", callback_data="shop_na")
            ])
        
        if total_pages > 1:
            nav_row = []
            if page > 1:
                nav_row.append(InlineKeyboardButton("◀️", callback_data=f"shop_page_{page-1}"))
            nav_row.append(InlineKeyboardButton(f"• {page}/{total_pages} •", callback_data="shop_info"))
            if page < total_pages:
                nav_row.append(InlineKeyboardButton("▶️", callback_data=f"shop_page_{page+1}"))
            keyboard.append(nav_row)
        
        keyboard.append([
            InlineKeyboardButton("🏷️ Discounts", callback_data="shop_filter_discount"),
            InlineKeyboardButton("⭐ Featured", callback_data="shop_filter_featured"),
            InlineKeyboardButton("🔄", callback_data="shop_refresh")
        ])
        
        return InlineKeyboardMarkup(keyboard)


class ShopManager:
    
    @staticmethod
    async def is_sudo(user_id: int) -> bool:
        return str(user_id) in SUDO_USERS
    
    @staticmethod
    async def add_item(char_id: str, price: int, limit: Optional[int] = None,
                      discount: int = 0, featured: bool = False, 
                      added_by: int = 0) -> tuple[bool, str]:
        
        character = await collection.find_one({"id": char_id})
        if not character:
            return False, "⚠️ Character not found"
        
        existing = await shop_collection.find_one({"id": char_id})
        if existing:
            return False, "⚠️ Already in shop"
        
        final_price = int(price * (1 - discount / 100))
        
        await shop_collection.insert_one({
            "id": char_id,
            "price": price,
            "original_price": price,
            "discount": discount,
            "final_price": final_price,
            "added_by": added_by,
            "added_at": datetime.utcnow(),
            "limit": limit,
            "sold": 0,
            "featured": featured,
            "views": 0
        })
        
        msg = f"✅ <b>Added to Shop</b>\n\n"
        msg += f"✨ {character['name']}\n"
        msg += f"💰 {price:,} → <b>{final_price:,}</b> gold\n"
        msg += f"📦 Limit: {'∞' if not limit else limit}"
        
        return True, msg
    
    @staticmethod
    async def remove_item(char_id: str) -> tuple[bool, str]:
        result = await shop_collection.delete_one({"id": char_id})
        if result.deleted_count:
            return True, "🗑️ Removed from shop"
        return False, "⚠️ Not found in shop"
    
    @staticmethod
    async def get_items(filter_type: Optional[str] = None) -> List[dict]:
        query = {}
        if filter_type == "discount":
            query = {"discount": {"$gt": 0}}
        elif filter_type == "featured":
            query = {"featured": True}
        
        return await shop_collection.find(query).sort([
            ("featured", -1),
            ("added_at", -1)
        ]).to_list(None)
    
    @staticmethod
    async def purchase(user_id: int, char_id: str) -> tuple[bool, str]:
        shop_item_data = await shop_collection.find_one({"id": char_id})
        if not shop_item_data:
            return False, "⚠️ Item not found"
        
        shop_item = ShopItem.from_db(shop_item_data)
        character_data = await collection.find_one({"id": char_id})
        character = Character.from_db(character_data)
        user_data = await UserData.fetch(user_id)
        
        if shop_item.is_sold_out:
            return False, "🚫 Sold out"
        
        if user_data.owns_character(char_id):
            return False, "✅ Already owned"
        
        if user_data.balance < shop_item.final_price:
            return False, f"⚠️ Need {shop_item.final_price:,} gold\n💰 Balance: {user_data.balance:,}"
        
        await user_collection.update_one(
            {"id": user_id},
            {
                "$inc": {"balance": -shop_item.final_price},
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
            "price": shop_item.final_price,
            "purchase_date": datetime.utcnow()
        })
        
        return True, f"✨ Purchased {character.name} for {shop_item.final_price:,} gold!"


async def shop_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    filter_type = context.args[0].lower() if context.args else None
    if filter_type not in [None, "discount", "featured"]:
        filter_type = None
    
    items = await ShopManager.get_items(filter_type)
    
    if not items:
        await update.message.reply_text(
            "╭─「 🏪 <b>SHOP</b> 」\n"
            "│\n"
            "│ Empty shop!\n"
            "│ Check back later\n"
            "│\n"
            "╰─────────",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Refresh", callback_data="shop_refresh")
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
    
    if shop_item.is_sold_out:
        status = ShopStatus.SOLD_OUT
    elif user_data.owns_character(char_id):
        status = ShopStatus.OWNED
    else:
        status = ShopStatus.AVAILABLE
    
    caption = ShopUI.build_caption(character, shop_item, page, len(items), status)
    keyboard = ShopUI.build_keyboard(shop_item, status, page, len(items))
    
    context.user_data['shop_page'] = page
    
    try:
        if edit:
            await message.edit_caption(
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            send_func = message.reply_video if character.is_video else message.reply_photo
            media_param = "video" if character.is_video else "photo"
            await send_func(
                **{media_param: character.img_url},
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    except BadRequest:
        if not edit:
            await message.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)


async def shop_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("shop_page_"):
        page = int(data.split("_")[2])
        await render_shop_page(query.message, context, user_id, page, edit=True)
    
    elif data == "shop_refresh":
        page = context.user_data.get('shop_page', 1)
        filter_type = context.user_data.get('shop_filter')
        items = await ShopManager.get_items(filter_type)
        context.user_data['shop_items'] = [item['id'] for item in items]
        await render_shop_page(query.message, context, user_id, page, edit=True)
    
    elif data.startswith("shop_filter_"):
        filter_type = data.split("_")[2]
        items = await ShopManager.get_items(filter_type)
        if items:
            context.user_data['shop_items'] = [item['id'] for item in items]
            context.user_data['shop_filter'] = filter_type
            await render_shop_page(query.message, context, user_id, 1, edit=True)
        else:
            await query.answer(f"⚠️ No {filter_type} items", show_alert=True)
    
    elif data.startswith("shop_buy_"):
        char_id = data.split("_", 2)[2]
        success, message = await ShopManager.purchase(user_id, char_id)
        await query.answer(message, show_alert=True)
        if success:
            page = context.user_data.get('shop_page', 1)
            await render_shop_page(query.message, context, user_id, page, edit=True)
    
    elif data == "shop_na":
        await query.answer("⚠️ This item is unavailable", show_alert=False)
    
    elif data == "shop_info":
        await query.answer("Use arrow buttons to navigate", show_alert=False)


async def shop_add_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await ShopManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Usage:\n<code>/sadd &lt;id&gt; &lt;price&gt; [limit] [discount%] [featured]</code>",
            parse_mode="HTML"
        )
        return
    
    char_id = context.args[0]
    price = int(context.args[1])
    limit = None if len(context.args) < 3 or context.args[2].lower() in ["0", "unlimited"] else int(context.args[2])
    discount = max(0, min(int(context.args[3]), 90)) if len(context.args) >= 4 else 0
    featured = len(context.args) >= 5 and context.args[4].lower() in ["yes", "true", "1"]
    
    success, message = await ShopManager.add_item(
        char_id, price, limit, discount, featured, user_id
    )
    
    await update.message.reply_text(message, parse_mode="HTML")


async def shop_remove_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not await ShopManager.is_sudo(user_id):
        await update.message.reply_text("⛔️ No permission")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text("⚠️ Usage: <code>/srm &lt;id&gt;</code>", parse_mode="HTML")
        return
    
    char_id = context.args[0]
    success, message = await ShopManager.remove_item(char_id)
    await update.message.reply_text(message, parse_mode="HTML")


async def shop_history_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    history = await shop_history_collection.find(
        {"user_id": user_id}
    ).sort("purchase_date", -1).limit(10).to_list(10)
    
    if not history:
        await update.message.reply_text(
            "╭─「 📜 <b>HISTORY</b> 」\n"
            "│\n"
            "│ No purchases yet\n"
            "│\n"
            "╰─────────",
            parse_mode="HTML"
        )
        return
    
    lines = ["╭─「 📜 <b>PURCHASE HISTORY</b> 」", "│"]
    total = 0
    
    for i, record in enumerate(history, 1):
        char = await collection.find_one({"id": record["character_id"]})
        name = char.get("name", "Unknown") if char else "Unknown"
        price = record.get("price", 0)
        total += price
        lines.append(f"│ {i}. {name}")
        lines.append(f"│    💰 {price:,} gold")
    
    lines.extend([
        "│",
        f"│ 💳 Total: <b>{total:,}</b> gold",
        "│",
        "╰─────────"
    ])
    
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


application.add_handler(CommandHandler("shop", shop_command, block=False))
application.add_handler(CommandHandler("sadd", shop_add_command, block=False))
application.add_handler(CommandHandler("srm", shop_remove_command, block=False))
application.add_handler(CommandHandler("shist", shop_history_command, block=False))
application.add_handler(CallbackQueryHandler(shop_callback_handler, pattern=r"^shop_", block=False))