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
    "ᴜsᴇ /ʜᴄʟᴀɪᴍ ғᴏʀ ᴅᴀɪʟʏ sʟᴀᴠᴇ ʀᴇᴡᴀʀᴅs",
    "ᴄʜᴇᴄᴋ /ʙᴀʟ ᴛᴏ ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ᴡᴀʟʟᴇᴛ ᴀɴᴅ ʙᴀɴᴋ",
    "ᴜsᴇ /ғᴀᴠ ᴛᴏ ᴍᴀʀᴋ ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ sʟᴀᴠᴇs",
    "ᴇxᴘʟᴏʀᴇ ɴᴇᴡ ᴀʀᴇᴀs ᴡɪᴛʜ /ᴇxᴘʟᴏʀᴇ ᴄᴏᴍᴍᴀɴᴅ",
    "ᴛʀᴀᴅᴇ sʟᴀᴠᴇs ᴡɪᴛʜ ᴏᴛʜᴇʀ ᴘʟᴀʏᴇʀs ғᴏʀ ᴘʀᴏғɪᴛ",
    "ᴄᴏᴍᴘʟᴇᴛᴇ ᴅᴀɪʟʏ ǫᴜᴇsᴛs ᴛᴏ ᴇᴀʀɴ ʙᴏɴᴜsᴇs",
    "ᴊᴏɪɴ ᴛᴏᴜʀɴᴀᴍᴇɴᴛs ᴡɪᴛʜ /sᴛᴏᴜʀ ᴄᴏᴍᴍᴀɴᴅ",
]

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
            InlineKeyboardButton("ᴇᴄᴏɴᴏᴍʏ", callback_data=f'help_economy_{user_id}'),
            InlineKeyboardButton("sʟᴀᴠᴇs", callback_data=f'help_slaves_{user_id}')
        ],
        [
            InlineKeyboardButton("ᴛʀᴀᴅɪɴɢ", callback_data=f'help_trading_{user_id}'),
            InlineKeyboardButton("ᴘʀᴏғɪʟᴇ", callback_data=f'help_profile_{user_id}'),
            InlineKeyboardButton("sᴏᴄɪᴀʟ", callback_data=f'help_social_{user_id}')
        ],
        [
            InlineKeyboardButton("ʀᴀɴᴋɪɴɢs", callback_data=f'help_rankings_{user_id}'),
            InlineKeyboardButton("sᴛᴏʀᴇ", callback_data=f'help_store_{user_id}'),
            InlineKeyboardButton("ᴀᴅᴠᴀɴᴄᴇᴅ", callback_data=f'help_advanced_{user_id}')
        ]
    ]

def get_main_caption(first_name, balance):
    return f"""<a href="{random.choice(PHOTOS)}">&#8203;</a><b>╔═══════════════════╗
║  ᴄᴏᴍᴍᴀɴᴅ ᴄᴇɴᴛᴇʀ  ║
╚═══════════════════╝</b>

<b>┌─ ᴜsᴇʀ ɪɴғᴏʀᴍᴀᴛɪᴏɴ</b>
<b>├</b> ᴜsᴇʀ <b>{first_name}</b>
<b>├</b> ʙᴀʟᴀɴᴄᴇ <b>{balance:,}</b> ɢᴏʟᴅ
<b>└─ sᴛᴀᴛᴜs</b> ᴀᴄᴛɪᴠᴇ

<b>┌─ sʏsᴛᴇᴍ ᴛɪᴘ</b>
<b>└─</b> <i>{random.choice(TIPS)}</i>

<b>▸</b> sᴇʟᴇᴄᴛ ᴀ ᴄᴀᴛᴇɢᴏʀʏ ʙᴇʟᴏᴡ"""

def get_category_caption(action):
    photo = random.choice(PHOTOS)
    captions = {
        'games': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║   ɢᴀᴍᴇ ᴢᴏɴᴇ    ║
╚═══════════════════╝</b>

<b>┌─ ɢᴀᴍʙʟɪɴɢ sʏsᴛᴇᴍ</b>
<b>├</b> <code>/sbet [amount] [heads/tails]</code>
<b>│</b>  ᴄᴏɪɴ ғʟɪᴘ ɢᴀᴍʙʟᴇ
<b>├</b> <code>/roll [amount] [even/odd]</code>
<b>│</b>  ᴅɪᴄᴇ ʀᴏʟʟ ʙᴇᴛᴛɪɴɢ
<b>└</b> <code>/gamble [amount] [l/r]</code>
   ʟᴇғᴛ ᴏʀ ʀɪɢʜᴛ ᴄʜᴀʟʟᴇɴɢᴇ

<b>┌─ sᴋɪʟʟ ʙᴀsᴇᴅ</b>
<b>├</b> <code>/basket [amount]</code>
<b>│</b>  ʙᴀsᴋᴇᴛʙᴀʟʟ sʜᴏᴏᴛɪɴɢ
<b>├</b> <code>/dart [amount]</code>
<b>│</b>  ᴘʀᴇᴄɪsɪᴏɴ ᴅᴀʀᴛ ᴛʜʀᴏᴡ
<b>└</b> <code>/riddle</code>
   ʙʀᴀɪɴ ᴛᴇᴀsᴇʀ ᴄʜᴀʟʟᴇɴɢᴇ

<b>┌─ ᴄᴏᴍᴘᴇᴛɪᴛɪᴠᴇ</b>
<b>├</b> <code>/stour</code> sʟᴀᴠᴇ ᴛᴏᴜʀɴᴀᴍᴇɴᴛ
<b>├</b> <code>/games</code> ɢᴀᴍᴇ ᴍᴇɴᴜ
<b>├</b> <code>/gamestats</code> ʏᴏᴜʀ sᴛᴀᴛs
<b>└</b> <code>/leaderboard</code> ᴛᴏᴘ ᴘʟᴀʏᴇʀs""",

        'economy': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║  ᴇᴄᴏɴᴏᴍʏ ʜᴜʙ  ║
╚═══════════════════╝</b>

<b>┌─ ᴡᴀʟʟᴇᴛ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ</b>
<b>├</b> <code>/bal</code>
<b>│</b>  ᴠɪᴇᴡ ʙᴀʟᴀɴᴄᴇ ᴀɴᴅ ʙᴀɴᴋ
<b>├</b> <code>/deposit [amount]</code>
<b>│</b>  sᴛᴏʀᴇ ɢᴏʟᴅ sᴀғᴇʟʏ
<b>├</b> <code>/withdraw [amount]</code>
<b>│</b>  ʀᴇᴛʀɪᴇᴠᴇ ғʀᴏᴍ ʙᴀɴᴋ
<b>└</b> <code>/pay @user [amount]</code>
   ᴛʀᴀɴsғᴇʀ ɢᴏʟᴅ

<b>┌─ ʟᴏᴀɴ sʏsᴛᴇᴍ</b>
<b>├</b> <code>/loan [amount]</code>
<b>│</b>  ʙᴏʀʀᴏᴡ ɢᴏʟᴅ
<b>└</b> <code>/repay [amount]</code>
   ᴘᴀʏ ʙᴀᴄᴋ ʟᴏᴀɴ

<b>┌─ ᴅᴀɪʟʏ ʀᴇᴡᴀʀᴅs</b>
<b>├</b> <code>/cclaim</code> ᴅᴀɪʟʏ ɢᴏʟᴅ
<b>├</b> <code>/daily</code> ʙᴏɴᴜs ʀᴇᴡᴀʀᴅ
<b>└</b> <code>/xp</code> ᴇxᴘᴇʀɪᴇɴᴄᴇ ᴘᴏɪɴᴛs

<b>┌─ ʜᴇʟᴘ</b>
<b>├</b> <code>/bankhelp</code> ɢᴜɪᴅᴇ
<b>└</b> <code>/bankexample</code> ᴇxᴀᴍᴘʟᴇs""",

        'slaves': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║ sʟᴀᴠᴇ sʏsᴛᴇᴍ ║
╚═══════════════════╝</b>

<b>┌─ ᴄᴏʟʟᴇᴄᴛɪᴏɴ</b>
<b>├</b> <code>/grab [name]</code>
<b>│</b>  ᴄᴀᴛᴄʜ sᴘᴀᴡɴᴇᴅ sʟᴀᴠᴇ
<b>├</b> <code>/harem</code>
<b>│</b>  ᴠɪᴇᴡ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ
<b>├</b> <code>/smode</code>
<b>│</b>  sᴏʀᴛ ʙʏ ʀᴀʀɪᴛʏ
<b>└</b> <code>/hclaim</code>
   ᴅᴀɪʟʏ sʟᴀᴠᴇ ʀᴇᴡᴀʀᴅ

<b>┌─ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ</b>
<b>├</b> <code>/fav [id]</code>
<b>│</b>  ᴍᴀʀᴋ ғᴀᴠᴏʀɪᴛᴇ
<b>├</b> <code>/unfav [id]</code>
<b>│</b>  ʀᴇᴍᴏᴠᴇ ғᴀᴠᴏʀɪᴛᴇ
<b>└</b> <code>/gift @user [id]</code>
   ɢɪғᴛ ᴛᴏ ᴜsᴇʀ

<b>┌─ ɪɴғᴏʀᴍᴀᴛɪᴏɴ</b>
<b>├</b> <code>/check [name]</code>
<b>│</b>  sʟᴀᴠᴇ ᴅᴇᴛᴀɪʟs
<b>├</b> <code>/find [name]</code>
<b>│</b>  sᴇᴀʀᴄʜ sʟᴀᴠᴇs
<b>└</b> <code>/explore</code>
   ᴅɪsᴄᴏᴠᴇʀ ɴᴇᴡ ᴀʀᴇᴀs""",

        'trading': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║  ᴛʀᴀᴅᴇ ᴄᴇɴᴛᴇʀ  ║
╚═══════════════════╝</b>

<b>┌─ ᴛʀᴀᴅɪɴɢ sʏsᴛᴇᴍ</b>
<b>├</b> <code>/trade @user</code>
<b>│</b>  ɪɴɪᴛɪᴀᴛᴇ ᴛʀᴀᴅᴇ
<b>├</b> <code>/gift @user [id]</code>
<b>│</b>  ɢɪғᴛ sʟᴀᴠᴇ
<b>└</b> <code>/pay @user [amount]</code>
   sᴇɴᴅ ɢᴏʟᴅ

<b>┌─ ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ</b>
<b>├</b> <code>/store</code>
<b>│</b>  ʙʀᴏᴡsᴇ sᴛᴏʀᴇ
<b>├</b> <code>/addshop [item]</code>
<b>│</b>  ʟɪsᴛ ғᴏʀ sᴀʟᴇ
<b>└</b> <code>/rmshop [item]</code>
   ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ

<b>┌─ ᴠᴀʟᴜᴀᴛɪᴏɴ</b>
<b>├</b> <code>/sinfo [id]</code>
<b>│</b>  sʟᴀᴠᴇ ᴠᴀʟᴜᴇ
<b>└</b> <code>/check [name]</code>
   ᴍᴀʀᴋᴇᴛ ᴘʀɪᴄᴇ""",

        'profile': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║  ᴜsᴇʀ ᴘʀᴏғɪʟᴇ  ║
╚═══════════════════╝</b>

<b>┌─ sᴛᴀᴛɪsᴛɪᴄs</b>
<b>├</b> <code>/stats</code>
<b>│</b>  ʏᴏᴜʀ ᴏᴠᴇʀᴀʟʟ sᴛᴀᴛs
<b>├</b> <code>/gamestats</code>
<b>│</b>  ɢᴀᴍɪɴɢ ʀᴇᴄᴏʀᴅ
<b>└</b> <code>/xp</code>
   ᴇxᴘᴇʀɪᴇɴᴄᴇ ʟᴇᴠᴇʟ

<b>┌─ ᴄᴜsᴛᴏᴍɪᴢᴀᴛɪᴏɴ</b>
<b>├</b> <code>/ps</code>
<b>│</b>  ᴘʀᴏғɪʟᴇ sᴇᴛᴛɪɴɢs
<b>├</b> <code>/pstats</code>
<b>│</b>  ᴘʀᴏғɪʟᴇ sᴛᴀᴛs
<b>├</b> <code>/pview</code>
<b>│</b>  ᴠɪᴇᴡ ᴘʀᴏғɪʟᴇ
<b>└</b> <code>/pconfig</code>
   ᴄᴏɴғɪɢᴜʀᴇ sᴇᴛᴛɪɴɢs

<b>┌─ ᴘʀᴇғᴇʀᴇɴᴄᴇs</b>
<b>├</b> <code>/notifications</code>
<b>│</b>  ᴛᴏɢɢʟᴇ ᴀʟᴇʀᴛs
<b>├</b> <code>/prarity</code>
<b>│</b>  sᴇᴛ ʀᴀʀɪᴛʏ
<b>└</b> <code>/preset</code>
   ʀᴇsᴇᴛ sᴇᴛᴛɪɴɢs""",

        'social': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║  sᴏᴄɪᴀʟ ʜᴜʙ   ║
╚═══════════════════╝</b>

<b>┌─ ʀᴇʟᴀᴛɪᴏɴsʜɪᴘs</b>
<b>├</b> <code>/propose @user</code>
<b>│</b>  ᴍᴀʀʀɪᴀɢᴇ ᴘʀᴏᴘᴏsᴀʟ
<b>├</b> <code>/marry @user</code>
<b>│</b>  ᴍᴀʀʀʏ ᴜsᴇʀ
<b>└</b> <code>/dice</code>
   ʀᴀɴᴅᴏᴍ ᴍᴀᴛᴄʜ

<b>┌─ ᴄᴏᴍᴍᴜɴɪᴛʏ</b>
<b>├</b> <code>/topchat</code>
<b>│</b>  ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛs
<b>├</b> <code>/topgroups</code>
<b>│</b>  ᴛᴏᴘ ɢʀᴏᴜᴘs
<b>└</b> <code>/raid</code>
   ɢʀᴏᴜᴘ ᴇᴠᴇɴᴛ

<b>┌─ ᴀᴅᴍɪɴ</b>
<b>├</b> <code>/list</code>
<b>│</b>  ᴜsᴇʀ ʟɪsᴛ
<b>└</b> <code>/groups</code>
   ɢʀᴏᴜᴘ ʟɪsᴛ""",

        'rankings': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║  ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅs  ║
╚═══════════════════╝</b>

<b>┌─ ɢʟᴏʙᴀʟ ʀᴀɴᴋɪɴɢs</b>
<b>├</b> <code>/gstop</code>
<b>│</b>  ᴛᴏᴘ ɢᴏʟᴅ ʜᴏʟᴅᴇʀs
<b>├</b> <code>/xtop</code>
<b>│</b>  ʜɪɢʜᴇsᴛ xᴘ
<b>├</b> <code>/tops</code>
<b>│</b>  ʀɪᴄʜᴇsᴛ ᴘʟᴀʏᴇʀs
<b>└</b> <code>/tophunters</code>
   ᴇʟɪᴛᴇ ʜᴜɴᴛᴇʀs

<b>┌─ ɢᴀᴍᴇ ʀᴀɴᴋɪɴɢs</b>
<b>├</b> <code>/leaderboard</code>
<b>│</b>  ɢᴀᴍᴇ ʟᴇᴀᴅᴇʀs
<b>└</b> <code>/gamestats</code>
   ʏᴏᴜʀ ɢᴀᴍᴇ ʀᴀɴᴋ

<b>┌─ ᴄᴏᴍᴍᴜɴɪᴛʏ</b>
<b>├</b> <code>/topchat</code>
<b>│</b>  ᴀᴄᴛɪᴠᴇ ᴄʜᴀᴛs
<b>└</b> <code>/topgroups</code>
   ᴛᴏᴘ ɢʀᴏᴜᴘs""",

        'store': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║  ᴍᴀʀᴋᴇᴛᴘʟᴀᴄᴇ  ║
╚═══════════════════╝</b>

<b>┌─ sʜᴏᴘᴘɪɴɢ</b>
<b>├</b> <code>/store</code>
<b>│</b>  ʙʀᴏᴡsᴇ ɪᴛᴇᴍs
<b>└</b> <code>/sinv</code>
   ʏᴏᴜʀ ɪɴᴠᴇɴᴛᴏʀʏ

<b>┌─ sᴇʟʟɪɴɢ</b>
<b>├</b> <code>/addshop [item]</code>
<b>│</b>  ʟɪsᴛ ɪᴛᴇᴍ
<b>└</b> <code>/rmshop [item]</code>
   ʀᴇᴍᴏᴠᴇ ʟɪsᴛɪɴɢ

<b>┌─ sᴘᴇᴄɪᴀʟ</b>
<b>├</b> ᴘʀᴇᴍɪᴜᴍ ɪᴛᴇᴍs
<b>├</b> ʟɪᴍɪᴛᴇᴅ ᴇᴅɪᴛɪᴏɴs
<b>└</b> sᴇᴀsᴏɴᴀʟ ᴏғғᴇʀs""",

        'advanced': f"""<a href="{photo}">&#8203;</a><b>╔═══════════════════╗
║ ᴀᴅᴠᴀɴᴄᴇᴅ sʏsᴛᴇᴍ ║
╚═══════════════════╝</b>

<b>┌─ ᴄᴜsᴛᴏᴍɪᴢᴀᴛɪᴏɴ</b>
<b>├</b> <code>/pconfig</code>
<b>│</b>  ᴘʀᴏғɪʟᴇ sᴇᴛᴛɪɴɢs
<b>├</b> <code>/prarity</code>
<b>│</b>  sᴇᴛ ʀᴀʀɪᴛʏ
<b>├</b> <code>/prmrarity</code>
<b>│</b>  ʀᴇᴍᴏᴠᴇ ʀᴀʀɪᴛʏ
<b>└</b> <code>/preset</code>
   ʀᴇsᴇᴛ ᴀʟʟ

<b>┌─ ᴜᴛɪʟɪᴛʏ</b>
<b>├</b> <code>/phelp</code>
<b>│</b>  ᴘʀᴏғɪʟᴇ ɢᴜɪᴅᴇ
<b>├</b> <code>/pview</code>
<b>│</b>  ᴠɪᴇᴡ sᴇᴛᴛɪɴɢs
<b>└</b> <code>/notifications</code>
   ᴀʟᴇʀᴛ ᴍᴀɴᴀɢᴇʀ

<b>┌─ ʜᴇʟᴘ</b>
<b>├</b> <code>/helpgames</code>
<b>│</b>  ɢᴀᴍᴇ ɢᴜɪᴅᴇ
<b>├</b> <code>/bankhelp</code>
<b>│</b>  ʙᴀɴᴋɪɴɢ ɢᴜɪᴅᴇ
<b>└</b> <code>/bankexample</code>
   ᴇxᴀᴍᴘʟᴇs"""
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
            await query.answer("ᴛʜɪs ɪɴᴛᴇʀғᴀᴄᴇ ɪs ɴᴏᴛ ғᴏʀ ʏᴏᴜ", show_alert=True)
            return

        current_state = user_states.get(user_id)

        if current_state == action:
            await query.answer("ᴀʟʀᴇᴀᴅʏ ᴏɴ ᴛʜɪs ᴘᴀɢᴇ", show_alert=False)
            return

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
                await query.answer("ᴄᴀᴛᴇɢᴏʀʏ ɴᴏᴛ ғᴏᴜɴᴅ", show_alert=True)

    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            print(f"BadRequest in help_callback: {e}")
    except Exception as e:
        print(f"Error in help_callback: {e}")

# Register handlers
application.add_handler(CommandHandler(['help', 'menu', 'panel'], help_command, block=False))
application.add_handler(CallbackQueryHandler(help_callback, pattern=r'^help_', block=False))