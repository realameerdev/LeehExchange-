"""
Configuration module for LEEH Exchange Bot
Contains bot settings, wallet addresses, and global variables
"""

import os
import telebot
from telebot import types

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# VTpass API configuration for telecom services
VT_API_KEY = os.getenv("VT_API_KEY")
VT_PUBLIC_KEY = os.getenv("VT_PUBLIC_KEY")
VT_SECRET_KEY = os.getenv("VT_SECRET_KEY")
VT_BASE_URL = "https://sandbox.vtpass.com/api"

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Cryptocurrency wallet addresses for receiving payments (Sell orders)
WALLETS = {
    "BTC": "bc1qxqmjwvq6kwtdq3t976778kcnxrx9pscgx68dx8",
    "ETH": "0xF591E996460A7DE2DE2B8d3d7D4cc3470840b314",
    "POL": "0xF591E996460A7DE2DE2B8d3d7D4cc3470840b314",
    "BNB": "0xF591E996460A7DE2DE2B8d3d7D4cc3470840b314",
    "SOL": "H5mimSB39wnKecorCwsKyJaSMhrTXsyzwGRE68UWmCD4",
    "XRP": "rBZuV6B74a67t51TGfrMXM5nrFJV2tF8hg",
    "DOGE": "DJ8hNp7FrfwfM3nmXi2cx1YAGVEQWtr4Az",
    "TRX": "TDngZHqefchJ3CMqgjEyTRPwDoYmuVJRbj",
    "TON": "UQDFaMIJSs08vYveCkVOC0eTQAakqf5hH_0jeAulJM1wZThp",
    "SUI": "0xaa22359f318e256196cc525fc37e2133bc2047fb1b8b501e2c73ec16ef73910c"
}

# CoinGecko API IDs for price fetching
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "POL": "polygon-ecosystem-token",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "TRX": "tron",
    "TON": "the-open-network",
    "SUI": "sui"
}

# Bank details for fiat payments
BANK_DETAILS = """
💳 **Payment Instructions:**
Send payment to:
🏦 Bank: **Opay**
🔢 Account Number: ****
👤 Name: **Abdulrofih Abdullah Hamzah**

After payment, upload your payment screenshot as proof.
"""

# User state storage (in production, use a database)
user_state = {}

# Bot messages
WELCOME_MESSAGE = """
🔄 **Welcome to LEEH Exchange Bot**

Your trusted platform for cryptocurrency trading!

Choose an option below to get started:
"""

BACK_BUTTON_TEXT = "🔙 Back"
BUY_BUTTON_TEXT = "🟢 Buy"
SELL_BUTTON_TEXT = "🔴 Sell"
