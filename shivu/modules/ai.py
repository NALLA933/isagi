from html import escape
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from cachetools import TTLCache
import aiohttp

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from shivu import shivuu as app
from shivu import db

# Collections
user_settings_collection = db['ai_image_settings']

# Available models
MODELS = {
    "flux": "Flux",
    "flux-realism": "Flux Realism",
    "flux-anime": "Flux Anime",
    "flux-3d": "Flux 3D",
    "turbo": "Turbo (Fast)",
    "any-dark": "Any Dark",
}

# Default settings
DEFAULT_SETTINGS = {
    "model": "flux",
    "enhance": True,
    "nologo": True,
    "private": False,
    "width": 1024,
    "height": 1024,
}

# Cache for user settings
settings_cache = TTLCache(maxsize=1000, ttl=3600)


async def get_user_settings(user_id: int) -> Dict:
    """Get user settings from cache or database"""
    if user_id in settings_cache:
        return settings_cache[user_id]
    
    settings = await user_settings_collection.find_one({"user_id": user_id})
    if not settings:
        settings = {"user_id": user_id, **DEFAULT_SETTINGS}
        await user_settings_collection.insert_one(settings)
    
    settings_cache[user_id] = settings
    return settings


async def update_user_settings(user_id: int, updates: Dict):
    """Update user settings in cache and database"""
    await user_settings_collection.update_one(
        {"user_id": user_id},
        {"$set": updates},
        upsert=True
    )
    settings = await get_user_settings(user_id)
    settings.update(updates)
    settings_cache[user_id] = settings


def build_pollinations_url(prompt: str, settings: Dict) -> str:
    """Build Pollinations AI URL with parameters"""
    model = settings.get("model", "flux")
    enhance = settings.get("enhance", True)
    nologo = settings.get("nologo", True)
    width = settings.get("width", 1024)
    height = settings.get("height", 1024)
    
    # Build URL
    url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
    params = []
    
    if model and model != "flux":
        params.append(f"model={model}")
    if enhance:
        params.append("enhance=true")
    if nologo:
        params.append("nologo=true")
    params.append(f"width={width}")
    params.append(f"height={height}")
    
    if params:
        url += "?" + "&".join(params)
    
    return url


def get_settings_keyboard(settings: Dict) -> InlineKeyboardMarkup:
    """Create settings keyboard"""
    current_model = settings.get("model", "flux")
    enhance = settings.get("enhance", True)
    nologo = settings.get("nologo", True)
    private = settings.get("private", False)
    
    keyboard = [
        [InlineKeyboardButton(
            f"🎨 Model: {MODELS.get(current_model, 'Flux')}",
            callback_data="ai_setting_model"
        )],
        [InlineKeyboardButton(
            f"✨ Enhance: {'✅' if enhance else '❌'}",
            callback_data="ai_toggle_enhance"
        )],
        [InlineKeyboardButton(
            f"🚫 No Logo: {'✅' if nologo else '❌'}",
            callback_data="ai_toggle_nologo"
        )],
        [InlineKeyboardButton(
            f"🔒 Private: {'✅' if private else '❌'}",
            callback_data="ai_toggle_private"
        )],
        [InlineKeyboardButton(
            "📐 Resolution",
            callback_data="ai_setting_resolution"
        )],
        [InlineKeyboardButton("🔙 Close", callback_data="ai_close")]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_model_keyboard() -> InlineKeyboardMarkup:
    """Create model selection keyboard"""
    keyboard = []
    for model_id, model_name in MODELS.items():
        keyboard.append([InlineKeyboardButton(
            model_name,
            callback_data=f"ai_model_{model_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="ai_back_settings")])
    return InlineKeyboardMarkup(keyboard)


def get_resolution_keyboard() -> InlineKeyboardMarkup:
    """Create resolution selection keyboard"""
    resolutions = [
        ("1024x1024 (Square)", "1024x1024"),
        ("1280x720 (Landscape)", "1280x720"),
        ("720x1280 (Portrait)", "720x1280"),
        ("1920x1080 (HD)", "1920x1080"),
        ("1080x1920 (Vertical HD)", "1080x1920"),
    ]
    
    keyboard = []
    for name, res in resolutions:
        keyboard.append([InlineKeyboardButton(
            name,
            callback_data=f"ai_res_{res}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="ai_back_settings")])
    return InlineKeyboardMarkup(keyboard)


@app.on_message(filters.command(["ai", "imagine", "generate"]))
async def ai_image_command(client: Client, message: Message):
    """Generate AI image"""
    user_id = message.from_user.id
    
    if len(message.command) < 2:
        return await message.reply(
            "**🎨 AI Image Generator**\n\n"
            "**Usage:**\n"
            "`/ai <prompt>` - Generate an image\n"
            "`/aisettings` - Configure settings\n\n"
            "**Example:**\n"
            "`/ai anime girl with green eyes`"
        )
    
    prompt = message.text.split(None, 1)[1]
    settings = await get_user_settings(user_id)
    
    # Check if private mode
    private = settings.get("private", False)
    
    status_msg = await message.reply("🎨 Generating your image... Please wait.")
    
    try:
        url = build_pollinations_url(prompt, settings)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    await status_msg.edit("⚠️ Failed to generate image. Please try again.")
                    return
                img_data = await resp.read()
        
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        caption = (
            f"🎨 **Prompt:** `{escape(prompt)}`\n"
            f"🤖 **Model:** {model_name}\n"
            f"✨ **Enhanced:** {'Yes' if settings.get('enhance') else 'No'}\n"
            f"👤 **Generated by:** {message.from_user.mention}"
        )
        
        # Send image
        if private:
            # Send to user privately
            await client.send_photo(
                chat_id=user_id,
                photo=img_data,
                caption=caption
            )
            await status_msg.edit("✅ Image sent to your private chat!")
        else:
            # Send to current chat
            await message.reply_photo(
                photo=img_data,
                caption=caption
            )
            await status_msg.delete()
            
    except Exception as e:
        await status_msg.edit(f"❌ Error: {str(e)}")


@app.on_message(filters.command(["aisettings", "aiconfig"]))
async def ai_settings_command(client: Client, message: Message):
    """Show AI settings"""
    user_id = message.from_user.id
    settings = await get_user_settings(user_id)
    
    model_name = MODELS.get(settings.get("model", "flux"), "Flux")
    
    text = (
        "**⚙️ AI Image Generator Settings**\n\n"
        f"🎨 **Current Model:** {model_name}\n"
        f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
        f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
        f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
        f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
        "Click the buttons below to change settings:"
    )
    
    await message.reply(
        text,
        reply_markup=get_settings_keyboard(settings)
    )


@app.on_callback_query(filters.regex("^ai_"))
async def ai_callback_handler(client: Client, callback: CallbackQuery):
    """Handle AI settings callbacks"""
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "ai_close":
        await callback.message.delete()
        return
    
    settings = await get_user_settings(user_id)
    
    if data == "ai_setting_model":
        await callback.message.edit_text(
            "**🎨 Select AI Model:**\n\n"
            "Choose the model for image generation:",
            reply_markup=get_model_keyboard()
        )
    
    elif data.startswith("ai_model_"):
        model = data.replace("ai_model_", "")
        await update_user_settings(user_id, {"model": model})
        await callback.answer(f"✅ Model set to {MODELS.get(model)}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        
        text = (
            "**⚙️ AI Image Generator Settings**\n\n"
            f"🎨 **Current Model:** {model_name}\n"
            f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
            f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
            "Click the buttons below to change settings:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )
    
    elif data == "ai_toggle_enhance":
        new_value = not settings.get("enhance", True)
        await update_user_settings(user_id, {"enhance": new_value})
        await callback.answer(f"✅ Enhance {'enabled' if new_value else 'disabled'}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        
        text = (
            "**⚙️ AI Image Generator Settings**\n\n"
            f"🎨 **Current Model:** {model_name}\n"
            f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
            f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
            "Click the buttons below to change settings:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )
    
    elif data == "ai_toggle_nologo":
        new_value = not settings.get("nologo", True)
        await update_user_settings(user_id, {"nologo": new_value})
        await callback.answer(f"✅ No Logo {'enabled' if new_value else 'disabled'}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        
        text = (
            "**⚙️ AI Image Generator Settings**\n\n"
            f"🎨 **Current Model:** {model_name}\n"
            f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
            f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
            "Click the buttons below to change settings:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )
    
    elif data == "ai_toggle_private":
        new_value = not settings.get("private", False)
        await update_user_settings(user_id, {"private": new_value})
        await callback.answer(f"✅ Private mode {'enabled' if new_value else 'disabled'}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        
        text = (
            "**⚙️ AI Image Generator Settings**\n\n"
            f"🎨 **Current Model:** {model_name}\n"
            f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
            f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
            "Click the buttons below to change settings:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )
    
    elif data == "ai_setting_resolution":
        await callback.message.edit_text(
            "**📐 Select Resolution:**\n\n"
            "Choose the image resolution:",
            reply_markup=get_resolution_keyboard()
        )
    
    elif data.startswith("ai_res_"):
        resolution = data.replace("ai_res_", "")
        width, height = map(int, resolution.split("x"))
        await update_user_settings(user_id, {"width": width, "height": height})
        await callback.answer(f"✅ Resolution set to {resolution}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        
        text = (
            "**⚙️ AI Image Generator Settings**\n\n"
            f"🎨 **Current Model:** {model_name}\n"
            f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
            f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
            "Click the buttons below to change settings:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )
    
    elif data == "ai_back_settings":
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        
        text = (
            "**⚙️ AI Image Generator Settings**\n\n"
            f"🎨 **Current Model:** {model_name}\n"
            f"✨ **Enhance:** {'Enabled' if settings.get('enhance') else 'Disabled'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private Mode:** {'On' if settings.get('private') else 'Off'}\n"
            f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n\n"
            "Click the buttons below to change settings:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )