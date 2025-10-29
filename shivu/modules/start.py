import random
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler
from shivu import application, SUPPORT_CHAT, BOT_USERNAME, LOGGER, user_collection, user_totals_collection

# Config
PHOTOS = [
    "https://files.catbox.moe/8722ku.jpeg",
    "https://files.catbox.moe/kgcrnb.jpeg"
]
REFERRER_REWARD = 1000
NEW_USER_BONUS = 500

OWNERS = [{"name": "Thorfinn", "username": "ll_Thorfinn_ll"}]
SUDO_USERS = [{"name": "Shadwoo", "username": "I_shadwoo"}]

# Referral Process
async def process_referral(user_id, first_name, referring_user_id, context):
    try:
        if user_id == referring_user_id:
            return False

        referring_user = await user_collection.find_one({"id": referring_user_id})
        if not referring_user:
            return False

        new_user = await user_collection.find_one({"id": user_id})
        if new_user and new_user.get('referred_by'):
            return False

        await user_collection.update_one(
            {"id": user_id},
            {"$set": {"referred_by": referring_user_id}, "$inc": {"balance": NEW_USER_BONUS}}
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

        msg = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>ʀᴇғᴇʀʀᴀʟ sᴜᴄᴄᴇss</b>

<b>{escape(first_name)}</b> ᴊᴏɪɴᴇᴅ ᴠɪᴀ ʏᴏᴜʀ ʟɪɴᴋ

ɢᴏʟᴅ: <code>{REFERRER_REWARD:,}</code>
ɪɴᴠɪᴛᴇ ᴛᴀsᴋ: +1"""

        try:
            await context.bot.send_message(chat_id=referring_user_id, text=msg, parse_mode='HTML')
        except:
            pass

        return True
    except Exception as e:
        LOGGER.error(f"Referral error: {e}")
        return False

# Start Command
async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    username = update.effective_user.username
    args = context.args

    referring_user_id = None
    if args and args[0].startswith('r_'):
        try:
            referring_user_id = int(args[0][2:])
        except:
            pass

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

        if referring_user_id:
            await process_referral(user_id, first_name, referring_user_id, context)

    balance = user_data.get('balance', 0)
    totals = await user_totals_collection.find_one({'id': user_id})
    chars = totals.get('count', 0) if totals else 0
    refs = user_data.get('referred_users', 0)

    welcome = "ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ" if not is_new_user else "ᴡᴇʟᴄᴏᴍᴇ"
    bonus = f"\n\n<b>+{NEW_USER_BONUS}</b> ɢᴏʟᴅ ʙᴏɴᴜs" if (is_new_user and referring_user_id) else ""

    caption = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>{welcome}</b>

ᴄᴏʟʟᴇᴄᴛ ᴀɴɪᴍᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs ɪɴ ɢʀᴏᴜᴘs
ᴀᴅᴅ ᴍᴇ ᴛᴏ sᴛᴀʀᴛ{bonus}

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

    try:
        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=False
        )
    except Exception as e:
        LOGGER.error(f"Start error: {e}")

# Button Callback Handler
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = await user_collection.find_one({"id": user_id})

    if not user_data:
        await query.answer("sᴛᴀʀᴛ ʙᴏᴛ ғɪʀsᴛ", show_alert=True)
        return

    if query.data == 'credits':
        text = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>🩵 ʙᴏᴛ ᴄʀᴇᴅɪᴛs</b>

sᴘᴇᴄɪᴀʟ ᴛʜᴀɴᴋs ᴛᴏ ᴇᴠᴇʀʏᴏɴᴇ ᴡʜᴏ ᴍᴀᴅᴇ ᴛʜɪs ᴘᴏssɪʙʟᴇ

<b>ᴏᴡɴᴇʀs</b>"""

        buttons = []
        if OWNERS:
            owner_row = [InlineKeyboardButton(f"👑 {o['name']}", url=f"https://t.me/{o['username']}") for o in OWNERS]
            buttons.append(owner_row)

        if SUDO_USERS:
            text += "\n\n<b>sᴜᴅᴏ ᴜsᴇʀs</b>"
            sudo_row = [InlineKeyboardButton(f"⚡ {s['name']}", url=f"https://t.me/{s['username']}") for s in SUDO_USERS]
            buttons.append(sudo_row)

        buttons.append([InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')])

        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode='HTML',
            disable_web_page_preview=False
        )

    elif query.data == 'help':
        text = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>ᴄᴏᴍᴍᴀɴᴅs</b>

/grab ɢᴜᴇss ᴄʜᴀʀᴀᴄᴛᴇʀ
/fav sᴇᴛ ғᴀᴠᴏʀɪᴛᴇ
/harem ᴠɪᴇᴡ ᴄᴏʟʟᴇᴄᴛɪᴏɴ
/trade ᴛʀᴀᴅᴇ ᴄʜᴀʀᴀᴄᴛᴇʀs
/gift ɢɪғᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ
/bal ᴄʜᴇᴄᴋ ᴡᴀʟʟᴇᴛ
/pay sᴇɴᴅ ɢᴏʟᴅ
/claim ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ
/roll ɢᴀᴍʙʟᴇ ɢᴏʟᴅ"""

        keyboard = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data='back')]]
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
            disable_web_page_preview=False
        )

    elif query.data == 'referral':
        link = f"https://t.me/{BOT_USERNAME}?start=r_{user_id}"
        count = user_data.get('referred_users', 0)
        earned = count * REFERRER_REWARD
        
        text = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>ɪɴᴠɪᴛᴇ ᴀɴᴅ ᴇᴀʀɴ</b>

ɪɴᴠɪᴛᴇᴅ: <b>{count}</b>
ᴇᴀʀɴᴇᴅ: <b>{earned:,}</b>

<code>{link}</code>"""

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

    elif query.data == 'back':
        balance = user_data.get('balance', 0)
        totals = await user_totals_collection.find_one({'id': user_id})
        chars = totals.get('count', 0) if totals else 0
        refs = user_data.get('referred_users', 0)
        
        caption = f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ</b>

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

# Register Handlers
application.add_handler(CommandHandler('start', start, block=False))
application.add_handler(CallbackQueryHandler(button_callback, pattern='^(help|referral|credits|back)$', block=False))