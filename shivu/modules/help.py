import random
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.error import BadRequest
from shivu import application, user_collection

PHOTOS = [
    "https://files.catbox.moe/z73gzs.jpg",
    "https://files.catbox.moe/r6k5dg.jpg",
    "https://files.catbox.moe/33yrky.jpg"
]

TIPS = [
    "ᴜsᴇ /ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ғᴏʀ ғʀᴇᴇ ɢᴏʟᴅ",
    "ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs ᴛᴏ ᴇᴀʀɴ ɢᴏʟᴅ",
    "ᴘʟᴀʏ ɢᴀᴍᴇs ᴛᴏ ɢᴀɪɴ xᴘ",
    "ᴄᴏʟʟᴇᴄᴛ ʀᴀʀᴇ sʟᴀᴠᴇs",
    "ᴜsᴇ /ʙᴀʟ ᴛᴏ ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ",
]

# Store current state to detect duplicates
user_states = {}

async def get_user_balance(user_id):
    try:
        user_data = await user_collection.find_one({'id': user_id})
        return user_data.get('balance', 0) if user_data else 0
    except:
        return 0

def get_main_keyboard(user_id):
    return [
        [
            InlineKeyboardButton("ɢᴀᴍᴇs", callback_data=f'help_games_{user_id}'),
            InlineKeyboardButton("ᴇᴄᴏɴᴏᴍʏ", callback_data=f'help_economy_{user_id}')
        ],
        [
            InlineKeyboardButton("sʟᴀᴠᴇs", callback_data=f'help_slaves_{user_id}'),
            InlineKeyboardButton("ᴘᴀss", callback_data=f'help_pass_{user_id}')
        ],
        [
            InlineKeyboardButton("ʀᴀɴᴋɪɴɢs", callback_data=f'help_top_{user_id}'),
            InlineKeyboardButton("ʀᴇᴡᴀʀᴅs", callback_data=f'help_rewards_{user_id}')
        ]
    ]

def get_main_caption(first_name, balance):
    # Always use a random photo and tip to make content unique
    return f"""<a href="{random.choice(PHOTOS)}">&#8203;</a>✦ <b>ʜᴇʟᴘ ᴄᴇɴᴛᴇʀ</b>

╰┈➤ ʜᴇʏ <b>{first_name}</b>
╰┈➤ ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ

✦ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{balance}</b>

<i>{random.choice(TIPS)}</i>"""

def get_category_caption(action):
    photo = random.choice(PHOTOS)
    captions = {
        'games': f"""<a href="{photo}">&#8203;</a>✦ <b>ɢᴀᴍᴇ ᴢᴏɴᴇ</b>

╰┈➤ <b>ɢᴀᴍʙʟɪɴɢ</b>
<code>/sbet 10000 heads</code> ᴄᴏɪɴ ᴛᴏss
<code>/roll 10000 even</code> ᴅɪᴄᴇ ʀᴏʟʟ
<code>/gamble 10000 l</code> ʟᴇғᴛ ᴏʀ ʀɪɢʜᴛ

╰┈➤ <b>sᴋɪʟʟ ɢᴀᴍᴇs</b>
<code>/basket 5000</code> ʙᴀsᴋᴇᴛʙᴀʟʟ
<code>/dart 2000</code> ᴅᴀʀᴛ ɢᴀᴍᴇ

╰┈➤ <b>sᴘᴇᴄɪᴀʟ</b>
<code>/riddle</code> sᴏʟᴠᴇ ᴀɴᴅ ᴇᴀʀɴ
<code>/stour</code> sʟᴀᴠᴇ ᴛᴏᴜʀɴᴀᴍᴇɴᴛs""",

        'economy': f"""<a href="{photo}">&#8203;</a>✦ <b>ᴇᴄᴏɴᴏᴍʏ</b>

╰┈➤ <b>ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ</b>
<code>/bal</code> ᴡᴀʟʟᴇᴛ ᴀɴᴅ ʙᴀɴᴋ
<code>/sinv</code> ɪɴᴠᴇɴᴛᴏʀʏ

╰┈➤ <b>ᴛʀᴀɴsᴀᴄᴛɪᴏɴs</b>
<code>/pay @user 1000</code> sᴇɴᴅ ɢᴏʟᴅ
<code>/claim</code> ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ

╰┈➤ <b>ʀᴇᴡᴀʀᴅs</b>
<code>/daily</code> ᴅᴀɪʟʏ ʙᴏɴᴜs
<code>/weekly</code> ᴡᴇᴇᴋʟʏ ʙᴏɴᴜs""",

        'slaves': f"""<a href="{photo}">&#8203;</a>✦ <b>sʟᴀᴠᴇ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</b>

╰┈➤ <b>ᴄᴀᴛᴄʜɪɴɢ</b>
<code>/grab name</code> ᴄᴀᴛᴄʜ sʟᴀᴠᴇ
sᴘᴀᴡɴs ᴇᴠᴇʀʏ 100 ᴍᴇssᴀɢᴇs

╰┈➤ <b>ᴄᴏʟʟᴇᴄᴛɪᴏɴ</b>
<code>/harem</code> ʏᴏᴜʀ sʟᴀᴠᴇs
<code>/slaves</code> ᴀʟʟ sʟᴀᴠᴇs
<code>/smode</code> sᴏʀᴛ ʙʏ ʀᴀɴᴋ

╰┈➤ <b>ᴛʀᴀᴅɪɴɢ</b>
<code>/trade</code> ᴛʀᴀᴅᴇ ᴡɪᴛʜ ᴏᴛʜᴇʀs
<code>/sinfo id</code> sʟᴀᴠᴇ ᴅᴇᴛᴀɪʟs""",

        'pass': f"""<a href="{photo}">&#8203;</a>✦ <b>sʟᴀᴠᴇ ᴘᴀss</b>

╰┈➤ <b>ᴡᴇᴇᴋʟʏ ʀᴇᴡᴀʀᴅs</b>
<code>/claim</code> ᴄʟᴀɪᴍ ᴡᴇᴇᴋʟʏ
<code>/sweekly</code> ʙᴏɴᴜs ᴀғᴛᴇʀ 6 ᴄʟᴀɪᴍs
<code>/pbonus</code> ᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs

╰┈➤ <b>ʙᴇɴᴇғɪᴛs</b>
ᴇxᴄʟᴜsɪᴠᴇ sʟᴀᴠᴇs
ᴇxᴛʀᴀ ɢᴏʟᴅ ʀᴇᴡᴀʀᴅs
sᴘᴇᴄɪᴀʟ ᴇᴠᴇɴᴛs

╰┈➤ <code>/pass</code> ᴠɪᴇᴡ sᴛᴀᴛᴜs""",

        'top': f"""<a href="{photo}">&#8203;</a>✦ <b>ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs</b>

╰┈➤ <b>ᴘʟᴀʏᴇʀ ʀᴀɴᴋɪɴɢs</b>
<code>/tops</code> ʀɪᴄʜᴇsᴛ ʜᴜɴᴛᴇʀs
<code>/xtop</code> ʜɪɢʜᴇsᴛ xᴘ
<code>/gstop</code> ᴍᴏsᴛ ɢᴏʟᴅ
<code>/tophunters</code> ᴇʟɪᴛᴇ ʟɪsᴛ

╰┈➤ <b>ɢʀᴏᴜᴘ sᴛᴀᴛs</b>
<code>/topchat</code> ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛs
<code>/topgroups</code> ᴛᴏᴘ ɢʀᴏᴜᴘs""",

        'rewards': f"""<a href="{photo}">&#8203;</a>✦ <b>ʀᴇᴡᴀʀᴅs</b>

╰┈➤ <b>ᴅᴀɪʟʏ</b>
<code>/claim</code> 2000 ɢᴏʟᴅ ᴅᴀɪʟʏ
<code>/daily</code> ʙᴏɴᴜs ɢᴏʟᴅ
<code>/hclaim</code> ᴅᴀɪʟʏ sʟᴀᴠᴇ

╰┈➤ <b>ᴡᴇᴇᴋʟʏ</b>
<code>/weekly</code> ᴡᴇᴇᴋʟʏ ʀᴇᴡᴀʀᴅ
<code>/sweekly</code> ᴘᴀss ʙᴏɴᴜs

╰┈➤ <b>ʀᴇғᴇʀʀᴀʟ</b>
ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs ғᴏʀ 1000 ɢᴏʟᴅ"""
    }
    return captions.get(action, "")

async def help_command(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        balance = await get_user_balance(user.id)

        caption = get_main_caption(user.first_name, balance)
        keyboard = get_main_keyboard(user.id)

        await update.message.reply_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            disable_web_page_preview=False
        )
        
        # Store initial state
        user_states[user.id] = 'main'
        
    except Exception as e:
        print(f"Error in help_command: {e}")

async def help_callback(update: Update, context: CallbackContext):
    query = update.callback_query

    try:
        data = query.data
        parts = data.split('_')
        action = parts[1]
        expected_user_id = int(parts[2])
        user_id = query.from_user.id

        if user_id != expected_user_id:
            await query.answer("ᴛʜɪs ɪsɴ'ᴛ ғᴏʀ ʏᴏᴜ", show_alert=True)
            return

        # Check if user is already on this page
        current_state = user_states.get(user_id)
        
        if current_state == action:
            # User clicked the same button - just answer the callback without editing
            await query.answer("ʏᴏᴜ'ʀᴇ ᴀʟʀᴇᴀᴅʏ ʜᴇʀᴇ", show_alert=False)
            return

        # Update state
        user_states[user_id] = action
        
        await query.answer()

        if action == 'back':
            balance = await get_user_balance(user_id)
            caption = get_main_caption(query.from_user.first_name, balance)
            keyboard = get_main_keyboard(user_id)
            user_states[user_id] = 'main'

            try:
                await query.edit_message_text(
                    text=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML',
                    disable_web_page_preview=False
                )
            except BadRequest as e:
                if "message is not modified" not in str(e).lower():
                    raise
        else:
            caption = get_category_caption(action)
            if caption:
                back_button = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data=f'help_back_{user_id}')]]

                try:
                    await query.edit_message_text(
                        text=caption,
                        reply_markup=InlineKeyboardMarkup(back_button),
                        parse_mode='HTML',
                        disable_web_page_preview=False
                    )
                except BadRequest as e:
                    if "message is not modified" not in str(e).lower():
                        raise
            else:
                await query.answer("ɪɴᴠᴀʟɪᴅ ᴄᴀᴛᴇɢᴏʀʏ", show_alert=True)

    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            # Silently ignore this specific error
            pass
        else:
            print(f"BadRequest in help_callback: {e}")
    except Exception as e:
        print(f"Error in help_callback: {e}")

# Register handlers
application.add_handler(CommandHandler(['help', 'menu', 'panel'], help_command, block=False))
application.add_handler(CallbackQueryHandler(help_callback, pattern=r'^help_', block=False))