from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
from shivu import application, user_collection, collection, user_totals_collection, LOGGER

OWNER_ID = 5147822244

PASS_CONFIG = {
    'free': {'name': 'ғʀᴇᴇ ᴘᴀss', 'weekly_reward': 1000, 'streak_bonus': 5000, 'mythic_characters': 0, 'grab_multiplier': 1.0},
    'premium': {'name': 'ᴘʀᴇᴍɪᴜᴍ ᴘᴀss', 'weekly_reward': 5000, 'streak_bonus': 25000, 'mythic_characters': 3, 'cost': 50000, 'grab_multiplier': 1.5},
    'elite': {'name': 'ᴇʟɪᴛᴇ ᴘᴀss', 'weekly_reward': 15000, 'streak_bonus': 100000, 'mythic_characters': 5, 'cost_inr': 50, 'upi_id': 'looktouhid@oksbi', 'activation_bonus': 100000000, 'grab_multiplier': 2.0}
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
        pass_data = {
            'tier': 'free',
            'weekly_claims': 0,
            'last_weekly_claim': None,
            'streak_count': 0,
            'last_streak_claim': None,
            'tasks': {'invites': 0, 'weekly_claims': 0, 'grabs': 0},
            'mythic_unlocked': False,
            'premium_expires': None,
            'elite_expires': None,
            'pending_elite_payment': None,
            'invited_users': [],
            'total_invite_earnings': 0
        }
        await user_collection.update_one({'id': target_user_id}, update_data)
        
        await update.message.reply_text(
            f"{to_small_caps('elite activated')}\n{to_small_caps('user')}: <code>{target_user_id}</code>\n{to_small_caps('gold')}: <code>{activation_bonus:,}</code>\n{to_small_caps('mythics')}: {len(mythic_chars)}",
            parse_mode='HTML'
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"{to_small_caps('elite pass activated')}\n\n{to_small_caps('gold')}: <code>{activation_bonus:,}</code>\n{to_small_caps('mythics')}: {len(mythic_chars)}\n{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}",
                parse_mode='HTML'
            )
        except Exception as e:
            LOGGER.error(f"Failed to notify user {target_user_id}: {e}")
            
    except ValueError:
        await update.message.reply_text(to_small_caps('invalid input'))
    except Exception as e:
        LOGGER.error(f"Approve elite error: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}: {str(e)}")

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
            now = datetime.now(timezone.utc)
            
            if last_claim and isinstance(last_claim, datetime):
                time_since = now - last_claim
                if time_since < timedelta(days=7):
                    remaining = timedelta(days=7) - time_since
                    await query.answer(
                        f"{to_small_caps('next claim')}: {remaining.days}d",
                        show_alert=True
                    )
                    return
            
            reward = PASS_CONFIG[tier]['weekly_reward']
            new_claims = pass_data.get('weekly_claims', 0) + 1
            
            # Update with task counter included
            update_data = {
                '$set': {
                    'pass_data.last_weekly_claim': now,
                    'pass_data.weekly_claims': new_claims,
                    'pass_data.tasks.weekly_claims': new_claims
                },
                '$inc': {'balance': reward}
            }
            
            # Handle streak
            last_streak = pass_data.get('last_streak_claim')
            current_streak = pass_data.get('streak_count', 0)
            
            if last_streak and isinstance(last_streak, datetime):
                days_since = (now - last_streak).days
                if 6 <= days_since <= 8:
                    current_streak += 1
                    update_data['$set']['pass_data.streak_count'] = current_streak
                    update_data['$set']['pass_data.last_streak_claim'] = now
                elif days_since > 8:
                    current_streak = 1
                    update_data['$set']['pass_data.streak_count'] = 1
                    update_data['$set']['pass_data.last_streak_claim'] = now
            else:
                current_streak = 1
                update_data['$set']['pass_data.streak_count'] = 1
                update_data['$set']['pass_data.last_streak_claim'] = now
            
            await user_collection.update_one({'id': user_id}, update_data)
            
            await query.message.reply_text(
                f"{to_small_caps('claimed')}: <code>{reward:,}</code>\n{to_small_caps('streak')}: {current_streak}",
                parse_mode='HTML'
            )
            
        elif action == 'tasks':
            pass_data = await get_or_create_pass_data(user_id)
            tasks = pass_data.get('tasks', {})
            
            task_list = []
            for k, v in MYTHIC_TASKS.items():
                current = tasks.get(k, 0)
                required = v['required']
                progress = min(100, int((current / required) * 100))
                bar_filled = '█' * (progress // 10)
                bar_empty = '░' * (10 - progress // 10)
                task_list.append(
                    f"{to_small_caps(k)}: {current}/{required} {bar_filled}{bar_empty} {progress}%"
                )
            
            caption = f"{to_small_caps('tasks')}\n\n" + "\n".join(task_list)
            keyboard = [[InlineKeyboardButton(to_small_caps("back"), callback_data="ps_back")]]
            
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
        elif action == 'invite':
            pass_data = await get_or_create_pass_data(user_id)
            total_invites = pass_data.get('tasks', {}).get('invites', 0)
            total_earnings = pass_data.get('total_invite_earnings', 0)
            
            bot_username = context.bot.username
            invite_link = f"https://t.me/{bot_username}?start=r_{user_id}"
            
            caption = f"""{to_small_caps('invite')}

{to_small_caps('referrals')}: {total_invites}
{to_small_caps('earned')}: {total_earnings:,}

<code>{invite_link}</code>"""
            
            keyboard = [[InlineKeyboardButton(to_small_caps("back"), callback_data="ps_back")]]
            
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
        elif action == 'upgrade':
            tier = await check_and_update_tier(user_id)
            user = await user_collection.find_one({'id': user_id})
            balance = user.get('balance', 0)
            
            caption = f"""{to_small_caps('upgrade')}

{to_small_caps('balance')}: <code>{balance:,}</code>
{to_small_caps('tier')}: {PASS_CONFIG[tier]['name']}

{to_small_caps('premium')}: 50,000 {to_small_caps('gold')}
{to_small_caps('elite')}: 50 INR"""
            
            keyboard = [
                [InlineKeyboardButton(to_small_caps("premium"), callback_data="ps_buypremium")],
                [InlineKeyboardButton(to_small_caps("elite"), callback_data="ps_buyelite")],
                [InlineKeyboardButton(to_small_caps("back"), callback_data="ps_back")]
            ]
            
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
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
            
            keyboard = [
                [InlineKeyboardButton(to_small_caps("claim"), callback_data="ps_claim"), InlineKeyboardButton(to_small_caps("tasks"), callback_data="ps_tasks")],
                [InlineKeyboardButton(to_small_caps("upgrade"), callback_data="ps_upgrade"), InlineKeyboardButton(to_small_caps("invite"), callback_data="ps_invite")]
            ]
            
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
        elif action == 'buypremium':
            user = await user_collection.find_one({'id': user_id})
            cost = PASS_CONFIG['premium']['cost']
            balance = user.get('balance', 0)
            
            caption = f"""{to_small_caps('premium')}

{to_small_caps('cost')}: <code>{cost:,}</code>
{to_small_caps('balance')}: <code>{balance:,}</code>"""
            
            keyboard = [
                [InlineKeyboardButton(to_small_caps("confirm"), callback_data="ps_confirmprem"), InlineKeyboardButton(to_small_caps("cancel"), callback_data="ps_upgrade")]
            ]
            
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
        elif action == 'confirmprem':
            user = await user_collection.find_one({'id': user_id})
            cost = PASS_CONFIG['premium']['cost']
            
            if user.get('balance', 0) < cost:
                await query.answer(
                    to_small_caps("insufficient balance"),
                    show_alert=True
                )
                return
            
            expires = datetime.now(timezone.utc) + timedelta(days=30)
            
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
            
            await query.edit_message_caption(
                caption=f"{to_small_caps('premium activated')}\n{to_small_caps('expires')}: {expires.strftime('%Y-%m-%d')}",
                parse_mode='HTML'
            )
            
        elif action == 'buyelite':
            caption = f"""{to_small_caps('elite payment')}

{to_small_caps('amount')}: 50 INR
{to_small_caps('upi')}: <code>{PASS_CONFIG['elite']['upi_id']}</code>

{to_small_caps('send payment then click submit')}"""
            
            keyboard = [
                [InlineKeyboardButton(to_small_caps("submit"), callback_data="ps_submitelite")],
                [InlineKeyboardButton(to_small_caps("cancel"), callback_data="ps_upgrade")]
            ]
            
            await query.edit_message_caption(
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            
        elif action == 'submitelite':
            await user_collection.update_one(
                {'id': user_id},
                {
                    '$set': {
                        'pass_data.pending_elite_payment': {
                            'timestamp': datetime.now(timezone.utc),
                            'user_id': user_id,
                            'username': query.from_user.username or 'No username',
                            'first_name': query.from_user.first_name
                        }
                    }
                }
            )
            
            try:
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"{to_small_caps('elite payment pending')}\n"
                         f"{to_small_caps('user')}: <code>{user_id}</code>\n"
                         f"{to_small_caps('name')}: {query.from_user.first_name}\n"
                         f"{to_small_caps('username')}: @{query.from_user.username or 'none'}\n\n"
                         f"/approveelite {user_id}",
                    parse_mode='HTML'
                )
            except Exception as e:
                LOGGER.error(f"Failed to notify owner about elite payment: {e}")
            
            await query.edit_message_caption(
                caption=f"{to_small_caps('payment submitted')}\n{to_small_caps('will be verified within 24h')}",
                parse_mode='HTML'
            )
            
    except Exception as e:
        LOGGER.error(f"Callback error for user {user_id if 'user_id' in locals() else 'unknown'}: {e}")
        try:
            await query.answer(to_small_caps('error'), show_alert=True)
        except:
            pass

# Register all handlers
application.add_handler(CommandHandler("start", start_command, block=False))
application.add_handler(CommandHandler("pass", pass_command, block=False))
application.add_handler(CommandHandler("pclaim", pclaim_command, block=False))
application.add_handler(CommandHandler("sweekly", sweekly_command, block=False))
application.add_handler(CommandHandler("tasks", tasks_command, block=False))
application.add_handler(CommandHandler("upgrade", upgrade_command, block=False))
application.add_handler(CommandHandler("invite", invite_command, block=False))
application.add_handler(CommandHandler("addinvite", addinvite_command, block=False))
application.add_handler(CommandHandler("addgrab", addgrab_command, block=False))
application.add_handler(CommandHandler("approveelite", approve_elite_command, block=False))
application.add_handler(CallbackQueryHandler(pass_callback, pattern=r"^ps_", block=False))one({'id': user_id}, {'$set': {'pass_data': pass_data}})
        return pass_data
    return user.get('pass_data', {})

async def check_and_update_tier(user_id: int):
    pass_data = await get_or_create_pass_data(user_id)
    tier = pass_data.get('tier', 'free')
    now = datetime.now(timezone.utc)
    
    if tier == 'elite':
        elite_expires = pass_data.get('elite_expires')
        if elite_expires and isinstance(elite_expires, datetime) and elite_expires < now:
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.tier': 'free', 'pass_data.elite_expires': None}})
            return 'free'
    elif tier == 'premium':
        premium_expires = pass_data.get('premium_expires')
        if premium_expires and isinstance(premium_expires, datetime) and premium_expires < now:
            await user_collection.update_one({'id': user_id}, {'$set': {'pass_data.tier': 'free', 'pass_data.premium_expires': None}})
            return 'free'
    return tier

async def get_mythic_characters(count: int):
    """Safely get available mythic characters"""
    try:
        mythic_chars = await collection.find({'rarity': '🏵 Mythic'}).limit(count).to_list(length=count)
        return mythic_chars
    except Exception as e:
        LOGGER.error(f"Error fetching mythic characters: {e}")
        return []

async def update_grab_task(user_id: int):
    """Update grab task counter"""
    try:
        await user_collection.update_one({'id': user_id}, {'$inc': {'pass_data.tasks.grabs': 1}})
        LOGGER.info(f"Grab task updated for user {user_id}")
    except Exception as e:
        LOGGER.error(f"Error updating grab task for user {user_id}: {e}")

async def start_command(update: Update, context: CallbackContext):
    """Handle /start command with referral tracking"""
    user_id = update.effective_user.id
    
    # Check for referral code
    if context.args and len(context.args) > 0 and context.args[0].startswith('r_'):
        try:
            referrer_id = int(context.args[0][2:])
            
            # Don't allow self-referral
            if referrer_id == user_id:
                await update.message.reply_text(to_small_caps("cannot refer yourself"))
                return
            
            # Check if user exists
            user = await user_collection.find_one({'id': user_id})
            
            if not user:
                # New user - create account
                await user_collection.insert_one({
                    'id': user_id,
                    'characters': [],
                    'balance': 0,
                    'referred_by': referrer_id
                })
                
                # Initialize referrer's pass data if needed
                await get_or_create_pass_data(referrer_id)
                
                # Credit referrer
                result = await user_collection.update_one(
                    {'id': referrer_id},
                    {
                        '$inc': {
                            'pass_data.tasks.invites': 1,
                            'pass_data.total_invite_earnings': INVITE_REWARD,
                            'balance': INVITE_REWARD
                        },
                        '$push': {'pass_data.invited_users': user_id}
                    }
                )
                
                if result.modified_count > 0:
                    # Notify referrer
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"{to_small_caps('new referral')}\n{to_small_caps('earned')}: <code>{INVITE_REWARD:,}</code>",
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        LOGGER.error(f"Failed to notify referrer {referrer_id}: {e}")
                    
                    await update.message.reply_text(
                        f"{to_small_caps('welcome')}\n{to_small_caps('you were referred')}\n{to_small_caps('use')} /pass {to_small_caps('to get started')}",
                        parse_mode='HTML'
                    )
                else:
                    await update.message.reply_text(to_small_caps("welcome! use /pass to get started"))
            elif not user.get('referred_by'):
                await update.message.reply_text(to_small_caps("referral only works for new users"))
            else:
                await update.message.reply_text(to_small_caps("you were already referred by someone"))
                
        except (ValueError, IndexError) as e:
            LOGGER.error(f"Invalid referral code: {e}")
            await update.message.reply_text(to_small_caps("invalid referral code"))
    else:
        # Regular start message
        await update.message.reply_text(
            f"{to_small_caps('welcome')}\n{to_small_caps('use')} /pass {to_small_caps('to get started')}",
            parse_mode='HTML'
        )

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
                days_left = max(0, (elite_expires - datetime.now(timezone.utc)).days)
                tier_status = to_small_caps("elite") + f" ({days_left} " + to_small_caps("days") + ")"
        elif tier == 'premium':
            premium_expires = pass_data.get('premium_expires')
            if premium_expires and isinstance(premium_expires, datetime):
                days_left = max(0, (premium_expires - datetime.now(timezone.utc)).days)
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
        
        keyboard = [
            [InlineKeyboardButton(to_small_caps("claim"), callback_data="ps_claim"), InlineKeyboardButton(to_small_caps("tasks"), callback_data="ps_tasks")],
            [InlineKeyboardButton(to_small_caps("upgrade"), callback_data="ps_upgrade"), InlineKeyboardButton(to_small_caps("invite"), callback_data="ps_invite")]
        ]
        
        await update.message.reply_photo(
            photo="https://files.catbox.moe/z8fhwx.jpg",
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Pass command error for user {user_id}: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}\n{to_small_caps('please try again later')}")

async def pclaim_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)
        
        last_claim = pass_data.get('last_weekly_claim')
        now = datetime.now(timezone.utc)
        
        # Check if user can claim
        if last_claim and isinstance(last_claim, datetime):
            time_since = now - last_claim
            if time_since < timedelta(days=7):
                remaining = timedelta(days=7) - time_since
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                await update.message.reply_text(
                    f"{to_small_caps('next claim in')}: {remaining.days}d {hours}h {minutes}m"
                )
                return
        
        reward = PASS_CONFIG[tier]['weekly_reward']
        mythic_chars_count = PASS_CONFIG[tier]['mythic_characters']
        new_claims = pass_data.get('weekly_claims', 0) + 1
        
        # Update basic claim data
        update_data = {
            '$set': {
                'pass_data.last_weekly_claim': now,
                'pass_data.weekly_claims': new_claims,
                'pass_data.tasks.weekly_claims': new_claims
            },
            '$inc': {'balance': reward}
        }
        
        # Handle streak logic
        last_streak = pass_data.get('last_streak_claim')
        current_streak = pass_data.get('streak_count', 0)
        
        if last_streak and isinstance(last_streak, datetime):
            days_since = (now - last_streak).days
            if 6 <= days_since <= 8:
                # Valid weekly claim - increment streak
                current_streak += 1
                update_data['$set']['pass_data.streak_count'] = current_streak
                update_data['$set']['pass_data.last_streak_claim'] = now
            elif days_since > 8:
                # Streak broken - reset to 1
                current_streak = 1
                update_data['$set']['pass_data.streak_count'] = 1
                update_data['$set']['pass_data.last_streak_claim'] = now
            # If days_since < 6, keep current streak (too early to claim streak)
        else:
            # First claim ever - start streak
            current_streak = 1
            update_data['$set']['pass_data.streak_count'] = 1
            update_data['$set']['pass_data.last_streak_claim'] = now
        
        # Add mythic characters for premium/elite
        premium_msg = ""
        if mythic_chars_count > 0:
            mythic_chars = await get_mythic_characters(mythic_chars_count)
            if mythic_chars:
                update_data['$push'] = {'characters': {'$each': mythic_chars}}
                await user_totals_collection.update_one(
                    {'id': user_id},
                    {'$inc': {'count': len(mythic_chars)}},
                    upsert=True
                )
                premium_msg = f"\n{to_small_caps('bonus')}: {len(mythic_chars)} {to_small_caps('mythic added')}"
        
        # Apply all updates
        await user_collection.update_one({'id': user_id}, update_data)
        
        await update.message.reply_text(
            f"{to_small_caps('claimed')}\n{to_small_caps('reward')}: <code>{reward:,}</code>\n{to_small_caps('claims')}: {new_claims}/6\n{to_small_caps('streak')}: {current_streak}{premium_msg}",
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Claim error for user {user_id}: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}\n{to_small_caps('please try again')}")

async def sweekly_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        tier = await check_and_update_tier(user_id)
        pass_data = await get_or_create_pass_data(user_id)
        
        weekly_claims = pass_data.get('weekly_claims', 0)
        if weekly_claims < 6:
            await update.message.reply_text(
                f"{to_small_caps('need 6 claims')}: {weekly_claims}/6"
            )
            return
        
        bonus = PASS_CONFIG[tier]['streak_bonus']
        mythic_char = await collection.find_one({'rarity': '🏵 Mythic'})
        
        update_data = {
            '$inc': {'balance': bonus},
            '$set': {'pass_data.weekly_claims': 0}
        }
        
        if mythic_char:
            update_data['$push'] = {'characters': mythic_char}
            await user_totals_collection.update_one(
                {'id': user_id},
                {'$inc': {'count': 1}},
                upsert=True
            )
        
        await user_collection.update_one({'id': user_id}, update_data)
        
        char_msg = f"\n{to_small_caps('bonus char')}: {mythic_char.get('name', 'unknown')}" if mythic_char else ""
        await update.message.reply_text(
            f"{to_small_caps('streak claimed')}\n{to_small_caps('bonus')}: <code>{bonus:,}</code>{char_msg}",
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Sweekly error for user {user_id}: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}\n{to_small_caps('please try again')}")

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
            
            bar_filled = '█' * (progress // 10)
            bar_empty = '░' * (10 - progress // 10)
            task_list.append(
                f"{to_small_caps(k)}: {current}/{required} {bar_filled}{bar_empty} {progress}% {status}"
            )
        
        # Check if all tasks completed and mythic not yet unlocked
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
                await update.message.reply_text(
                    f"🎉 {to_small_caps('all tasks completed')}\n{to_small_caps('mythic character unlocked')}: {mythic_char.get('name', 'unknown')}",
                    parse_mode='HTML'
                )
        
        mythic_status = to_small_caps('unlocked') if mythic_unlocked else to_small_caps('locked')
        caption = f"{to_small_caps('tasks')}\n\n" + "\n".join(task_list) + f"\n\n{to_small_caps('mythic')}: {mythic_status}"
        
        await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Tasks error for user {user_id}: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}\n{to_small_caps('please try again')}")

async def invite_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        pass_data = await get_or_create_pass_data(user_id)
        total_invites = pass_data.get('tasks', {}).get('invites', 0)
        total_earnings = pass_data.get('total_invite_earnings', 0)
        
        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start=r_{user_id}"
        
        caption = f"""{to_small_caps('invite program')}

{to_small_caps('referrals')}: {total_invites}
{to_small_caps('earned')}: {total_earnings:,}

{to_small_caps('reward')}: {INVITE_REWARD:,} {to_small_caps('per invite')}

<code>{invite_link}</code>"""
        
        await update.message.reply_text(caption, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Invite error for user {user_id}: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}\n{to_small_caps('please try again')}")

async def upgrade_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    try:
        tier = await check_and_update_tier(user_id)
        user = await user_collection.find_one({'id': user_id})
        balance = user.get('balance', 0)
        
        caption = f"""{to_small_caps('upgrade')}

{to_small_caps('balance')}: <code>{balance:,}</code>
{to_small_caps('tier')}: {PASS_CONFIG[tier]['name']}

{to_small_caps('premium')}: 50,000 {to_small_caps('gold')} - 30d
{to_small_caps('elite')}: 50 INR - 30d"""
        
        keyboard = [
            [InlineKeyboardButton(to_small_caps("premium"), callback_data="ps_buypremium")],
            [InlineKeyboardButton(to_small_caps("elite"), callback_data="ps_buyelite")]
        ]
        
        await update.message.reply_photo(
            photo="https://files.catbox.moe/z8fhwx.jpg",
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception as e:
        LOGGER.error(f"Upgrade error for user {user_id}: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}\n{to_small_caps('please try again')}")

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
        
        result = await user_collection.update_one(
            {'id': target_user_id},
            {
                '$inc': {
                    'pass_data.tasks.invites': invite_count,
                    'pass_data.total_invite_earnings': gold_reward,
                    'balance': gold_reward
                }
            }
        )
        
        if result.modified_count > 0:
            await update.message.reply_text(
                f"{to_small_caps('added')}\n{to_small_caps('user')}: <code>{target_user_id}</code>\n{to_small_caps('invites')}: {invite_count}\n{to_small_caps('gold')}: <code>{gold_reward:,}</code>",
                parse_mode='HTML'
            )
            
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"{to_small_caps('invite reward')}\n{invite_count} {to_small_caps('credits')}\n<code>{gold_reward:,}</code> {to_small_caps('gold')}",
                    parse_mode='HTML'
                )
            except Exception as e:
                LOGGER.error(f"Failed to notify user {target_user_id}: {e}")
        else:
            await update.message.reply_text(to_small_caps('failed to update user'))
            
    except ValueError:
        await update.message.reply_text(to_small_caps('invalid input'))
    except Exception as e:
        LOGGER.error(f"Addinvite error: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}: {str(e)}")

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
        
        result = await user_collection.update_one(
            {'id': target_user_id},
            {'$inc': {'pass_data.tasks.grabs': grab_count}}
        )
        
        if result.modified_count > 0:
            await update.message.reply_text(
                f"{to_small_caps('added')}\n{to_small_caps('user')}: <code>{target_user_id}</code>\n{to_small_caps('grabs')}: {grab_count}",
                parse_mode='HTML'
            )
            
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"{grab_count} {to_small_caps('grab credits added')}",
                    parse_mode='HTML'
                )
            except Exception as e:
                LOGGER.error(f"Failed to notify user {target_user_id}: {e}")
        else:
            await update.message.reply_text(to_small_caps('failed to update user'))
            
    except ValueError:
        await update.message.reply_text(to_small_caps('invalid input'))
    except Exception as e:
        LOGGER.error(f"Addgrab error: {e}")
        await update.message.reply_text(f"{to_small_caps('error occurred')}: {str(e)}")

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
        
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        activation_bonus = PASS_CONFIG['elite']['activation_bonus']
        mythic_chars = await get_mythic_characters(5)
        
        update_data = {
            '$set': {
                'pass_data.tier': 'elite',
                'pass_data.elite_expires': expires,
                'pass_data.pending_elite_payment': None
            },
            '$inc': {'balance': activation_bonus}
        }
        
        if mythic_chars:
            update_data['$push'] = {'characters': {'$each': mythic_chars}}
            await user_totals_collection.update_one(
                {'id': target_user_id},
                {'$inc': {'count': len(mythic_chars)}},
                upsert=True
            )
        
        await user_collection.update_