"""
Message handlers for LEEH Exchange Bot
Contains all bot command and message handlers
"""

import logging
import os
from datetime import datetime
from telebot import types
from telebot.types import InputFile
from config import (
    WALLETS, ADMIN_ID, BANK_DETAILS, WELCOME_MESSAGE,
    BACK_BUTTON_TEXT, BUY_BUTTON_TEXT, SELL_BUTTON_TEXT
)
from services import get_crypto_price, format_price, validate_amount, format_order_details
from utils import (
    create_main_keyboard, create_coin_selection_keyboard, create_back_keyboard,
    create_network_keyboard, clear_user_state, get_user_state, set_user_state, escape_markdown
)
from csv_handler import initialize_csv, log_order, format_user_orders, create_user_orders_file
from vtpass_service import (
    calculate_data_price, verify_phone_number, purchase_airtime, 
    purchase_data, get_data_plans, format_data_plans_display
)

logger = logging.getLogger(__name__)

def setup_handlers(bot, user_state):
    """
    Setup all message handlers for the bot
    
    Args:
        bot: Telegram bot instance
        user_state (dict): User state storage
    """
    
    # Initialize CSV file on startup
    initialize_csv()
    
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        """Handle /start command"""
        try:
            chat_id = message.chat.id
            clear_user_state(user_state, chat_id)
            
            # Check if user is the admin to show the admin dashboard button
            is_admin = str(chat_id) == str(ADMIN_ID)
            
            # Explicitly log the check for debugging
            logger.info(f"Start command from {chat_id}. Admin ID is {ADMIN_ID}. is_admin: {is_admin}")
            
            markup = create_main_keyboard(is_admin=is_admin)
            
            bot.send_message(
                chat_id,
                WELCOME_MESSAGE,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
            # If admin, also send a welcoming inline message for quick access
            if is_admin:
                web_app_url = f"https://{os.getenv('REPLIT_DEV_DOMAIN')}"
                inline_markup = types.InlineKeyboardMarkup()
                inline_markup.add(types.InlineKeyboardButton("🚀 Launch Admin Center", web_app=types.WebAppInfo(url=web_app_url)))
                
                bot.send_message(
                    chat_id,
                    "👑 **Hello Hamzah!**\nYour admin tools are ready. You can access the dashboard using the persistent button on your keyboard or the link below.",
                    reply_markup=inline_markup,
                    parse_mode='Markdown'
                )
            
            logger.info(f"User {chat_id} started the bot")
        except Exception as e:
            logger.error(f"Error in start handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(commands=['myorders'])
    def handle_my_orders(message):
        """Handle /myorders command"""
        try:
            user_id = message.from_user.id
            orders_text = format_user_orders(user_id)
            
            bot.send_message(
                message.chat.id,
                orders_text,
                parse_mode='Markdown'
            )
            logger.info(f"User {user_id} requested order history")
        except Exception as e:
            logger.error(f"Error in myorders handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong retrieving your orders.")

    @bot.message_handler(commands=['downloadorders'])
    def handle_download_orders(message):
        """Handle /downloadorders command"""
        try:
            user_id = message.from_user.id
            filename = create_user_orders_file(user_id)
            
            if filename and os.path.exists(filename):
                with open(filename, 'rb') as doc:
                    bot.send_document(
                        message.chat.id,
                        doc,
                        caption="📥 Your complete order history"
                    )
                os.remove(filename)
                logger.info(f"User {user_id} downloaded order history")
            else:
                bot.send_message(
                    message.chat.id,
                    "❌ Unable to generate your order file. Please try again."
                )
        except Exception as e:
            logger.error(f"Error in download orders handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong creating your order file.")

    @bot.message_handler(func=lambda msg: msg.text == "📋 My Orders")
    def handle_my_orders_button(message):
        """Handle My Orders button press"""
        handle_my_orders(message)

    @bot.message_handler(func=lambda msg: msg.text == "📥 Download Orders")
    def handle_download_orders_button(message):
        """Handle Download Orders button press"""
        handle_download_orders(message)

    @bot.message_handler(func=lambda msg: msg.text == "📱 Buy Airtime")
    def handle_buy_airtime(message):
        """Handle Buy Airtime button press"""
        try:
            chat_id = message.chat.id
            set_user_state(user_state, chat_id, {"mode": "airtime", "step": "select_network"})
            
            markup = create_network_keyboard()
            bot.send_message(
                chat_id,
                "📱 **Airtime Top-up**\n\nSelect your network provider:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            logger.info(f"User {chat_id} started airtime purchase")
        except Exception as e:
            logger.error(f"Error in buy airtime handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(func=lambda msg: msg.text == "📶 Buy Data")
    def handle_buy_data(message):
        """Handle Buy Data button press"""
        try:
            chat_id = message.chat.id
            set_user_state(user_state, chat_id, {"mode": "data", "step": "select_network"})
            
            markup = create_network_keyboard()
            bot.send_message(
                chat_id,
                "📶 **Data Bundle Purchase**\n\nSelect your network provider:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            logger.info(f"User {chat_id} started data purchase")
        except Exception as e:
            logger.error(f"Error in buy data handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(func=lambda msg: msg.text in ["MTN", "Airtel", "Glo", "9mobile"])
    def handle_network_selection(message):
        """Handle network selection for airtime/data"""
        try:
            chat_id = message.chat.id
            network = message.text
            state = get_user_state(user_state, chat_id)
            mode = state.get("mode")
            
            if not mode or state.get("step") != "select_network":
                return
            
            set_user_state(user_state, chat_id, {"network": network})
            
            if mode == "airtime":
                set_user_state(user_state, chat_id, {"step": "enter_amount"})
                markup = create_back_keyboard()
                bot.send_message(
                    chat_id,
                    f"📱 **{network} Airtime**\n\n"
                    f"Enter the airtime amount (₦):\n"
                    f"Example: 100, 200, 500, 1000",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            elif mode == "data":
                set_user_state(user_state, chat_id, {"step": "enter_data_size"})
                markup = create_back_keyboard()
                bot.send_message(
                    chat_id,
                    f"📶 **{network} Data Bundle**\n\n"
                    f"Enter data size in MB:\n"
                    f"Example: 500 (for 500MB), 1024 (for 1GB), 2048 (for 2GB)",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            
            logger.info(f"User {chat_id} selected {network} for {mode}")
            
        except Exception as e:
            logger.error(f"Error in network selection handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(func=lambda msg: msg.text == BUY_BUTTON_TEXT)
    def handle_buy(message):
        """Handle Buy button press"""
        try:
            chat_id = message.chat.id
            set_user_state(user_state, chat_id, {"mode": "buy", "step": "select_coin"})
            
            markup = create_coin_selection_keyboard()
            bot.send_message(
                chat_id,
                "💰 **Which cryptocurrency would you like to buy?**\n\nSelect from the options below:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            logger.info(f"User {chat_id} entered buy mode")
        except Exception as e:
            logger.error(f"Error in buy handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(func=lambda msg: msg.text == SELL_BUTTON_TEXT)
    def handle_sell(message):
        """Handle Sell button press"""
        try:
            chat_id = message.chat.id
            set_user_state(user_state, chat_id, {"mode": "sell", "step": "select_coin"})
            
            markup = create_coin_selection_keyboard()
            bot.send_message(
                chat_id,
                "💸 **Which cryptocurrency would you like to sell?**\n\nSelect from the options below:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            logger.info(f"User {chat_id} entered sell mode")
        except Exception as e:
            logger.error(f"Error in sell handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(func=lambda msg: msg.text in WALLETS.keys())
    def handle_coin_selection(message):
        """Handle cryptocurrency selection"""
        try:
            chat_id = message.chat.id
            coin = message.text.upper()
            state = get_user_state(user_state, chat_id)
            mode = state.get("mode")
            
            if not mode:
                return
            
            # Get current price
            price = get_crypto_price(coin)
            formatted_price = format_price(price)
            
            if mode == "buy":
                set_user_state(user_state, chat_id, {
                    "coin": coin,
                    "step": "amount",
                    "price": price
                })
                
                markup = create_back_keyboard()
                bot.send_message(
                    chat_id,
                    f"💰 **{coin} Purchase**\n\n"
                    f"💵 Current Price: **{formatted_price}**\n\n"
                    f"Please enter the amount of **{coin}** you want to buy:",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                
            elif mode == "sell":
                wallet_address = WALLETS[coin]
                set_user_state(user_state, chat_id, {
                    "coin": coin,
                    "step": "amount_sent",
                    "price": price
                })
                
                markup = create_back_keyboard()
                bot.send_message(
                    chat_id,
                    f"💸 **{coin} Sale**\n\n"
                    f"💵 Current Price: **{formatted_price}**\n\n"
                    f"📧 Send your **{coin}** to this address:\n"
                    f"`{wallet_address}`\n\n"
                    f"After sending, enter the amount you sent:",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            
            logger.info(f"User {chat_id} selected {coin} for {mode}")
            
        except Exception as e:
            logger.error(f"Error in coin selection handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(func=lambda msg: msg.text == BACK_BUTTON_TEXT)
    def handle_back(message):
        """Handle Back button press"""
        try:
            chat_id = message.chat.id
            state = get_user_state(user_state, chat_id)
            step = state.get("step")
            
            if step == "select_coin":
                # Go back to main menu
                handle_start(message)
            elif step in ["amount", "amount_sent"]:
                # Go back to coin selection
                mode = state.get("mode")
                if mode == "buy":
                    handle_buy(message)
                elif mode == "sell":
                    handle_sell(message)
            else:
                # Default: go to main menu
                handle_start(message)
                
            logger.info(f"User {chat_id} pressed back button")
            
        except Exception as e:
            logger.error(f"Error in back handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

    @bot.message_handler(content_types=['text', 'photo'])
    def handle_all_messages(message):
        """Handle all other text and photo messages"""
        try:
            chat_id = message.chat.id
            state = get_user_state(user_state, chat_id)
            
            if not state:
                # No active state, redirect to start
                handle_start(message)
                return
            
            mode = state.get("mode")
            step = state.get("step")
            
            if mode == "buy":
                handle_buy_flow(bot, message, state, user_state)
            elif mode == "sell":
                handle_sell_flow(bot, message, state, user_state)
            elif mode == "airtime":
                handle_airtime_flow(bot, message, state, user_state)
            elif mode == "data":
                handle_data_flow(bot, message, state, user_state)
            else:
                # Unknown state, redirect to start
                handle_start(message)
                
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            bot.send_message(message.chat.id, "❌ Sorry, something went wrong. Please try again.")

def handle_buy_flow(bot, message, state, user_state):
    """Handle buy transaction flow"""
    chat_id = message.chat.id
    step = state.get("step")
    
    try:
        if step == "amount":
            # Validate amount
            if not validate_amount(message.text):
                bot.send_message(
                    chat_id,
                    "❌ **Invalid amount!**\n\n"
                    "Please enter a valid positive number:",
                    parse_mode='Markdown'
                )
                return
            
            set_user_state(user_state, chat_id, {
                "amount": message.text,
                "step": "wallet"
            })
            
            markup = create_back_keyboard()
            bot.send_message(
                chat_id,
                f"🏦 **Wallet Address Required**\n\n"
                f"Please enter your **{state.get('coin')}** wallet address to receive the cryptocurrency:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        elif step == "wallet":
            set_user_state(user_state, chat_id, {
                "wallet": message.text,
                "step": "awaiting_proof"
            })
            
            markup = create_back_keyboard()
            bot.send_message(
                chat_id,
                BANK_DETAILS,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        elif step == "awaiting_proof" and message.content_type == 'photo':
            # Process payment proof
            current_state = get_user_state(user_state, chat_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            order_data = {
                'coin': current_state.get('coin'),
                'amount': current_state.get('amount'),
                'wallet': current_state.get('wallet'),
                'username': message.from_user.username or 'N/A',
                'user_id': chat_id,
                'price': current_state.get('price')
            }
            
            # Log order to CSV
            log_order(
                user_id=chat_id,
                username=message.from_user.username or 'NoUsername',
                order_type='Buy',
                coin=current_state.get('coin'),
                amount=current_state.get('amount'),
                wallet_or_bank=current_state.get('wallet'),
                timestamp=timestamp
            )
            
            # Send to admin with photo
            caption = format_order_details(order_data, "buy")
            
            try:
                bot.send_photo(
                    ADMIN_ID,
                    message.photo[-1].file_id,
                    caption=caption,
                    parse_mode='Markdown'
                )
                
                bot.send_message(
                    chat_id,
                    "✅ **Payment Proof Received!**\n\n"
                    "Your buy order has been submitted successfully. "
                    "Our team will process your transaction shortly.\n\n"
                    "Thank you for using LEEH Exchange! 🚀",
                    reply_markup=create_main_keyboard(),
                    parse_mode='Markdown'
                )
                
                clear_user_state(user_state, chat_id)
                logger.info(f"Buy order completed for user {chat_id}")
                
            except Exception as e:
                logger.error(f"Failed to send order to admin: {e}")
                bot.send_message(
                    chat_id,
                    "❌ **Error processing your order.**\n\n"
                    "Please try again or contact support.",
                    parse_mode='Markdown'
                )
                
        elif step == "awaiting_proof" and message.content_type != 'photo':
            bot.send_message(
                chat_id,
                "📸 **Payment Proof Required**\n\n"
                "Please upload a screenshot of your payment as proof.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in buy flow: {e}")
        bot.send_message(chat_id, "❌ Sorry, something went wrong. Please try again.")

def handle_sell_flow(bot, message, state, user_state):
    """Handle sell transaction flow"""
    chat_id = message.chat.id
    step = state.get("step")
    
    try:
        if step == "amount_sent":
            # Validate amount
            if not validate_amount(message.text):
                bot.send_message(
                    chat_id,
                    "❌ **Invalid amount!**\n\n"
                    "Please enter a valid positive number:",
                    parse_mode='Markdown'
                )
                return
            
            set_user_state(user_state, chat_id, {
                "amount": message.text,
                "step": "bank_details"
            })
            
            markup = create_back_keyboard()
            bot.send_message(
                chat_id,
                "🏦 **Bank Details Required**\n\n"
                "Please provide your bank details for payment:\n"
                "• Bank Name\n"
                "• Account Number\n"
                "• Account Holder Name\n\n"
                "Format: Bank Name, Account Number, Full Name",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        elif step == "bank_details":
            current_state = get_user_state(user_state, chat_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            order_data = {
                'coin': current_state.get('coin'),
                'amount': current_state.get('amount'),
                'bank_details': message.text,
                'username': message.from_user.username or 'N/A',
                'user_id': chat_id,
                'price': current_state.get('price')
            }
            
            # Log order to CSV
            log_order(
                user_id=chat_id,
                username=message.from_user.username or 'NoUsername',
                order_type='Sell',
                coin=current_state.get('coin'),
                amount=current_state.get('amount'),
                wallet_or_bank=message.text,
                timestamp=timestamp
            )
            
            # Send to admin
            caption = format_order_details(order_data, "sell")
            
            try:
                bot.send_message(
                    ADMIN_ID,
                    caption,
                    parse_mode='Markdown'
                )
                
                bot.send_message(
                    chat_id,
                    "✅ **Sell Order Submitted!**\n\n"
                    "Your sell request has been received successfully. "
                    "Payment will be processed to your provided bank account shortly.\n\n"
                    "Thank you for using LEEH Exchange! 🚀",
                    reply_markup=create_main_keyboard(),
                    parse_mode='Markdown'
                )
                
                clear_user_state(user_state, chat_id)
                logger.info(f"Sell order completed for user {chat_id}")
                
            except Exception as e:
                logger.error(f"Failed to send sell order to admin: {e}")
                bot.send_message(
                    chat_id,
                    "❌ **Error processing your order.**\n\n"
                    "Please try again or contact support.",
                    parse_mode='Markdown'
                )
                
    except Exception as e:
        logger.error(f"Error in sell flow: {e}")
        bot.send_message(chat_id, "❌ Sorry, something went wrong. Please try again.")

def handle_airtime_flow(bot, message, state, user_state):
    """Handle airtime purchase flow"""
    chat_id = message.chat.id
    step = state.get("step")
    
    try:
        if step == "enter_amount":
            # Validate amount
            try:
                amount = int(message.text)
                if amount < 50 or amount > 10000:
                    bot.send_message(
                        chat_id,
                        "❌ **Invalid amount!**\n\n"
                        "Amount must be between ₦50 and ₦10,000",
                        parse_mode='Markdown'
                    )
                    return
                
                set_user_state(user_state, chat_id, {
                    "amount": amount,
                    "step": "enter_phone"
                })
                
                markup = create_back_keyboard()
                bot.send_message(
                    chat_id,
                    f"📞 **Phone Number**\n\n"
                    f"Enter the phone number to recharge:\n"
                    f"Format: 08012345678 or 2348012345678",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(
                    chat_id,
                    "❌ **Invalid amount!**\n\n"
                    "Please enter a valid number (e.g., 100, 500, 1000)",
                    parse_mode='Markdown'
                )
                
        elif step == "enter_phone":
            phone = message.text.strip()
            current_state = get_user_state(user_state, chat_id)
            network = current_state.get("network")
            amount = current_state.get("amount")
            
            # Basic phone validation
            if not phone.isdigit() or len(phone) < 10:
                bot.send_message(
                    chat_id,
                    "❌ **Invalid phone number!**\n\n"
                    "Please enter a valid phone number",
                    parse_mode='Markdown'
                )
                return
            
            set_user_state(user_state, chat_id, {
                "phone": phone,
                "step": "awaiting_proof"
            })
            
            markup = create_back_keyboard()
            bot.send_message(
                chat_id,
                f"✅ **Airtime Order Summary**\n\n"
                f"📱 Network: **{network}**\n"
                f"📞 Phone: **{phone}**\n"
                f"💰 Amount: **₦{amount:,}**\n\n"
                f"💳 **Payment Instructions:**\n"
                f"Send payment to:\n"
                f"🏦 Bank: **Opay**\n"
                f"🔢 Account: **8148842778**\n"
                f"👤 Name: **Abdulrofih Abdullah Hamzah**\n\n"
                f"📸 Upload payment screenshot to proceed:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        elif step == "awaiting_proof" and message.content_type == 'photo':
            current_state = get_user_state(user_state, chat_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Log order to CSV
            log_order(
                user_id=chat_id,
                username=message.from_user.username or 'NoUsername',
                order_type='Airtime',
                coin=current_state.get('network'),
                amount=f"₦{current_state.get('amount'):,}",
                wallet_or_bank=current_state.get('phone'),
                timestamp=timestamp
            )
            
            # Send to admin
            caption = (
                f"📱 **New Airtime Order**\n\n"
                f"👤 User: @{message.from_user.username or 'N/A'} ({chat_id})\n"
                f"📱 Network: {current_state.get('network')}\n"
                f"📞 Phone: {current_state.get('phone')}\n"
                f"💰 Amount: ₦{current_state.get('amount'):,}\n"
                f"⏰ Time: {timestamp}"
            )
            
            bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id,
                caption=caption,
                parse_mode='Markdown'
            )
            
            bot.send_message(
                chat_id,
                "✅ **Payment Received!**\n\n"
                "Your airtime order has been submitted successfully. "
                "Your phone will be recharged shortly.\n\n"
                "Thank you for using LEEH Exchange! 🚀",
                reply_markup=create_main_keyboard(),
                parse_mode='Markdown'
            )
            
            clear_user_state(user_state, chat_id)
            logger.info(f"Airtime order completed for user {chat_id}")
            
        elif step == "awaiting_proof" and message.content_type != 'photo':
            bot.send_message(
                chat_id,
                "📸 **Payment Proof Required**\n\n"
                "Please upload a screenshot of your payment as proof.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in airtime flow: {e}")
        bot.send_message(chat_id, "❌ Sorry, something went wrong. Please try again.")

def handle_data_flow(bot, message, state, user_state):
    """Handle data purchase flow"""
    chat_id = message.chat.id
    step = state.get("step")
    
    try:
        if step == "enter_data_size":
            # Validate data size
            try:
                size_mb = int(message.text)
                if size_mb < 50 or size_mb > 50000:
                    bot.send_message(
                        chat_id,
                        "❌ **Invalid data size!**\n\n"
                        "Data size must be between 50MB and 50GB (50000MB)",
                        parse_mode='Markdown'
                    )
                    return
                
                # Calculate price
                price = calculate_data_price(size_mb)
                
                set_user_state(user_state, chat_id, {
                    "data_size": size_mb,
                    "price": price,
                    "step": "enter_phone"
                })
                
                markup = create_back_keyboard()
                bot.send_message(
                    chat_id,
                    f"📞 **Phone Number**\n\n"
                    f"📦 Data Size: **{size_mb}MB**\n"
                    f"💰 Price: **₦{price:,}**\n\n"
                    f"Enter the phone number to receive data:\n"
                    f"Format: 08012345678 or 2348012345678",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                
            except ValueError:
                bot.send_message(
                    chat_id,
                    "❌ **Invalid data size!**\n\n"
                    "Please enter a valid number in MB (e.g., 500, 1024, 2048)",
                    parse_mode='Markdown'
                )
                
        elif step == "enter_phone":
            phone = message.text.strip()
            current_state = get_user_state(user_state, chat_id)
            network = current_state.get("network")
            data_size = current_state.get("data_size")
            price = current_state.get("price")
            
            # Basic phone validation
            if not phone.isdigit() or len(phone) < 10:
                bot.send_message(
                    chat_id,
                    "❌ **Invalid phone number!**\n\n"
                    "Please enter a valid phone number",
                    parse_mode='Markdown'
                )
                return
            
            set_user_state(user_state, chat_id, {
                "phone": phone,
                "step": "awaiting_proof"
            })
            
            markup = create_back_keyboard()
            bot.send_message(
                chat_id,
                f"✅ **Data Order Summary**\n\n"
                f"📶 Network: **{network}**\n"
                f"📞 Phone: **{phone}**\n"
                f"📦 Data Size: **{data_size}MB**\n"
                f"💰 Amount: **₦{price:,}**\n\n"
                f"💳 **Payment Instructions:**\n"
                f"Send payment to:\n"
                f"🏦 Bank: **Opay**\n"
                f"🔢 Account: **8148842778**\n"
                f"👤 Name: **Abdulrofih Abdullah Hamzah**\n\n"
                f"📸 Upload payment screenshot to proceed:",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        elif step == "awaiting_proof" and message.content_type == 'photo':
            current_state = get_user_state(user_state, chat_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Log order to CSV
            log_order(
                user_id=chat_id,
                username=message.from_user.username or 'NoUsername',
                order_type='Data',
                coin=current_state.get('network'),
                amount=f"{current_state.get('data_size')}MB - ₦{current_state.get('price'):,}",
                wallet_or_bank=current_state.get('phone'),
                timestamp=timestamp
            )
            
            # Send to admin
            caption = (
                f"📶 **New Data Order**\n\n"
                f"👤 User: @{message.from_user.username or 'N/A'} ({chat_id})\n"
                f"📶 Network: {current_state.get('network')}\n"
                f"📞 Phone: {current_state.get('phone')}\n"
                f"📦 Size: {current_state.get('data_size')}MB\n"
                f"💰 Amount: ₦{current_state.get('price'):,}\n"
                f"⏰ Time: {timestamp}"
            )
            
            bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id,
                caption=caption,
                parse_mode='Markdown'
            )
            
            bot.send_message(
                chat_id,
                "✅ **Payment Received!**\n\n"
                "Your data order has been submitted successfully. "
                "Data will be sent to your phone shortly.\n\n"
                "Thank you for using LEEH Exchange! 🚀",
                reply_markup=create_main_keyboard(),
                parse_mode='Markdown'
            )
            
            clear_user_state(user_state, chat_id)
            logger.info(f"Data order completed for user {chat_id}")
            
        elif step == "awaiting_proof" and message.content_type != 'photo':
            bot.send_message(
                chat_id,
                "📸 **Payment Proof Required**\n\n"
                "Please upload a screenshot of your payment as proof.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in data flow: {e}")
        bot.send_message(chat_id, "❌ Sorry, something went wrong. Please try again.")
