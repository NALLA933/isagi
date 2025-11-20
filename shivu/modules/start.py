import random
from shivu.modules.database.sudo import fetch_sudo_users
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection
from shivu.modules.chatlog import track_bot_start

PHOTOS = [
    "https://files.catbox.moe/k3dhbe.mp4",
    "https://graph.org/file/example2.jpg",
    "https://graph.org/file/example3.jpg"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500

OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
SUDO_USERS = [{"name": "Shadwoo", "username": "I_shadwoo"}]


def get_media_html(url):
    return f'<a href="{url}"><b>‌</b></a>'


async def process_referral(user_id, first_name, referring_user_id, context):
    try:
        if not user_id or not referring_user_id or user_id == referring_user_id:
            return False

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            return False

        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {"referred_by": referring_user_id},
                "$inc": {"balance": NEW_USER_BONUS}
            }
        )

        await user_collection.update_one(
            {"id": referring_user_id},
            {
                "$inc": {
                    "balance": REFERRER_REWARD,
                    "referred_users": 1,
                    "pass_data.tasks.invites": 1,
                    "pass_data.total_invite_earnings": REFERRER_REWARD
                },
                "$push": {"invited_user_ids": user_id}
            }
        )

        msg = f"""{get_media_html(random.choice(PHOTOS))}<b>ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ

ɢᴏʟᴅ: <code>{REFERRER_REWARD:,}</code>
ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1"""

        try:
            await context.bot.send_message(
                chat_id=referring_user_id,
                text=msg,
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"Could not notify referrer {referring_user_id}: {e}")

        return True

    except Exception as e:
        LOGGER.error(f"Referral processing error: {e}", exc_info=True)
        return False


async def start(update: Update, context: CallbackContext):
    try:
        if not update or not update.effective_user:
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

        referring_user_id = None
        if args and len(args) > 0 and args[0].startswith('r_'):
            try:
                referring_user_id = int(args[0][2:])
            except (ValueError, IndexError):
                referring_user_id = None

        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            new_user = {
                "id": user_id,
                "first_name": first_name,
                "username": username,
                "balance": NEW_USER_BONUS if referring_user_id else 500,
                "characters": [],
                "referred_users": 0,
                "referred_by": None,
                "invited_user_ids": [],
                "pass_data": {
                    "tier": "free",
                    "weekly_claims": 0,
                    "last_weekly_claim": None,
                    "streak_count": 0,
                    "last_streak_claim": None,
                    "tasks": {"invites": 0, "weekly_claims": 0, "grabs": 0},
                    "mythic_unlocked": False,
                    "premium_expires": None,
                    "elite_expires": None,
                    "pending_elite_payment": None,
                    "invited_users": [],
                    "total_invite_earnings": 0
                }
            }

            await user_collection.insert_one(new_user)
            user_data = new_user

            try:
                await track_bot_start(user_id, first_name, username, is_new_user)
            except Exception as e:
                LOGGER.error(f"Error tracking bot start: {e}")

            if referring_user_id:
                await process_referral(user_id, first_name, referring_user_id, context)

        else:
            await user_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "first_name": first_name,
                        "username": username
                    }
                }
            )

            try:
                await track_bot_start(user_id, first_name, username, is_new_user)
            except Exception as e:
                LOGGER.error(f"Error tracking bot start: {e}")

        balance = user_data.get('balance', 0)

        try:
            totals = await user_totals_collection.find_one({'id': user_id})
            chars = totals.get('count', 0) if totals else 0
        except:
            chars = 0

        refs = user_data.get('referred_users', 0)

        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus = f"\n\n<b>+{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs" if (is_new_user and referring_user_id) else ""

        caption = f"""{get_media_html(random.choice(PHOTOS))}<b>{welcome}</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ɪ sᴘᴀᴡɴ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘs ᴀɴᴅ ʟᴇᴛ ᴜsᴇʀs ᴄᴏʟʟᴇᴄᴛ ᴛʜᴇᴍ
sᴏ ᴡʜᴀᴛ ᴀʀᴇ ʏᴏᴜ ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
ɢᴏʟᴅ: <b>{balance:,}</b>
ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>{bonus}"""

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
            parse_mode='HTML'
        )

    except Exception as e:
        LOGGER.error(f"Critical error in start command: {e}", exc_info=True)
        try:
            await update.message.reply_text("⚠️ An error occurred while processing your request. Please try again later.")
        except:
            pass


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query

    try:
        await query.answer()
    except Exception as e:
        LOGGER.error(f"Error answering callback query: {e}")
        return

    try:
        user_id = query.from_user.id
        user_data = await user_collection.find_one({"id": user_id})

        if not user_data:
            await query.answer("⚠️ sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ", show_alert=True)
            return

        if query.data == 'credits':
            text = f"""{get_media_html(random.choice(PHOTOS))}<b>🩵 ʙᴏᴛ ᴄʀᴇᴅɪᴛs</b>

sᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋs ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ ᴡʜᴏ ᴍᴀᴅᴇ ᴛʜɪs ᴘᴏssɪʙʟᴇ

<b>ᴏᴡɴᴇʀs</b>"""

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

            buttons.append([InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')])

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode='HTML'
            )

        elif query.data == 'help':
            text = f"""{get_media_html(random.choice(PHOTOS))}<b>📖 ᴄᴏᴍᴍᴀɴᴅs</b>

/grab - ɢᴜᴇss ᴄʜᴀʀᴀᴄᴛᴇʀ
/fav - sᴇᴛ ғᴀᴠᴏʀɪᴛᴇ
/harem - ᴠɪᴇᴡ ᴄᴏʟʟᴇᴄᴛɪᴏɴ
/trade - ᴛʀᴀᴅᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs
/gift - ɢɪғᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ
/bal - ᴄʜᴇᴄᴋ ᴡᴀʟʟᴇᴛ
/pay - sᴇɴᴅ ɢᴏʟᴅ
/claim - ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
/roll - ɢᴀᴍʙʟᴇ ɢᴏʟᴅ"""

            keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

        elif query.data == 'referral':
            link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
            count = user_data.get('referred_users', 0)
            earned = count * REFERRER_REWARD

            text = f"""{get_media_html(random.choice(PHOTOS))}<b>🎁 ɪɴᴠɪᴛᴇ ᴀɴᴅ ᴇᴀʀɴ</b>

ɪɴᴠɪᴛᴇᴅ: <b>{count}</b>
ᴇᴀʀɴᴇᴅ: <b>{earned:,}</b> ɢᴏʟᴅ

sʜᴀʀᴇ ʏᴏᴜʀ ʟɪɴᴋ:
<code>{link}</code>

ʀᴇᴡᴀʀᴅs:
• ʏᴏᴜ: <b>{REFERRER_REWARD:,}</b> ɢᴏʟᴅ
• ғʀɪᴇɴᴅ: <b>{NEW_USER_BONUS:,}</b> ɢᴏʟᴅ"""

            keyboard = [
                [InlineKeyboardButton("sʜᴀʀᴇ", url=f"https://t.me/share/url?url={link}")],
                [InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]
            ]

            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )

        elif query.data == 'back':
            balance = user_data.get('balance', 0)

            try:
                totals = await user_totals_collection.find_one({'id': user_id})
                chars = totals.get('count', 0) if totals else 0
            except:
                chars = 0

            refs = user_data.get('referred_users', 0)

            caption = f"""{get_media_html(random.choice(PHOTOS))}<b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ᴄᴏʟʟᴇᴄᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ɢʀᴏᴜᴘs

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
ɢᴏʟᴅ: <b>{balance:,}</b>
ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>"""

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
                parse_mode='HTML'
            )

    except Exception as e:
        LOGGER.error(f"Error in button callback: {e}", exc_info=True)
        try:
            await query.answer("⚠️ An error occurred. Please try again.", show_alert=True)
        except:
            pass


application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|credits|back)$', block=False))