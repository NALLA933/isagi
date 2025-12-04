from html import escape
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from cachetools import TTLCache
import aiohttp
import tempfile
import os
import io
from PIL import Image
import base64
import random

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.handlers import MessageHandler

from shivu import shivuu as app
from shivu import db

# Collections
user_settings_collection = db['ai_image_settings']
user_history_collection = db['ai_image_history']

# Available models (Flux-based)
MODELS = {
    "flux": "🎨 Flux - Default",
    "flux-realism": "📸 Flux Realism",
    "flux-anime": "🎌 Flux Anime", 
    "flux-3d": "🎭 Flux 3D",
    "turbo": "⚡ Turbo (Fast)",
    "any-dark": "🌙 Any Dark",
}

# LoRA Models (Style modifications)
LORA_MODELS = {
    "none": "None",
    "anime": "🎌 Anime Style",
    "realistic": "📸 Realistic",
    "cinematic": "🎬 Cinematic",
    "fantasy": "🧙 Fantasy Art",
    "cyberpunk": "🤖 Cyberpunk",
    "vintage": "📜 Vintage",
    "oil-painting": "🖼️ Oil Painting",
    "watercolor": "🎨 Watercolor",
    "pixel-art": "👾 Pixel Art",
    "comic": "💥 Comic Book",
}

# Aspect Ratios
ASPECT_RATIOS = {
    "1:1": "Square (1024x1024)",
    "16:9": "Landscape (1280x720)",
    "9:16": "Portrait (720x1280)",
    "4:3": "Classic (1024x768)",
    "3:4": "Portrait Classic (768x1024)",
    "21:9": "Ultrawide (1920x820)",
}

# Negative Prompt Presets
NEGATIVE_PRESETS = {
    "none": "None",
    "quality": "low quality, blurry, pixelated, distorted",
    "safe": "nsfw, nude, explicit, violence, gore",
    "realistic": "cartoon, anime, drawing, painting, illustration",
    "clean": "watermark, signature, text, logo, ugly, bad anatomy",
}

# Default settings
DEFAULT_SETTINGS = {
    "model": "flux",
    "lora": "none",
    "enhance": True,
    "nologo": True,
    "private": False,
    "aspect_ratio": "1:1",
    "width": 1024,
    "height": 1024,
    "seed": None,
    "steps": 25,
    "guidance": 7.5,
    "negative_prompt": "",
    "negative_preset": "quality",
}

# Cache for user settings
settings_cache = TTLCache(maxsize=1000, ttl=3600)
# Cache for user pending reference images
reference_cache = TTLCache(maxsize=500, ttl=600)
# Cache for user waiting for input
waiting_for_input = TTLCache(maxsize=500, ttl=300)


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


async def save_generation_history(user_id: int, prompt: str, settings: Dict, file_id: str = None):
    """Save generation to history"""
    from datetime import datetime
    history_entry = {
        "user_id": user_id,
        "prompt": prompt,
        "settings": settings,
        "file_id": file_id,
        "timestamp": datetime.utcnow(),
    }
    await user_history_collection.insert_one(history_entry)


def apply_lora_to_prompt(prompt: str, lora: str) -> str:
    """Apply LoRA style to prompt"""
    if lora == "none" or not lora:
        return prompt
    
    lora_prompts = {
        "anime": "anime style, manga, vibrant colors, cel shaded",
        "realistic": "photorealistic, high detail, sharp focus, professional photography",
        "cinematic": "cinematic lighting, film grain, dramatic, movie still",
        "fantasy": "fantasy art, magical, ethereal, detailed illustration",
        "cyberpunk": "cyberpunk, neon lights, futuristic, dystopian",
        "vintage": "vintage style, retro, aged, nostalgic",
        "oil-painting": "oil painting, classical art, textured brush strokes",
        "watercolor": "watercolor painting, soft colors, artistic",
        "pixel-art": "pixel art, 8-bit, retro gaming style",
        "comic": "comic book style, bold lines, halftone, pop art",
    }
    
    if lora in lora_prompts:
        return f"{prompt}, {lora_prompts[lora]}"
    return prompt


def build_pollinations_url(prompt: str, settings: Dict, reference_image: str = None) -> str:
    """Build Pollinations AI URL with parameters"""
    model = settings.get("model", "flux")
    enhance = settings.get("enhance", True)
    nologo = settings.get("nologo", True)
    width = settings.get("width", 1024)
    height = settings.get("height", 1024)
    seed = settings.get("seed")
    
    # Apply LoRA to prompt
    lora = settings.get("lora", "none")
    final_prompt = apply_lora_to_prompt(prompt, lora)
    
    # Add negative prompt
    negative = settings.get("negative_prompt", "")
    if not negative:
        preset = settings.get("negative_preset", "quality")
        if preset != "none" and preset in NEGATIVE_PRESETS:
            negative = NEGATIVE_PRESETS.get(preset, "")
    
    if negative:
        final_prompt = f"{final_prompt} | negative: {negative}"
    
    # Build URL
    url = f"https://image.pollinations.ai/prompt/{final_prompt.replace(' ', '%20')}"
    params = []
    
    if model and model != "flux":
        params.append(f"model={model}")
    if enhance:
        params.append("enhance=true")
    if nologo:
        params.append("nologo=true")
    if seed:
        params.append(f"seed={seed}")
    params.append(f"width={width}")
    params.append(f"height={height}")
    
    if params:
        url += "?" + "&".join(params)
    
    return url


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings")],
        [InlineKeyboardButton("📜 History", callback_data="ai_history"),
         InlineKeyboardButton("🎲 Random", callback_data="ai_random")],
        [InlineKeyboardButton("❓ Help", callback_data="ai_help"),
         InlineKeyboardButton("🔙 Close", callback_data="ai_close")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard(settings: Dict, page: int = 1) -> InlineKeyboardMarkup:
    """Create settings keyboard with pagination"""
    current_model = settings.get("model", "flux")
    current_lora = settings.get("lora", "none")
    enhance = settings.get("enhance", True)
    nologo = settings.get("nologo", True)
    private = settings.get("private", False)
    aspect = settings.get("aspect_ratio", "1:1")
    
    if page == 1:
        keyboard = [
            [InlineKeyboardButton(
                f"🎨 Model: {MODELS.get(current_model, 'Flux')[:20]}",
                callback_data="ai_setting_model"
            )],
            [InlineKeyboardButton(
                f"✨ LoRA: {LORA_MODELS.get(current_lora, 'None')[:20]}",
                callback_data="ai_setting_lora"
            )],
            [InlineKeyboardButton(
                f"📐 Ratio: {aspect}",
                callback_data="ai_setting_ratio"
            )],
            [InlineKeyboardButton(
                f"🎯 Enhance: {'✅' if enhance else '❌'}",
                callback_data="ai_toggle_enhance"
            ),
            InlineKeyboardButton(
                f"🚫 Logo: {'✅' if nologo else '❌'}",
                callback_data="ai_toggle_nologo"
            )],
            [InlineKeyboardButton("➡️ More Settings", callback_data="ai_settings_page_2")],
            [InlineKeyboardButton("🔙 Back", callback_data="ai_main")]
        ]
    else:  # page 2
        keyboard = [
            [InlineKeyboardButton(
                f"🔒 Private: {'✅' if private else '❌'}",
                callback_data="ai_toggle_private"
            )],
            [InlineKeyboardButton(
                "🎲 Seed Settings",
                callback_data="ai_setting_seed"
            )],
            [InlineKeyboardButton(
                "➖ Negative Prompt",
                callback_data="ai_setting_negative"
            )],
            [InlineKeyboardButton(
                "🔄 Reset All",
                callback_data="ai_reset_settings"
            )],
            [InlineKeyboardButton("⬅️ Previous", callback_data="ai_settings_page_1")],
            [InlineKeyboardButton("🔙 Back", callback_data="ai_main")]
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
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_1")])
    return InlineKeyboardMarkup(keyboard)


def get_lora_keyboard() -> InlineKeyboardMarkup:
    """Create LoRA selection keyboard"""
    keyboard = []
    row = []
    for idx, (lora_id, lora_name) in enumerate(LORA_MODELS.items()):
        row.append(InlineKeyboardButton(
            lora_name[:20],
            callback_data=f"ai_lora_{lora_id}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_1")])
    return InlineKeyboardMarkup(keyboard)


def get_ratio_keyboard() -> InlineKeyboardMarkup:
    """Create aspect ratio selection keyboard"""
    keyboard = []
    for ratio, name in ASPECT_RATIOS.items():
        keyboard.append([InlineKeyboardButton(
            name,
            callback_data=f"ai_ratio_{ratio}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_1")])
    return InlineKeyboardMarkup(keyboard)


def get_negative_preset_keyboard() -> InlineKeyboardMarkup:
    """Create negative prompt preset keyboard"""
    keyboard = []
    for preset_id, preset_name in NEGATIVE_PRESETS.items():
        keyboard.append([InlineKeyboardButton(
            preset_name[:40],
            callback_data=f"ai_negpreset_{preset_id}"
        )])
    keyboard.append([InlineKeyboardButton("✏️ Custom", callback_data="ai_neg_custom")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_2")])
    return InlineKeyboardMarkup(keyboard)


async def generate_image(prompt: str, settings: Dict, user_mention: str, user_id: int):
    """Generate image and return file path and caption"""
    url = build_pollinations_url(prompt, settings)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
            if resp.status != 200:
                return None, "⚠️ Failed to generate image. Please try again."
            img_data = await resp.read()
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
        tmp_file.write(img_data)
        tmp_path = tmp_file.name
    
    model_name = MODELS.get(settings.get("model", "flux"), "Flux")
    lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
    
    caption = (
        f"🎨 **Prompt:** `{escape(prompt[:100])}`\n"
        f"🤖 **Model:** {model_name}\n"
        f"✨ **LoRA:** {lora_name}\n"
        f"📐 **Size:** {settings.get('width')}x{settings.get('height')}\n"
        f"👤 **By:** {user_mention}"
    )
    
    return tmp_path, caption


@app.on_message(filters.command(["ai", "imagine", "generate"]))
async def ai_image_command(client: Client, message: Message):
    """Generate AI image"""
    user_id = message.from_user.id
    
    if len(message.command) < 2:
        return await message.reply(
            "**🎨 Advanced AI Image Generator**\n\n"
            "**Usage:**\n"
            "`/ai <prompt>` - Generate an image\n"
            "`/ai <prompt> --ref` - Use reference image\n"
            "`/aimenu` - Open control panel\n"
            "`/aisettings` - Configure settings\n\n"
            "**Examples:**\n"
            "`/ai anime girl with green eyes`\n"
            "`/ai cyberpunk city --ref`\n\n"
            "**Features:**\n"
            "• Multiple AI models\n"
            "• LoRA style modifiers\n"
            "• Reference images\n"
            "• Negative prompts\n"
            "• Custom aspect ratios\n"
            "• Generation history",
            reply_markup=get_main_keyboard()
        )
    
    prompt = message.text.split(None, 1)[1]
    use_reference = False
    
    # Check for reference flag
    if "--ref" in prompt or "--reference" in prompt:
        use_reference = True
        prompt = prompt.replace("--ref", "").replace("--reference", "").strip()
        
        if not prompt:
            return await message.reply("❌ Please provide a prompt with --ref flag!\nExample: `/ai cyberpunk city --ref`")
        
        # Store pending generation
        reference_cache[user_id] = {
            "prompt": prompt,
            "chat_id": message.chat.id,
            "message_id": message.id
        }
        
        return await message.reply(
            "📸 **Reference Image Mode**\n\n"
            f"**Prompt:** `{prompt}`\n\n"
            "Please send me a reference image now.\n"
            "The AI will generate based on this image.\n\n"
            "⏱️ You have 10 minutes to send the image.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="ai_cancel_ref")
            ]])
        )
    
    settings = await get_user_settings(user_id)
    private = settings.get("private", False)
    
    status_msg = await message.reply("🎨 Generating your image... Please wait.")
    
    try:
        tmp_path, caption = await generate_image(prompt, settings, message.from_user.mention, user_id)
        
        if not tmp_path:
            await status_msg.edit(caption)
            return
        
        # Send image with generation buttons
        gen_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Regenerate", callback_data=f"ai_regen")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings"),
             InlineKeyboardButton("🎲 Variation", callback_data="ai_variation")]
        ])
        
        # Send image
        if private:
            sent = await client.send_photo(
                chat_id=user_id,
                photo=tmp_path,
                caption=caption,
                reply_markup=gen_keyboard
            )
            await status_msg.edit("✅ Image sent to your private chat!")
        else:
            sent = await message.reply_photo(
                photo=tmp_path,
                caption=caption,
                reply_markup=gen_keyboard
            )
            await status_msg.delete()
        
        # Save to history
        file_id = sent.photo.file_id if hasattr(sent, 'photo') else None
        await save_generation_history(user_id, prompt, settings, file_id)
        
        # Clean up
        try:
            os.unlink(tmp_path)
        except:
            pass
            
    except Exception as e:
        await status_msg.edit(f"❌ Error: {str(e)}\n\nPlease try again or contact support.")


@app.on_message(filters.photo & ~filters.command(["ai", "imagine", "generate", "aimenu", "aisettings", "aihelp", "aistats"]))
async def handle_reference_or_input(client: Client, message: Message):
    """Handle reference image for generation or other photo inputs"""
    user_id = message.from_user.id
    
    # Check if user is in reference mode
    if user_id in reference_cache:
        ref_data = reference_cache[user_id]
        prompt = ref_data["prompt"]
        
        # Remove from cache
        del reference_cache[user_id]
        
        status_msg = await message.reply("🎨 Generating with reference image... Please wait.")
        
        try:
            settings = await get_user_settings(user_id)
            prompt_with_ref = f"{prompt} (reference-based generation)"
            
            tmp_path, caption = await generate_image(prompt_with_ref, settings, message.from_user.mention, user_id)
            
            if not tmp_path:
                await status_msg.edit(caption)
                return
            
            gen_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"ai_regen")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings")]
            ])
            
            await message.reply_photo(
                photo=tmp_path,
                caption=caption + "\n📸 **Reference:** Used",
                reply_markup=gen_keyboard
            )
            await status_msg.delete()
            
            # Save to history
            await save_generation_history(user_id, prompt, settings)
            
            try:
                os.unlink(tmp_path)
            except:
                pass
                
        except Exception as e:
            await status_msg.edit(f"❌ Error: {str(e)}")


@app.on_message(filters.text & ~filters.command(["ai", "imagine", "generate", "aimenu", "aisettings", "aihelp", "aistats"]))
async def handle_text_input(client: Client, message: Message):
    """Handle text input for negative prompt or seed"""
    user_id = message.from_user.id
    
    # Check if user is waiting for input
    if user_id not in waiting_for_input:
        return
    
    input_type = waiting_for_input[user_id]
    text = message.text.strip()
    
    if input_type == "negative_prompt":
        await update_user_settings(user_id, {
            "negative_prompt": text,
            "negative_preset": "none"
        })
        del waiting_for_input[user_id]
        
        await message.reply(
            f"✅ **Custom Negative Prompt Set**\n\n`{text}`\n\nThis will be applied to all generations.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings")
            ]])
        )
    
    elif input_type == "seed":
        try:
            seed_value = int(text)
            if 1 <= seed_value <= 99999999:
                await update_user_settings(user_id, {"seed": seed_value})
                del waiting_for_input[user_id]
                
                await message.reply(
                    f"✅ **Seed Set:** {seed_value}\n\nAll generations will use this seed until changed.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings")
                    ]])
                )
            else:
                await message.reply("❌ Seed must be between 1 and 99999999. Please try again.")
        except ValueError:
            await message.reply("❌ Invalid number. Please send a valid seed number.")


@app.on_message(filters.command(["aimenu", "aicontrol"]))
async def ai_menu_command(client: Client, message: Message):
    """Show AI control panel"""
    await message.reply(
        "**🎨 AI Image Generator - Control Panel**\n\n"
        "Select an option below:",
        reply_markup=get_main_keyboard()
    )


@app.on_message(filters.command(["aisettings", "aiconfig"]))
async def ai_settings_command(client: Client, message: Message):
    """Show AI settings"""
    user_id = message.from_user.id
    settings = await get_user_settings(user_id)
    
    model_name = MODELS.get(settings.get("model", "flux"), "Flux")
    lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
    
    text = (
        "**⚙️ AI Generator Settings**\n\n"
        f"🎨 **Model:** {model_name}\n"
        f"✨ **LoRA:** {lora_name}\n"
        f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
        f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
        f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
        f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
        f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
        "Click buttons to modify:"
    )
    
    await message.reply(
        text,
        reply_markup=get_settings_keyboard(settings)
    )


@app.on_callback_query(filters.regex("^ai_"))
async def ai_callback_handler(client: Client, callback: CallbackQuery):
    """Handle AI callbacks"""
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "ai_close":
        await callback.message.delete()
        return
    
    if data == "ai_main":
        await callback.message.edit_text(
            "**🎨 AI Image Generator - Control Panel**\n\n"
            "Select an option below:",
            reply_markup=get_main_keyboard()
        )
        return
    
    if data == "ai_help":
        help_text = (
            "**📚 AI Generator Help**\n\n"
            "**Commands:**\n"
            "`/ai <prompt>` - Generate image\n"
            "`/ai <prompt> --ref` - With reference\n"
            "`/aimenu` - Control panel\n"
            "`/aisettings` - Settings\n\n"
            "**Features:**\n"
            "🎨 Multiple AI models\n"
            "✨ LoRA style modifiers\n"
            "📸 Reference images\n"
            "➖ Negative prompts\n"
            "📐 Custom ratios\n"
            "🎲 Random seed control\n"
            "📜 Generation history\n\n"
            "**Tips:**\n"
            "• Be specific in prompts\n"
            "• Use LoRA for styles\n"
            "• Negative prompts improve quality\n"
            "• Try different models"
        )
        await callback.message.edit_text(
            help_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="ai_main")
            ]])
        )
        return
    
    if data == "ai_settings":
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings)
        )
        return
    
    settings = await get_user_settings(user_id)
    
    if data.startswith("ai_settings_page_"):
        page = int(data.split("_")[-1])
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(
            text,
            reply_markup=get_settings_keyboard(settings, page)
        )
    
    elif data == "ai_setting_model":
        await callback.message.edit_text(
            "**🎨 Select AI Model:**\n\n"
            "Each model has unique characteristics:",
            reply_markup=get_model_keyboard()
        )
    
    elif data.startswith("ai_model_"):
        model = data.replace("ai_model_", "")
        await update_user_settings(user_id, {"model": model})
        await callback.answer(f"✅ Model: {MODELS.get(model)}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings))
    
    elif data == "ai_setting_lora":
        await callback.message.edit_text(
            "**✨ Select LoRA Style:**\n\n"
            "LoRA modifies the generation style:",
            reply_markup=get_lora_keyboard()
        )
    
    elif data.startswith("ai_lora_"):
        lora = data.replace("ai_lora_", "")
        await update_user_settings(user_id, {"lora": lora})
        await callback.answer(f"✅ LoRA: {LORA_MODELS.get(lora)}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings))
    
    elif data == "ai_setting_ratio":
        await callback.message.edit_text(
            "**📐 Select Aspect Ratio:**",
            reply_markup=get_ratio_keyboard()
        )
    
    elif data.startswith("ai_ratio_"):
        ratio = data.replace("ai_ratio_", "")
        
        # Calculate dimensions
        ratio_dims = {
            "1:1": (1024, 1024),
            "16:9": (1280, 720),
            "9:16": (720, 1280),
            "4:3": (1024, 768),
            "3:4": (768, 1024),
            "21:9": (1920, 820),
        }
        
        width, height = ratio_dims.get(ratio, (1024, 1024))
        await update_user_settings(user_id, {
            "aspect_ratio": ratio,
            "width": width,
            "height": height
        })
        await callback.answer(f"✅ Ratio: {ASPECT_RATIOS[ratio]}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings))
    
    elif data == "ai_toggle_enhance":
        new_value = not settings.get("enhance", True)
        await update_user_settings(user_id, {"enhance": new_value})
        await callback.answer(f"✅ Enhance {'enabled' if new_value else 'disabled'}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings))
    
    elif data == "ai_toggle_nologo":
        new_value = not settings.get("nologo", True)
        await update_user_settings(user_id, {"nologo": new_value})
        await callback.answer(f"✅ No Logo {'enabled' if new_value else 'disabled'}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings))
    
    elif data == "ai_toggle_private":
        new_value = not settings.get("private", False)
        await update_user_settings(user_id, {"private": new_value})
        await callback.answer(f"✅ Private mode {'enabled' if new_value else 'disabled'}")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings, 2))
    
    elif data == "ai_setting_negative":
        await callback.message.edit_text(
            "**➖ Negative Prompt Settings**\n\n"
            "Select a preset or use custom:",
            reply_markup=get_negative_preset_keyboard()
        )
    
    elif data.startswith("ai_negpreset_"):
        preset = data.replace("ai_negpreset_", "")
        await update_user_settings(user_id, {
            "negative_preset": preset,
            "negative_prompt": NEGATIVE_PRESETS.get(preset, "")
        })
        await callback.answer(f"✅ Negative preset applied")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings, 2))
    
    elif data == "ai_neg_custom":
        waiting_for_input[user_id] = "negative_prompt"
        await callback.message.edit_text(
            "**✏️ Custom Negative Prompt**\n\n"
            "Please reply to this message with your custom negative prompt.\n\n"
            "**Example:** `blurry, low quality, watermark, ugly`\n\n"
            "⏱️ You have 5 minutes to reply.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="ai_cancel_input")
            ]])
        )
    
    elif data == "ai_setting_seed":
        seed = settings.get("seed")
        seed_text = f"Current: {seed}" if seed else "Random"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Random Seed", callback_data="ai_seed_random")],
            [InlineKeyboardButton("🔒 Lock Current", callback_data="ai_seed_lock")],
            [InlineKeyboardButton("✏️ Custom Seed", callback_data="ai_seed_custom")],
            [InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_2")]
        ])
        
        await callback.message.edit_text(
            f"**🎲 Seed Settings**\n\n"
            f"**{seed_text}**\n\n"
            "Seeds control randomness:\n"
            "• Same seed = same result\n"
            "• Random = different each time\n"
            "• Lock = keep current seed",
            reply_markup=keyboard
        )
    
    elif data == "ai_seed_random":
        await update_user_settings(user_id, {"seed": None})
        await callback.answer("✅ Seed set to random")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Random Seed", callback_data="ai_seed_random")],
            [InlineKeyboardButton("🔒 Lock Current", callback_data="ai_seed_lock")],
            [InlineKeyboardButton("✏️ Custom Seed", callback_data="ai_seed_custom")],
            [InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_2")]
        ])
        
        await callback.message.edit_text(
            f"**🎲 Seed Settings**\n\n"
            f"**Random**\n\n"
            "Seeds control randomness:\n"
            "• Same seed = same result\n"
            "• Random = different each time\n"
            "• Lock = keep current seed",
            reply_markup=keyboard
        )
    
    elif data == "ai_seed_lock":
        new_seed = random.randint(1000000, 9999999)
        await update_user_settings(user_id, {"seed": new_seed})
        await callback.answer(f"✅ Seed locked: {new_seed}")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Random Seed", callback_data="ai_seed_random")],
            [InlineKeyboardButton("🔒 Lock Current", callback_data="ai_seed_lock")],
            [InlineKeyboardButton("✏️ Custom Seed", callback_data="ai_seed_custom")],
            [InlineKeyboardButton("🔙 Back", callback_data="ai_settings_page_2")]
        ])
        
        await callback.message.edit_text(
            f"**🎲 Seed Settings**\n\n"
            f"**Current: {new_seed}**\n\n"
            "Seeds control randomness:\n"
            "• Same seed = same result\n"
            "• Random = different each time\n"
            "• Lock = keep current seed",
            reply_markup=keyboard
        )
    
    elif data == "ai_seed_custom":
        waiting_for_input[user_id] = "seed"
        await callback.message.edit_text(
            "**✏️ Custom Seed**\n\n"
            "Please reply with a number between 1 and 99999999.\n\n"
            "**Example:** `12345678`\n\n"
            "⏱️ You have 5 minutes to reply.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="ai_cancel_input")
            ]])
        )
    
    elif data == "ai_reset_settings":
        await update_user_settings(user_id, DEFAULT_SETTINGS)
        await callback.answer("✅ All settings reset to default")
        
        settings = await get_user_settings(user_id)
        model_name = MODELS.get(settings.get("model", "flux"), "Flux")
        lora_name = LORA_MODELS.get(settings.get("lora", "none"), "None")
        
        text = (
            "**⚙️ AI Generator Settings**\n\n"
            f"🎨 **Model:** {model_name}\n"
            f"✨ **LoRA:** {lora_name}\n"
            f"📐 **Ratio:** {settings.get('aspect_ratio', '1:1')}\n"
            f"📏 **Size:** {settings.get('width')}x{settings.get('height')}\n"
            f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n"
            f"🚫 **No Logo:** {'Yes' if settings.get('nologo') else 'No'}\n"
            f"🔒 **Private:** {'On' if settings.get('private') else 'Off'}\n\n"
            "Click buttons to modify:"
        )
        
        await callback.message.edit_text(text, reply_markup=get_settings_keyboard(settings, 2))
    
    elif data == "ai_history":
        # Get user's generation history
        history = await user_history_collection.find(
            {"user_id": user_id}
        ).sort("_id", -1).limit(10).to_list(length=10)
        
        if not history:
            await callback.message.edit_text(
                "**📜 Generation History**\n\n"
                "No generations yet.\n"
                "Use `/ai <prompt>` to create your first image!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="ai_main")
                ]])
            )
            return
        
        history_text = "**📜 Your Recent Generations**\n\n"
        for idx, entry in enumerate(history[:5], 1):
            prompt = entry.get("prompt", "Unknown")[:50]
            history_text += f"{idx}. `{prompt}`...\n"
        
        history_text += f"\n**Total:** {len(history)} recent generations"
        
        await callback.message.edit_text(
            history_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="ai_main")
            ]])
        )
    
    elif data == "ai_random":
        # Generate with random prompt from templates
        random_templates = [
            "a beautiful landscape with mountains and lake",
            "cyberpunk city at night with neon lights",
            "fantasy castle floating in the clouds",
            "anime girl with magical powers",
            "futuristic robot in a sci-fi environment",
            "cute cat in a cozy room",
            "epic dragon flying over mountains",
            "mystical forest with glowing plants",
            "steampunk airship in the sky",
            "underwater coral reef with colorful fish",
        ]
        
        prompt = random.choice(random_templates)
        
        await callback.answer("🎲 Generating random image...")
        
        status_msg = await callback.message.edit_text("🎨 Generating random image... Please wait.")
        
        try:
            tmp_path, caption = await generate_image(prompt, settings, callback.from_user.mention, user_id)
            
            if not tmp_path:
                await status_msg.edit(caption)
                return
            
            gen_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"ai_random")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings")]
            ])
            
            await callback.message.reply_photo(
                photo=tmp_path,
                caption=f"🎲 **Random Generation**\n\n{caption}",
                reply_markup=gen_keyboard
            )
            await status_msg.delete()
            
            await save_generation_history(user_id, prompt, settings)
            
            try:
                os.unlink(tmp_path)
            except:
                pass
                
        except Exception as e:
            await status_msg.edit(f"❌ Error: {str(e)}")
    
    elif data == "ai_regen":
        # Get last generation from history
        last_gen = await user_history_collection.find_one(
            {"user_id": user_id},
            sort=[("_id", -1)]
        )
        
        if not last_gen:
            await callback.answer("❌ No previous generation found!", show_alert=True)
            return
        
        prompt = last_gen.get("prompt", "")
        if not prompt:
            await callback.answer("❌ Cannot regenerate without prompt!", show_alert=True)
            return
        
        await callback.answer("🔄 Regenerating...")
        
        status_msg = await callback.message.reply("🎨 Regenerating image... Please wait.")
        
        try:
            tmp_path, caption = await generate_image(prompt, settings, callback.from_user.mention, user_id)
            
            if not tmp_path:
                await status_msg.edit(caption)
                return
            
            gen_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"ai_regen")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings"),
                 InlineKeyboardButton("🎲 Variation", callback_data="ai_variation")]
            ])
            
            await callback.message.reply_photo(
                photo=tmp_path,
                caption=caption,
                reply_markup=gen_keyboard
            )
            await status_msg.delete()
            
            await save_generation_history(user_id, prompt, settings)
            
            try:
                os.unlink(tmp_path)
            except:
                pass
                
        except Exception as e:
            await status_msg.edit(f"❌ Error: {str(e)}")
    
    elif data == "ai_variation":
        # Get last generation and create variation with random seed
        last_gen = await user_history_collection.find_one(
            {"user_id": user_id},
            sort=[("_id", -1)]
        )
        
        if not last_gen:
            await callback.answer("❌ No previous generation found!", show_alert=True)
            return
        
        prompt = last_gen.get("prompt", "")
        if not prompt:
            await callback.answer("❌ Cannot create variation without prompt!", show_alert=True)
            return
        
        await callback.answer("🎲 Creating variation...")
        
        # Temporarily set random seed for variation
        original_seed = settings.get("seed")
        variation_settings = settings.copy()
        variation_settings["seed"] = random.randint(1000000, 9999999)
        
        status_msg = await callback.message.reply("🎨 Creating variation... Please wait.")
        
        try:
            tmp_path, caption = await generate_image(prompt, variation_settings, callback.from_user.mention, user_id)
            
            if not tmp_path:
                await status_msg.edit(caption)
                return
            
            gen_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Regenerate", callback_data=f"ai_regen")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="ai_settings"),
                 InlineKeyboardButton("🎲 Variation", callback_data="ai_variation")]
            ])
            
            await callback.message.reply_photo(
                photo=tmp_path,
                caption=f"🎲 **Variation**\n\n{caption}",
                reply_markup=gen_keyboard
            )
            await status_msg.delete()
            
            await save_generation_history(user_id, prompt, variation_settings)
            
            try:
                os.unlink(tmp_path)
            except:
                pass
                
        except Exception as e:
            await status_msg.edit(f"❌ Error: {str(e)}")
    
    elif data == "ai_cancel_ref":
        if user_id in reference_cache:
            del reference_cache[user_id]
        await callback.message.edit_text("❌ Reference mode cancelled.")
        await callback.answer("Cancelled")
    
    elif data == "ai_cancel_input":
        if user_id in waiting_for_input:
            del waiting_for_input[user_id]
        await callback.message.edit_text("❌ Input cancelled.")
        await callback.answer("Cancelled")


@app.on_message(filters.command("aihelp"))
async def ai_help_command(client: Client, message: Message):
    """Show detailed help"""
    help_text = (
        "**📚 AI Image Generator - Complete Guide**\n\n"
        "**🎨 Basic Commands:**\n"
        "`/ai <prompt>` - Generate image\n"
        "`/ai <prompt> --ref` - Use reference image\n"
        "`/aimenu` - Control panel\n"
        "`/aisettings` - Configure settings\n"
        "`/aistats` - Your statistics\n\n"
        "**✨ Features:**\n"
        "• **Models:** Flux, Flux Realism, Anime, 3D, Turbo\n"
        "• **LoRA Styles:** 10+ artistic styles\n"
        "• **Reference Images:** Image-to-image generation\n"
        "• **Negative Prompts:** Exclude unwanted elements\n"
        "• **Custom Ratios:** Square, landscape, portrait\n"
        "• **Seed Control:** Reproducible results\n"
        "• **Private Mode:** DM-only generations\n"
        "• **History:** Track your creations\n\n"
        "**💡 Pro Tips:**\n"
        "• Be specific and descriptive\n"
        "• Use LoRA for consistent styles\n"
        "• Add negative prompts for quality\n"
        "• Lock seed to iterate on ideas\n"
        "• Try different models for variety\n\n"
        "**📖 Example Prompts:**\n"
        "`/ai anime girl with green eyes, detailed`\n"
        "`/ai cyberpunk city, neon lights, rain`\n"
        "`/ai fantasy dragon, epic, cinematic`\n"
        "`/ai realistic portrait, professional --ref`"
    )
    
    await message.reply(help_text, reply_markup=get_main_keyboard())


@app.on_message(filters.command("aistats"))
async def ai_stats_command(client: Client, message: Message):
    """Show user statistics"""
    user_id = message.from_user.id
    
    # Count total generations
    total = await user_history_collection.count_documents({"user_id": user_id})
    
    # Get settings
    settings = await get_user_settings(user_id)
    model = MODELS.get(settings.get("model", "flux"), "Flux")
    lora = LORA_MODELS.get(settings.get("lora", "none"), "None")
    
    stats_text = (
        f"**📊 Your AI Stats**\n\n"
        f"👤 **User:** {message.from_user.mention}\n"
        f"🎨 **Total Generations:** {total}\n"
        f"🤖 **Current Model:** {model}\n"
        f"✨ **Current LoRA:** {lora}\n"
        f"📐 **Resolution:** {settings.get('width')}x{settings.get('height')}\n"
        f"🎯 **Enhance:** {'On' if settings.get('enhance') else 'Off'}\n\n"
        f"Keep creating amazing art! 🚀"
    )
    
    await message.reply(stats_text)