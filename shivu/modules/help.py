import random
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.error import BadRequest
from shivu import application, user_collection

TIPS = [
    "ᴜsᴇ /ᴄʟᴀɪᴍ ᴅᴀɪʟʏ ғᴏʀ ғʀᴇᴇ ɢᴏʟᴅ",
    "ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs ᴛᴏ ᴇᴀʀɴ ɢᴏʟᴅ",
    "ᴘʟᴀʏ ɢᴀᴍᴇs ᴛᴏ ɢᴀɪɴ xᴘ",
    "ᴄᴏʟʟᴇᴄᴛ ʀᴀʀᴇ sʟᴀᴠᴇs",
    "ᴜsᴇ /ʙᴀʟ ᴛᴏ ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ",
]

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
    return f"""<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>ʜᴇʟᴘ ᴄᴇɴᴛᴇʀ</b>

╰┈➤ ʜᴇʏ <b>{first_name}</b>
╰┈➤ ᴄʜᴏᴏsᴇ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ

✦ ʏᴏᴜʀ ʙᴀʟᴀɴᴄᴇ: <b>{balance}</b>

<i>{random.choice(TIPS)}</i>"""

async def help_command(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        balance = await get_user_balance(user.id)
        
        caption = get_main_caption(user.first_name, balance)
        keyboard = get_main_keyboard(user.id)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
            disable_web_page_preview=False
        )
    except Exception as e:
        print(f"Error: {e}")

def get_category_caption(action):
    captions = {
        'games': """<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>ɢᴀᴍᴇ ᴢᴏɴᴇ</b>

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

        'economy': """<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>ᴇᴄᴏɴᴏᴍʏ</b>

╰┈➤ <b>ᴄʜᴇᴄᴋ ʙᴀʟᴀɴᴄᴇ</b>
<code>/bal</code> ᴡᴀʟʟᴇᴛ ᴀɴᴅ ʙᴀɴᴋ
<code>/sinv</code> ɪɴᴠᴇɴᴛᴏʀʏ

╰┈➤ <b>ᴛʀᴀɴsᴀᴄᴛɪᴏɴs</b>
<code>/pay @user 1000</code> sᴇɴᴅ ɢᴏʟᴅ
<code>/claim</code> ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅ

╰┈➤ <b>ʀᴇᴡᴀʀᴅs</b>
<code>/daily</code> ᴅᴀɪʟʏ ʙᴏɴᴜs
<code>/weekly</code> ᴡᴇᴇᴋʟʏ ʙᴏɴᴜs""",

        'slaves': """<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>sʟᴀᴠᴇ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</b>

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

        'pass': """<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>sʟᴀᴠᴇ ᴘᴀss</b>

╰┈➤ <b>ᴡᴇᴇᴋʟʏ ʀᴇᴡᴀʀᴅs</b>
<code>/claim</code> ᴄʟᴀɪᴍ ᴡᴇᴇᴋʟʏ
<code>/sweekly</code> ʙᴏɴᴜs ᴀғᴛᴇʀ 6 ᴄʟᴀɪᴍs
<code>/pbonus</code> ᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs

╰┈➤ <b>ʙᴇɴᴇғɪᴛs</b>
ᴇxᴄʟᴜsɪᴠᴇ sʟᴀᴠᴇs
ᴇxᴛʀᴀ ɢᴏʟᴅ ʀᴇᴡᴀʀᴅs
sᴘᴇᴄɪᴀʟ ᴇᴠᴇɴᴛs

╰┈➤ <code>/pass</code> ᴠɪᴇᴡ sᴛᴀᴛᴜs""",

        'top': """<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs</b>

╰┈➤ <b>ᴘʟᴀʏᴇʀ ʀᴀɴᴋɪɴɢs</b>
<code>/tops</code> ʀɪᴄʜᴇsᴛ ʜᴜɴᴛᴇʀs
<code>/xtop</code> ʜɪɢʜᴇsᴛ xᴘ
<code>/gstop</code> ᴍᴏsᴛ ɢᴏʟᴅ
<code>/tophunters</code> ᴇʟɪᴛᴇ ʟɪsᴛ

╰┈➤ <b>ɢʀᴏᴜᴘ sᴛᴀᴛs</b>
<code>/topchat</code> ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛs
<code>/topgroups</code> ᴛᴏᴘ ɢʀᴏᴜᴘs""",

        'rewards': """<a href="https://files.catbox.moe/33yrky.jpg">&#8203;</a>✦ <b>ʀᴇᴡᴀʀᴅs</b>

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

async def help_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    
    try:
        await query.answer()
    except:
        return

    try:
        data = query.data
        parts = data.split('_')
        action = '_'.join(parts[1:-1])
        expected_user_id = int(parts[-1])
        user_id = query.from_user.id

        if user_id != expected_user_id:
            await query.answer("ᴛʜɪs ɪsɴ'ᴛ ғᴏʀ ʏᴏᴜ", show_alert=True)
            return

        if action == 'back':
            balance = await get_user_balance(user_id)
            caption = get_main_caption(query.from_user.first_name, balance)
            keyboard = get_main_keyboard(user_id)
            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML',
                disable_web_page_preview=False
            )
            return

        caption = get_category_caption(action)
        if caption:
            back_button = [[InlineKeyboardButton("ʙᴀᴄᴋ", callback_data=f'help_back_{user_id}')]]
            await query.edit_message_text(
                text=caption,
                reply_markup=InlineKeyboardMarkup(back_button),
                parse_mode='HTML',
                disable_web_page_preview=False
            )
        else:
            await query.answer("ɪɴᴠᴀʟɪᴅ ᴄᴀᴛᴇɢᴏʀʏ", show_alert=True)

    except BadRequest as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")

help_handler = CommandHandler(['help', 'menu', 'panel'], help_command, block=False)
application.add_handler(help_handler)

callback_pattern = r'help_(games|economy|slaves|pass|top|rewards|back)_\d+$'
help_callback_handler = CallbackQueryHandler(help_callback, pattern=callback_pattern, block=False)
application.add_handler(help_callback_handler)