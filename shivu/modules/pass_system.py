from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from html import escape
from shivu import application, user_collection, collection, user_totals_collection, LOGGER

OWNER_ID = 5147822244
INVITE_REWARD = 1000

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

def sc(text):
    m = {'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ғ','g':'ɢ','h':'ʜ','i':'ɪ','j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ','q':'ǫ','r':'ʀ','s':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','x':'x','y':'ʏ','z':'ᴢ'}
    return ''.join(m.get(c.lower(), c) for c in text)

async def get_pass_data(uid):
    u = await user_collection.find_one({'id': uid})
    if not u:
        await user_collection.insert_one({'id': uid, 'characters': [], 'balance': 0})
    if 'pass_data' not in (u or {}):
        pd = {'tier': 'free', 'weekly_claims': 0, 'last_weekly_claim': None, 'streak_count': 0, 'last_streak_claim': None, 'tasks': {'invites': 0, 'weekly_claims': 0, 'grabs': 0}, 'mythic_unlocked': False, 'premium_expires': None, 'elite_expires': None, 'pending_elite_payment': None, 'invited_users': [], 'total_invite_earnings': 0}
        await user_collection.update_one({'id': uid}, {'$set': {'pass_data': pd}})
        return pd
    return u.get('pass_data', {})

async def check_tier(uid):
    pd = await get_pass_data(uid)
    tier = pd.get('tier', 'free')
    now = datetime.now(timezone.utc)
    if tier == 'elite' and pd.get('elite_expires') and pd['elite_expires'] < now:
        await user_collection.update_one({'id': uid}, {'$set': {'pass_data.tier': 'free'}})
        return 'free'
    if tier == 'premium' and pd.get('premium_expires') and pd['premium_expires'] < now:
        await user_collection.update_one({'id': uid}, {'$set': {'pass_data.tier': 'free'}})
        return 'free'
    return tier

async def get_mythics(cnt):
    try:
        return await collection.find({'rarity': '🏵 Mythic'}).limit(cnt).to_list(length=cnt)
    except:
        return []

async def update_grab_task(uid):
    try:
        await user_collection.update_one({'id': uid}, {'$inc': {'pass_data.tasks.grabs': 1}})
    except Exception as e:
        LOGGER.error(f"Grab task error {uid}: {e}")

async def start_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if context.args and context.args[0].startswith('r_'):
        try:
            rid = int(context.args[0][2:])
            if rid == uid:
                return await update.message.reply_text(sc("cannot refer yourself"))
            u = await user_collection.find_one({'id': uid})
            if not u:
                await user_collection.insert_one({'id': uid, 'characters': [], 'balance': 0, 'referred_by': rid})
                await get_pass_data(rid)
                r = await user_collection.update_one({'id': rid}, {'$inc': {'pass_data.tasks.invites': 1, 'pass_data.total_invite_earnings': INVITE_REWARD, 'balance': INVITE_REWARD}, '$push': {'pass_data.invited_users': uid}})
                if r.modified_count > 0:
                    try:
                        await context.bot.send_message(rid, f"{sc('new referral')}\n{sc('earned')}: <code>{INVITE_REWARD:,}</code>", parse_mode='HTML')
                    except:
                        pass
                    return await update.message.reply_text(f"{sc('welcome')}\n{sc('use')} /pass", parse_mode='HTML')
            elif not u.get('referred_by'):
                return await update.message.reply_text(sc("referral only for new users"))
            return await update.message.reply_text(sc("already referred"))
        except:
            pass
    await update.message.reply_text(f"{sc('welcome')}\n{sc('use')} /pass")

async def pass_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        tier = await check_tier(uid)
        pd = await get_pass_data(uid)
        u = await user_collection.find_one({'id': uid})
        ts = pd.get('tasks', {})
        comp = sum(1 for k, v in MYTHIC_TASKS.items() if ts.get(k, 0) >= v['required'])
        
        tier_txt = sc("free")
        if tier == 'elite' and pd.get('elite_expires'):
            days = max(0, (pd['elite_expires'] - datetime.now(timezone.utc)).days)
            tier_txt = sc("elite") + f" ({days} {sc('days')})"
        elif tier == 'premium' and pd.get('premium_expires'):
            days = max(0, (pd['premium_expires'] - datetime.now(timezone.utc)).days)
            tier_txt = sc("premium") + f" ({days} {sc('days')})"
        
        cap = f"""{PASS_CONFIG[tier]['name']}

{sc('user')}: {escape(update.effective_user.first_name)}
{sc('id')}: <code>{uid}</code>
{sc('balance')}: <code>{u.get('balance', 0):,}</code>

{sc('claims')}: {pd.get('weekly_claims', 0)}/6
{sc('streak')}: {pd.get('streak_count', 0)}
{sc('tasks')}: {comp}/{len(MYTHIC_TASKS)}
{sc('mythic')}: {sc('unlocked') if pd.get('mythic_unlocked') else sc('locked')}
{sc('multiplier')}: {PASS_CONFIG[tier]['grab_multiplier']}x

{sc('tier')}: {tier_txt}"""
        
        kb = [[InlineKeyboardButton(sc("claim"), callback_data="ps_claim"), InlineKeyboardButton(sc("tasks"), callback_data="ps_tasks")], [InlineKeyboardButton(sc("upgrade"), callback_data="ps_upgrade"), InlineKeyboardButton(sc("invite"), callback_data="ps_invite")]]
        await update.message.reply_photo("https://files.catbox.moe/z8fhwx.jpg", caption=cap, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Pass error {uid}: {e}")
        await update.message.reply_text(sc('error'))

async def handle_streak(uid, pd, now):
    ls = pd.get('last_streak_claim')
    cs = pd.get('streak_count', 0)
    upd = {}
    if ls and isinstance(ls, datetime):
        days = (now - ls).days
        if 6 <= days <= 8:
            cs += 1
            upd = {'pass_data.streak_count': cs, 'pass_data.last_streak_claim': now}
        elif days > 8:
            cs = 1
            upd = {'pass_data.streak_count': 1, 'pass_data.last_streak_claim': now}
    else:
        cs = 1
        upd = {'pass_data.streak_count': 1, 'pass_data.last_streak_claim': now}
    return cs, upd

async def pclaim_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        tier = await check_tier(uid)
        pd = await get_pass_data(uid)
        lc = pd.get('last_weekly_claim')
        now = datetime.now(timezone.utc)
        
        if lc and isinstance(lc, datetime) and now - lc < timedelta(days=7):
            rem = timedelta(days=7) - (now - lc)
            return await update.message.reply_text(f"{sc('next claim in')}: {rem.days}d {rem.seconds//3600}h")
        
        rwd = PASS_CONFIG[tier]['weekly_reward']
        nc = pd.get('weekly_claims', 0) + 1
        cs, s_upd = await handle_streak(uid, pd, now)
        
        upd = {'$set': {'pass_data.last_weekly_claim': now, 'pass_data.weekly_claims': nc, 'pass_data.tasks.weekly_claims': nc, **s_upd}, '$inc': {'balance': rwd}}
        
        msg = ""
        mc = PASS_CONFIG[tier]['mythic_characters']
        if mc > 0:
            mcs = await get_mythics(mc)
            if mcs:
                upd['$push'] = {'characters': {'$each': mcs}}
                await user_totals_collection.update_one({'id': uid}, {'$inc': {'count': len(mcs)}}, upsert=True)
                msg = f"\n{sc('bonus')}: {len(mcs)} {sc('mythic')}"
        
        await user_collection.update_one({'id': uid}, upd)
        await update.message.reply_text(f"{sc('claimed')}\n{sc('reward')}: <code>{rwd:,}</code>\n{sc('streak')}: {cs}{msg}", parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Claim error {uid}: {e}")
        await update.message.reply_text(sc('error'))

async def sweekly_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        tier = await check_tier(uid)
        pd = await get_pass_data(uid)
        if pd.get('weekly_claims', 0) < 6:
            return await update.message.reply_text(f"{sc('need 6 claims')}: {pd.get('weekly_claims', 0)}/6")
        
        bonus = PASS_CONFIG[tier]['streak_bonus']
        mc = await collection.find_one({'rarity': '🏵 Mythic'})
        upd = {'$inc': {'balance': bonus}, '$set': {'pass_data.weekly_claims': 0}}
        if mc:
            upd['$push'] = {'characters': mc}
            await user_totals_collection.update_one({'id': uid}, {'$inc': {'count': 1}}, upsert=True)
        await user_collection.update_one({'id': uid}, upd)
        cm = f"\n{sc('bonus char')}: {mc.get('name')}" if mc else ""
        await update.message.reply_text(f"{sc('streak claimed')}\n{sc('bonus')}: <code>{bonus:,}</code>{cm}", parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Weekly error {uid}: {e}")
        await update.message.reply_text(sc('error'))

async def tasks_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        pd = await get_pass_data(uid)
        ts = pd.get('tasks', {})
        mu = pd.get('mythic_unlocked', False)
        tl, ac = [], True
        
        for k, v in MYTHIC_TASKS.items():
            cur, req = ts.get(k, 0), v['required']
            prg = min(100, int((cur / req) * 100))
            if cur < req: ac = False
            tl.append(f"{sc(k)}: {cur}/{req} {'█'*(prg//10)}{'░'*(10-prg//10)} {prg}%")
        
        if ac and not mu:
            mc = await collection.find_one({'rarity': '🏵 Mythic'})
            if mc:
                await user_collection.update_one({'id': uid}, {'$push': {'characters': mc}, '$set': {'pass_data.mythic_unlocked': True}})
                await user_totals_collection.update_one({'id': uid}, {'$inc': {'count': 1}}, upsert=True)
                mu = True
                await update.message.reply_text(f"🎉 {sc('mythic unlocked')}: {mc.get('name')}")
        
        await update.message.reply_text(f"{sc('tasks')}\n\n" + "\n".join(tl) + f"\n\n{sc('mythic')}: {sc('unlocked') if mu else sc('locked')}")
    except Exception as e:
        LOGGER.error(f"Tasks error {uid}: {e}")
        await update.message.reply_text(sc('error'))

async def invite_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        pd = await get_pass_data(uid)
        ti = pd.get('tasks', {}).get('invites', 0)
        te = pd.get('total_invite_earnings', 0)
        lnk = f"https://t.me/{context.bot.username}?start=r_{uid}"
        await update.message.reply_text(f"{sc('invite')}\n\n{sc('referrals')}: {ti}\n{sc('earned')}: {te:,}\n{sc('reward')}: {INVITE_REWARD:,}\n\n<code>{lnk}</code>", parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Invite error {uid}: {e}")
        await update.message.reply_text(sc('error'))

async def upgrade_command(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    try:
        tier = await check_tier(uid)
        u = await user_collection.find_one({'id': uid})
        cap = f"{sc('upgrade')}\n\n{sc('balance')}: <code>{u.get('balance', 0):,}</code>\n{sc('tier')}: {PASS_CONFIG[tier]['name']}\n\n{sc('premium')}: 50,000 - 30d\n{sc('elite')}: 50 INR - 30d"
        kb = [[InlineKeyboardButton(sc("premium"), callback_data="ps_buypremium")], [InlineKeyboardButton(sc("elite"), callback_data="ps_buyelite")]]
        await update.message.reply_photo("https://files.catbox.moe/z8fhwx.jpg", caption=cap, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"Upgrade error {uid}: {e}")
        await update.message.reply_text(sc('error'))

async def addinvite_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text(sc('unauthorized'))
    try:
        if len(context.args) < 2:
            return await update.message.reply_text(f"{sc('usage')}: /addinvite <uid> <count>")
        tuid, cnt = int(context.args[0]), int(context.args[1])
        if cnt <= 0:
            return await update.message.reply_text(sc('invalid'))
        await get_pass_data(tuid)
        gold = cnt * INVITE_REWARD
        await user_collection.update_one({'id': tuid}, {'$inc': {'pass_data.tasks.invites': cnt, 'pass_data.total_invite_earnings': gold, 'balance': gold}})
        await update.message.reply_text(f"{sc('added')}\n{sc('user')}: <code>{tuid}</code>\n{sc('invites')}: {cnt}\n{sc('gold')}: <code>{gold:,}</code>", parse_mode='HTML')
        try:
            await context.bot.send_message(tuid, f"{sc('reward')}\n{cnt} {sc('invites')}\n<code>{gold:,}</code>", parse_mode='HTML')
        except:
            pass
    except:
        await update.message.reply_text(sc('error'))

async def addgrab_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text(sc('unauthorized'))
    try:
        if len(context.args) < 2:
            return await update.message.reply_text(f"{sc('usage')}: /addgrab <uid> <count>")
        tuid, cnt = int(context.args[0]), int(context.args[1])
        if cnt <= 0:
            return await update.message.reply_text(sc('invalid'))
        await get_pass_data(tuid)
        await user_collection.update_one({'id': tuid}, {'$inc': {'pass_data.tasks.grabs': cnt}})
        await update.message.reply_text(f"{sc('added')}\n{sc('user')}: <code>{tuid}</code>\n{sc('grabs')}: {cnt}", parse_mode='HTML')
        try:
            await context.bot.send_message(tuid, f"{cnt} {sc('grab credits added')}")
        except:
            pass
    except:
        await update.message.reply_text(sc('error'))

async def approve_elite_command(update: Update, context: CallbackContext):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text(sc('unauthorized'))
    try:
        if len(context.args) < 1:
            return await update.message.reply_text(f"{sc('usage')}: /approveelite <uid>")
        tuid = int(context.args[0])
        tu = await user_collection.find_one({'id': tuid})
        if not tu or not tu.get('pass_data', {}).get('pending_elite_payment'):
            return await update.message.reply_text(sc('no pending payment'))
        
        exp = datetime.now(timezone.utc) + timedelta(days=30)
        bonus = PASS_CONFIG['elite']['activation_bonus']
        mcs = await get_mythics(5)
        upd = {'$set': {'pass_data.tier': 'elite', 'pass_data.elite_expires': exp, 'pass_data.pending_elite_payment': None}, '$inc': {'balance': bonus}}
        if mcs:
            upd['$push'] = {'characters': {'$each': mcs}}
            await user_totals_collection.update_one({'id': tuid}, {'$inc': {'count': len(mcs)}}, upsert=True)
        await user_collection.update_one({'id': tuid}, upd)
        await update.message.reply_text(f"{sc('elite activated')}\n{sc('user')}: <code>{tuid}</code>\n{sc('gold')}: <code>{bonus:,}</code>\n{sc('mythics')}: {len(mcs)}", parse_mode='HTML')
        try:
            await context.bot.send_message(tuid, f"{sc('elite activated')}\n\n{sc('gold')}: <code>{bonus:,}</code>\n{sc('mythics')}: {len(mcs)}\n{sc('expires')}: {exp.strftime('%Y-%m-%d')}", parse_mode='HTML')
        except:
            pass
    except:
        await update.message.reply_text(sc('error'))

async def pass_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    await q.answer()
    try:
        act = q.data.split('_')[1]
        uid = q.from_user.id
        
        if act == 'claim':
            tier = await check_tier(uid)
            pd = await get_pass_data(uid)
            now = datetime.now(timezone.utc)
            lc = pd.get('last_weekly_claim')
            if lc and isinstance(lc, datetime) and now - lc < timedelta(days=7):
                return await q.answer(f"{sc('wait')}: {((timedelta(days=7)-(now-lc)).days)}d", show_alert=True)
            
            rwd = PASS_CONFIG[tier]['weekly_reward']
            nc = pd.get('weekly_claims', 0) + 1
            cs, s_upd = await handle_streak(uid, pd, now)
            upd = {'$set': {'pass_data.last_weekly_claim': now, 'pass_data.weekly_claims': nc, 'pass_data.tasks.weekly_claims': nc, **s_upd}, '$inc': {'balance': rwd}}
            await user_collection.update_one({'id': uid}, upd)
            await q.message.reply_text(f"{sc('claimed')}: <code>{rwd:,}</code>\n{sc('streak')}: {cs}", parse_mode='HTML')
            
        elif act == 'tasks':
            pd = await get_pass_data(uid)
            ts = pd.get('tasks', {})
            tl = [f"{sc(k)}: {ts.get(k, 0)}/{v['required']}" for k, v in MYTHIC_TASKS.items()]
            kb = [[InlineKeyboardButton(sc("back"), callback_data="ps_back")]]
            await q.edit_message_caption(f"{sc('tasks')}\n\n" + "\n".join(tl), reply_markup=InlineKeyboardMarkup(kb))
            
        elif act == 'invite':
            pd = await get_pass_data(uid)
            ti = pd.get('tasks', {}).get('invites', 0)
            te = pd.get('total_invite_earnings', 0)
            lnk = f"https://t.me/{context.bot.username}?start=r_{uid}"
            kb = [[InlineKeyboardButton(sc("back"), callback_data="ps_back")]]
            await q.edit_message_caption(f"{sc('invite')}\n\n{sc('referrals')}: {ti}\n{sc('earned')}: {te:,}\n\n<code>{lnk}</code>", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            
        elif act == 'upgrade':
            tier = await check_tier(uid)
            u = await user_collection.find_one({'id': uid})
            kb = [[InlineKeyboardButton(sc("premium"), callback_data="ps_buypremium")], [InlineKeyboardButton(sc("elite"), callback_data="ps_buyelite")], [InlineKeyboardButton(sc("back"), callback_data="ps_back")]]
            await q.edit_message_caption(f"{sc('upgrade')}\n\n{sc('balance')}: <code>{u.get('balance', 0):,}</code>\n{sc('tier')}: {PASS_CONFIG[tier]['name']}\n\n{sc('premium')}: 50,000\n{sc('elite')}: 50 INR", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            
        elif act == 'back':
            tier = await check_tier(uid)
            pd = await get_pass_data(uid)
            u = await user_collection.find_one({'id': uid})
            ts = pd.get('tasks', {})
            comp = sum(1 for k, v in MYTHIC_TASKS.items() if ts.get(k, 0) >= v['required'])
            cap = f"{PASS_CONFIG[tier]['name']}\n\n{sc('balance')}: <code>{u.get('balance', 0):,}</code>\n{sc('claims')}: {pd.get('weekly_claims', 0)}/6\n{sc('streak')}: {pd.get('streak_count', 0)}\n{sc('tasks')}: {comp}/{len(MYTHIC_TASKS)}\n{sc('multiplier')}: {PASS_CONFIG[tier]['grab_multiplier']}x"
            kb = [[InlineKeyboardButton(sc("claim"), callback_data="ps_claim"), InlineKeyboardButton(sc("tasks"), callback_data="ps_tasks")], [InlineKeyboardButton(sc("upgrade"), callback_data="ps_upgrade"), InlineKeyboardButton(sc("invite"), callback_data="ps_invite")]]
            await q.edit_message_caption(cap, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            
        elif act == 'buypremium':
            u = await user_collection.find_one({'id': uid})
            cost = PASS_CONFIG['premium']['cost']
            kb = [[InlineKeyboardButton(sc("confirm"), callback_data="ps_confirmprem"), InlineKeyboardButton(sc("cancel"), callback_data="ps_upgrade")]]
            await q.edit_message_caption(f"{sc('premium')}\n\n{sc('cost')}: <code>{cost:,}</code>\n{sc('balance')}: <code>{u.get('balance', 0):,}</code>", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            
        elif act == 'confirmprem':
            u = await user_collection.find_one({'id': uid})
            cost = PASS_CONFIG['premium']['cost']
            if u.get('balance', 0) < cost:
                return await q.answer(sc("insufficient balance"), show_alert=True)
            exp = datetime.now(timezone.utc) + timedelta(days=30)
            await user_collection.update_one({'id': uid}, {'$inc': {'balance': -cost}, '$set': {'pass_data.tier': 'premium', 'pass_data.premium_expires': exp}})
            await q.edit_message_caption(f"{sc('premium activated')}\n{sc('expires')}: {exp.strftime('%Y-%m-%d')}")
            
        elif act == 'buyelite':
            kb = [[InlineKeyboardButton(sc("submit"), callback_data="ps_submitelite")], [InlineKeyboardButton(sc("cancel"), callback_data="ps_upgrade")]]
            await q.edit_message_caption(f"{sc('elite payment')}\n\n{sc('amount')}: 50 INR\n{sc('upi')}: <code>{PASS_CONFIG['elite']['upi_id']}</code>\n\n{sc('send payment then click submit')}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            
        elif act == 'submitelite':
            await user_collection.update_one({'id': uid}, {'$set': {'pass_data.pending_elite_payment': {'timestamp': datetime.now(timezone.utc), 'user_id': uid, 'username': q.from_user.username or 'none', 'first_name': q.from_user.first_name}}})
            try:
                await context.bot.send_message(OWNER_ID, f"{sc('elite pending')}\n{sc('user')}: <code>{uid}</code>\n{sc('name')}: {q.from_user.first_name}\n{sc('username')}: @{q.from_user.username or 'none'}\n\n/approveelite {uid}", parse_mode='HTML')
            except:
                pass
            await q.edit_message_caption(f"{sc('payment submitted')}\n{sc('will be verified within 24h')}")
    except Exception as e:
        LOGGER.error(f"Callback error {uid if 'uid' in locals() else 'unknown'}: {e}")
        try:
            await q.answer(sc('error'), show_alert=True)
        except:
            pass

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
application.add_handler(CallbackQueryHandler(pass_callback, pattern=r"^ps_", block=False))