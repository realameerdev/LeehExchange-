"""
Utility functions for LEEH Exchange Bot
Contains helper functions for creating keyboards and managing user states
"""

from telebot import types
from config import WALLETS, BACK_BUTTON_TEXT, BUY_BUTTON_TEXT, SELL_BUTTON_TEXT

def create_main_keyboard(is_admin=False):
    """
    Create the main menu keyboard with Buy/Sell options, telecom services, and order tracking
    
    Returns:
        types.ReplyKeyboardMarkup: Main menu keyboard
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(BUY_BUTTON_TEXT, SELL_BUTTON_TEXT)
    markup.row("📱 Buy Airtime", "📶 Buy Data")
    markup.row("📋 My Orders", "📥 Download Orders")
    
    if is_admin:
        # Web App URL using the dev domain
        web_app_url = f"https://{os.getenv('REPLIT_DEV_DOMAIN')}"
        markup.row(types.KeyboardButton("🔓 Open Admin Dashboard", web_app=types.WebAppInfo(url=web_app_url)))
        
    return markup

def create_network_keyboard():
    """
    Create keyboard for network selection
    
    Returns:
        types.ReplyKeyboardMarkup: Network selection keyboard
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("MTN", "Airtel")
    markup.row("Glo", "9mobile")
    markup.row(BACK_BUTTON_TEXT)
    return markup

def create_coin_selection_keyboard():
    """
    Create keyboard for coin selection
    
    Returns:
        types.ReplyKeyboardMarkup: Coin selection keyboard
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Add coins in pairs for better layout
    coins = list(WALLETS.keys())
    for i in range(0, len(coins), 2):
        if i + 1 < len(coins):
            markup.row(coins[i], coins[i + 1])
        else:
            markup.row(coins[i])
    
    markup.row(BACK_BUTTON_TEXT)
    return markup

def create_back_keyboard():
    """
    Create keyboard with just a back button
    
    Returns:
        types.ReplyKeyboardMarkup: Back button keyboard
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(BACK_BUTTON_TEXT)
    return markup

def clear_user_state(user_state, chat_id):
    """
    Clear user state for a specific chat
    
    Args:
        user_state (dict): User state dictionary
        chat_id (int): Chat ID to clear
    """
    if chat_id in user_state:
        del user_state[chat_id]

def get_user_state(user_state, chat_id):
    """
    Get user state for a specific chat
    
    Args:
        user_state (dict): User state dictionary
        chat_id (int): Chat ID
    
    Returns:
        dict: User state or empty dict if not found
    """
    return user_state.get(chat_id, {})

def set_user_state(user_state, chat_id, state_data):
    """
    Set user state for a specific chat
    
    Args:
        user_state (dict): User state dictionary
        chat_id (int): Chat ID
        state_data (dict): State data to set
    """
    if chat_id not in user_state:
        user_state[chat_id] = {}
    user_state[chat_id].update(state_data)

def escape_markdown(text):
    """
    Escape markdown special characters
    
    Args:
        text (str): Text to escape
    
    Returns:
        str: Escaped text
    """
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text
