from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape

from shivu import application, user_collection, collection, user_totals_collection, LOGGER

# Owner ID for approval
OWNER_ID = 5147822244

# Pass configuration
PASS_CONFIG = {
    'free': {
        'name': 'ғʀᴇᴇ ᴘᴀss',
        'weekly_reward': 1000,
        'streak_bonus': 5000,
        'mythic_characters': 0,
        'grab_multiplier': 1.0
    },
    'premium': {
        'name': 'ᴘʀᴇᴍɪᴜᴍ ᴘᴀss',
        'weekly_reward': 5000,
        'streak_bonus': 25000,
        'mythic_characters': 1,
        'cost': 50000,
        'grab_multiplier': 1.5
    },
    'elite': {
        'name': 'ᴇʟɪᴛᴇ ᴘᴀss',
        'weekly_reward': 15000,
        'streak_bonus': 100000,
        'mythic_characters': 5,
        'cost_inr': 50,
        'upi_id': 'looktouhid@oksbi',
        'activation_bonus': 1000000,
        'grab_multiplier': 2.0
    }
}

# Task requirements
MYTHIC_TASKS = {
    'invites': {'required': 5, 'reward': 'ᴍʏᴛʜɪᴄ ᴄʜᴀʀᴀᴄᴛᴇʀ'},
    'weekly_claims': {'required': 4, 'reward': 'ʙᴏɴᴜs ʀᴇᴡᴀʀᴅ'},
    'grabs': {'required': 50, 'reward': 'ᴄᴏʟʟᴇᴄᴛᴏʀ'}
}

# Invite rewards
INVITE_REWARD = 1000


def to_small_caps(text):
    """Convert text to small caps"""
    small_caps_map = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ',
        'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ',
        's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 'H': 'ʜ', 'I': 'ɪ',
        'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ',
        'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'
    }
    return ''.join(small_caps_map.get(c, c) for c in text)


async def get_or_create_pass_data(user_id: int) -> dict:
    """Get or create user pass data"""
    user = await user_collection.find_one({'id': user_id})

    if not user:
        user = {
            'id': user_id,
            'characters': [],
            'balance': 0
        }
        await user_collection.insert_one(user)

    if 'pass_data' not in user:
        pass_data = {
            'tier': 'free',
            'weekly_claims': 0,
            'last_weekly_claim': None,
            'streak_count': 0,
            'last_streak_claim': None,
            'tasks': {
                'invites': 0,
                'weekly_claims': 0,
                'grabs': 0
            },
            'mythic_unlocked': False,
            'premium_expires': None,
            'elite_expires': None,
            'pending_elite_payment': None,
            'invited_users': [],
            'total_invite_earnings': 0
        }
        await user_collection.update_one(
            {'id': user_id},
            {'$set': {'pass_data': pass_data}}
        )
        return pass_data

    return user.get('pass_data', {})


async def check_and_update_tier(user_id: int) -> str:
    """Check if tier has expired and update accordingly"""
    pass_data = await get_or_create_pass_data(user_id)
    tier = pass_data.get('tier', 'free')

    if tier == 'elite':
        elite_expires = pass_data.get('elite_expires')
        if elite_expires and isinstance(elite_expires, datetime):
            if elite_expires < datetime.utcnow():
                await user_collection.update_one(
                    {'id': user_id},
                    {'$set': {'pass_data.tier': 'free'}}
                )
                return 'free'
    elif tier == 'premium':
        premium_expires = pass_data.get('premium_expires')
        if premium_expires and isinstance(premium_expires, datetime):
            if premium_expires < datetime.utcnow():
                await user_collection.update_one(
                    {'id': user_id},
                    {'$set': {'pass_data.tier': 'free'}}
                )
                return 'free'

    return tier


async def update_grab_task(user_id: int):
    """Update grab task count - Call this from your grab handler"""
    try:
        await user_collection.update_one(
            {'id': user_id},
            {'$inc': {'pass_data.tasks.grabs': 1}}
        )
        LOGGER.info(f"[PASS] Grab task updated for user {user_id}")
    except Exception as e:
        LOGGER.error(f"[PASS] Error updating grab task: {e}")


async def pass_command(update: Update, context: CallbackContext) -> None:
    """Show pass status and information - /pass"""
    user_id = update.effective_user.id

    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)
        user = await user_collection.find_one({'id': user_id})

        tier_name = PASS_CONFIG[tier]['name']
        weekly_claims = pass_data.get('weekly_claims', 0)
        streak_count = pass_data.get('streak_count', 0)
        tasks = pass_data.get('tasks', {})
        mythic_unlocked = pass_data.get('mythic_unlocked', False)
        balance = user.get('balance', 0)

        total_tasks = len(MYTHIC_TASKS)
        completed_tasks = sum(1 for task_key, task_info in MYTHIC_TASKS.items() 
                             if tasks.get(task_key, 0) >= task_info['required'])

        tier_status = to_small_caps("free")
        if tier == 'elite':
            elite_expires = pass_data.get('elite_expires')
            if elite_expires and isinstance(elite_expires, datetime):
                days_left = (elite_expires - datetime.utcnow()).days
                tier_status = to_small_caps("elite") + f" ({days_left} " + to_small_caps("days") + ")"
        elif tier == 'premium':
            premium_expires = pass_data.get('premium_expires')
            if premium_expires and isinstance(premium_expires, datetime):
                days_left = (premium_expires - datetime.utcnow()).days
                tier_status = to_small_caps("premium") + f" ({days_left} " + to_small_caps("days") + ")"

        mythic_status = to_small_caps("unlocked") if mythic_unlocked else to_small_caps("locked")
        grab_multiplier = PASS_CONFIG[tier]['grab_multiplier']

        caption = f"""╔═══════════════════╗
  {tier_name}
╚═══════════════════╝

{to_small_caps('user')}: {escape(update.effective_user.first_name)}
{to_small_caps('id')}: <code>{user_id}</code>
{to_small_caps('balance')}: <code>{balance:,}</code>

━━━━━━━━━━━━━━━━━━━
{to_small_caps('progress')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('weekly claims')}: {weekly_claims}/6
{to_small_caps('streak')}: {streak_count} {to_small_caps('weeks')}
{to_small_caps('tasks completed')}: {completed_tasks}/{total_tasks}
{to_small_caps('mythic unlock')}: {mythic_status}
{to_small_caps('grab multiplier')}: {grab_multiplier}x

━━━━━━━━━━━━━━━━━━━
{to_small_caps('rewards')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('weekly')}: {PASS_CONFIG[tier]['weekly_reward']:,}
{to_small_caps('streak bonus')}: {PASS_CONFIG[tier]['streak_bonus']:,}
{to_small_caps('tier status')}: {tier_status}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('commands')}
━━━━━━━━━━━━━━━━━━━
/pclaim - {to_small_caps('weekly reward')}
/sweekly - {to_small_caps('streak bonus')}
/tasks - {to_small_caps('view tasks')}
/upgrade - {to_small_caps('get premium')}
/invite - {to_small_caps('invite friends')}

{to_small_caps('complete tasks to unlock mythic character')}
"""

        keyboard = [
            [
                InlineKeyboardButton(to_small_caps("claim"), callback_data=f"pass_claim_{user_id}"),
                InlineKeyboardButton(to_small_caps("tasks"), callback_data=f"pass_tasks_{user_id}")
            ],
            [
                InlineKeyboardButton(to_small_caps("upgrade"), callback_data=f"pass_upgrade_{user_id}"),
                InlineKeyboardButton(to_small_caps("invite"), callback_data=f"pass_invite_{user_id}")
            ],
            [
                InlineKeyboardButton(to_small_caps("help"), callback_data=f"pass_help_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_photo(
            photo="https://files.catbox.moe/z8fhwx.jpg",
            caption=caption,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        LOGGER.info(f"[PASS] Status shown for user {user_id}")

    except Exception as e:
        LOGGER.error(f"[PASS ERROR] {e}")
        await update.message.reply_text(to_small_caps('error loading pass data'))


async def pclaim_command(update: Update, context: CallbackContext) -> None:
    """Claim weekly reward - /pclaim"""
    user_id = update.effective_user.id

    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)

        last_claim = pass_data.get('last_weekly_claim')
        if last_claim and isinstance(last_claim, datetime):
            time_since = datetime.utcnow() - last_claim
            if time_since < timedelta(days=7):
                remaining = timedelta(days=7) - time_since
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60

                msg = (
                    f"{to_small_caps('next claim in')}\n\n"
                    f"{remaining.days} {to_small_caps('days')} {hours} {to_small_caps('hours')} {minutes} {to_small_caps('minutes')}"
                )
                await update.message.reply_text(msg)
                return

        reward = PASS_CONFIG[tier]['weekly_reward']
        mythic_chars_count = PASS_CONFIG[tier]['mythic_characters']

        new_claims = pass_data.get('weekly_claims', 0) + 1
        await user_collection.update_one(
            {'id': user_id},
            {
                '$set': {
                    'pass_data.last_weekly_claim': datetime.utcnow(),
                    'pass_data.weekly_claims': new_claims,
                    'pass_data.tasks.weekly_claims': new_claims
                },
                '$inc': {'balance': reward}
            }
        )

        # Streak management
        last_streak = pass_data.get('last_streak_claim')
        if last_streak and isinstance(last_streak, datetime):
            days_since = (datetime.utcnow() - last_streak).days
            if 6 <= days_since <= 8:
                await user_collection.update_one(
                    {'id': user_id},
                    {
                        '$inc': {'pass_data.streak_count': 1},
                        '$set': {'pass_data.last_streak_claim': datetime.utcnow()}
                    }
                )
            elif days_since > 8:
                await user_collection.update_one(
                    {'id': user_id},
                    {'$set': {'pass_data.streak_count': 0}}
                )
        else:
            await user_collection.update_one(
                {'id': user_id},
                {
                    '$set': {
                        'pass_data.streak_count': 1,
                        'pass_data.last_streak_claim': datetime.utcnow()
                    }
                }
            )

        premium_msg = ""
        if mythic_chars_count > 0:
            mythic_chars = await collection.find({'rarity': '🏵 Mythic'}).limit(mythic_chars_count).to_list(length=mythic_chars_count)

            if mythic_chars:
                await user_collection.update_one(
                    {'id': user_id},
                    {'$push': {'characters': {'$each': mythic_chars}}}
                )

                await user_totals_collection.update_one(
                    {'id': user_id},
                    {'$inc': {'count': len(mythic_chars)}},
                    upsert=True
                )

                premium_msg = f"\n\n{to_small_caps('bonus')}: {len(mythic_chars)} {to_small_caps('mythic characters added')}"

        success_text = (
            f"{to_small_caps('claimed successfully')}\n\n"
            f"{to_small_caps('reward')}: <code>{reward:,}</code>\n"
            f"{to_small_caps('total claims')}: {new_claims}/6{premium_msg}"
        )

        await update.message.reply_text(success_text, parse_mode='HTML')
        LOGGER.info(f"[PASS] User {user_id} claimed weekly reward")

    except Exception as e:
        LOGGER.error(f"[PASS CLAIM ERROR] {e}")
        await update.message.reply_text(to_small_caps('error processing claim'))


async def sweekly_command(update: Update, context: CallbackContext) -> None:
    """Claim 6-week streak bonus - /sweekly"""
    user_id = update.effective_user.id

    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)

        weekly_claims = pass_data.get('weekly_claims', 0)
        if weekly_claims < 6:
            msg = (
                f"{to_small_caps('you need 6 weekly claims')}\n"
                f"{to_small_caps('current')}: {weekly_claims}/6"
            )
            await update.message.reply_text(msg)
            return

        bonus = PASS_CONFIG[tier]['streak_bonus']
        mythic_char = await collection.find_one({'rarity': '🏵 Mythic'})

        update_data = {
            '$inc': {'balance': bonus},
            '$set': {'pass_data.weekly_claims': 0}
        }

        if mythic_char:
            update_data['$push'] = {'characters': mythic_char}

        await user_collection.update_one(
            {'id': user_id},
            update_data
        )

        if mythic_char:
            await user_totals_collection.update_one(
                {'id': user_id},
                {'$inc': {'count': 1}},
                upsert=True
            )

        char_msg = ""
        if mythic_char:
            char_name = mythic_char.get('name', 'unknown')
            char_anime = mythic_char.get('anime', 'unknown')
            char_msg = f"\n\n{to_small_caps('bonus character')}:\n{to_small_caps('name')}: {char_name}\n{to_small_caps('anime')}: {char_anime}"

        await update.message.reply_text(
            f"{to_small_caps('streak bonus claimed')}\n\n"
            f"{to_small_caps('bonus gold')}: <code>{bonus:,}</code>\n"
            f"{to_small_caps('weekly claims reset to')} 0{char_msg}",
            parse_mode='HTML'
        )

        LOGGER.info(f"[PASS] User {user_id} claimed streak bonus")

    except Exception as e:
        LOGGER.error(f"[PASS SWEEKLY ERROR] {e}")
        await update.message.reply_text(to_small_caps('error processing bonus'))


async def tasks_command(update: Update, context: CallbackContext) -> None:
    """Show task progress - /tasks"""
    user_id = update.effective_user.id

    try:
        pass_data = await get_or_create_pass_data(user_id)
        tasks = pass_data.get('tasks', {})
        mythic_unlocked = pass_data.get('mythic_unlocked', False)

        task_list = []
        all_completed = True
        for task_key, task_info in MYTHIC_TASKS.items():
            current = tasks.get(task_key, 0)
            required = task_info['required']
            reward = task_info['reward']
            progress = min(100, int((current / required) * 100))

            if current >= required:
                status = to_small_caps("completed")
            else:
                status = to_small_caps("in progress")
                all_completed = False

            task_list.append(
                f"<b>{to_small_caps(task_key.replace('_', ' '))}:</b> {current}/{required}\n"
                f"   {'█' * (progress // 10)}{'░' * (10 - progress // 10)} {progress}%\n"
                f"   {to_small_caps('reward')}: {reward}\n"
                f"   {to_small_caps('status')}: {status}"
            )

        if all_completed and not mythic_unlocked:
            mythic_char = await collection.find_one({'rarity': '🏵 Mythic'})
            if mythic_char:
                await user_collection.update_one(
                    {'id': user_id},
                    {
                        '$push': {'characters': mythic_char},
                        '$set': {'pass_data.mythic_unlocked': True}
                    }
                )

                await user_totals_collection.update_one(
                    {'id': user_id},
                    {'$inc': {'count': 1}},
                    upsert=True
                )

                mythic_unlocked = True
                LOGGER.info(f"[PASS] Mythic unlocked for user {user_id}")

        mythic_status = to_small_caps('completed') if mythic_unlocked else to_small_caps('locked')

        caption = f"""╔═══════════════════╗
  {to_small_caps('mythic tasks')}
╚═══════════════════╝

{chr(10).join(task_list)}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('mythic unlock')}: {mythic_status}

{to_small_caps('complete all tasks to unlock a free mythic character')}
"""

        await update.message.reply_text(caption, parse_mode='HTML')
        LOGGER.info(f"[PASS] Tasks shown for user {user_id}")

    except Exception as e:
        LOGGER.error(f"[PASS TASKS ERROR] {e}")
        await update.message.reply_text(to_small_caps('error loading tasks'))


async def invite_command(update: Update, context: CallbackContext) -> None:
    """Show invite program - /invite"""
    user_id = update.effective_user.id

    try:
        pass_data = await get_or_create_pass_data(user_id)

        invited_users = pass_data.get('invited_users', [])
        total_invites = pass_data.get('tasks', {}).get('invites', 0)
        total_earnings = pass_data.get('total_invite_earnings', 0)

        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start=r_{user_id}"

        caption = f"""╔═══════════════════╗
  {to_small_caps('invite program')}
╚═══════════════════╝

{to_small_caps('your referrals')}: {total_invites}
{to_small_caps('earned')}: {total_earnings:,} {to_small_caps('gold')}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('how to invite')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('copy link below')}
{to_small_caps('share with friends')}
{to_small_caps('they click and start bot')}
{to_small_caps('instant rewards')}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('rewards')}
━━━━━━━━━━━━━━━━━━━
{INVITE_REWARD:,} {to_small_caps('gold per invite')}
{to_small_caps('counts toward tasks')}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('your invite link')}
━━━━━━━━━━━━━━━━━━━
<code>{invite_link}</code>

{to_small_caps('tap to copy link')}

{to_small_caps('use')} /addinvite {to_small_caps('command to manually add invites')}
"""

        await update.message.reply_text(caption, parse_mode='HTML')
        LOGGER.info(f"[PASS] Invite shown for user {user_id}")

    except Exception as e:
        LOGGER.error(f"[PASS INVITE ERROR] {e}")
        await update.message.reply_text(to_small_caps('error loading invite'))


async def upgrade_command(update: Update, context: CallbackContext) -> None:
    """Show upgrade options - /upgrade"""
    user_id = update.effective_user.id

    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)
        user = await user_collection.find_one({'id': user_id})
        balance = user.get('balance', 0)

        caption = f"""╔═══════════════════╗
  {to_small_caps('upgrade options')}
╚═══════════════════╝

{to_small_caps('your balance')}: <code>{balance:,}</code>
{to_small_caps('current tier')}: {PASS_CONFIG[tier]['name']}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('premium pass')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('cost')}: <code>50,000</code> {to_small_caps('gold')}
{to_small_caps('duration')}: 30 {to_small_caps('days')}

<b>{to_small_caps('benefits')}:</b>
{to_small_caps('weekly reward')}: 5,000
{to_small_caps('streak bonus')}: 25,000
{to_small_caps('mythic chars')}: 3 {to_small_caps('per claim')}
{to_small_caps('multiplier')}: 1.5x

━━━━━━━━━━━━━━━━━━━
{to_small_caps('elite pass')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('cost')}: 50 {to_small_caps('inr')}
{to_small_caps('payment')}: UPI
{to_small_caps('duration')}: 30 {to_small_caps('days')}

<b>{to_small_caps('benefits')}:</b>
{to_small_caps('activation bonus')}: 100,000,0 {to_small_caps('gold')}
{to_small_caps('instant mythics')}: 5 {to_small_caps('characters')}
{to_small_caps('weekly reward')}: 15,000
{to_small_caps('streak bonus')}: 100,000
{to_small_caps('mythic per claim')}: 1
{to_small_caps('multiplier')}: 2x

{to_small_caps('choose your upgrade')}
"""

        keyboard = [
            [InlineKeyboardButton(to_small_caps("buy premium"), callback_data=f"pass_buypremium_{user_id}")],
            [InlineKeyboardButton(to_small_caps("buy elite"), callback_data=f"pass_buyelite_{user_id}")],
            [InlineKeyboardButton(to_small_caps("back"), callback_data=f"pass_back_{user_id}")]
        ]

        await update.message.reply_photo(
            photo="https://files.catbox.moe/z8fhwx.jpg",
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

        LOGGER.info(f"[PASS] Upgrade options shown for user {user_id}")

    except Exception as e:
        LOGGER.error(f"[PASS UPGRADE ERROR] {e}")
        await update.message.reply_text(to_small_caps('error loading upgrade'))


async def addinvite_command(update: Update, context: CallbackContext) -> None:
    """Add invite count for a user - Owner only - /addinvite <user_id> <count>"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(to_small_caps('unauthorized'))
        return

    try:
        if len(context.args) < 2:
            await update.message.reply_text(
                f"{to_small_caps('usage')}: /addinvite <{to_small_caps('user id')}> <{to_small_caps('count')}>\n\n"
                f"{to_small_caps('example')}: /addinvite 123456789 5"
            )
            return

        target_user_id = int(context.args[0])
        invite_count = int(context.args[1])

        if invite_count <= 0:
            await update.message.reply_text(to_small_caps('count must be positive'))
            return

        await get_or_create_pass_data(target_user_id)

        gold_reward = invite_count * INVITE_REWARD

        await user_collection.update_one(
            {'id': target_user_id},
            {
                '$inc': {
                    'pass_data.tasks.invites': invite_count,
                    'pass_data.total_invite_earnings': gold_reward,
                    'balance': gold_reward
                }
            }
        )

        await update.message.reply_text(
            f"{to_small_caps('invite added')}\n\n"
            f"{to_small_caps('user id')}: <code>{target_user_id}</code>\n"
            f"{to_small_caps('invites added')}: {invite_count}\n"
            f"{to_small_caps('gold awarded')}: <code>{gold_reward:,}</code>",
            parse_mode='HTML'
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"{to_small_caps('invite reward')}\n\n"
                    f"{to_small_caps('you received')} {invite_count} {to_small_caps('invite credits')}\n"
                    f"{to_small_caps('gold earned')}: <code>{gold_reward:,}</code>"
                ),
                parse_mode='HTML'
            )
        except:
            pass

        LOGGER.info(f"[PASS] Added {invite_count} invites to user {target_user_id}")

    except ValueError:
        await update.message.reply_text(to_small_caps('invalid user id or count'))
    except Exception as e:
        LOGGER.error(f"[PASS ADDINVITE ERROR] {e}")
        await update.message.reply_text(to_small_caps('error adding invite'))


async def addgrab_command(update: Update, context: CallbackContext) -> None:
    """Add grab count for a user - Owner only - /addgrab <user_id> <count>"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(to_small_caps('unauthorized'))
        return

    try:
        if len(context.args) < 2:
            await update.message.reply_text(
                f"{to_small_caps('usage')}: /addgrab <{to_small_caps('user id')}> <{to_small_caps('count')}>\n\n"
                f"{to_small_caps('example')}: /addgrab 123456789 10"
            )
            return

        target_user_id = int(context.args[0])
        grab_count = int(context.args[1])

        if grab_count <= 0:
            await update.message.reply_text(to_small_caps('count must be positive'))
            return

        await get_or_create_pass_data(target_user_id)

        await user_collection.update_one(
            {'id': target_user_id},
            {'$inc': {'pass_data.tasks.grabs': grab_count}}
        )

        await update.message.reply_text(
            f"{to_small_caps('grabs added')}\n\n"
            f"{to_small_caps('user id')}: <code>{target_user_id}</code>\n"
            f"{to_small_caps('grabs added')}: {grab_count}",
            parse_mode='HTML'
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"{to_small_caps('grab credits added')}\n\n"
                    f"{to_small_caps('you received')} {grab_count} {to_small_caps('grab credits')}"
                ),
                parse_mode='HTML'
            )
        except:
            pass

        LOGGER.info(f"[PASS] Added {grab_count} grabs to user {target_user_id}")

    except ValueError:
        await update.message.reply_text(to_small_caps('invalid user id or count'))
    except Exception as e:
        LOGGER.error(f"[PASS ADDGRAB ERROR] {e}")
        await update.message.reply_text(to_small_caps('error adding grabs'))


async def approve_elite_command(update: Update, context: CallbackContext) -> None:
    """Owner command to approve elite pass payment - /approveelite <user_id>"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(to_small_caps('unauthorized'))
        return

    try:
        if len(context.args) < 1:
            await update.message.reply_text(
                f"{to_small_caps('usage')}: /approveelite <{to_small_caps('user id')}>\n\n"
                f"{to_small_caps('example')}: /approveelite 123456789"
            )
            return

        target_user_id = int(context.args[0])

        target_user = await user_collection.find_one({'id': target_user_id})
        if not target_user:
            await update.message.reply_text(to_small_caps('user not found'))
            return

        pass_data = target_user.get('pass_data', {})
        pending = pass_data.get('pending_elite_payment')

        if not pending:
            await update.message.reply_text(to_small_caps('no pending payment for this user'))
            return

        expires = datetime.utcnow() + timedelta(days=30)
        activation_bonus = PASS_CONFIG['elite']['activation_bonus']

        mythic_chars = await collection.find({'rarity': '🏵 Mythic'}).limit(5).to_list(length=5)

        await user_collection.update_one(
            {'id': target_user_id},
            {
                '$set': {
                    'pass_data.tier': 'elite',
                    'pass_data.elite_expires': expires,
                    'pass_data.pending_elite_payment': None
                },
                '$inc': {'balance': activation_bonus},
                '$push': {'characters': {'$each': mythic_chars}}
            }
        )

        await user_totals_collection.update_one(
            {'id': target_user_id},
            {'$inc': {'count': len(mythic_chars)}},
            upsert=True
        )

        await update.message.reply_text(
            f"{to_small_caps('elite pass activated')}\n\n"
            f"{to_small_caps('user id')}: <code>{target_user_id}</code>\n"
            f"{to_small_caps('gold bonus')}: <code>{activation_bonus:,}</code>\n"
            f"{to_small_caps('mythic characters')}: {len(mythic_chars)}\n"
            f"{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}",
            parse_mode='HTML'
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"╔═══════════════════╗\n"
                    f"  {to_small_caps('elite pass activated')}\n"
                    f"╚═══════════════════╝\n\n"
                    f"{to_small_caps('your elite pass has been activated')}\n\n"
                    f"<b>{to_small_caps('received')}:</b>\n"
                    f"{to_small_caps('gold coins')}: <code>{activation_bonus:,}</code>\n"
                    f"{to_small_caps('mythic characters')}: {len(mythic_chars)}\n"
                    f"{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}\n\n"
                    f"{to_small_caps('enjoy your benefits')}\n"
                    f"{to_small_caps('multiplier')}: 2x"
                ),
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"[PASS] Could not notify user {target_user_id}: {e}")

        LOGGER.info(f"[PASS] Elite pass approved for user {target_user_id}")

    except ValueError:
        await update.message.reply_text(to_small_caps('invalid user id'))
    except Exception as e:
        LOGGER.error(f"[PASS APPROVE ERROR] {e}")
        await update.message.reply_text(to_small_caps('error processing approval'))


async def passhelp_command(update: Update, context: CallbackContext) -> None:
    """Show all pass commands - /passhelp"""
    help_text = f"""╔═══════════════════╗
  {to_small_caps('pass system commands')}
╚═══════════════════╝

<b>{to_small_caps('user commands')}:</b>
/pass - {to_small_caps('view pass status')}
/pclaim - {to_small_caps('claim weekly reward')}
/sweekly - {to_small_caps('claim 6 week streak bonus')}
/tasks - {to_small_caps('view task progress')}
/upgrade - {to_small_caps('upgrade to premium or elite')}
/invite - {to_small_caps('get invite link')}
/passhelp - {to_small_caps('show this help')}

<b>{to_small_caps('owner commands')}:</b>
/addinvite <{to_small_caps('user id')}> <{to_small_caps('count')}> - {to_small_caps('add invites')}
/addgrab <{to_small_caps('user id')}> <{to_small_caps('count')}> - {to_small_caps('add grabs')}
/approveelite <{to_small_caps('user id')}> - {to_small_caps('approve elite payment')}

<b>{to_small_caps('pass tiers')}:</b>
{to_small_caps('free')}: 1,000 {to_small_caps('weekly')} | 5,000 {to_small_caps('streak')}
{to_small_caps('premium')}: 5,000 {to_small_caps('weekly')} | 25,000 {to_small_caps('streak')} | 3
{to_small_caps('elite')}: 15,000 {to_small_caps('weekly')} | 100,000 {to_small_caps('streak')} | 10 {to_small_caps('mythic per claim')}

<b>{to_small_caps('tasks for mythic unlock')}:</b>
5 {to_small_caps('invites')}
4 {to_small_caps('weekly claims')}
50 {to_small_caps('grabs')}
"""

    await update.message.reply_text(help_text, parse_mode='HTML')


async def pass_callback(update: Update, context: CallbackContext) -> None:
    """Handle all pass button callbacks"""
    query = update.callback_query

    try:
        data = query.data
        if not data.startswith('pass_'):
            await query.answer()
            return

        parts = data.split('_')
        action = parts[1]

        # Get user_id from callback data
        if len(parts) >= 3:
            try:
                user_id = int(parts[-1])
            except:
                user_id = query.from_user.id
        else:
            user_id = query.from_user.id

        # Verify it's the correct user
        if query.from_user.id != user_id:
            await query.answer(to_small_caps("not your request"), show_alert=True)
            return

        # Handle claim action
        if action == 'claim':
            await query.answer()
            tier = await check_and_update_tier(user_id)
            pass_data = await get_or_create_pass_data(user_id)

            last_claim = pass_data.get('last_weekly_claim')
            if last_claim and isinstance(last_claim, datetime):
                time_since = datetime.utcnow() - last_claim
                if time_since < timedelta(days=7):
                    remaining = timedelta(days=7) - time_since
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60

                    msg = (
                        f"{to_small_caps('next claim in')}\n\n"
                        f"{remaining.days} {to_small_caps('days')} {hours} {to_small_caps('hours')} {minutes} {to_small_caps('minutes')}"
                    )
                    await query.answer(msg, show_alert=True)
                    return

            reward = PASS_CONFIG[tier]['weekly_reward']
            mythic_chars_count = PASS_CONFIG[tier]['mythic_characters']

            new_claims = pass_data.get('weekly_claims', 0) + 1
            await user_collection.update_one(
                {'id': user_id},
                {
                    '$set': {
                        'pass_data.last_weekly_claim': datetime.utcnow(),
                        'pass_data.weekly_claims': new_claims,
                        'pass_data.tasks.weekly_claims': new_claims
                    },
                    '$inc': {'balance': reward}
                }
            )

            # Streak management
            last_streak = pass_data.get('last_streak_claim')
            if last_streak and isinstance(last_streak, datetime):
                days_since = (datetime.utcnow() - last_streak).days
                if 6 <= days_since <= 8:
                    await user_collection.update_one(
                        {'id': user_id},
                        {
                            '$inc': {'pass_data.streak_count': 1},
                            '$set': {'pass_data.last_streak_claim': datetime.utcnow()}
                        }
                    )
                elif days_since > 8:
                    await user_collection.update_one(
                        {'id': user_id},
                        {'$set': {'pass_data.streak_count': 0}}
                    )
            else:
                await user_collection.update_one(
                    {'id': user_id},
                    {
                        '$set': {
                            'pass_data.streak_count': 1,
                            'pass_data.last_streak_claim': datetime.utcnow()
                        }
                    }
                )

            premium_msg = ""
            if mythic_chars_count > 0:
                mythic_chars = await collection.find({'rarity': '🏵 Mythic'}).limit(mythic_chars_count).to_list(length=mythic_chars_count)

                if mythic_chars:
                    await user_collection.update_one(
                        {'id': user_id},
                        {'$push': {'characters': {'$each': mythic_chars}}}
                    )

                    await user_totals_collection.update_one(
                        {'id': user_id},
                        {'$inc': {'count': len(mythic_chars)}},
                        upsert=True
                    )

                    premium_msg = f"\n\n{to_small_caps('bonus')}: {len(mythic_chars)} {to_small_caps('mythic characters added')}"

            success_text = (
                f"{to_small_caps('claimed successfully')}\n\n"
                f"{to_small_caps('reward')}: <code>{reward:,}</code>\n"
                f"{to_small_caps('total claims')}: {new_claims}/6{premium_msg}"
            )

            await query.message.reply_text(success_text, parse_mode='HTML')
            LOGGER.info(f"[PASS] User {user_id} claimed weekly reward")

        # Handle tasks action
        elif action == 'tasks':
            await query.answer()
            pass_data = await get_or_create_pass_data(user_id)
            tasks = pass_data.get('tasks', {})
            mythic_unlocked = pass_data.get('mythic_unlocked', False)

            task_list = []
            all_completed = True
            for task_key, task_info in MYTHIC_TASKS.items():
                current = tasks.get(task_key, 0)
                required = task_info['required']
                reward = task_info['reward']
                progress = min(100, int((current / required) * 100))

                if current >= required:
                    status = to_small_caps("completed")
                else:
                    status = to_small_caps("in progress")
                    all_completed = False

                task_list.append(
                    f"<b>{to_small_caps(task_key.replace('_', ' '))}:</b> {current}/{required}\n"
                    f"   {'█' * (progress // 10)}{'░' * (10 - progress // 10)} {progress}%\n"
                    f"   {to_small_caps('reward')}: {reward}\n"
                    f"   {to_small_caps('status')}: {status}"
                )

            if all_completed and not mythic_unlocked:
                mythic_char = await collection.find_one({'rarity': '🏵 Mythic'})
                if mythic_char:
                    await user_collection.update_one(
                        {'id': user_id},
                        {
                            '$push': {'characters': mythic_char},
                            '$set': {'pass_data.mythic_unlocked': True}
                        }
                    )

                    await user_totals_collection.update_one(
                        {'id': user_id},
                        {'$inc': {'count': 1}},
                        upsert=True
                    )

                    mythic_unlocked = True
                    LOGGER.info(f"[PASS] Mythic unlocked for user {user_id}")

            mythic_status = to_small_caps('completed') if mythic_unlocked else to_small_caps('locked')

            caption = f"""╔═══════════════════╗
  {to_small_caps('mythic tasks')}
╚═══════════════════╝

{chr(10).join(task_list)}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('mythic unlock')}: {mythic_status}

{to_small_caps('complete all tasks to unlock a free mythic character')}
"""

            keyboard = [[
                InlineKeyboardButton(to_small_caps("back"), callback_data=f"pass_back_{user_id}")
            ]]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle upgrade action
        elif action == 'upgrade':
            await query.answer()
            tier = await check_and_update_tier(user_id)
            pass_data = await get_or_create_pass_data(user_id)
            user = await user_collection.find_one({'id': user_id})
            balance = user.get('balance', 0)

            caption = f"""╔═══════════════════╗
  {to_small_caps('upgrade options')}
╚═══════════════════╝

{to_small_caps('your balance')}: <code>{balance:,}</code>
{to_small_caps('current tier')}: {PASS_CONFIG[tier]['name']}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('premium pass')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('cost')}: <code>50,000</code> {to_small_caps('gold')}
{to_small_caps('duration')}: 30 {to_small_caps('days')}

<b>{to_small_caps('benefits')}:</b>
{to_small_caps('weekly reward')}: 5,000
{to_small_caps('streak bonus')}: 25,000
{to_small_caps('mythic chars')}: 3 {to_small_caps('per claim')}
{to_small_caps('multiplier')}: 1.5x

━━━━━━━━━━━━━━━━━━━
{to_small_caps('elite pass')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('cost')}: 50 {to_small_caps('inr')}
{to_small_caps('payment')}: UPI
{to_small_caps('duration')}: 30 {to_small_caps('days')}

<b>{to_small_caps('benefits')}:</b>
{to_small_caps('activation bonus')}: 100,000,0 {to_small_caps('gold')}
{to_small_caps('instant mythics')}: 5 {to_small_caps('characters')}
{to_small_caps('weekly reward')}: 15,000
{to_small_caps('streak bonus')}: 100,000
{to_small_caps('multiplier')}: 2x

{to_small_caps('choose your upgrade')}
"""

            keyboard = [
                [InlineKeyboardButton(to_small_caps("buy premium"), callback_data=f"pass_buypremium_{user_id}")],
                [InlineKeyboardButton(to_small_caps("buy elite"), callback_data=f"pass_buyelite_{user_id}")],
                [InlineKeyboardButton(to_small_caps("back"), callback_data=f"pass_back_{user_id}")]
            ]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle invite action
        elif action == 'invite':
            await query.answer()
            pass_data = await get_or_create_pass_data(user_id)

            invited_users = pass_data.get('invited_users', [])
            total_invites = pass_data.get('tasks', {}).get('invites', 0)
            total_earnings = pass_data.get('total_invite_earnings', 0)

            bot_username = context.bot.username
            invite_link = f"https://t.me/{bot_username}?start=r_{user_id}"

            caption = f"""╔═══════════════════╗
  {to_small_caps('invite program')}
╚═══════════════════╝

{to_small_caps('your referrals')}: {total_invites}
{to_small_caps('earned')}: {total_earnings:,} {to_small_caps('gold')}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('how to invite')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('copy link below')}
{to_small_caps('share with friends')}
{to_small_caps('they click and start bot')}
{to_small_caps('instant rewards')}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('rewards')}
━━━━━━━━━━━━━━━━━━━
{INVITE_REWARD:,} {to_small_caps('gold per invite')}
{to_small_caps('counts toward tasks')}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('your invite link')}
━━━━━━━━━━━━━━━━━━━
<code>{invite_link}</code>

{to_small_caps('tap to copy link')}

{to_small_caps('use')} /addinvite {to_small_caps('command to manually add invites')}
"""

            keyboard = [
                [InlineKeyboardButton(to_small_caps("share link"), url=invite_link)],
                [InlineKeyboardButton(to_small_caps("back"), callback_data=f"pass_back_{user_id}")]
            ]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle help action
        elif action == 'help':
            await query.answer()
            help_text = (
                f"╔═══════════════════╗\n"
                f"  {to_small_caps('pass help')}\n"
                f"╚═══════════════════╝\n\n"
                f"<b>{to_small_caps('commands')}:</b>\n"
                f"/pass - {to_small_caps('view pass status')}\n"
                f"/pclaim - {to_small_caps('claim weekly reward')}\n"
                f"/sweekly - {to_small_caps('claim streak bonus')}\n"
                f"/tasks - {to_small_caps('view task progress')}\n"
                f"/upgrade - {to_small_caps('upgrade options')}\n"
                f"/invite - {to_small_caps('invite friends')}\n"
                f"/passhelp - {to_small_caps('full command list')}\n\n"
                f"<b>{to_small_caps('how to unlock mythic')}:</b>\n"
                f"{to_small_caps('invite 5 people')}\n"
                f"{to_small_caps('claim 4 weekly rewards')}\n"
                f"{to_small_caps('grab 50 characters')}\n\n"
                f"<b>{to_small_caps('pass tiers')}:</b>\n"
                f"{to_small_caps('free')}: {to_small_caps('basic rewards')}\n"
                f"{to_small_caps('premium')}: {to_small_caps('50k gold for 30 days')}\n"
                f"{to_small_caps('elite')}: {to_small_caps('50 inr for 30 days')}\n\n"
                f"{to_small_caps('complete all tasks for free mythic')}"
            )

            keyboard = [[
                InlineKeyboardButton(to_small_caps("back"), callback_data=f"pass_back_{user_id}")
            ]]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=help_text,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=help_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle back action
        elif action == 'back':
            await query.answer()
            tier = await check_and_update_tier(user_id)
            pass_data = await get_or_create_pass_data(user_id)
            user = await user_collection.find_one({'id': user_id})

            tier_name = PASS_CONFIG[tier]['name']
            weekly_claims = pass_data.get('weekly_claims', 0)
            streak_count = pass_data.get('streak_count', 0)
            tasks = pass_data.get('tasks', {})
            mythic_unlocked = pass_data.get('mythic_unlocked', False)
            balance = user.get('balance', 0)

            total_tasks = len(MYTHIC_TASKS)
            completed_tasks = sum(1 for task_key, task_info in MYTHIC_TASKS.items() 
                                 if tasks.get(task_key, 0) >= task_info['required'])

            tier_status = to_small_caps("free")
            if tier == 'elite':
                elite_expires = pass_data.get('elite_expires')
                if elite_expires and isinstance(elite_expires, datetime):
                    days_left = (elite_expires - datetime.utcnow()).days
                    tier_status = to_small_caps("elite") + f" ({days_left} " + to_small_caps("days") + ")"
            elif tier == 'premium':
                premium_expires = pass_data.get('premium_expires')
                if premium_expires and isinstance(premium_expires, datetime):
                    days_left = (premium_expires - datetime.utcnow()).days
                    tier_status = to_small_caps("premium") + f" ({days_left} " + to_small_caps("days") + ")"

            mythic_status = to_small_caps("unlocked") if mythic_unlocked else to_small_caps("locked")
            grab_multiplier = PASS_CONFIG[tier]['grab_multiplier']

            caption = f"""╔═══════════════════╗
  {tier_name}
╚═══════════════════╝

{to_small_caps('user')}: {escape(query.from_user.first_name)}
{to_small_caps('id')}: <code>{user_id}</code>
{to_small_caps('balance')}: <code>{balance:,}</code>

━━━━━━━━━━━━━━━━━━━
{to_small_caps('progress')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('weekly claims')}: {weekly_claims}/6
{to_small_caps('streak')}: {streak_count} {to_small_caps('weeks')}
{to_small_caps('tasks completed')}: {completed_tasks}/{total_tasks}
{to_small_caps('mythic unlock')}: {mythic_status}
{to_small_caps('grab multiplier')}: {grab_multiplier}x

━━━━━━━━━━━━━━━━━━━
{to_small_caps('rewards')}
━━━━━━━━━━━━━━━━━━━
{to_small_caps('weekly')}: {PASS_CONFIG[tier]['weekly_reward']:,}
{to_small_caps('streak bonus')}: {PASS_CONFIG[tier]['streak_bonus']:,}
{to_small_caps('tier status')}: {tier_status}

━━━━━━━━━━━━━━━━━━━
{to_small_caps('commands')}
━━━━━━━━━━━━━━━━━━━
/pclaim - {to_small_caps('weekly reward')}
/sweekly - {to_small_caps('streak bonus')}
/tasks - {to_small_caps('view tasks')}
/upgrade - {to_small_caps('get premium')}
/invite - {to_small_caps('invite friends')}

{to_small_caps('complete tasks to unlock mythic character')}
"""

            keyboard = [
                [
                    InlineKeyboardButton(to_small_caps("claim"), callback_data=f"pass_claim_{user_id}"),
                    InlineKeyboardButton(to_small_caps("tasks"), callback_data=f"pass_tasks_{user_id}")
                ],
                [
                    InlineKeyboardButton(to_small_caps("upgrade"), callback_data=f"pass_upgrade_{user_id}"),
                    InlineKeyboardButton(to_small_caps("invite"), callback_data=f"pass_invite_{user_id}")
                ],
                [
                    InlineKeyboardButton(to_small_caps("help"), callback_data=f"pass_help_{user_id}")
                ]
            ]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle buy premium action
        elif action == 'buypremium':
            await query.answer()
            user = await user_collection.find_one({'id': user_id})
            cost = PASS_CONFIG['premium']['cost']
            balance = user.get('balance', 0)

            caption = (
                f"╔═══════════════════╗\n"
                f"  {to_small_caps('confirm premium purchase')}\n"
                f"╚═══════════════════╝\n\n"
                f"{to_small_caps('cost')}: <code>{cost:,}</code> {to_small_caps('gold')}\n"
                f"{to_small_caps('your balance')}: <code>{balance:,}</code>\n\n"
                f"<b>{to_small_caps('benefits')}:</b>\n"
                f"• {to_small_caps('weekly reward')}: 5,000 {to_small_caps('gold')}\n"
                f"• {to_small_caps('streak bonus')}: 25,000 {to_small_caps('gold')}\n"
                f"• {to_small_caps('mythic chars')}: 3 {to_small_caps('per claim')}\n"
                f"• {to_small_caps('grab multiplier')}: 1.5x\n"
                f"• {to_small_caps('duration')}: 30 {to_small_caps('days')}\n\n"
                f"{to_small_caps('confirm purchase?')}"
            )

            keyboard = [
                [
                    InlineKeyboardButton(to_small_caps("✓ confirm"), callback_data=f"pass_confirmprem_{user_id}"),
                    InlineKeyboardButton(to_small_caps("✗ cancel"), callback_data=f"pass_upgrade_{user_id}")
                ]
            ]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle confirm premium purchase
        elif action == 'confirmprem':
            await query.answer()
            user = await user_collection.find_one({'id': user_id})
            cost = PASS_CONFIG['premium']['cost']
            balance = user.get('balance', 0)

            if balance < cost:
                await query.answer(to_small_caps("insufficient balance"), show_alert=True)
                return

            expires = datetime.utcnow() + timedelta(days=30)

            await user_collection.update_one(
                {'id': user_id},
                {
                    '$inc': {'balance': -cost},
                    '$set': {
                        'pass_data.tier': 'premium',
                        'pass_data.premium_expires': expires
                    }
                }
            )

            caption = (
                f"╔═══════════════════╗\n"
                f"  {to_small_caps('premium activated')}\n"
                f"╚═══════════════════╝\n\n"
                f"✨ {to_small_caps('premium pass activated successfully')} ✨\n\n"
                f"{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}\n\n"
                f"<b>{to_small_caps('your benefits')}:</b>\n"
                f"• {to_small_caps('weekly reward')}: 5,000 {to_small_caps('gold')}\n"
                f"• {to_small_caps('streak bonus')}: 25,000 {to_small_caps('gold')}\n"
                f"• {to_small_caps('mythic chars')}: 3 {to_small_caps('per claim')}\n"
                f"• {to_small_caps('grab multiplier')}: 1.5x\n\n"
                f"{to_small_caps('enjoy your benefits!')}"
            )

            keyboard = [[
                InlineKeyboardButton(to_small_caps("back to pass"), callback_data=f"pass_back_{user_id}")
            ]]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

            LOGGER.info(f"[PASS] User {user_id} upgraded to premium")

        # Handle buy elite action
        elif action == 'buyelite':
            await query.answer()
            upi_id = PASS_CONFIG['elite']['upi_id']
            cost_inr = PASS_CONFIG['elite']['cost_inr']

            caption = (
                f"╔═══════════════════╗\n"
                f"  {to_small_caps('elite pass payment')}\n"
                f"╚═══════════════════╝\n\n"
                f"<b>{to_small_caps('payment details')}:</b>\n"
                f"{to_small_caps('amount')}: ₹{cost_inr}\n"
                f"{to_small_caps('upi id')}: <code>{upi_id}</code>\n\n"
                f"<b>{to_small_caps('instructions')}:</b>\n"
                f"1️⃣ {to_small_caps('send')} ₹{cost_inr} {to_small_caps('to the upi id above')}\n"
                f"2️⃣ {to_small_caps('take a screenshot of payment')}\n"
                f"3️⃣ {to_small_caps('click submit payment button')}\n"
                f"4️⃣ {to_small_caps('owner will verify within 24 hours')}\n\n"
                f"<b>{to_small_caps('elite benefits')}:</b>\n"
                f"💰 {to_small_caps('activation bonus')}: 100,000,0 {to_small_caps('gold')}\n"
                f"🏵 {to_small_caps('instant mythics')}: 5 {to_small_caps('characters')}\n"
                f"📅 {to_small_caps('weekly reward')}: 15,000 {to_small_caps('gold')}\n"
                f"🔥 {to_small_caps('streak bonus')}: 100,000 {to_small_caps('gold')}\n"
                f"✨ {to_small_caps('grab multiplier')}: 2.0x\n"
                f"⏰ {to_small_caps('duration')}: 30 {to_small_caps('days')}"
            )

            keyboard = [
                [InlineKeyboardButton(to_small_caps("✓ submit payment"), callback_data=f"pass_submitelite_{user_id}")],
                [InlineKeyboardButton(to_small_caps("✗ cancel"), callback_data=f"pass_upgrade_{user_id}")]
            ]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

        # Handle submit elite payment
        elif action == 'submitelite':
            await query.answer()
            await user_collection.update_one(
                {'id': user_id},
                {'$set': {'pass_data.pending_elite_payment': datetime.utcnow()}}
            )

            try:
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        f"╔═══════════════════╗\n"
                        f"  {to_small_caps('elite pass payment')}\n"
                        f"╚═══════════════════╝\n\n"
                        f"💳 {to_small_caps('new payment request')}\n\n"
                        f"{to_small_caps('user id')}: <code>{user_id}</code>\n"
                        f"{to_small_caps('username')}: @{query.from_user.username or 'none'}\n"
                        f"{to_small_caps('name')}: {query.from_user.first_name}\n"
                        f"{to_small_caps('amount')}: ₹50\n"
                        f"{to_small_caps('time')}: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                        f"<b>{to_small_caps('to approve')}:</b>\n"
                        f"<code>/approveelite {user_id}</code>"
                    ),
                    parse_mode='HTML'
                )
            except Exception as e:
                LOGGER.error(f"[PASS] Could not notify owner: {e}")

            caption = (
                f"╔═══════════════════╗\n"
                f"  {to_small_caps('payment submitted')}\n"
                f"╚═══════════════════╝\n\n"
                f"✅ {to_small_caps('your payment request has been submitted')}\n\n"
                f"⏰ {to_small_caps('owner will verify and activate your elite pass within 24 hours')}\n\n"
                f"📬 {to_small_caps('you will receive a notification once activated')}\n\n"
                f"<b>{to_small_caps('you will receive')}:</b>\n"
                f"💰 100,000,0 {to_small_caps('gold')}\n"
                f"🏵 5 {to_small_caps('mythic characters')}\n"
                f"⚡ 2.0x {to_small_caps('grab multiplier')}\n\n"
                f"{to_small_caps('thank you for your purchase!')}"
            )

            keyboard = [[
                InlineKeyboardButton(to_small_caps("back to pass"), callback_data=f"pass_back_{user_id}")
            ]]

            try:
                media = InputMediaPhoto(
                    media="https://files.catbox.moe/z8fhwx.jpg",
                    caption=caption,
                    parse_mode='HTML'
                )
                await query.edit_message_media(
                    media=media,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except:
                await query.edit_message_caption(
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )

            LOGGER.info(f"[PASS] User {user_id} submitted elite payment")

    except Exception as e:
        LOGGER.error(f"[PASS CALLBACK ERROR] {e}")
        try:
            await query.answer(to_small_caps('error processing request'), show_alert=True)
        except:
            pass


# ========================================
# REGISTER ALL HANDLERS
# ========================================

# User commands
application.add_handler(CommandHandler("pass", pass_command, block=False))
application.add_handler(CommandHandler("pclaim", pclaim_command, block=False))
application.add_handler(CommandHandler("sweekly", sweekly_command, block=False))
application.add_handler(CommandHandler("tasks", tasks_command, block=False))
application.add_handler(CommandHandler("upgrade", upgrade_command, block=False))
application.add_handler(CommandHandler("invite", invite_command, block=False))
application.add_handler(CommandHandler("passhelp", passhelp_command, block=False))

# Owner commands
application.add_handler(CommandHandler("addinvite", addinvite_command, block=False))
application.add_handler(CommandHandler("addgrab", addgrab_command, block=False))
application.add_handler(CommandHandler("approveelite", approve_elite_command, block=False))

# Callback handler for all buttons
application.add_handler(CallbackQueryHandler(pass_callback, pattern=r"^pass_", block=False))

LOGGER.info("[PASS] All handlers registered successfully")


# ========================================
# INTEGRATION GUIDE
# ========================================
"""
TO INTEGRATE WITH YOUR EXISTING GRAB/GACHA SYSTEM:

1. Import the function at the top of your grab handler file:
   from your_pass_module import update_grab_task

2. Add this line AFTER a successful character grab:
   await update_grab_task(user_id)

Example:
   
async def your_grab_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    # Your existing grab logic here...
    # Character successfully grabbed
    
    # Update pass grab task
    await update_grab_task(user_id)
    
    # Rest of your code...
"""