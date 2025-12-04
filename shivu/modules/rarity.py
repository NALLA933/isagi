import traceback
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from shivu import application, db, LOGGER

spawn_settings_collection = db['spawn_settings']
group_rarity_collection = db['group_rarity_spawns']

RARITY_MAP = {
    1: "🟢 Common", 2: "🟣 Rare", 3: "🟡 Legendary", 4: "💮 Special Edition",
    5: "💫 Neon", 6: "✨ Manga", 7: "🎭 Cosplay", 8: "🎐 Celestial",
    9: "🔮 Premium Edition", 10: "💋 Erotic", 11: "🌤 Summer", 12: "☃️ Winter",
    13: "☔️ Monsoon", 14: "💝 Valentine", 15: "🎃 Halloween", 16: "🎄 Christmas",
    17: "🏵 Mythic", 18: "🎗 Special Events", 19: "🎥 AMV", 20: "👼 Tiny"
}

DEFAULT_RARITIES = {
    '🟢': {'name': 'Common', 'enabled': True, 'chance': 25.0},
    '🟣': {'name': 'Rare', 'enabled': True, 'chance': 20.0},
    '🟡': {'name': 'Legendary', 'enabled': True, 'chance': 10.0},
    '💮': {'name': 'Special Edition', 'enabled': True, 'chance': 8.0},
    '💫': {'name': 'Neon', 'enabled': True, 'chance': 7.0},
    '✨': {'name': 'Manga', 'enabled': True, 'chance': 6.0},
    '🎭': {'name': 'Cosplay', 'enabled': True, 'chance': 5.0},
    '🎐': {'name': 'Celestial', 'enabled': True, 'chance': 4.0},
    '🔮': {'name': 'Premium Edition', 'enabled': True, 'chance': 3.0},
    '💋': {'name': 'Erotic', 'enabled': True, 'chance': 2.5},
    '🌤': {'name': 'Summer', 'enabled': True, 'chance': 2.0},
    '☃️': {'name': 'Winter', 'enabled': True, 'chance': 2.0},
    '☔️': {'name': 'Monsoon', 'enabled': True, 'chance': 1.5},
    '💝': {'name': 'Valentine', 'enabled': True, 'chance': 1.0},
    '🎃': {'name': 'Halloween', 'enabled': True, 'chance': 1.0},
    '🎄': {'name': 'Christmas', 'enabled': True, 'chance': 1.0},
    '🏵': {'name': 'Mythic', 'enabled': True, 'chance': 0.5},
    '🎗': {'name': 'Special Events', 'enabled': True, 'chance': 0.3},
    '🎥': {'name': 'AMV', 'enabled': True, 'chance': 0.15},
    '👼': {'name': 'Tiny', 'enabled': True, 'chance': 0.1},
}

OWNER_ID = 8420981179

EMOJI_TO_NAME = {
    '🟢': 'common', '🟣': 'rare', '🟡': 'legendary', '💮': 'special',
    '💫': 'neon', '✨': 'manga', '🎭': 'cosplay', '🎐': 'celestial',
    '🔮': 'premium', '💋': 'erotic', '🌤': 'summer', '☃️': 'winter',
    '☔️': 'monsoon', '💝': 'valentine', '🎃': 'halloween', '🎄': 'christmas',
    '🏵': 'mythic', '🎗': 'events', '🎥': 'amv', '👼': 'tiny'
}
NAME_TO_EMOJI = {v: k for k, v in EMOJI_TO_NAME.items()}


async def get_spawn_settings():
    try:
        settings = await spawn_settings_collection.find_one({'type': 'rarity_control'})
        if not settings:
            settings = {'type': 'rarity_control', 'rarities': DEFAULT_RARITIES.copy()}
            await spawn_settings_collection.insert_one(settings)
        return settings
    except Exception as e:
        LOGGER.error(f"Error getting spawn settings: {e}")
        return {'type': 'rarity_control', 'rarities': DEFAULT_RARITIES.copy()}


async def update_spawn_settings(rarities):
    try:
        await spawn_settings_collection.update_one(
            {'type': 'rarity_control'},
            {'$set': {'rarities': rarities}},
            upsert=True
        )
        return True
    except Exception as e:
        LOGGER.error(f"Error updating spawn settings: {e}")
        return False


async def get_group_exclusive(chat_id):
    try:
        return await group_rarity_collection.find_one({'chat_id': chat_id})
    except Exception as e:
        LOGGER.error(f"Error getting group exclusive: {e}")
        return None


def normalize_chances(rarities):
    enabled = {k: v for k, v in rarities.items() if v['enabled']}
    if not enabled:
        return rarities
    total = sum(r['chance'] for r in enabled.values())
    if total > 0:
        for emoji in enabled:
            rarities[emoji]['chance'] = round((rarities[emoji]['chance'] / total) * 100, 2)
    return rarities


def find_rarity_emoji(rarity_input):
    rarity_input = rarity_input.lower().strip()
    if rarity_input in DEFAULT_RARITIES:
        return rarity_input
    if rarity_input in NAME_TO_EMOJI:
        return NAME_TO_EMOJI[rarity_input]
    for name, emoji in NAME_TO_EMOJI.items():
        if rarity_input in name:
            return emoji
    return None


async def setg_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("⚠️ Owner only!")
            return

        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/setg <chat_id> <rarity_num> [chance]`\n"
                "Example: `/setg -1001234567890 17 15.5`\n\n"
                "Rarities:\n" + "\n".join([f"`{k}` - {v}" for k, v in RARITY_MAP.items()]),
                parse_mode='Markdown'
            )
            return

        try:
            chat_id = int(context.args[0])
            rarity_num = int(context.args[1])
            chance = float(context.args[2]) if len(context.args) > 2 else 10.0
        except ValueError:
            await update.message.reply_text("❌ Invalid values!")
            return

        if rarity_num not in RARITY_MAP:
            await update.message.reply_text(f"❌ Rarity {rarity_num} not found!")
            return

        if not 0 <= chance <= 100:
            await update.message.reply_text("❌ Chance must be 0-100!")
            return

        rarity_full = RARITY_MAP[rarity_num]
        rarity_emoji = rarity_full.split(' ')[0]

        existing = await group_rarity_collection.find_one({
            'rarity_emoji': rarity_emoji,
            'chat_id': {'$ne': chat_id}
        })
        
        if existing:
            await update.message.reply_text(
                f"⚠️ Warning: {rarity_emoji} {rarity_full} is already exclusive to chat `{existing['chat_id']}`!\n"
                f"Setting it for this group will remove it from the other group.",
                parse_mode='Markdown'
            )

        await group_rarity_collection.delete_many({
            'rarity_emoji': rarity_emoji,
            'chat_id': {'$ne': chat_id}
        })

        await group_rarity_collection.update_one(
            {'chat_id': chat_id},
            {'$set': {
                'chat_id': chat_id,
                'rarity_number': rarity_num,
                'rarity_emoji': rarity_emoji,
                'rarity_full': rarity_full,
                'chance': round(chance, 2)
            }},
            upsert=True
        )

        await update.message.reply_text(
            f"✅ Group exclusive set!\n"
            f"Chat: `{chat_id}`\n"
            f"Exclusive: {rarity_emoji} {rarity_full}\n"
            f"Chance: `{chance:.2f}%`\n\n"
            f"Group spawns:\n"
            f"• This exclusive rarity ({chance:.2f}%)\n"
            f"• All global enabled rarities\n"
            f"• Other groups won't get this rarity",
            parse_mode='Markdown'
        )
        LOGGER.info(f"Owner set chat {chat_id} exclusive: {rarity_full} ({chance}%)")

    except Exception as e:
        LOGGER.error(f"Error in setg: {e}\n{traceback.format_exc()}")
        await update.message.reply_text("❌ Error setting group exclusive!")


async def unsetg_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("⚠️ Owner only!")
            return

        if not context.args:
            await update.message.reply_text(
                "❌ Usage: `/unsetg <chat_id>`\n"
                "Example: `/unsetg -1001234567890`",
                parse_mode='Markdown'
            )
            return

        chat_id = int(context.args[0])
        result = await group_rarity_collection.delete_one({'chat_id': chat_id})

        if result.deleted_count > 0:
            await update.message.reply_text(
                f"✅ Removed exclusive!\n"
                f"Chat: `{chat_id}`\n"
                f"Now uses only global settings",
                parse_mode='Markdown'
            )
            LOGGER.info(f"Owner removed exclusive for chat {chat_id}")
        else:
            await update.message.reply_text(f"ℹ️ No settings for chat `{chat_id}`", parse_mode='Markdown')

    except Exception as e:
        LOGGER.error(f"Error in unsetg: {e}\n{traceback.format_exc()}")
        await update.message.reply_text("❌ Error!")


async def listg_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("⚠️ Owner only!")
            return

        groups = await group_rarity_collection.find({}).to_list(length=None)

        if not groups:
            await update.message.reply_text("ℹ️ No group exclusives set")
            return

        text = "🎯 **GROUP EXCLUSIVES**\n━━━━━━━━━━━━━━━━\n\n"
        for g in groups:
            text += (
                f"Chat: `{g['chat_id']}`\n"
                f"Exclusive: {g['rarity_emoji']} {g['rarity_full']}\n"
                f"Chance: `{g.get('chance', 10.0):.2f}%`\n\n"
            )

        await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        LOGGER.error(f"Error in listg: {e}\n{traceback.format_exc()}")
        await update.message.reply_text("❌ Error!")


async def rview_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("⚠️ Owner only!")
            return

        settings = await get_spawn_settings()
        rarities = settings['rarities']
        enabled = sum(1 for r in rarities.values() if r['enabled'])
        total = sum(r['chance'] for r in rarities.values() if r['enabled'])

        text = f"🎯 **GLOBAL RARITY**\n━━━━━━━━━━━━━━\n\n📊 {enabled}/{len(rarities)} enabled\n💯 Total: {total:.2f}%\n\n"

        for emoji, data in sorted(rarities.items(), key=lambda x: x[1]['chance'], reverse=True):
            s = "✅" if data['enabled'] else "❌"
            text += f"{emoji} {data['name']}: {s} `{data['chance']:.2f}%`\n"

        text += (
            f"\n━━━━━━━━━━━━━━\n"
            f"`/renable <rarity>` - Enable\n"
            f"`/rdisable <rarity>` - Disable\n"
            f"`/rchance <rarity> <val>` - Set chance\n"
            f"`/rnormalize` - Balance to 100%\n"
            f"`/rreset` - Reset\n"
            f"`/setg <chat> <num> [chance]` - Set exclusive\n"
            f"`/unsetg <chat>` - Remove exclusive\n"
            f"`/listg` - List exclusives"
        )

        await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as e:
        LOGGER.error(f"Error in rview: {e}\n{traceback.format_exc()}")
        await update.message.reply_text("❌ Error!")


async def renable_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            return
        if not context.args:
            await update.message.reply_text("❌ Usage: `/renable <rarity>`", parse_mode='Markdown')
            return

        emoji = find_rarity_emoji(' '.join(context.args))
        if not emoji:
            await update.message.reply_text("❌ Not found!")
            return

        settings = await get_spawn_settings()
        rarities = settings['rarities']

        if rarities[emoji]['enabled']:
            await update.message.reply_text(f"ℹ️ {emoji} {rarities[emoji]['name']} already enabled")
            return

        rarities[emoji]['enabled'] = True
        await update_spawn_settings(rarities)
        await update.message.reply_text(f"✅ Enabled {emoji} {rarities[emoji]['name']}")

    except Exception as e:
        LOGGER.error(f"Error in renable: {e}")
        await update.message.reply_text("❌ Error!")


async def rdisable_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            return
        if not context.args:
            await update.message.reply_text("❌ Usage: `/rdisable <rarity>`", parse_mode='Markdown')
            return

        emoji = find_rarity_emoji(' '.join(context.args))
        if not emoji:
            await update.message.reply_text("❌ Not found!")
            return

        settings = await get_spawn_settings()
        rarities = settings['rarities']

        if not rarities[emoji]['enabled']:
            await update.message.reply_text(f"ℹ️ {emoji} {rarities[emoji]['name']} already disabled")
            return

        rarities[emoji]['enabled'] = False
        await update_spawn_settings(rarities)
        await update.message.reply_text(f"✅ Disabled {emoji} {rarities[emoji]['name']}")

    except Exception as e:
        LOGGER.error(f"Error in rdisable: {e}")
        await update.message.reply_text("❌ Error!")


async def rchance_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            return
        if len(context.args) < 2:
            await update.message.reply_text("❌ Usage: `/rchance <rarity> <val>`", parse_mode='Markdown')
            return

        chance = float(context.args[-1])
        if not 0 <= chance <= 100:
            await update.message.reply_text("❌ Value must be 0-100!")
            return

        emoji = find_rarity_emoji(' '.join(context.args[:-1]))
        if not emoji:
            await update.message.reply_text("❌ Not found!")
            return

        settings = await get_spawn_settings()
        rarities = settings['rarities']
        old = rarities[emoji]['chance']
        rarities[emoji]['chance'] = round(chance, 2)
        await update_spawn_settings(rarities)

        await update.message.reply_text(
            f"✅ {emoji} {rarities[emoji]['name']}\n"
            f"`{old:.2f}%` → `{chance:.2f}%`",
            parse_mode='Markdown'
        )

    except Exception as e:
        LOGGER.error(f"Error in rchance: {e}")
        await update.message.reply_text("❌ Error!")


async def rnormalize_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            return

        settings = await get_spawn_settings()
        rarities = settings['rarities']
        old = sum(r['chance'] for r in rarities.values() if r['enabled'])

        rarities = normalize_chances(rarities)
        await update_spawn_settings(rarities)

        new = sum(r['chance'] for r in rarities.values() if r['enabled'])
        await update.message.reply_text(f"✅ Normalized!\n`{old:.2f}%` → `{new:.2f}%`", parse_mode='Markdown')

    except Exception as e:
        LOGGER.error(f"Error in rnormalize: {e}")
        await update.message.reply_text("❌ Error!")


async def rreset_command(update: Update, context: CallbackContext):
    try:
        if update.effective_user.id != OWNER_ID:
            return
        await update_spawn_settings(DEFAULT_RARITIES.copy())
        await update.message.reply_text("✅ Reset to default settings!")
    except Exception as e:
        LOGGER.error(f"Error in rreset: {e}")
        await update.message.reply_text("❌ Error!")


try:
    application.add_handler(CommandHandler("rview", rview_command, block=False))
    application.add_handler(CommandHandler("renable", renable_command, block=False))
    application.add_handler(CommandHandler("rdisable", rdisable_command, block=False))
    application.add_handler(CommandHandler("rchance", rchance_command, block=False))
    application.add_handler(CommandHandler("rnormalize", rnormalize_command, block=False))
    application.add_handler(CommandHandler("rreset", rreset_command, block=False))
    application.add_handler(CommandHandler("setg", setg_command, block=False))
    application.add_handler(CommandHandler("unsetg", unsetg_command, block=False))
    application.add_handler(CommandHandler("listg", listg_command, block=False))
    LOGGER.info("✅ Rarity handlers registered")
except Exception as e:
    LOGGER.error(f"❌ Failed to register handlers: {e}")

__all__ = ['spawn_settings_collection', 'group_rarity_collection', 'get_spawn_settings', 'get_group_exclusive']
