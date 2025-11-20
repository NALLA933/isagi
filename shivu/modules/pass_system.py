from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
from shivu import application, user_collection, collection, user_totals_collection, LOGGER

OWNER_ID = 8420981179

PASS_CONFIG = {
    'free': {'name': 'ғʀᴇᴇ ᴘᴀss', 'weekly_reward': 1000, 'streak_bonus': 5000, 'mythic_characters': 0, 'grab_multiplier': 1.0},
    'premium': {'name': 'ᴘʀᴇᴍɪᴜᴍ ᴘᴀss', 'weekly_reward': 5000, 'streak_bonus': 25000, 'mythic_characters': 3, 'cost': 50000, 'grab_multiplier': 1.5},
    'elite': {'name': 'ᴇʟɪᴛᴇ ᴘᴀss', 'weekly_reward': 15000, 'streak_bonus': 100000, 'mythic_characters': 5, 'cost_inr': 50, 'upi_id': 'piyushrathod007@axl', 'activation_bonus': 100000000, 'grab_multiplier': 2.0}
}

MYTHIC_TASKS = {
    'invites': {'required': 5, 'reward': 'ᴍʏᴛʜɪᴄ ᴄʜᴀʀᴀᴄᴛᴇʀ'},
    'weekly_claims': {'required': 4, 'reward': 'ʙᴏɴᴜs ʀᴇᴡᴀʀᴅ'},
    'grabs': {'required': 50, 'reward': 'ᴄᴏʟʟᴇᴄᴛᴏʀ'}
}

INVITE_REWARD = 1000

def to_small_caps(text):
    m = {'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ','h':'ʜ','i':'ɪ','j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ','s':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ'}
    return ''.join(m.get(c.lower(), c) for c in text)

async def get_or_create_pass_data(user_id: int):
    user = await user_collection.find_one({'id': user_id})
    if not user:
        user = {'id': user_id, 'characters': [], 'balance': 0}
        await user_collection.insert_one(user)
    if 'pass_data' not in user:
        pass_data = {'tier': 'free', 'weekly_claims': 0, 'last_weekly_claim': None, 'streak_count': 0, 'last_streak_claim': None, 'tasks': {'invites': 0, 'weekly_claims': 0, 'grabs': 0}, 'mythic_unlocked': False, 'premium_expires': None, 'elite_expires': None, 'pending_elite_payment': None, 'invited_users': [], 'total_invite_earnings': 0}
        await user_collection.update_one({'id': user_id}, {'$set': {'pass_data': pass_data}})
        return pass_data
    return user.get('pass_data', {})

async def check_and_update_tier(user_id: int):
    pass_data = await get_or_create_pass_data(user_id)
    tier = pass_data.get('tier', 'free')
    if tier == 'elite':
        elite_expires = pass_data.get('elite_expires')
        if elite_expires and isinstance(elite_expires, datetime) and elite_expires < datetime.utcnow():
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.tier': 'free'}})
            return 'free'
    elif tier == 'premium':
        premium_expires = pass_data.get('premium_expires')
        if premium_expires and isinstance(premium_expires, datetime) and premium_expires < datetime.utcnow():
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.tier': 'free'}})
            return 'free'
    return tier

async def update_grab_task(user_id: int):
    try:
        await user_collection.update_one({'id': user_id}, {'$inc': {'pass_data.tasks.grabs': 1}})
        LOGGER.info(f"Grab task updated for user {user_id}")
    except Exception as e:
        LOGGER.error(f"Error updating grab task: {e}")

async def pass_command(update: Update, context: CallbackContext):
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
        completed_tasks = sum(1 for k, v in MYTHIC_TASKS.items() if tasks.get(k, 0) >= v['required'])
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
        caption = f"""{tier_name}

{to_small_caps('user')}: {escape(update.effective_user.first_name)}
{to_small_caps('id')}: <code>{user_id}</code>
{to_small_caps('balance')}: <code>{balance:,}</code>

{to_small_caps('weekly claims')}: {weekly_claims}/6
{to_small_caps('streak')}: {streak_count} {to_small_caps('weeks')}
{to_small_caps('tasks')}: {completed_tasks}/{total_tasks}
{to_small_caps('mythic')}: {mythic_status}
{to_small_caps('multiplier')}: {grab_multiplier}x

{to_small_caps('weekly')}: {PASS_CONFIG[tier]['weekly_reward']:,}
{to_small_caps('streak bonus')}: {PASS_CONFIG[tier]['streak_bonus']:,}
{to_small_caps('tier')}: {tier_status}"""
        keyboard = [[InlineKeyboardButton(to_small_caps("claim"), callback_data="ps_claim"), InlineKeyboardButton(to_small_caps("tasks"), callback_data="ps_tasks")], [InlineKeyboardButton(to_small_caps("upgrade"), callback_data="ps_upgrade"), InlineKeyboardButton(to_small_caps("invite"), callback_data="ps_invite")]]
        await update.message.reply_photo(photo="https://files.catbox.moe/z8fhwx.jpg", caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Pass error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def pclaim_command(update: Update, context: CallbackContext):
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
                await update.message.reply_text(f"{to_small_caps('next claim in')}: {remaining.days}d {hours}h {minutes}m")
                return
        reward = PASS_CONFIG[tier]['weekly_reward']
        mythic_chars_count = PASS_CONFIG[tier]['mythic_characters']
        new_claims = pass_data.get('weekly_claims', 0) + 1
        await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.last_weekly_claim': datetime.utcnow(), 'pass_data.weekly_claims': new_claims, 'pass_data.tasks.weekly_claims': new_claims}, '$inc': {'balance': reward}})
        last_streak = pass_data.get('last_streak_claim')
        if last_streak and isinstance(last_streak, datetime):
            days_since = (datetime.utcnow() - last_streak).days
            if 6 <= days_since <= 8:
                await user_collection.update_one({'id': user_id}, {'$inc': {'pass_data.streak_count': 1}, '$set': {'pass_data.last_streak_claim': datetime.utcnow()}})
            elif days_since > 8:
                await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.streak_count': 0}})
        else:
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.streak_count': 1, 'pass_data.last_streak_claim': datetime.utcnow()}})
        premium_msg = ""
        if mythic_chars_count > 0:
            mythic_chars = await collection.find({'rarity': '🏵 Mythic'}).limit(mythic_chars_count).to_list(length=mythic_chars_count)
            if mythic_chars:
                await user_collection.update_one({'id': user_id}, {'$push': {'characters': {'$each': mythic_chars}}})
                await user_totals_collection.update_one({'id': user_id}, {'$inc': {'count': len(mythic_chars)}}, upsert=True)
                premium_msg = f"\n{to_small_caps('bonus')}: {len(mythic_chars)} {to_small_caps('mythic added')}"
        await update.message.reply_text(f"{to_small_caps('claimed')}\n{to_small_caps('reward')}: <code>{reward:,}</code>\n{to_small_caps('claims')}: {new_claims}/6{premium_msg}", parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Claim error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def sweekly_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)
        weekly_claims = pass_data.get('weekly_claims', 0)
        if weekly_claims < 6:
            await update.message.reply_text(f"{to_small_caps('need 6 claims')}: {weekly_claims}/6")
            return
        bonus = PASS_CONFIG[tier]['streak_bonus']
        mythic_char = await collection.find_one({'rarity': '🏵 Mythic'})
        update_data = {'$inc': {'balance': bonus}, '$set': {'pass_data.weekly_claims': 0}}
        if mythic_char:
            update_data['$push'] = {'characters': mythic_char}
        await user_collection.update_one({'id': user_id}, update_data)
        if mythic_char:
            await user_totals_collection.update_one({'id': user_id}, {'$inc': {'count': 1}}, upsert=True)
        char_msg = f"\n{to_small_caps('bonus char')}: {mythic_char.get('name', 'unknown')}" if mythic_char else ""
        await update.message.reply_text(f"{to_small_caps('streak claimed')}\n{to_small_caps('bonus')}: <code>{bonus:,}</code>{char_msg}", parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Sweekly error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def tasks_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        pass_data = await get_or_create_pass_data(user_id)
        tasks = pass_data.get('tasks', {})
        mythic_unlocked = pass_data.get('mythic_unlocked', False)
        task_list = []
        all_completed = True
        for k, v in MYTHIC_TASKS.items():
            current = tasks.get(k, 0)
            required = v['required']
            progress = min(100, int((current / required) * 100))
            status = to_small_caps("done") if current >= required else to_small_caps("pending")
            if current < required:
                all_completed = False
            task_list.append(f"{to_small_caps(k)}: {current}/{required} {'█' * (progress // 10)}{'░' * (10 - progress // 10)} {progress}% {status}")
        if all_completed and not mythic_unlocked:
            mythic_char = await collection.find_one({'rarity': '🏵 Mythic'})
            if mythic_char:
                await user_collection.update_one({'id': user_id}, {'$push': {'characters': mythic_char}, '$set': {'pass_data.mythic_unlocked': True}})
                await user_totals_collection.update_one({'id': user_id}, {'$inc': {'count': 1}}, upsert=True)
                mythic_unlocked = True
        mythic_status = to_small_caps('unlocked') if mythic_unlocked else to_small_caps('locked')
        caption = f"{to_small_caps('tasks')}\n\n" + "\n".join(task_list) + f"\n\n{to_small_caps('mythic')}: {mythic_status}"
        await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Tasks error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def invite_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        pass_data = await get_or_create_pass_data(user_id)
        total_invites = pass_data.get('tasks', {}).get('invites', 0)
        total_earnings = pass_data.get('total_invite_earnings', 0)
        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start=r_{user_id}"
        caption = f"{to_small_caps('invite program')}\n\n{to_small_caps('referrals')}: {total_invites}\n{to_small_caps('earned')}: {total_earnings:,}\n\n{to_small_caps('reward')}: {INVITE_REWARD:,} {to_small_caps('per invite')}\n\n<code>{invite_link}</code>"
        await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Invite error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def upgrade_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        tier = await check_and_update_tier(user_id)
        user = await user_collection.find_one({'id': user_id})
        balance = user.get('balance', 0)
        caption = f"{to_small_caps('upgrade')}\n\n{to_small_caps('balance')}: <code>{balance:,}</code>\n{to_small_caps('tier')}: {PASS_CONFIG[tier]['name']}\n\n{to_small_caps('premium')}: 50,000 {to_small_caps('gold')} 30d\n{to_small_caps('elite')}: 50 INR 30d"
        keyboard = [[InlineKeyboardButton(to_small_caps("premium"), callback_data="ps_buypremium")], [InlineKeyboardButton(to_small_caps("elite"), callback_data="ps_buyelite")]]
        await update.message.reply_photo(photo="https://files.catbox.moe/z8fhwx.jpg", caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Upgrade error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def addinvite_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(to_small_caps('unauthorized'))
        return
    try:
        if len(context.args) < 2:
            await update.message.reply_text(f"{to_small_caps('usage')}: /addinvite <user_id> <count>")
            return
        target_user_id = int(context.args[0])
        invite_count = int(context.args[1])
        if invite_count <= 0:
            await update.message.reply_text(to_small_caps('invalid count'))
            return
        await get_or_create_pass_data(target_user_id)
        gold_reward = invite_count * INVITE_REWARD
        await user_collection.update_one({'id': target_user_id}, {'$inc': {'pass_data.tasks.invites': invite_count, 'pass_data.total_invite_earnings': gold_reward, 'balance': gold_reward}})
        await update.message.reply_text(f"{to_small_caps('added')}\n{to_small_caps('user')}: <code>{target_user_id}</code>\n{to_small_caps('invites')}: {invite_count}\n{to_small_caps('gold')}: <code>{gold_reward:,}</code>", parse_mode='HTML')
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"{to_small_caps('invite reward')}\n{invite_count} {to_small_caps('credits')}\n<code>{gold_reward:,}</code> {to_small_caps('gold')}", parse_mode='HTML')
        except:
            pass
    except ValueError:
        await update.message.reply_text(to_small_caps('invalid input'))
    except Exception as e:
        LOGGER.error(f"Addinvite error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def addgrab_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(to_small_caps('unauthorized'))
        return
    try:
        if len(context.args) < 2:
            await update.message.reply_text(f"{to_small_caps('usage')}: /addgrab <user_id> <count>")
            return
        target_user_id = int(context.args[0])
        grab_count = int(context.args[1])
        if grab_count <= 0:
            await update.message.reply_text(to_small_caps('invalid count'))
            return
        await get_or_create_pass_data(target_user_id)
        await user_collection.update_one({'id': target_user_id}, {'$inc': {'pass_data.tasks.grabs': grab_count}})
        await update.message.reply_text(f"{to_small_caps('added')}\n{to_small_caps('user')}: <code>{target_user_id}</code>\n{to_small_caps('grabs')}: {grab_count}", parse_mode='HTML')
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"{grab_count} {to_small_caps('grab credits added')}", parse_mode='HTML')
        except:
            pass
    except ValueError:
        await update.message.reply_text(to_small_caps('invalid input'))
    except Exception as e:
        LOGGER.error(f"Addgrab error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def approve_elite_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(to_small_caps('unauthorized'))
        return
    try:
        if len(context.args) < 1:
            await update.message.reply_text(f"{to_small_caps('usage')}: /approveelite <user_id>")
            return
        target_user_id = int(context.args[0])
        target_user = await user_collection.find_one({'id': target_user_id})
        if not target_user:
            await update.message.reply_text(to_small_caps('user not found'))
            return
        pass_data = target_user.get('pass_data', {})
        if not pass_data.get('pending_elite_payment'):
            await update.message.reply_text(to_small_caps('no pending payment'))
            return
        expires = datetime.utcnow() + timedelta(days=30)
        activation_bonus = PASS_CONFIG['elite']['activation_bonus']
        mythic_chars = await collection.find({'rarity': '🏵 Mythic'}).limit(5).to_list(length=5)
        await user_collection.update_one({'id': target_user_id}, {'$set': {'pass_data.tier': 'elite', 'pass_data.elite_expires': expires, 'pass_data.pending_elite_payment': None}, '$inc': {'balance': activation_bonus}, '$push': {'characters': {'$each': mythic_chars}}})
        await user_totals_collection.update_one({'id': target_user_id}, {'$inc': {'count': len(mythic_chars)}}, upsert=True)
        await update.message.reply_text(f"{to_small_caps('elite activated')}\n{to_small_caps('user')}: <code>{target_user_id}</code>\n{to_small_caps('gold')}: <code>{activation_bonus:,}</code>\n{to_small_caps('mythics')}: {len(mythic_chars)}", parse_mode='HTML')
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"{to_small_caps('elite pass activated')}\n\n{to_small_caps('gold')}: <code>{activation_bonus:,}</code>\n{to_small_caps('mythics')}: {len(mythic_chars)}\n{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}", parse_mode='HTML')
        except:
            pass
    except ValueError:
        await update.message.reply_text(to_small_caps('invalid input'))
    except Exception as e:
        LOGGER.error(f"Approve error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def pass_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    try:
        data = query.data
        if not data.startswith('ps_'):
            return
        parts = data.split('_')
        action = parts[1]
        user_id = query.from_user.id
        if action == 'claim':
            tier = await check_and_update_tier(user_id)
            pass_data = await get_or_create_pass_data(user_id)
            last_claim = pass_data.get('last_weekly_claim')
            if last_claim and isinstance(last_claim, datetime):
                time_since = datetime.utcnow() - last_claim
                if time_since < timedelta(days=7):
                    remaining = timedelta(days=7) - time_since
                    await query.answer(f"{to_small_caps('next claim')}: {remaining.days}d", show_alert=True)
                    return
            reward = PASS_CONFIG[tier]['weekly_reward']
            new_claims = pass_data.get('weekly_claims', 0) + 1
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.last_weekly_claim': datetime.utcnow(), 'pass_data.weekly_claims': new_claims}, '$inc': {'balance': reward}})
            await query.message.reply_text(f"{to_small_caps('claimed')}: <code>{reward:,}</code>", parse_mode='HTML')
        elif action == 'tasks':
            pass_data = await get_or_create_pass_data(user_id)
            tasks = pass_data.get('tasks', {})
            task_list = []
            for k, v in MYTHIC_TASKS.items():
                current = tasks.get(k, 0)
                required = v['required']
                task_list.append(f"{to_small_caps(k)}: {current}/{required}")
            caption = f"{to_small_caps('tasks')}\n\n" + "\n".join(task_list)
            keyboard = [[InlineKeyboardButton(to_small_caps("back"), callback_data="ps_back")]]
            await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        elif action == 'invite':
            pass_data = await get_or_create_pass_data(user_id)
            total_invites = pass_data.get('tasks', {}).get('invites', 0)
            total_earnings = pass_data.get('total_invite_earnings', 0)
            bot_username = context.bot.username
            invite_link = f"https://t.me/{bot_username}?start=r_{user_id}"
            caption = f"{to_small_caps('invite')}\n\n{to_small_caps('referrals')}: {total_invites}\n{to_small_caps('earned')}: {total_earnings:,}\n\n<code>{invite_link}</code>"
            keyboard = [[InlineKeyboardButton(to_small_caps("back"), callback_data="ps_back")]]
            await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        elif action == 'upgrade':
            tier = await check_and_update_tier(user_id)
            user = await user_collection.find_one({'id': user_id})
            balance = user.get('balance', 0)
            caption = f"{to_small_caps('upgrade')}\n\n{to_small_caps('balance')}: <code>{balance:,}</code>\n{to_small_caps('tier')}: {PASS_CONFIG[tier]['name']}\n\n{to_small_caps('premium')}: 50,000 {to_small_caps('gold')}\n{to_small_caps('elite')}: 50 INR"
            keyboard = [[InlineKeyboardButton(to_small_caps("premium"), callback_data="ps_buypremium")], [InlineKeyboardButton(to_small_caps("elite"), callback_data="ps_buyelite")], [InlineKeyboardButton(to_small_caps("back"), callback_data="ps_back")]]
            await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        elif action == 'back':
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
            completed_tasks = sum(1 for k, v in MYTHIC_TASKS.items() if tasks.get(k, 0) >= v['required'])
            mythic_status = to_small_caps("unlocked") if mythic_unlocked else to_small_caps("locked")
            grab_multiplier = PASS_CONFIG[tier]['grab_multiplier']
            caption = f"""{tier_name}

{to_small_caps('user')}: {escape(query.from_user.first_name)}
{to_small_caps('balance')}: <code>{balance:,}</code>

{to_small_caps('claims')}: {weekly_claims}/6
{to_small_caps('streak')}: {streak_count}
{to_small_caps('tasks')}: {completed_tasks}/{total_tasks}
{to_small_caps('mythic')}: {mythic_status}
{to_small_caps('multiplier')}: {grab_multiplier}x"""
            keyboard = [[InlineKeyboardButton(to_small_caps("claim"), callback_data="ps_claim"), InlineKeyboardButton(to_small_caps("tasks"), callback_data="ps_tasks")], [InlineKeyboardButton(to_small_caps("upgrade"), callback_data="ps_upgrade"), InlineKeyboardButton(to_small_caps("invite"), callback_data="ps_invite")]]
            await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        elif action == 'buypremium':
            user = await user_collection.find_one({'id': user_id})
            cost = PASS_CONFIG['premium']['cost']
            balance = user.get('balance', 0)
            caption = f"{to_small_caps('premium')}\n\n{to_small_caps('cost')}: <code>{cost:,}</code>\n{to_small_caps('balance')}: <code>{balance:,}</code>"
            keyboard = [[InlineKeyboardButton(to_small_caps("confirm"), callback_data="ps_confirmprem"), InlineKeyboardButton(to_small_caps("cancel"), callback_data="ps_upgrade")]]
            await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        elif action == 'confirmprem':
            user = await user_collection.find_one({'id': user_id})
            cost = PASS_CONFIG['premium']['cost']
            if user.get('balance', 0) < cost:
                await query.answer(to_small_caps("insufficient balance"), show_alert=True)
                return
            expires = datetime.utcnow() + timedelta(days=30)
            await user_collection.update_one({'id': user_id}, {'$inc': {'balance': -cost}, '$set': {'pass_data.tier': 'premium', 'pass_data.premium_expires': expires}})
            await query.edit_message_caption(caption=f"{to_small_caps('premium activated')}\n{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}", parse_mode='HTML')
        elif action == 'buyelite':
            caption = f"{to_small_caps('elite payment')}\n\n{to_small_caps('amount')}: 50 INR\n{to_small_caps('upi')}: <code>{PASS_CONFIG['elite']['upi_id']}</code>\n\n{to_small_caps('send payment then click submit')}"
            keyboard = [[InlineKeyboardButton(to_small_caps("submit"), callback_data="ps_submitelite")], [InlineKeyboardButton(to_small_caps("cancel"), callback_data="ps_upgrade")]]
            await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        elif action == 'submitelite':
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.pending_elite_payment': datetime.utcnow()}})
            try:
                await context.bot.send_message(chat_id=OWNER_ID, text=f"{to_small_caps('elite payment')}\n{to_small_caps('user')}: <code>{user_id}</code>\n/approveelite {user_id}", parse_mode='HTML')
            except:
                pass
            await query.edit_message_caption(caption=f"{to_small_caps('payment submitted')}\n{to_small_caps('will be verified within 24h')}", parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Callback error: {e}")
        try:
            await query.answer(to_small_caps('error'), show_alert=True)
        except:
            pass

async def passhelp_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        # Main help page
        help_text = f"""<b>{to_small_caps('pass system guide')}</b>

{to_small_caps('welcome to the ultimate reward system designed for active players unlock exclusive benefits gold and rare characters')}

<b>{to_small_caps('available tiers')}</b>

<b>{to_small_caps('free pass')}</b>
{to_small_caps('weekly')}: 1,000
{to_small_caps('streak')}: 5,000
{to_small_caps('multiplier')}: 1.0x

<b>{to_small_caps('premium pass')}</b>
{to_small_caps('weekly')}: 5,000
{to_small_caps('streak')}: 25,000
{to_small_caps('multiplier')}: 1.5x
{to_small_caps('mythics')}: 3 {to_small_caps('per claim')}
{to_small_caps('cost')}: 50,000 {to_small_caps('gold')}

<b>{to_small_caps('elite pass')}</b>
{to_small_caps('weekly')}: 15,000
{to_small_caps('streak')}: 100,000
{to_small_caps('multiplier')}: 2.0x
{to_small_caps('activation')}: 100,000,000
{to_small_caps('mythics')}: 5 {to_small_caps('instant')}
{to_small_caps('cost')}: 50 INR

{to_small_caps('tap the buttons below to learn more')}"""

        keyboard = [
            [
                InlineKeyboardButton(f"⚡ {to_small_caps('how to claim')}", callback_data="ph_claim"),
                InlineKeyboardButton(f"🔥 {to_small_caps('streak info')}", callback_data="ph_streak")
            ],
            [
                InlineKeyboardButton(f"🎯 {to_small_caps('tasks guide')}", callback_data="ph_tasks"),
                InlineKeyboardButton(f"🎁 {to_small_caps('invite rewards')}", callback_data="ph_invite")
            ],
            [
                InlineKeyboardButton(f"💰 {to_small_caps('upgrade guide')}", callback_data="ph_upgrade"),
                InlineKeyboardButton(f"📊 {to_small_caps('commands list')}", callback_data="ph_commands")
            ],
            [
                InlineKeyboardButton(f"❓ {to_small_caps('faq')}", callback_data="ph_faq")
            ]
        ]

        await update.message.reply_photo(
            photo="https://files.catbox.moe/z8fhwx.jpg",
            caption=help_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Passhelp error: {e}")
        await update.message.reply_text(to_small_caps('error'))

async def passhelp_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        if not data.startswith('ph_'):
            return
        
        action = data.split('_')[1]
        
        if action == 'claim':
            text = f"""<b>{to_small_caps('how to claim rewards')}</b>

<b>{to_small_caps('weekly claims')}</b>
{to_small_caps('use')} /pclaim {to_small_caps('to claim your weekly reward')}
{to_small_caps('available once every 7 days')}
{to_small_caps('each claim counts toward your streak')}

<b>{to_small_caps('what you get')}</b>
{to_small_caps('free')}: 1,000 {to_small_caps('gold')}
{to_small_caps('premium')}: 5,000 {to_small_caps('gold + 3 mythics')}
{to_small_caps('elite')}: 15,000 {to_small_caps('gold + 5 mythics')}

<b>{to_small_caps('claim counter')}</b>
{to_small_caps('you can make up to 6 claims')}
{to_small_caps('after 6 claims use')} /sweekly {to_small_caps('for streak bonus')}
{to_small_caps('counter resets after streak claim')}

<b>{to_small_caps('timer system')}</b>
{to_small_caps('7 day cooldown between claims')}
{to_small_caps('check')} /pass {to_small_caps('to see time remaining')}
{to_small_caps('plan your claims carefully for maximum rewards')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'streak':
            text = f"""<b>{to_small_caps('streak bonus system')}</b>

<b>{to_small_caps('how streaks work')}</b>
{to_small_caps('make 6 weekly claims consecutively')}
{to_small_caps('claim within 6-8 days to maintain streak')}
{to_small_caps('missing 8+ days breaks your streak')}

<b>{to_small_caps('streak rewards')}</b>
{to_small_caps('free')}: 5,000 {to_small_caps('gold + 1 mythic')}
{to_small_caps('premium')}: 25,000 {to_small_caps('gold + 1 mythic')}
{to_small_caps('elite')}: 100,000 {to_small_caps('gold + 1 mythic')}

<b>{to_small_caps('claiming streak bonus')}</b>
{to_small_caps('use')} /sweekly {to_small_caps('after 6 claims')}
{to_small_caps('resets your claim counter to 0')}
{to_small_caps('streak counter continues')}

<b>{to_small_caps('pro tips')}</b>
{to_small_caps('set reminders for claim days')}
{to_small_caps('elite pass gives 20x more gold than free')}
{to_small_caps('dont miss the 8 day window')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'tasks':
            text = f"""<b>{to_small_caps('tasks and mythic unlock')}</b>

<b>{to_small_caps('available tasks')}</b>

<b>{to_small_caps('invites')}</b>
{to_small_caps('requirement')}: 5 {to_small_caps('referrals')}
{to_small_caps('reward')}: {to_small_caps('mythic character')}
{to_small_caps('share your invite link and get rewarded')}

<b>{to_small_caps('weekly claims')}</b>
{to_small_caps('requirement')}: 4 {to_small_caps('claims')}
{to_small_caps('reward')}: {to_small_caps('bonus reward')}
{to_small_caps('automatically tracked with')} /pclaim

<b>{to_small_caps('grabs')}</b>
{to_small_caps('requirement')}: 50 {to_small_caps('character grabs')}
{to_small_caps('reward')}: {to_small_caps('collector badge')}
{to_small_caps('grab characters in the game')}

<b>{to_small_caps('completing all tasks')}</b>
{to_small_caps('finish all 3 tasks to unlock mythic tier')}
{to_small_caps('receive exclusive mythic character')}
{to_small_caps('check progress with')} /tasks

<b>{to_small_caps('tracking progress')}</b>
{to_small_caps('use')} /tasks {to_small_caps('to see current progress')}
{to_small_caps('progress bars show completion percentage')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'invite':
            text = f"""<b>{to_small_caps('invite reward program')}</b>

<b>{to_small_caps('how it works')}</b>
{to_small_caps('get your unique invite link with')} /invite
{to_small_caps('share with friends and groups')}
{to_small_caps('earn rewards when they join')}

<b>{to_small_caps('rewards per invite')}</b>
{to_small_caps('gold earned')}: 1,000 {to_small_caps('per referral')}
{to_small_caps('task progress')}: +1 {to_small_caps('invite count')}
{to_small_caps('unlimited invites allowed')}

<b>{to_small_caps('invite benefits')}</b>
{to_small_caps('passive gold income')}
{to_small_caps('progress toward mythic unlock')}
{to_small_caps('help grow the community')}

<b>{to_small_caps('tracking invites')}</b>
{to_small_caps('use')} /invite {to_small_caps('to see total referrals')}
{to_small_caps('view total earnings from invites')}
{to_small_caps('get your personal invite link')}

<b>{to_small_caps('pro strategy')}</b>
{to_small_caps('share in gaming communities')}
{to_small_caps('5 invites = mythic character unlock')}
{to_small_caps('each invite = free 1k gold')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'upgrade':
            text = f"""<b>{to_small_caps('upgrading your pass')}</b>

<b>{to_small_caps('premium pass upgrade')}</b>
{to_small_caps('cost')}: 50,000 {to_small_caps('gold')}
{to_small_caps('duration')}: 30 {to_small_caps('days')}
{to_small_caps('how to buy')}: /upgrade {to_small_caps('then select premium')}

<b>{to_small_caps('premium benefits')}</b>
5x {to_small_caps('weekly rewards')}
5x {to_small_caps('streak bonus')}
1.5x {to_small_caps('grab multiplier')}
3 {to_small_caps('mythics per claim')}

<b>{to_small_caps('elite pass upgrade')}</b>
{to_small_caps('cost')}: 50 INR
{to_small_caps('duration')}: 30 {to_small_caps('days')}
{to_small_caps('how to buy')}: /upgrade {to_small_caps('then select elite')}

<b>{to_small_caps('elite benefits')}</b>
15x {to_small_caps('weekly rewards')}
20x {to_small_caps('streak bonus')}
2.0x {to_small_caps('grab multiplier')}
100,000,000 {to_small_caps('activation bonus')}
5 {to_small_caps('mythics instantly')}

<b>{to_small_caps('payment process')}</b>
{to_small_caps('premium')}: {to_small_caps('instant activation with gold')}
{to_small_caps('elite')}: {to_small_caps('upi payment then approval')}
{to_small_caps('elite verified within 24 hours')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'commands':
            text = f"""<b>{to_small_caps('available commands')}</b>

<b>{to_small_caps('main commands')}</b>
/pass {to_small_caps('view your pass dashboard')}
/pclaim {to_small_caps('claim weekly rewards')}
/sweekly {to_small_caps('claim streak bonus')}
/tasks {to_small_caps('view task progress')}
/invite {to_small_caps('get your invite link')}
/upgrade {to_small_caps('upgrade your pass tier')}
/passhelp {to_small_caps('view this help guide')}

<b>{to_small_caps('admin commands')}</b>
/addinvite {to_small_caps('add invite credits')}
/addgrab {to_small_caps('add grab credits')}
/approveelite {to_small_caps('approve elite payment')}

<b>{to_small_caps('quick tips')}</b>
{to_small_caps('use')} /pass {to_small_caps('to check everything')}
{to_small_caps('claim rewards regularly')}
{to_small_caps('complete tasks for mythic unlock')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'faq':
            text = f"""<b>{to_small_caps('frequently asked questions')}</b>

<b>Q: {to_small_caps('when can i claim rewards')}</b>
A: {to_small_caps('every 7 days use')} /pclaim

<b>Q: {to_small_caps('do i lose my streak if i upgrade')}</b>
A: {to_small_caps('no all progress is saved')}

<b>Q: {to_small_caps('what happens if pass expires')}</b>
A: {to_small_caps('you return to free tier keep all rewards')}

<b>Q: {to_small_caps('can i upgrade from premium to elite')}</b>
A: {to_small_caps('yes anytime during active period')}

<b>Q: {to_small_caps('how long for elite approval')}</b>
A: {to_small_caps('within 24 hours after payment verification')}

<b>Q: {to_small_caps('do tasks reset')}</b>
A: {to_small_caps('no they accumulate permanently')}

<b>Q: {to_small_caps('whats the best pass tier')}</b>
A: {to_small_caps('elite gives best value with 100m gold bonus')}

<b>Q: {to_small_caps('can i get refund')}</b>
A: {to_small_caps('premium yes elite contact owner')}"""
            
            keyboard = [[InlineKeyboardButton(f"◀ {to_small_caps('back')}", callback_data="ph_main")]]
            
        elif action == 'main':
            text = f"""<b>{to_small_caps('pass system guide')}</b>

{to_small_caps('welcome to the ultimate reward system designed for active players unlock exclusive benefits gold and rare characters')}

<b>{to_small_caps('available tiers')}</b>

<b>{to_small_caps('free pass')}</b>
{to_small_caps('weekly')}: 1,000
{to_small_caps('streak')}: 5,000
{to_small_caps('multiplier')}: 1.0x

<b>{to_small_caps('premium pass')}</b>
{to_small_caps('weekly')}: 5,000
{to_small_caps('streak')}: 25,000
{to_small_caps('multiplier')}: 1.5x
{to_small_caps('mythics')}: 3 {to_small_caps('per claim')}
{to_small_caps('cost')}: 50,000 {to_small_caps('gold')}

<b>{to_small_caps('elite pass')}</b>
{to_small_caps('weekly')}: 15,000
{to_small_caps('streak')}: 100,000
{to_small_caps('multiplier')}: 2.0x
{to_small_caps('activation')}: 100,000,000
{to_small_caps('mythics')}: 5 {to_small_caps('instant')}
{to_small_caps('cost')}: 50 INR

{to_small_caps('tap the buttons below to learn more')}"""
            
            keyboard = [
                [
                    InlineKeyboardButton(f"⚡ {to_small_caps('how to claim')}", callback_data="ph_claim"),
                    InlineKeyboardButton(f"🔥 {to_small_caps('streak info')}", callback_data="ph_streak")
                ],
                [
                    InlineKeyboardButton(f"🎯 {to_small_caps('tasks guide')}", callback_data="ph_tasks"),
                    InlineKeyboardButton(f"🎁 {to_small_caps('invite rewards')}", callback_data="ph_invite")
                ],
                [
                    InlineKeyboardButton(f"💰 {to_small_caps('upgrade guide')}", callback_data="ph_upgrade"),
                    InlineKeyboardButton(f"📊 {to_small_caps('commands list')}", callback_data="ph_commands")
                ],
                [
                    InlineKeyboardButton(f"❓ {to_small_caps('faq')}", callback_data="ph_faq")
                ]
            ]
        
        await query.edit_message_caption(
            caption=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
    except Exception as e:
        LOGGER.error(f"Passhelp callback error: {e}")
        try:
            await query.answer(to_small_caps('error'), show_alert=True)
        except:
            pass

# Add these handlers at the end of your file
application.add_handler(CommandHandler("passhelp", passhelp_command, block=False))
application.add_handler(CallbackQueryHandler(passhelp_callback, pattern=r"^ph_", block=False))
application.add_handler(CommandHandler("pass", pass_command, block=False))
application.add_handler(CommandHandler("pclaim", pclaim_command, block=False))
application.add_handler(CommandHandler("sweekly", sweekly_command, block=False))
application.add_handler(CommandHandler("tasks", tasks_command, block=False))
application.add_handler(CommandHandler("upgrade", upgrade_command, block=False))
application.add_handler(CommandHandler("invite", invite_command, block=False))
application.add_handler(CommandHandler("addinvite", addinvite_command, block=False))
application.add_handler(CommandHandler("addgrab", addgrab_command, block=False))
application.add_handler(CommandHandler("approveelite", approve_elite_command, block=False))
application.add_handler(CallbackQueryHandler(pass_callback, pattern=r"^ps_", block=False))
