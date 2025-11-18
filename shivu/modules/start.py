import random
from shivu.modules.database.sudo import fetch_sudo_users
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection

# Import tracking function
from shivu.modules.chatlog import track_bot_start

# Config - USE ACTUAL IMAGE URLS, NOT VIDEOS
PHOTOS = [
    "https://graph.org/file/example1.jpg",  # Replace with your actual image URLs
    "https://graph.org/file/example2.jpg",
    "https://graph.org/file/example3.jpg"
]

REFERRER_REWARD = 1000
NEW_USER_BONUS = 500

OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
SUDO_USERS = [{"name": "Shadwoo", "username": "I_shadwoo"}]  # Fallback if DB fails


async def process_referral(user_id, first_name, referring_user_id, context):
    """Process referral rewards for both new user and referrer"""
    try:
        # Validate inputs
        if not user_id or not referring_user_id:
            return False
            
        if user_id == referring_user_id:
            LOGGER.warning(f"User {user_id} tried to refer themselves")
            return False

        # Check if referring user exists
        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            LOGGER.warning(f"Referring user {referring_user_id} not found")
            return False

        # Check if new user was already referred
        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            LOGGER.info(f"User {user_id} already referred by {new_user.get('referred_by')}")
            return False

        # Update new user with referral info
        await user_collection.update_one(
            {"id": user_id},
            {
                "$set": {"referred_by": referring_user_id},
                "$inc": {"balance": NEW_USER_BONUS}
            }
        )

        # Update referring user with rewards
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

        # Notify referring user
        msg = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ

ɢᴏʟᴅ: <code>{REFERRER_REWARD:,}</code>
ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1"""

        try:
            await context.bot.send_message(
                chat_id=referring_user_id,
                text=msg,
                parse_mode='HTML',
                disable_web_page_preview=False
            )
        except Exception as e:
            LOGGER.error(f"Could not notify referrer {referring_user_id}: {e}")

        return True
        
    except Exception as e:
        LOGGER.error(f"Referral processing error: {e}", exc_info=True)
        return False


async def start(update: Update, context: CallbackContext):
    """Handle /start command"""
    try:
        # Validate update
        if not update or not update.effective_user:
            LOGGER.error("Invalid update object in start command")
            return

        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        username = update.effective_user.username or ""
        args = context.args

        # Parse referral code if present
        referring_user_id = None
        if args and len(args) > 0 and args[0].startswith('r_'):
            try:
                referring_user_id = int(args[0][2:])
                LOGGER.info(f"User {user_id} started with referral from {referring_user_id}")
            except (ValueError, IndexError) as e:
                LOGGER.warning(f"Invalid referral code format: {args[0]} - {e}")
                referring_user_id = None

        # Check if user exists in database
        user_data = await user_collection.find_one({"id": user_id})
        is_new_user = user_data is None

        if is_new_user:
            # Create new user document
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
            LOGGER.info(f"New user created: {user_id} - {first_name}")

            # Track bot start AFTER user creation
            try:
                await track_bot_start(user_id, first_name, username, is_new_user)
            except Exception as e:
                LOGGER.error(f"Error tracking bot start: {e}")

            # Process referral if applicable
            if referring_user_id:
                await process_referral(user_id, first_name, referring_user_id, context)

        else:
            # Update existing user info
            await user_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "first_name": first_name,
                        "username": username
                    }
                }
            )
            
            # Track returning user
            try:
                await track_bot_start(user_id, first_name, username, is_new_user)
            except Exception as e:
                LOGGER.error(f"Error tracking bot start: {e}")

        # Get user stats
        balance = user_data.get('balance', 0)
        
        try:
            totals = await user_totals_collection.find_one({'id': user_id})
            chars = totals.get('count', 0) if totals else 0
        except Exception as e:
            LOGGER.error(f"Error fetching user totals: {e}")
            chars = 0
            
        refs = user_data.get('referred_users', 0)

        # Prepare welcome message
        welcome = "ᴡᴇʟᴄᴏᴍᴇ" if is_new_user else "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ"
        bonus = f"\n\n<b>+{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs" if (is_new_user and referring_user_id) else ""

        caption = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>{welcome}</b>

ɪ ᴀᴍ ᴘɪᴄᴋ ᴄᴀᴛᴄʜᴇʀ
ɪ sᴘᴀᴡɴ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘs ᴀɴᴅ ʟᴇᴛ ᴜsᴇʀs ᴄᴏʟʟᴇᴄᴛ ᴛʜᴇᴍ
sᴏ ᴡʜᴀᴛ ᴀʀᴇ ʏᴏᴜ ᴡᴀɪᴛɪɴɢ ғᴏʀ ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ʙʏ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ

<b>ʏᴏᴜʀ sᴛᴀᴛs</b>
ɢᴏʟᴅ: <b>{balance:,}</b>
ᴄʜᴀʀᴀᴄᴛᴇʀs: <b>{chars}</b>
ʀᴇғᴇʀʀᴀʟs: <b>{refs}</b>{bonus}"""

        # Create inline keyboard
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

        # Send welcome message
        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=False
        )

    except Exception as e:
        LOGGER.error(f"Critical error in start command: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "⚠️ An error occurred while processing your request. Please try again later."
            )
        except:
            pass


async def button_callback(update: Update, context: CallbackContext):
    """Handle button callbacks"""
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

        # CREDITS PAGE
        if query.data == 'credits':
            text = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>🩵 ʙᴏᴛ ᴄʀᴇᴅɪᴛs</b>

sᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋs ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ ᴡʜᴏ ᴍᴀᴅᴇ ᴛʜɪs ᴘᴏssɪʙʟᴇ

<b>ᴏᴡɴᴇʀs</b>"""

            buttons = []
            
            # Add owners
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

            # Fetch sudo users from database
            sudo_users_db = []
            try:
                sudo_users_db = await fetch_sudo_users()
            except Exception as e:
                LOGGER.error(f"Error fetching sudo users from database: {e}")
                # Use fallback static list
                sudo_users_db = []

            # If database fetch successful and has users
            if sudo_users_db and len(sudo_users_db) > 0:
                text += "\n\n<b>sᴜᴅᴏ ᴜsᴇʀs</b>"
                
                for i in range(0, len(sudo_users_db), 2):
                    sudo_row = []
                    for sudo in sudo_users_db[i:i+2]:
                        # Get sudo title/name
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
            
            # Fallback to static sudo users if DB returned nothing
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
                parse_mode='HTML',
                disable_web_page_preview=False
            )

        # HELP PAGE
        elif query.data == 'help':
            text = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>📖 ᴄᴏᴍᴍᴀɴᴅs</b>

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
                parse_mode='HTML',
                disable_web_page_preview=False
            )

        # REFERRAL PAGE
        elif query.data == 'referral':
            link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
            count = user_data.get('referred_users', 0)
            earned = count * REFERRER_REWARD

            text = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>🎁 ɪɴᴠɪᴛᴇ ᴀɴᴅ ᴇᴀʀɴ</b>

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
                parse_mode='HTML',
                disable_web_page_preview=False
            )

        # BACK TO MAIN PAGE
        elif query.data == 'back':
            balance = user_data.get('balance', 0)
            
            try:
                totals = await user_totals_collection.find_one({'id': user_id})
                chars = totals.get('count', 0) if totals else 0
            except Exception as e:
                LOGGER.error(f"Error fetching user totals: {e}")
                chars = 0
                
            refs = user_data.get('referred_users', 0)

            caption = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>

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
                parse_mode='HTML',
                disable_web_page_preview=False
            )

    except Exception as e:
        LOGGER.error(f"Error in button callback: {e}", exc_info=True)
        try:
            await query.answer("⚠️ An error occurred. Please try again.", show_alert=True)
        except:
            pass


# Register Handlers
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|credits|back)$', block=False))