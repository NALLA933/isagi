import random
import hashlib
import base64
import time
import os
from shivu.modules.database.sudo import fetch_sudo_users
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LinkPreviewOptions
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ConversationHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection, collection
from shivu.modules.chatlog import track_bot_start
import asyncio

# ═══════════════════════════════════════════════════════════════════
# QUANTUM COPYRIGHT PROTECTION SYSTEM v5.0
# Developed by: @siyaprobot
# Licensed to: Pick Catcher Bot (@ll_Thorfinn_ll)
# Security Level: MAXIMUM - Dynamic PIN Protected
# Unauthorized use will result in bot lockdown
# ═══════════════════════════════════════════════════════════════════

# Conversation states for PIN setup
WAITING_FOR_PIN, WAITING_FOR_UNLOCK_PIN = range(2)

class CopyrightProtection:
    """Advanced copyright protection with dynamic PIN verification system"""
    
    # Bot authorization signature (DO NOT MODIFY)
    _BOT_SIGNATURE = hashlib.sha256(f"{BOT_USERNAME}_AUTHORIZED".encode()).hexdigest()
    _COPYRIGHT_HASH = "8f4a9c2e1b7d6f3a5e8c9d2f1a4b7e5c9d8f2a6b3e7c1d4f8a9b2e5c7d1f4a8b"
    _WATERMARK = base64.b64encode(b"SIYAPROBOT_ORIGINAL_2024_QUANTUM_PROTECTED").decode()
    _GENESIS_BLOCK = hashlib.sha256(b"@siyaprobot_genesis_2024").hexdigest()
    
    # Authorized developers who can set PIN
    _AUTHORIZED_DEVS = ['siyaprobot', 'i_shadwoo']
    
    # System status
    _master_pin = 
        keyboard = [
            [InlineKeyboardButton("ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
            [
                InlineKeyboardButton("sᴜᴘᴘᴏʀᴛ", url=f'https://t.me/{SUPPORT_CHAT}'),
                InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url='https://t.me/PICK_X_UPDATE')
            ],
            [
                InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'),
                InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral')
            ],
            [InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data='credits')]
        ]

        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            link_preview_options=LinkPreviewOptions(
                url=video_url,
                show_above_text=True,
                prefer_large_media=True
            )
        )

    except Exception as e:
        LOGGER.error(f"Critical error in start command: {e}", exc_info=True)
        try:
            await update.message.reply_text("⚠️ An error occurred while processing your request. Please try again later.")
        except:
            pass


async def safe_track_bot_start(user_id, first_name, username, is_new_user):
    """Wrapper to safely call track_bot_start without blocking the main flow"""
    try:
        await asyncio.wait_for(
            track_bot_start(user_id, first_name, username, is_new_user),
            timeout=5.0
        )
    except asyncio.TimeoutError:
        LOGGER.warning(f"track_bot_start timed out for user {user_id}")
    except Exception as e:
        LOGGER.error(f"Error in safe_track_bot_start: {e}", exc_info=True)


async def refer_command(update: Update, context: CallbackContext):
    """Dedicated referral command with detailed information"""
    try:
        # Check if bot is locked
        if await check_lock_before_command(update, context):
            return
        
        user_id = update.effective_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await update.message.reply_text("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ ᴜsɪɴɢ /start")
            return

        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        base_earned = count * REFERRER_REWARD
        milestone_earned = 0

        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if count >= milestone:
                milestone_earned += REFERRAL_MILESTONES[milestone]["gold"]

        total_earned = base_earned + milestone_earned

        next_milestone = None
        next_reward = None
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            if count < milestone:
                next_milestone = milestone
                next_reward = REFERRAL_MILESTONES[milestone]
                break

        milestone_text = ""
        for milestone in sorted(REFERRAL_MILESTONES.keys()):
            reward = REFERRAL_MILESTONES[milestone]
            status = "✅" if count >= milestone else "🔒"
            milestone_text += f"\n{status} <b>{milestone}</b> ʀᴇғs → {reward['gold']:,} ɢᴏʟᴅ + {reward['characters']} ᴄʜᴀʀs"

        text = CopyrightProtection.embed_watermark(f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b> ᴜsᴇʀs
💰 ᴛᴏᴛᴀʟ ᴇᴀʀɴᴇᴅ: <b>{total_earned:,}</b> ɢᴏʟᴅ

<b>💎 ᴘᴇʀ ʀᴇғᴇʀʀᴀʟ</b>
• ʏᴏᴜ ɢᴇᴛ: <b>{REFERRER_REWARD:,}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ ɢᴇᴛs: <b>{NEW_USER_BONUS:,}</b> ɢᴏʟᴅ

<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇ ʀᴇᴡᴀʀᴅs</b>{milestone_text}""")

        if next_milestone:
            remaining = next_milestone - count
            text += f"\n\n<b>🎯 ɴᴇxᴛ ɢᴏᴀʟ</b>\n{remaining} ᴍᴏʀᴇ ғᴏʀ <b>{next_reward['gold']:,}</b> ɢᴏʟᴅ + <b>{next_reward['characters']}</b> ᴄʜᴀʀᴀᴄᴛᴇʀs"

        text += f"\n\n<b>🔗 ʏᴏᴜʀ ʀᴇғᴇʀʀᴀʟ ʟɪɴᴋ</b>\n<code>{link}</code>"

        keyboard = [
            [InlineKeyboardButton("📤 sʜᴀʀᴇ ʟɪɴᴋ", url=f"https://t.me/share/url?url={link}&text=Join me on Pick Catcher and get {NEW_USER_BONUS} gold bonus!")],
            [InlineKeyboardButton("👥 ᴠɪᴇᴡ ɪɴᴠɪᴛᴇs", callback_data='view_invites')]
        ]

        await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            link_preview_options=LinkPreviewOptions(
                url=random.choice(VIDEOS),
                show_above_text=True,
                prefer_large_media=True
            )
        )

    except Exception as e:
        LOGGER.error(f"Error in refer command: {e}", exc_info=True)
        await update.message.reply_text("⚠️ An error occurred. Please try again.")


async def verify_copyright(update: Update, context: CallbackContext):
    """Hidden command to verify copyright integrity"""
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username.lower() if update.effective_user.username else ""
        
        # Only accessible by authorized developers
        if username not in CopyrightProtection._AUTHORIZED_DEVS:
            return
        
        info = await CopyrightProtection.get_copyright_info()
        
        text = f"""<b>🔒 ᴄᴏᴘʏʀɪɢʜᴛ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ</b>

<b>ᴅᴇᴠᴇʟᴏᴘᴇʀ:</b> <code>{info['developer']}</code>
<b>ʙᴏᴛ:</b> <code>@{BOT_USERNAME}</code>
<b>sᴛᴀᴛᴜs:</b> {'✅ ᴠᴇʀɪғɪᴇᴅ' if info['verified'] else '⚠️ ᴠɪᴏʟᴀᴛɪᴏɴ'}
<b>ᴀᴜᴛʜᴏʀɪᴢᴇᴅ:</b> {'✅ ʏᴇs' if info['authorized'] else '❌ ɴᴏ'}
<b>ʟᴏᴄᴋᴇᴅ:</b> {'🔒 ʏᴇs' if info['locked'] else '🔓 ɴᴏ'}
<b>ᴘɪɴ sᴇᴛ:</b> {'✅ ʏᴇs' if info['pin_set'] else '❌ ɴᴏ'}

<b>ғɪɴɢᴇʀᴘʀɪɴᴛ:</b>
<code>{info['fingerprint'][:32]}...</code>

<b>ʙᴏᴛ ғɪɴɢᴇʀᴘʀɪɴᴛ:</b>
<code>{info['bot_fingerprint'][:32]}...</code>

<b>ɢᴇɴᴇsɪs ʙʟᴏᴄᴋ:</b>
<code>{info['genesis'][:32]}...</code>

<i>ǫᴜᴀɴᴛᴜᴍ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ ᴀᴄᴛɪᴠᴇ</i>

<b>ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴏᴍᴍᴀɴᴅs:</b>
/setpin - Set new PIN
/unlock - Unlock bot with PIN
/copyright_verify - This verification"""

        await update.message.reply_text(
            text=text,
            parse_mode='HTML'
        )
        
    except Exception as e:
        LOGGER.error(f"Error in verify_copyright: {e}")


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        LOGGER.error(f"Error answering callback query: {e}")
        return

    try:
        # Check if bot is locked
        if await CopyrightProtection.is_system_locked():
            await query.answer(
                "🔒 Bot is locked. Use /unlock to unlock with PIN.",
                show_alert=True
            )
            return
        
        user_id = query.from_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await query.answer("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ", show_alert=True)
            return

        video_url = random.choice(VIDEOS)

        if query.data == 'credits':
            text = CopyrightProtection.embed_watermark(f"""<b>🩵 ʙᴏᴛ ᴄʀᴇᴅɪᴛs</b>

sᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋs ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ ᴡʜᴏ ᴍᴀᴅᴇ ᴛʜɪs ᴘᴏssɪʙʟᴇ

<b>ᴏᴡɴᴇʀs</b>""")

            buttons = []

            if OWNERS:
                for i in range(0, len(OWNERS), 2):
                    owner_row = []
                    for owner in OWNERS[i:i+2]:
                        owner_name = owner.get('name', 'Owner')
                        owner_username = owner.get('username', '').replace('@', '')
                        if owner_username:
                            owner_row.append(
                                InlineKeyboardButton(
                                    f"👑 {owner_name}",
                                    url=f"https://t.me/{owner_username}"
                                )
                            )
                    if owner_row:
                        buttons.append(owner_row)

            sudo_users_db = []
            try:
                sudo_users_db = await fetch_sudo_users()
            except Exception as e:
                LOGGER.error(f"Error fetching sudo users from database: {e}")

            if sudo_users_db and len(sudo_users_db) > 0:
                text += "\n\n<b>sᴜᴅᴏ ᴜsᴇʀs</b>"

                for i in range(0, len(sudo_users_db), 2):
                    sudo_row = []
                    for sudo in sudo_users_db[i:i+2]:
                        sudo_title = sudo.get('sudo_title') or sudo.get('name') or sudo.get('first_name', 'Sudo User')
                        sudo_username = sudo.get('username', '').replace('@', '')

                        if sudo_username:
                            sudo_row.append(
                                InlineKeyboardButton(
                                    sudo_title,
                                    url=f"https://t.me/{sudo_username}"
                                )
                            )
                    if sudo_row:
                        buttons.append(sudo_row)

            elif SUDO_USERS:
                text += "\n\n<b>sᴜᴅᴏ ᴜsᴇʀs</b>"
                for i in range(0, len(SUDO_USERS), 2):
                    sudo_row = []
                    for sudo in SUDO_USERS[i:i+2]:
                        sudo_name = sudo.get('name', 'Sudo User')
                        sudo_username = sudo.get('username', '').replace('@', '')
                        if sudo_username:
                            sudo_row.append(
                                InlineKeyboardButton(
                                    sudo_name,
                                    url=f"https://t.me/{sudo_username}"
                                )
                            )
                    if sudo_row:
                        buttons.append(sudo_row)

            # Hidden copyright credit
            text += "\n\n<b>🔐 ᴅᴇᴠᴇʟᴏᴘᴇʀ</b>"
            buttons.append([InlineKeyboardButton("💎 @siyaprobot", url="https://t.me/siyaprobot")])
            buttons.append([InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')])

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'help':
            text = CopyrightProtection.embed_watermark(f"""<b>📖 ᴄᴏᴍᴍᴀɴᴅs</b>

/grab - ɢᴜᴇss ᴄʜᴀʀᴀᴄᴛᴇʀ
/fav - sᴇᴛ ғᴀᴠᴏʀɪᴛᴇ
/harem - ᴠɪᴇᴡ ᴄᴏʟʟᴇᴄᴛɪᴏɴ
/trade - ᴛʀᴀᴅᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs
/gift - ɢɪғᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ
/bal - ᴄʜᴇᴄᴋ ᴡᴀʟʟᴇᴛ
/pay - sᴇɴᴅ ɢᴏʟᴅ
/claim - ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
/roll - ɢᴀᴍʙʟᴇ ɢᴏʟᴅ
/refer - ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs""")

            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'referral':
            link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
            count = user_data.get('referred_users', 0)
            base_earned = count * REFERRER_REWARD
            milestone_earned = 0

            for milestone in sorted(REFERRAL_MILESTONES.keys()):
                if count >= milestone:
                    milestone_earned += REFERRAL_MILESTONES[milestone]["gold"]

            total_earned = base_earned + milestone_earned

            next_milestone = None
            next_reward = None
            for milestone in sorted(REFERRAL_MILESTONES.keys()):
                if count < milestone:
                    next_milestone = milestone
                    next_reward = REFERRAL_MILESTONES[milestone]
                    break

            milestone_text = ""
            for milestone in sorted(REFERRAL_MILESTONES.keys()):
                reward = REFERRAL_MILESTONES[milestone]
                status = "✅" if count >= milestone else "🔒"
                milestone_text += f"\n{status} <b>{milestone}</b> → {reward['gold']:,} + {reward['characters']} ᴄʜᴀʀs"

            text = CopyrightProtection.embed_watermark(f"""<b>🎁 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</b>

<b>📊 ʏᴏᴜʀ sᴛᴀᴛs</b>
👥 ɪɴᴠɪᴛᴇᴅ: <b>{count}</b>
💰 ᴇᴀʀɴᴇᴅ: <b>{total_earned:,}</b> ɢᴏʟᴅ

<b>💎 ʀᴇᴡᴀʀᴅs</b>
• ʏᴏᴜ: <b>{REFERRER_REWARD:,}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ: <b>{NEW_USER_BONUS:,}</b> ɢᴏʟᴅ

<b>🏆 ᴍɪʟᴇsᴛᴏɴᴇs</b>{milestone_text}""")

            if next_milestone:
                remaining = next_milestone - count
                text += f"\n\n<b>🎯 ɴᴇxᴛ</b>\n{remaining} ᴍᴏʀᴇ → <b>{next_reward['gold']:,}</b> + <b>{next_reward['characters']}</b> ᴄʜᴀʀs"

            text += f"\n\n<code>{link}</code>"

            keyboard = [
                [InlineKeyboardButton("📤 sʜᴀʀᴇ", url=f"https://t.me/share/url?url={link}&text=Join Pick Catcher! Get {NEW_USER_BONUS:,} gold bonus 🎁")],
                [InlineKeyboardButton("👥 ᴠɪᴇᴡ ɪɴᴠɪᴛᴇs", callback_data='view_invites')],
                [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]
            ]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'view_invites':
            count = user_data.get('referred_users', 0)
            invited_ids = user_data.get('invited_user_ids', [])

            if count == 0:
                text = CopyrightProtection.embed_watermark("""<b>👥 ʏᴏᴜʀ ɪɴᴠɪᴛᴇs</b>

ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ɪɴᴠɪᴛᴇᴅ ᴀɴʏᴏɴᴇ ʏᴇᴛ

sᴛᴀʀᴛ sʜᴀʀɪɴɢ ʏᴏᴜʀ ʟɪɴᴋ ᴛᴏ ᴇᴀʀɴ ʀᴇᴡᴀʀᴅs""")
            else:
                invited_users = []
                for uid in invited_ids[:10]:
                    try:
                        invited = await user_collection.find_one({"id": uid})
                        if invited:
                            name = invited.get('first_name', 'User')
                            invited_users.append(f"• {escape(name)}")
                    except:
                        pass

                users_text = "\n".join(invited_users) if invited_users else "• ɴᴏ ᴅᴀᴛᴀ"
                more = f"\n\n<i>+{count - 10} ᴍᴏʀᴇ...</i>" if count > 10 else ""

                text = CopyrightProtection.embed_watermark(f"""<b>👥 ʏᴏᴜʀ ɪɴᴠɪᴛᴇs</b>

<b>ᴛᴏᴛᴀʟ:</b> {count} ᴜsᴇʀs
<b>ᴇᴀʀɴᴇᴅ:</b> {count * REFERRER_REWARD:,} ɢᴏʟᴅ

<b>ʀᴇᴄᴇɴᴛ ɪɴᴠɪᴛᴇs</b>
{users_text}{more}""")

            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='referral')]]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

        elif query.data == 'back':
            balance = user_data.get('balance', 0)

            try:
                characters = user_data.get('characters', [])
                unique_char_ids = set()
                for char in characters:
                    if isinstance(char, dict):
                        char_id = char.get('id')
                        if char_id:
                            unique_char_ids.add(char_id)
                chars = len(unique_char_ids)
            except:
                chars = 0

            refs = user_data.get('referred_users', 0)

            caption = CopyrightProtection.embed_watermark(f"""<b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ᴄᴏʟʟᴇᴄᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ɢʀᴏᴜᴘs

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
💰 ɢᴏʟᴅ: <b>{balance:,}</b>
🎴 ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
👥 ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>""")

            keyboard = [
                [InlineKeyboardButton("ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ", url=f'https://t.me/{BOT_USERNAME}?startgroup=new')],
                [
                    InlineKeyboardButton("sᴜᴘᴘᴏʀᴛ", url=f'https://t.me/{SUPPORT_CHAT}'),
                    InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url='https://t.me/PICK_X_UPDATE')
                ],
                [
                    InlineKeyboardButton("ʜᴇʟᴘ", callback_data='help'),
                    InlineKeyboardButton("ɪɴᴠɪᴛᴇ", callback_data='referral')
                ],
                [InlineKeyboardButton("ᴄʀᴇᴅɪᴛs", callback_data='credits')]
            ]

            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                link_preview_options=LinkPreviewOptions(
                    url=video_url,
                    show_above_text=True,
                    prefer_large_media=True
                )
            )

    except Exception as e:
        LOGGER.error(f"Error in button callback: {e}", exc_info=True)
        try:
            await query.answer("⚠️ An error occurred. Please try again.", show_alert=True)
        except:
            pass


# ═══════════════════════════════════════════════════════════════════
# REGISTER HANDLERS
# ═══════════════════════════════════════════════════════════════════

# PIN Setup Conversation Handler (Only for @siyaprobot and @I_shadwoo)
pin_setup_handler = ConversationHandler(
    entry_points=[CommandHandler('setpin', setpin_command, block=False)],
    states={
        WAITING_FOR_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pin, block=False)],
    },
    fallbacks=[CommandHandler('cancel', cancel_command, block=False)],
)

# Unlock Conversation Handler
unlock_handler = ConversationHandler(
    entry_points=[CommandHandler('unlock', unlock_command, block=False)],
    states={
        WAITING_FOR_UNLOCK_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_unlock_pin, block=False)],
    },
    fallbacks=[CommandHandler('cancel', cancel_command, block=False)],
)

# Register all handlers
application.add_handler(pin_setup_handler)
application.add_handler(unlock_handler)
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CommandHandler('refer', refer_command, block=False))
application.add_handler(CommandHandler('copyright_verify', verify_copyright, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|credits|back|view_invites)$', block=False))


# ═══════════════════════════════════════════════════════════════════
# COPYRIGHT PROTECTION ACTIVATION ON STARTUP
# ═══════════════════════════════════════════════════════════════════

async def startup_check():
    """Check copyright protection on bot startup"""
    try:
        info = await CopyrightProtection.get_copyright_info()
        
        LOGGER.info("=" * 60)
        LOGGER.info("🔐 COPYRIGHT PROTECTION SYSTEM v5.0")
        LOGGER.info("=" * 60)
        LOGGER.info(f"Developer: {info['developer']}")
        LOGGER.info(f"Bot: @{BOT_USERNAME}")
        LOGGER.info(f"Verified: {'✓' if info['verified'] else '✗'}")
        LOGGER.info(f"Authorized: {'✓' if info['authorized'] else '✗'}")
        LOGGER.info(f"PIN Set: {'✓' if info['pin_set'] else '✗'}")
        LOGGER.info(f"Status: {'🔒 LOCKED' if info['locked'] else '🔓 UNLOCKED'}")
        LOGGER.info("=" * 60)
        
        if info['locked']:
            LOGGER.warning("")
            LOGGER.warning("⚠️  BOT IS CURRENTLY LOCKED")
            LOGGER.warning("")
            if not info['authorized']:
                LOGGER.warning("Reason: Unauthorized bot instance detected")
                LOGGER.warning(f"This code is licensed to: Pick Catcher Bot")
                LOGGER.warning(f"Current bot: @{BOT_USERNAME}")
            if not info['pin_set']:
                LOGGER.warning("Reason: No PIN has been set")
                LOGGER.warning("Action: Use /setpin command to set PIN")
                LOGGER.warning("Access: Only @siyaprobot and @I_shadwoo can set PIN")
            else:
                LOGGER.warning("Action: Use /unlock command and enter PIN")
            LOGGER.warning("")
            LOGGER.warning("Contact: @siyaprobot or @I_shadwoo for assistance")
            LOGGER.warning("=" * 60)
        else:
            LOGGER.info("✓ Bot is operational and ready")
            LOGGER.info("=" * 60)
        
        if not info['verified']:
            LOGGER.critical("")
            LOGGER.critical("⚠️  COPYRIGHT VIOLATION DETECTED")
            LOGGER.critical("Unauthorized modification of copyright protection code")
            LOGGER.critical("=" * 60)
            
    except Exception as e:
        LOGGER.error(f"Error during startup check: {e}", exc_info=True)

# Run startup check
import asyncio
loop = asyncio.get_event_loop()
if loop.is_running():
    asyncio.create_task(startup_check())
else:
    loop.run_until_complete(startup_check())  # Will be set dynamically
    _is_unlocked = False
    _unlock_attempts = {}  # Track attempts per bot instance
    _max_attempts = 3
    _pin_hash = None  # Store hashed PIN in database
    
    @staticmethod
    async def get_stored_pin():
        """Retrieve PIN from database"""
        try:
            pin_doc = await user_collection.find_one({"_id": "system_pin_protection"})
            if pin_doc and 'pin_hash' in pin_doc:
                return pin_doc['pin_hash']
            return None
        except Exception as e:
            LOGGER.error(f"Error retrieving PIN: {e}")
            return None
    
    @staticmethod
    async def set_pin(new_pin):
        """Store PIN hash in database"""
        try:
            pin_hash = hashlib.sha256(new_pin.encode()).hexdigest()
            await user_collection.update_one(
                {"_id": "system_pin_protection"},
                {
                    "$set": {
                        "pin_hash": pin_hash,
                        "set_by": "authorized_dev",
                        "set_at": time.time(),
                        "bot_signature": CopyrightProtection._BOT_SIGNATURE
                    }
                },
                upsert=True
            )
            CopyrightProtection._pin_hash = pin_hash
            return True
        except Exception as e:
            LOGGER.error(f"Error setting PIN: {e}")
            return False
    
    @staticmethod
    async def verify_pin(pin_input, bot_username):
        """Verify PIN and unlock system"""
        stored_hash = await CopyrightProtection.get_stored_pin()
        
        if not stored_hash:
            return {
                "success": False,
                "message": "⚠️ No PIN set. Contact @I_shadwoo to set PIN first.",
                "locked": True
            }
        
        # Check attempts for this bot instance
        if bot_username not in CopyrightProtection._unlock_attempts:
            CopyrightProtection._unlock_attempts[bot_username] = 0
        
        if CopyrightProtection._unlock_attempts[bot_username] >= CopyrightProtection._max_attempts:
            return {
                "success": False,
                "message": "🔒 Maximum attempts reached. Bot locked permanently.\n\nContact @siyaprobot or @I_shadwoo",
                "locked": True
            }
        
        input_hash = hashlib.sha256(pin_input.encode()).hexdigest()
        
        if input_hash == stored_hash:
            CopyrightProtection._is_unlocked = True
            CopyrightProtection._unlock_attempts[bot_username] = 0
            
            # Store unlock status in database
            await user_collection.update_one(
                {"_id": "system_pin_protection"},
                {"$set": {"unlocked": True, "unlocked_at": time.time()}}
            )
            
            return {
                "success": True,
                "message": "✅ System unlocked successfully!\n\nBot is now fully operational.",
                "locked": False
            }
        else:
            CopyrightProtection._unlock_attempts[bot_username] += 1
            remaining = CopyrightProtection._max_attempts - CopyrightProtection._unlock_attempts[bot_username]
            
            if remaining == 0:
                return {
                    "success": False,
                    "message": "🔒 Invalid PIN. Maximum attempts reached.\n\nBot locked permanently.\n\nContact @siyaprobot or @I_shadwoo",
                    "locked": True
                }
            
            return {
                "success": False,
                "message": f"❌ Invalid PIN.\n\n⚠️ {remaining} attempt{'s' if remaining > 1 else ''} remaining before permanent lockdown.",
                "locked": False
            }
    
    @staticmethod
    async def is_system_locked():
        """Check if system is locked"""
        # Check if unlocked in memory
        if CopyrightProtection._is_unlocked:
            return False
        
        # Check database unlock status
        try:
            pin_doc = await user_collection.find_one({"_id": "system_pin_protection"})
            if pin_doc and pin_doc.get('unlocked', False):
                CopyrightProtection._is_unlocked = True
                return False
        except:
            pass
        
        # Check if PIN is set
        stored_pin = await CopyrightProtection.get_stored_pin()
        if not stored_pin:
            return True  # Lock if no PIN set
        
        # Check if bot is authorized
        if not CopyrightProtection._check_authorization():
            return True
        
        return True  # Default to locked
    
    @staticmethod
    def _check_authorization():
        """Check if bot is authorized to run"""
        current_sig = hashlib.sha256(f"{BOT_USERNAME}_AUTHORIZED".encode()).hexdigest()
        if current_sig != CopyrightProtection._BOT_SIGNATURE:
            return False
        return True
    
    @staticmethod
    def _generate_bot_fingerprint():
        """Generate unique fingerprint for this bot instance"""
        bot_data = f"{BOT_USERNAME}_{SUPPORT_CHAT}_{time.time()}"
        return hashlib.sha512(bot_data.encode()).hexdigest()
    
    @staticmethod
    def _generate_fingerprint():
        """Generate unique bot fingerprint"""
        timestamp = str(int(time.time()))
        data = f"@siyaprobot|{timestamp}|quantum_protection"
        return hashlib.sha512(data.encode()).hexdigest()
    
    @staticmethod
    def _verify_integrity():
        """Verify copyright integrity"""
        expected = hashlib.sha256(CopyrightProtection._GENESIS_BLOCK.encode()).hexdigest()
        return expected == hashlib.sha256(b"@siyaprobot_genesis_2024").hexdigest()
    
    @staticmethod
    def embed_watermark(text):
        """Embed invisible watermark in text using zero-width characters"""
        zwc = ['\u200b', '\u200c', '\u200d', '\ufeff']
        watermark = ""
        for char in "SIYAPROBOT":
            watermark += zwc[ord(char) % 4]
        return text + watermark
    
    @staticmethod
    async def get_copyright_info():
        """Return copyright information"""
        return {
            "developer": "@siyaprobot",
            "fingerprint": CopyrightProtection._generate_fingerprint(),
            "bot_fingerprint": CopyrightProtection._generate_bot_fingerprint(),
            "hash": CopyrightProtection._COPYRIGHT_HASH,
            "watermark": CopyrightProtection._WATERMARK,
            "genesis": CopyrightProtection._GENESIS_BLOCK,
            "verified": CopyrightProtection._verify_integrity(),
            "authorized": CopyrightProtection._check_authorization(),
            "locked": await CopyrightProtection.is_system_locked(),
            "pin_set": await CopyrightProtection.get_stored_pin() is not None
        }


# ═══════════════════════════════════════════════════════════════════
# PIN MANAGEMENT COMMANDS (Only for @siyaprobot and @I_shadwoo)
# ═══════════════════════════════════════════════════════════════════

async def setpin_command(update: Update, context: CallbackContext):
    """Command to set the master PIN (only authorized devs)"""
    try:
        user = update.effective_user
        username = user.username.lower() if user.username else ""
        
        # Check if user is authorized
        if username not in CopyrightProtection._AUTHORIZED_DEVS:
            await update.message.reply_text(
                "⛔️ <b>Access Denied</b>\n\n"
                "This command is restricted to authorized developers only.",
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "<b>🔐 Set Master PIN</b>\n\n"
            "Please enter a 6-digit PIN to protect this bot.\n\n"
            "⚠️ <b>IMPORTANT:</b>\n"
            "• This PIN will be required if bot is used elsewhere\n"
            "• Keep it secure and private\n"
            "• You can change it anytime\n\n"
            "Send /cancel to abort.",
            parse_mode='HTML'
        )
        return WAITING_FOR_PIN
        
    except Exception as e:
        LOGGER.error(f"Error in setpin command: {e}")
        return ConversationHandler.END