import logging
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from pymongo import MongoClient, ASCENDING
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson.objectid import ObjectId
from rich.logging import RichHandler
from config import settings

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger("godly_bot")

# --- MongoDB Integration ---
def init_mongodb():
    try:
        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB_NAME]
        users = db.users
        # Indexes for performance
        users.create_index([("user_id", ASCENDING)], unique=True)
        users.create_index([("telegram_username", ASCENDING)])
        users.create_index([("godfather", ASCENDING)])
        users.create_index([("status", ASCENDING)])
        logger.info("Connected to MongoDB and ensured indexes.")
        return users
    except Exception as e:
        logger.critical(f"MongoDB connection/indexing failed: {e}")
        exit(1)

users_collection = init_mongodb()

# --- Conversation States ---
(
    LANGUAGE_SELECTION,
    NAME_INPUT,
    NUMBER_INPUT,
    EMAIL_INPUT,
    GODFATHER_INPUT,
    PAYMENT_METHOD,
    TRANSACTION_ID,
) = range(7)

# --- Bot Text & Messages ---
def get_messages(lang, renewal_date_str=""):
    post_approval_fr = (
        "Vous recevrez une somme de 2000 FCFA chaque fois qu’un nouveau compte est créé et une somme globale lorsque les différents "
        "individus parrainés par vous paient leurs abonnements de 5000 FCFA à la fin du mois (25 de chaque mois).\n\n"
        "Tous les paiements sont faits le 25 de chaque mois et les comptes qui manqueront de payer seront automatiquement supprimés.\n\n"
        "Profitez au maximum de notre service de parrainage et gagnez plus grâce à l’achat et la revente des crypto."
    )
    post_approval_en = (
        "You will receive a sum of 2000 FCFA each time a new account is created and a global amount when the different individuals "
        "sponsored by you pay their subscriptions of 5000 FCFA at the end of the month (25th of each month).\n\n"
        "All payments are made on the 25th of each month and accounts that fail to pay will be automatically deleted.\n\n"
        "Make the most of our referral service and earn more by buying and reselling crypto."
    )
    return {
        'welcome': "🎉 Welcome to our referral system! / Bienvenue dans notre système de parrainage!\n\n"
                   "Please choose your language / Choisissez votre langue:",
        'ask_name': {'fr': "📝 Entrez votre nom complet:", 'en': "📝 Please enter your full name:"}[lang],
        'ask_number': {'fr': "📞 Entrez votre numéro de téléphone (Ex: 67...):", 'en': "📞 Please enter your phone number (e.g., 67...):"}[lang],
        'ask_email': {'fr': "📧 Entrez votre adresse e-mail:", 'en': "📧 Please enter your email address:"}[lang],
        'ask_godfather': {'fr': "👨‍👦 Entrez le numéro d'utilisateur Telegram de votre parrain (ou envoyez 'skip' si vous n'en avez pas):", 'en': "👨‍👦 Please enter your godfather's Telegram user ID (or send 'skip' if you don't have one):"}[lang],
        'choose_payment': {'fr': f"✅ Informations enregistrées ! Pour activer votre compte, veuillez payer les frais d'abonnement de **{settings.SUBSCRIPTION_FEE} FCFA**. Choisissez votre mode de paiement :", 'en': f"✅ Information saved! To activate your account, please pay the **{settings.SUBSCRIPTION_FEE} FCFA** subscription fee. Choose your payment method:"}[lang],
        'pending_approval': {'fr': "⏳ Votre paiement est en cours de vérification. Vous recevrez une notification de l'administrateur très bientôt.", 'en': "⏳ Your payment is being verified. You will receive a notification from the admin very soon."}[lang],
        'approved_message': {
            'fr': f"✅ **Félicitations ! Votre compte est approuvé.**\n\n"
                  f"Votre prochain renouvellement est le **{renewal_date_str}**.\n\n"
                  f"**Règles de Parrainage :**\n{post_approval_fr}",
            'en': f"✅ **Congratulations! Your account has been approved.**\n\n"
                  f"Your next renewal is on **{renewal_date_str}**.\n\n"
                  f"**Referral Rules:**\n{post_approval_en}"
        }[lang],
        'rejected_message': {'fr': "❌ **Paiement Refusé**\n\nDésolé, votre paiement n'a pas pu être vérifié. Veuillez vérifier les détails de la transaction et contacter un administrateur si vous pensez qu'il s'agit d'une erreur.", 'en': "❌ **Payment Rejected**\n\nSorry, your payment could not be verified. Please check the transaction details and contact an admin if you believe this is an error."}[lang],
        'cancel': {'fr': "❌ Inscription annulée. Tapez /start pour recommencer.", 'en': "❌ Registration cancelled. Type /start to begin again."}[lang],
        'error': {'fr': "❌ Une erreur de base de données s'est produite. Veuillez réessayer ou contacter un administrateur.", 'en': "❌ A database error occurred. Please try again or contact an admin."}[lang]
    }

PAYMENT_DETAILS = {
    'mtn': {
        'fr': f"📱 **Paiement par MTN Mobile Money**\n\nVeuillez transférer **{settings.SUBSCRIPTION_FEE} FCFA** au numéro suivant:\nNuméro: `+237 6XXXXXXXX`\nNom: `NOM DU BÉNÉFICIAIRE`\n\nAprès le paiement, revenez ici et envoyez l'ID de la transaction pour vérification.",
        'en': f"📱 **MTN Mobile Money Payment**\n\nPlease transfer **{settings.SUBSCRIPTION_FEE} FCFA** to the following number:\nNumber: `+237 6XXXXXXXX`\nName: `RECIPIENT NAME`\n\nAfter payment, come back here and send the Transaction ID for verification."
    },
    'orange': {
        'fr': f"🍊 **Paiement par Orange Money**\n\nVeuillez transférer **{settings.SUBSCRIPTION_FEE} FCFA** au numéro suivant:\nNuméro: `+237 6XXXXXXXX`\nNom: `NOM DU BÉNÉFICIAIRE`\n\nAprès le paiement, revenez ici et envoyez l'ID de la transaction pour vérification.",
        'en': f"🍊 **Orange Money Payment**\n\nPlease transfer **{settings.SUBSCRIPTION_FEE} FCFA** to the following number:\nNumber: `+237 6XXXXXXXX`\nName: `RECIPIENT NAME`\n\nAfter payment, come back here and send the Transaction ID for verification."
    }
}

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["/myinfo", "/referralstats"],
        ["/aboutus", "/contactus"]
    ],
    resize_keyboard=True
)

# --- Utility Functions ---
def calculate_renewal_date() -> date:
    today = date.today()
    next_month = today + relativedelta(months=1)
    renewal_date = next_month.replace(day=settings.RENEWAL_DAY)
    return renewal_date

def normalize_godfather(godfather_input):
    """Always store godfather as user_id (int) if possible, else None."""
    try:
        return int(godfather_input)
    except (ValueError, TypeError):
        # Try to resolve username to user_id
        user = users_collection.find_one({"telegram_username": godfather_input})
        return user["user_id"] if user else None

# --- Conversation Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    existing_user = users_collection.find_one({"user_id": user.id})
    if existing_user and existing_user.get('status') == 'Approved':
        lang = existing_user.get('language', 'en')
        renewal_date = existing_user.get('subscription_renewal_date').strftime('%d %B %Y')
        await update.message.reply_text({
            'fr': f"👋 Re-bonjour! Votre compte est déjà actif. Votre prochain renouvellement est le {renewal_date}.",
            'en': f"👋 Welcome back! Your account is already active. Your next renewal date is {renewal_date}."
        }[lang], reply_markup=MAIN_MENU_KEYBOARD)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data='lang_fr')],
        [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_messages('en', '')['welcome'], reply_markup=reply_markup)
    return LANGUAGE_SELECTION

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = query.data.split('_')[1]
    context.user_data['language'] = lang
    messages = get_messages(lang)
    await query.edit_message_text(text=messages['ask_name'])
    return NAME_INPUT

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['name'] = update.message.text.strip()
    lang = context.user_data['language']
    await update.message.reply_text(get_messages(lang)['ask_number'])
    return NUMBER_INPUT

async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['phone'] = update.message.text.strip()
    lang = context.user_data['language']
    await update.message.reply_text(get_messages(lang)['ask_email'])
    return EMAIL_INPUT

async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['email'] = update.message.text.strip().lower()
    lang = context.user_data['language']
    await update.message.reply_text(get_messages(lang)['ask_godfather'])
    return GODFATHER_INPUT

async def handle_godfather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    godfather_input = update.message.text.strip()
    godfather_id = None if godfather_input.lower() == 'skip' else normalize_godfather(godfather_input)
    context.user_data['godfather'] = godfather_id
    lang = context.user_data['language']
    keyboard = [
        [InlineKeyboardButton("📱 MTN Mobile Money", callback_data='payment_mtn')],
        [InlineKeyboardButton("🍊 Orange Money", callback_data='payment_orange')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_messages(lang)['choose_payment'], reply_markup=reply_markup, parse_mode='Markdown')
    return PAYMENT_METHOD

async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    payment_method = query.data.split('_')[1]
    context.user_data['payment_method'] = payment_method
    lang = context.user_data['language']
    instructions = PAYMENT_DETAILS[payment_method][lang]
    await query.edit_message_text(text=instructions, parse_mode='Markdown')
    return TRANSACTION_ID

async def handle_transaction_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    context.user_data['transaction_id'] = update.message.text.strip()
    lang = context.user_data['language']
    user_data = {
        "user_id": user.id,
        "telegram_id": user.id,
        "telegram_username": user.username,
        "name": context.user_data['name'],
        "phone": context.user_data['phone'],
        "email": context.user_data['email'],
        "godfather": context.user_data['godfather'],
        "payment_method": context.user_data['payment_method'],
        "transaction_id": context.user_data['transaction_id'],
        "language": lang,
        "status": "Pending",
        "registration_date": datetime.utcnow()
    }
    try:
        users_collection.update_one(
            {"user_id": user.id},
            {"$set": user_data},
            upsert=True
        )
        logger.info(f"User data for {user.id} saved/updated in MongoDB.")
        await update.message.reply_text(
            get_messages(lang)['pending_approval'],
            reply_markup=MAIN_MENU_KEYBOARD
        )
        # Forward details to admin
        godfather_display = user_data['godfather'] if user_data['godfather'] else "None"
        admin_message = (
            f"🔔 **NEW PAYMENT SUBMISSION** 🔔\n\n"
            f"👤 **User:** {user_data['name']} ({'@'+user_data['telegram_username'] if user_data['telegram_username'] else 'No username'})\n"
            f"🆔 **User ID:** `{user_data['user_id']}`\n"
            f"📞 **Phone:** {user_data['phone']}\n"
            f"📧 **Email:** {user_data['email']}\n"
            f"👨‍👦 **Godfather ID:** {godfather_display}\n"
            f"💳 **Method:** {user_data['payment_method'].upper()}\n"
            f"🧾 **Transaction ID:** `{user_data['transaction_id']}`\n"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f'approve_{user.id}')],
            [InlineKeyboardButton("❌ Reject", callback_data=f'reject_{user.id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=admin_message, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to save user data for {user.id} to MongoDB: {e}")
        await update.message.reply_text(get_messages(lang)['error'])
        return ConversationHandler.END
    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, user_id_str = query.data.split('_', 1)
    user_id = int(user_id_str)
    user_record = users_collection.find_one({"user_id": user_id})
    if not user_record:
        await query.edit_message_text(text=f"⚠️ Error: User with ID {user_id} not found in the database.")
        return
    lang = user_record.get('language', 'en')
    original_message = query.message.text
    if action == 'approve':
        renewal_date = calculate_renewal_date()
        update_data = {
            "status": "Approved",
            "subscription_start_date": datetime.utcnow(),
            "subscription_renewal_date": datetime.combine(renewal_date, datetime.min.time())
        }
        users_collection.update_one({"user_id": user_id}, {"$set": update_data})
        renewal_date_str = renewal_date.strftime('%d %B %Y')
        messages = get_messages(lang, renewal_date_str)
        try:
            await context.bot.send_message(chat_id=user_id, text=messages['approved_message'], parse_mode='Markdown')
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ✅ APPROVED by {query.from_user.first_name} ] ---")
        except Exception as e:
            logger.error(f"Failed to send approval message to {user_id}: {e}")
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ✅ APPROVED but user could not be notified. ] ---")
    elif action == 'reject':
        users_collection.update_one({"user_id": user_id}, {"$set": {"status": "Rejected"}})
        messages = get_messages(lang)
        try:
            await context.bot.send_message(chat_id=user_id, text=messages['rejected_message'], parse_mode='Markdown')
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ❌ REJECTED by {query.from_user.first_name} ] ---")
        except Exception as e:
            logger.error(f"Failed to send rejection message to {user_id}: {e}")
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ❌ REJECTED but user could not be notified. ] ---")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('language', 'en')
    await update.message.reply_text(get_messages(lang)['cancel'], reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- Command Handlers ---
async def renewal_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"user_id": user_id})
    if user and user.get("subscription_renewal_date"):
        renewal_date = user["subscription_renewal_date"].strftime('%d %B %Y')
        await update.message.reply_text(f"Your next renewal date is: {renewal_date}")
    else:
        await update.message.reply_text("You do not have an active subscription.")

async def referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_link = f"https://t.me/{context.bot.username}?start={user_id}"
    await update.message.reply_text(f"Your referral link is:\n{referral_link}")

async def stats_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = users_collection.count_documents({"godfather": user_id})
    await update.message.reply_text(f"You have referred {count} people.")

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"user_id": user_id})
    if user:
        info = (
            f"👤 Name: {user.get('name')}\n"
            f"📞 Phone: {user.get('phone')}\n"
            f"📧 Email: {user.get('email')}\n"
            f"👨‍👦 Godfather ID: {user.get('godfather')}\n"
            f"💳 Payment: {user.get('payment_method')}\n"
            f"🧾 Transaction ID: {user.get('transaction_id')}\n"
            f"Status: {user.get('status')}"
        )
        await update.message.reply_text(info, reply_markup=MAIN_MENU_KEYBOARD)
    else:
        await update.message.reply_text("No info found.", reply_markup=MAIN_MENU_KEYBOARD)

async def referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = users_collection.count_documents({"godfather": user_id})
    await update.message.reply_text(f"You have referred {count} people.", reply_markup=MAIN_MENU_KEYBOARD)

async def about_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *About Us*\n\nWe are a referral-based subscription service helping you earn rewards for inviting others. For more info, contact support.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KEYBOARD
    )

async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 *Contact Us*\n\nFor support, email: support@example.com or call +237 6XXXXXXXX.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KEYBOARD
    )

async def referral_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now()
    last_25th = now.replace(day=settings.RENEWAL_DAY)
    if now.day < settings.RENEWAL_DAY:
        last_25th = last_25th - relativedelta(months=1)
    period_start = last_25th.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    all_time_count = users_collection.count_documents({
        "godfather": user_id,
        "status": "Approved"
    })
    this_month_count = users_collection.count_documents({
        "godfather": user_id,
        "status": "Approved",
        "registration_date": {"$gte": period_start, "$lte": period_end}
    })
    all_time_earnings = all_time_count * settings.REFERRAL_REWARD
    this_month_earnings = this_month_count * settings.REFERRAL_REWARD
    await update.message.reply_text(
        f"💸 *Referral Earnings*\n\n"
        f"All-time: {all_time_count} referrals = {all_time_earnings} FCFA\n"
        f"This month: {this_month_count} referrals = {this_month_earnings} FCFA",
        parse_mode="Markdown"
    )

# --- Monthly Admin Report ---
async def send_monthly_referral_report(application):
    now = datetime.now()
    last_25th = now.replace(day=settings.RENEWAL_DAY)
    if now.day < settings.RENEWAL_DAY:
        last_25th = last_25th - relativedelta(months=1)
    period_start = last_25th.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    users = list(users_collection.find({}))
    godfather_map = {}
    for user in users:
        godfather = user.get("godfather")
        if godfather:
            reg_date = user.get("registration_date")
            status = user.get("status")
            if reg_date and status == "Approved" and period_start <= reg_date <= period_end:
                godfather_map.setdefault(godfather, {"count": 0, "user": None})
                godfather_map[godfather]["count"] += 1
    # Attach user info for reporting
    for godfather_id in godfather_map:
        godfather_map[godfather_id]["user"] = users_collection.find_one({"user_id": godfather_id})
    total_payout = 0
    report_lines = ["Referral Earnings Report ({} - {})".format(
        period_start.strftime("%d %b %Y"), period_end.strftime("%d %b %Y"))]
    report_lines.append("User | Referrals | Amount (FCFA)")
    report_lines.append("-" * 35)
    for godfather_id, data in godfather_map.items():
        user = data["user"]
        count = data["count"]
        amount = count * settings.REFERRAL_REWARD
        total_payout += amount
        username = user.get("telegram_username", "") if user else ""
        name = user.get("name", "") if user else str(godfather_id)
        report_lines.append(f"{name} (@{username}) | {count} | {amount}")
        # Notify user if they have earnings
        if user and amount > 0:
            try:
                await application.bot.send_message(
                    chat_id=godfather_id,
                    text=f"🎉 You earned {amount} FCFA from {count} referral(s) this month! Thank you for referring new users.",
                )
            except Exception as e:
                logger.error(f"Failed to notify user {godfather_id} of referral earnings: {e}")
    report_lines.append("-" * 35)
    report_lines.append(f"Total payout: {total_payout} FCFA")
    try:
        await application.bot.send_message(
            chat_id=settings.ADMIN_CHAT_ID,
            text="\n".join(report_lines)
        )
    except Exception as e:
        logger.error(f"Failed to send monthly referral report to admin: {e}")

def setup_scheduler(application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_monthly_referral_report,
        "cron",
        day=settings.RENEWAL_DAY,
        hour=0,
        minute=5,
        args=[application]
    )
    scheduler.start()

async def on_startup(application):
    setup_scheduler(application)

def main() -> None:
    application = Application.builder().token(settings.BOT_TOKEN).build()
    application.post_init = on_startup
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE_SELECTION: [CallbackQueryHandler(language_callback, pattern='^lang_')],
            NAME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            NUMBER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_number)],
            EMAIL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            GODFATHER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_godfather)],
            PAYMENT_METHOD: [CallbackQueryHandler(payment_callback, pattern='^payment_')],
            TRANSACTION_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transaction_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^(approve_|reject_)"))
    application.add_handler(CommandHandler("renew", renewal_info))
    application.add_handler(CommandHandler("referral", referral_info))
    application.add_handler(CommandHandler("stats", stats_info))
    application.add_handler(CommandHandler("myinfo", my_info))
    application.add_handler(CommandHandler("referralstats", referral_stats))
    application.add_handler(CommandHandler("aboutus", about_us))
    application.add_handler(CommandHandler("contactus", contact_us))
    application.add_handler(CommandHandler("referral_earnings", referral_earnings))
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

