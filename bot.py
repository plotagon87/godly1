import logging
import os
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
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# --- Configuration & Setup ---

# Load environment variables from .env file
load_dotenv()

# Configure logging for debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states for the finite state machine
(
    LANGUAGE_SELECTION,
    NAME_INPUT,
    NUMBER_INPUT,
    EMAIL_INPUT,
    GODFATHER_INPUT,
    PAYMENT_METHOD,
    TRANSACTION_ID,
) = range(7)

# --- Environment Variables & Constants ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")

EVERSEND_LINK = "https://eversend.page.link/tnB3"
SUBSCRIPTION_FEE = 5000
RENEWAL_DAY = 25  # All subscriptions renew on the 25th of the month

# Check for missing essential variables
if not all([BOT_TOKEN, ADMIN_CHAT_ID, MONGO_URI, MONGO_DB_NAME]):
    logger.critical("CRITICAL: One or more environment variables are missing. Check your .env file.")
    exit()

# --- MongoDB Integration ---

def init_mongodb():
    """Initializes and returns the MongoDB users collection."""
    try:
        client = MongoClient(MONGO_URI)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        db = client[MONGO_DB_NAME]
        logger.info("Successfully connected to MongoDB.")
        return db.users
    except ConnectionFailure as e:
        logger.error(f"MongoDB Connection Failure: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return None

# Initialize the collection globally
users_collection = init_mongodb()
if users_collection is None:
    logger.critical("Could not establish a connection to the database. The bot will exit.")
    exit()

def calculate_renewal_date() -> date:
    """Calculates the next renewal date, which is always the 25th of the next month."""
    today = date.today()
    # Move to the first day of the next month
    next_month = (today.replace(day=1) + relativedelta(months=1))
    # Set the day to the RENEWAL_DAY
    renewal_date = next_month.replace(day=RENEWAL_DAY)
    return renewal_date

# --- Bot Text & Messages ---

PAYMENT_DETAILS = {
    'mtn': {
        'fr': f"📱 **Paiement par MTN Mobile Money**\n\n" \
              f"Veuillez transférer **{SUBSCRIPTION_FEE} FCFA** au numéro suivant:\n" \
              f"Numéro: `+237 6XXXXXXXX`\n" \
              f"Nom: `NOM DU BÉNÉFICIAIRE`\n\n" \
              f"Après le paiement, revenez ici et envoyez l'ID de la transaction pour vérification.",
        'en': f"📱 **MTN Mobile Money Payment**\n\n" \
              f"Please transfer **{SUBSCRIPTION_FEE} FCFA** to the following number:\n" \
              f"Number: `+237 6XXXXXXXX`\n" \
              f"Name: `RECIPIENT NAME`\n\n" \
              f"After payment, come back here and send the Transaction ID for verification."
    },
    'orange': {
        'fr': f"🍊 **Paiement par Orange Money**\n\n" \
              f"Veuillez transférer **{SUBSCRIPTION_FEE} FCFA** au numéro suivant:\n" \
              f"Numéro: `+237 6XXXXXXXX`\n" \
              f"Nom: `NOM DU BÉNÉFICIAIRE`\n\n" \
              f"Après le paiement, revenez ici et envoyez l'ID de la transaction pour vérification.",
        'en': f"🍊 **Orange Money Payment**\n\n" \
              f"Please transfer **{SUBSCRIPTION_FEE} FCFA** to the following number:\n" \
              f"Number: `+237 6XXXXXXXX`\n" \
              f"Name: `RECIPIENT NAME`\n\n" \
              f"After payment, come back here and send the Transaction ID for verification."
    }
}

def get_messages(lang, renewal_date_str=""):
    """Returns a dictionary of all messages in the specified language."""
    # The user-provided text for after approval
    post_approval_fr = (
        "Vous recevrez une somme de 2000 FCFA chaque fois qu’un nouveau compte est créé et une somme global lorsque les différents "
        "individus parrainés par vous paie leurs abonnements de 5000 FCFA à la fin du mois ( 25 de chaque mois ).\n\n"
        "Tout les payment sont fait le 25 de chaque mois et les comptes qui manqueront de payer seront automatiquement supprimés.\n\n"
        "Profitez au maximum de notre service de parrainage et gagnez plus grâce à l’achat et la revente des crypto sur votre portefeuille Eversend."
    )
    post_approval_en = (
        "You will receive a sum of 2000 FCFA each time a new account is created and a global amount when the different individuals "
        "sponsored by you pay their subscriptions of 5000 FCFA at the end of the month (25th of each month).\n\n"
        "All payments are made on the 25th of each month and accounts that fail to pay will be automatically deleted.\n\n"
        "Make the most of our referral service and earn more by buying and reselling crypto on your Eversend wallet."
    )
    
    return {
        'welcome': "🎉 Welcome to our referral system! / Bienvenue dans notre système de parrainage!\n\n" \
                   "Please choose your language / Choisissez votre langue:",
        'ask_name': {'fr': "📝 Entrez votre nom complet:", 'en': "📝 Please enter your full name:"}[lang],
        'ask_number': {'fr': "📞 Entrez votre numéro de téléphone (Ex: 67...):", 'en': "📞 Please enter your phone number (e.g., 67...):"}[lang],
        'ask_email': {'fr': "📧 Entrez votre adresse e-mail:", 'en': "📧 Please enter your email address:"}[lang],
        'ask_godfather': {'fr': "👨‍👦 Entrez le nom d'utilisateur Telegram de votre parrain (ou envoyez 'skip' si vous n'en avez pas):", 'en': "👨‍👦 Please enter your godfather's Telegram username (or send 'skip' if you don't have one):"}[lang],
        'choose_payment': {'fr': f"✅ Informations enregistrées ! Pour activer votre compte, veuillez payer les frais d'abonnement de **{SUBSCRIPTION_FEE} FCFA**. Choisissez votre mode de paiement :", 'en': f"✅ Information saved! To activate your account, please pay the **{SUBSCRIPTION_FEE} FCFA** subscription fee. Choose your payment method:"}[lang],
        'pending_approval': {'fr': "⏳ Votre paiement est en cours de vérification. Vous recevrez une notification de l'administrateur très bientôt.", 'en': "⏳ Your payment is being verified. You will receive a notification from the admin very soon."}[lang],
        'approved_message': {
            'fr': f"✅ **Félicitations ! Votre compte est approuvé.**\n\n"
                  f"Votre prochain renouvellement est le **{renewal_date_str}**.\n\n"
                  f"🔗 Voici votre lien pour recevoir vos gains :\n{EVERSEND_LINK}\n\n"
                  f"**Règles de Parrainage :**\n{post_approval_fr}",
            'en': f"✅ **Congratulations! Your account has been approved.**\n\n"
                  f"Your next renewal is on **{renewal_date_str}**.\n\n"
                  f"🔗 Here is your link to receive your earnings:\n{EVERSEND_LINK}\n\n"
                  f"**Referral Rules:**\n{post_approval_en}"
        }[lang],
        'rejected_message': {'fr': "❌ **Paiement Refusé**\n\nDésolé, votre paiement n'a pas pu être vérifié. Veuillez vérifier les détails de la transaction et contacter un administrateur si vous pensez qu'il s'agit d'une erreur.", 'en': "❌ **Payment Rejected**\n\nSorry, your payment could not be verified. Please check the transaction details and contact an admin if you believe this is an error."}[lang],
        'cancel': {'fr': "❌ Inscription annulée. Tapez /start pour recommencer.", 'en': "❌ Registration cancelled. Type /start to begin again."}[lang],
        'error': {'fr': "❌ Une erreur de base de données s'est produite. Veuillez réessayer ou contacter un administrateur.", 'en': "❌ A database error occurred. Please try again or contact an admin."}[lang]
    }

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["My Info", "Referral Stats"],
        ["About Us", "Contact Us"]
    ],
    resize_keyboard=True
)

# --- Conversation Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks for language selection."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    
    # Check if user is already in the database
    existing_user = users_collection.find_one({"user_id": user.id})
    if existing_user and existing_user.get('status') == 'Approved':
        lang = existing_user.get('language', 'en')
        renewal_date = existing_user.get('subscription_renewal_date').strftime('%d %B %Y')
        await update.message.reply_text({
            'fr': f"👋 Re-bonjour! Votre compte est déjà actif. Votre prochain renouvellement est le {renewal_date}.",
            'en': f"👋 Welcome back! Your account is already active. Your next renewal date is {renewal_date}."
        }[lang])
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data='lang_fr')],
        [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_messages('en', '')['welcome'], reply_markup=reply_markup)
    return LANGUAGE_SELECTION

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the selected language and asks for the user's name."""
    query = update.callback_query
    await query.answer()
    lang = query.data.split('_')[1]
    context.user_data['language'] = lang
    messages = get_messages(lang)
    await query.edit_message_text(text=messages['ask_name'])
    return NAME_INPUT

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the name and asks for the phone number."""
    context.user_data['name'] = update.message.text.strip()
    lang = context.user_data['language']
    await update.message.reply_text(get_messages(lang)['ask_number'])
    return NUMBER_INPUT

async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the phone number and asks for the email."""
    context.user_data['phone'] = update.message.text.strip()
    lang = context.user_data['language']
    await update.message.reply_text(get_messages(lang)['ask_email'])
    return EMAIL_INPUT

async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the email and asks for the godfather."""
    context.user_data['email'] = update.message.text.strip().lower()
    lang = context.user_data['language']
    await update.message.reply_text(get_messages(lang)['ask_godfather'])
    return GODFATHER_INPUT

async def handle_godfather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the godfather and asks for payment method."""
    godfather_input = update.message.text.strip()
    context.user_data['godfather'] = 'None' if godfather_input.lower() == 'skip' else godfather_input
    lang = context.user_data['language']
    
    keyboard = [
        [InlineKeyboardButton("📱 MTN Mobile Money", callback_data='payment_mtn')],
        [InlineKeyboardButton("🍊 Orange Money", callback_data='payment_orange')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_messages(lang)['choose_payment'], reply_markup=reply_markup, parse_mode='Markdown')
    return PAYMENT_METHOD

async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows payment instructions based on selection."""
    query = update.callback_query
    await query.answer()
    payment_method = query.data.split('_')[1]
    context.user_data['payment_method'] = payment_method
    lang = context.user_data['language']
    
    instructions = PAYMENT_DETAILS[payment_method][lang]
    await query.edit_message_text(text=instructions, parse_mode='Markdown')
    return TRANSACTION_ID

async def handle_transaction_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves all user data to DB and forwards to admin."""
    user = update.effective_user
    context.user_data['transaction_id'] = update.message.text.strip()
    lang = context.user_data['language']

    # Prepare data for MongoDB
    user_data = {
        "user_id": user.id,
        "telegram_id": user.id,  # <-- Add this line
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
        # Use update_one with upsert=True to create or update the record
        users_collection.update_one(
            {"user_id": user.id},
            {"$set": user_data},
            upsert=True
        )
        logger.info(f"User data for {user.id} saved/updated in MongoDB.")

        # Notify user
        await update.message.reply_text(
            get_messages(lang)['pending_approval'],
            reply_markup=MAIN_MENU_KEYBOARD
        )

        # Forward details to admin
        admin_message = (
            f"🔔 **NOUVELLE SOUMISSION DE PAIEMENT** 🔔\n\n"
            f"👤 **Utilisateur:** {user_data['name']} (@{user_data['telegram_username']})\n"
            f"🆔 **ID Utilisateur:** `{user_data['user_id']}`\n"
            f"📞 **Téléphone:** {user_data['phone']}\n"
            f"📧 **Email:** {user_data['email']}\n"
            f"👨‍👦 **Parrain:** {user_data['godfather']}\n"
            f"💳 **Méthode:** {user_data['payment_method'].upper()}\n"
            f"🧾 **ID Transaction:** `{user_data['transaction_id']}`\n"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Approuver", callback_data=f'approve_{user.id}')],
            [InlineKeyboardButton("❌ Rejeter", callback_data=f'reject_{user.id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Failed to save user data for {user.id} to MongoDB: {e}")
        await update.message.reply_text(get_messages(lang)['error'])
        return ConversationHandler.END

    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles admin approval/rejection from inline buttons."""
    query = update.callback_query
    await query.answer()
    
    action, user_id_str = query.data.split('_', 1)
    user_id = int(user_id_str)
    
    user_record = users_collection.find_one({"user_id": user_id})
    if not user_record:
        await query.edit_message_text(text=f"⚠️ Erreur: Utilisateur avec ID {user_id} non trouvé dans la base de données.")
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
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ✅ APPROUVÉ par {query.from_user.first_name} ] ---")
        except Exception as e:
            logger.error(f"Failed to send approval message to {user_id}: {e}")
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ✅ APPROUVÉ mais l'utilisateur n'a pas pu être notifié. ] ---")

    elif action == 'reject':
        users_collection.update_one({"user_id": user_id}, {"$set": {"status": "Rejected"}})
        messages = get_messages(lang)
        try:
            await context.bot.send_message(chat_id=user_id, text=messages['rejected_message'], parse_mode='Markdown')
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ❌ REJETÉ par {query.from_user.first_name} ] ---")
        except Exception as e:
            logger.error(f"Failed to send rejection message to {user_id}: {e}")
            await query.edit_message_text(text=f"{original_message}\n\n--- [ ❌ REJETÉ mais l'utilisateur n'a pas pu être notifié. ] ---")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    lang = context.user_data.get('language', 'en')
    await update.message.reply_text(get_messages(lang)['cancel'], reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

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
    count = users_collection.count_documents({"godfather": str(user_id)})
    await update.message.reply_text(f"You have referred {count} people.")

async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"user_id": user_id})
    if user:
        info = (
            f"👤 Name: {user.get('name')}\n"
            f"📞 Phone: {user.get('phone')}\n"
            f"📧 Email: {user.get('email')}\n"
            f"👨‍👦 Godfather: {user.get('godfather')}\n"
            f"💳 Payment: {user.get('payment_method')}\n"
            f"🧾 Transaction ID: {user.get('transaction_id')}\n"
            f"Status: {user.get('status')}"
        )
        await update.message.reply_text(info, reply_markup=MAIN_MENU_KEYBOARD)
    else:
        await update.message.reply_text("No info found.", reply_markup=MAIN_MENU_KEYBOARD)

async def referral_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = users_collection.count_documents({"godfather": str(user_id)})
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

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

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
        fallbacks=[]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("renew", renewal_info))
    application.add_handler(CommandHandler("referral", referral_info))
    application.add_handler(CommandHandler("stats", stats_info))
    application.add_handler(MessageHandler(filters.Regex("^My Info$"), my_info))
    application.add_handler(MessageHandler(filters.Regex("^Referral Stats$"), referral_stats))
    application.add_handler(MessageHandler(filters.Regex("^About Us$"), about_us))
    application.add_handler(MessageHandler(filters.Regex("^Contact Us$"), contact_us))

    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

