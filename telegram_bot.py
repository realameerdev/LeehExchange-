#!/usr/bin/env python3
"""
LEEH Exchange Telegram Bot - Full Implementation
Python-telegram-bot version with crypto trading, airtime, and data services
"""

import os
import csv
import logging
import requests
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackContext, MessageHandler,
    filters, CallbackQueryHandler, ConversationHandler, PicklePersistence
)
from rewards import (
    award_action,
    award_verified_transaction,
    snapshot as rewards_snapshot,
    history as rewards_history,
    leaderboard as rewards_leaderboard,
    list_rewards,
    load_rewards_data,
    redeem_reward,
    adjust_points,
)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# --- ENVIRONMENT SETTINGS ---
BOT_TOKEN = os.getenv("BOT_TOKEN").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BANK_DETAILS = "\n🏦 Bank: Opay\n🔢 Account: 8148842778\n👤 Name: Abdulrofih Abdullah Hamzah"

# ── Rate limiting ────────────────────────────────────────────────────────────
_last_msg_time: dict = {}
RATE_LIMIT_SEC = 3

def is_rate_limited(user_id: int) -> bool:
    now = datetime.now()
    last = _last_msg_time.get(user_id)
    if last and (now - last).total_seconds() < RATE_LIMIT_SEC:
        return True
    _last_msg_time[user_id] = now
    return False

# ── Lightweight email helper (used inside bot without importing app.py) ───────
def send_confirmation_email(to_email: str, subject: str, body: str):
    if not to_email or '@' not in str(to_email):
        return
    try:
        _cfg = {}
        if os.path.exists('admin_config.json'):
            with open('admin_config.json') as _f:
                _cfg = json.load(_f)
        sender = _cfg.get('sender_email', 'leehexchange@gmail.com')
        from replitmail import Mail
        mail = Mail()
        mail.send(to=str(to_email), subject=subject, body=body, from_email=sender)
        logger.info(f"Confirmation email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email send failed to {to_email}: {e}")

# --- COIN ADDRESSES ---
COIN_WALLETS = {
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

# --- COINGECKO MAPPING (Extended 40+ coins) ---
COIN_IDS = {
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

# Extended list for rate checking (40 cryptocurrencies)
EXTENDED_COIN_IDS = {
    # Major Coins
    "BTC": ("bitcoin", "Bitcoin"),
    "ETH": ("ethereum", "Ethereum"),
    "BNB": ("binancecoin", "BNB"),
    "SOL": ("solana", "Solana"),
    "XRP": ("ripple", "XRP"),
    "ADA": ("cardano", "Cardano"),
    "DOGE": ("dogecoin", "Dogecoin"),
    "TRX": ("tron", "TRON"),
    "TON": ("the-open-network", "Toncoin"),
    "AVAX": ("avalanche-2", "Avalanche"),
    # DeFi & Layer 2
    "LINK": ("chainlink", "Chainlink"),
    "UNI": ("uniswap", "Uniswap"),
    "AAVE": ("aave", "Aave"),
    "MKR": ("maker", "Maker"),
    "CRV": ("curve-dao-token", "Curve"),
    "LDO": ("lido-dao", "Lido DAO"),
    "ARB": ("arbitrum", "Arbitrum"),
    "OP": ("optimism", "Optimism"),
    "MATIC": ("matic-network", "Polygon"),
    "FTM": ("fantom", "Fantom"),
    # Layer 1s
    "DOT": ("polkadot", "Polkadot"),
    "ATOM": ("cosmos", "Cosmos"),
    "NEAR": ("near", "NEAR Protocol"),
    "APT": ("aptos", "Aptos"),
    "SUI": ("sui", "Sui"),
    "ICP": ("internet-computer", "Internet Computer"),
    "FIL": ("filecoin", "Filecoin"),
    "INJ": ("injective-protocol", "Injective"),
    "SEI": ("sei-network", "Sei"),
    "STX": ("blockstack", "Stacks"),
    # Meme & Community
    "SHIB": ("shiba-inu", "Shiba Inu"),
    "PEPE": ("pepe", "Pepe"),
    "FLOKI": ("floki", "Floki"),
    "BONK": ("bonk", "Bonk"),
    "WIF": ("dogwifcoin", "dogwifhat"),
    # Exchange & Utility
    "CRO": ("crypto-com-chain", "Cronos"),
    "OKB": ("okb", "OKB"),
    "LEO": ("leo-token", "LEO Token"),
    "KCS": ("kucoin-shares", "KuCoin"),
    "GT": ("gatechain-token", "Gate"),
    # Stablecoins (for reference)
    "USDT": ("tether", "Tether"),
    "USDC": ("usd-coin", "USD Coin"),
    "DAI": ("dai", "Dai"),
}

# Categorized coins for display
COIN_CATEGORIES = {
    "🔥 Top 10": ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON", "AVAX"],
    "🌐 Layer 1": ["DOT", "ATOM", "NEAR", "APT", "SUI", "ICP", "FIL", "INJ", "SEI", "STX"],
    "⚡ DeFi": ["LINK", "UNI", "AAVE", "MKR", "CRV", "LDO", "ARB", "OP", "MATIC", "FTM"],
    "🐕 Meme": ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF"],
    "💱 Exchange": ["BNB", "CRO", "OKB", "LEO", "KCS", "GT"],
    "💵 Stablecoins": ["USDT", "USDC", "DAI"],
}

# Conversation states
SELECTING_CRYPTO, ENTERING_AMOUNT, ENTERING_WALLET, UPLOADING_PROOF = range(4)
NETWORK_SELECT, AMOUNT_INPUT, PHONE_INPUT, PROOF_UPLOAD = range(4, 8)
DATA_TYPE_SELECT, DATA_NETWORK_SELECT, DATA_SIZE_INPUT, DATA_PHONE_INPUT, DATA_PROOF_UPLOAD = range(8, 13)
SELL_CONFIRM_PAYMENT, SELL_BANK_DETAILS = range(13, 15)
# Giveaway form states
(GIVEAWAY_START, GIVEAWAY_FULLNAME, GIVEAWAY_USERNAME, GIVEAWAY_TYPE, 
 GIVEAWAY_REFERENCE, GIVEAWAY_AMOUNT, GIVEAWAY_DATE, GIVEAWAY_PROOF, 
 GIVEAWAY_REWARD, GIVEAWAY_CONFIRM) = range(15, 25)
# Email collection states
ENTERING_EMAIL_BUY, ENTERING_EMAIL_SELL = range(25, 27)

# Gift card states
(SELL_GC_BRAND, SELL_GC_VALUE, SELL_GC_COUNTRY, SELL_GC_PROOF,
 SELL_GC_BANK, SELL_GC_EMAIL,
 BUY_GC_BRAND, BUY_GC_VALUE, BUY_GC_RECIPIENT, BUY_GC_PROOF, BUY_GC_EMAIL) = range(30, 41)

GIFT_CARD_BRANDS = [
    "Amazon", "iTunes", "Steam", "Google Play", "Apple",
    "eBay", "Walmart", "Sephora", "Nike", "Razer Gold", "Visa", "Xbox"
]

# --- UTILITY FUNCTIONS ---
def get_crypto_price(coin_symbol):
    """Get real-time crypto price from CoinGecko"""
    try:
        coin_id = COIN_IDS.get(coin_symbol.upper())
        if not coin_id:
            return None
        
        url = f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd'
        response = requests.get(url, timeout=10)
        data = response.json()
        return data[coin_id]['usd']
    except Exception as e:
        logger.error(f"Error fetching price for {coin_symbol}: {e}")
        return None

def format_price(price):
    """Format price for display"""
    if price is None:
        return "N/A"
    return f"${price:,.2f}"

def save_user_email(user_id, username, email):
    """Save user email to the subscriber list (user_emails.csv)"""
    import csv as _csv
    file = 'user_emails.csv'
    file_exists = os.path.isfile(file)
    # Load existing to avoid duplicates
    existing = set()
    if file_exists:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    existing.add(str(row.get('UserID', '')))
        except Exception:
            pass
    with open(file, 'a', newline='', encoding='utf-8') as f:
        writer = _csv.DictWriter(f, fieldnames=['UserID', 'Username', 'Email', 'Timestamp'])
        if not file_exists:
            writer.writeheader()
        if str(user_id) not in existing:
            writer.writerow({
                'UserID': user_id,
                'Username': username,
                'Email': email,
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

def log_transaction(user_id, username, order_type, details, amount, timestamp=None, email=''):
    """Log transaction to CSV — columns must match: UserID,Username,Type,Coin,Amount,Wallet/Bank,Timestamp,Status,Email"""
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    file_exists = os.path.isfile('transactions.csv')
    
    with open('transactions.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['UserID', 'Username', 'Type', 'Coin', 'Amount', 'Wallet/Bank', 'Timestamp', 'Status', 'Email'])
        # Column order matches existing CSV header exactly
        writer.writerow([user_id, username, order_type, details, amount, '', timestamp, 'Pending', email])

def calculate_data_price(size_mb):
    """Calculate data price with profit markup"""
    # Base price calculation (₦0.5 per MB)
    base_price = size_mb * 0.5
    
    # Apply profit markup (20% with max ₦70)
    profit = min(base_price * 0.2, 70)
    return int(base_price + profit)

def generate_transaction_ref():
    """Generate a unique transaction reference"""
    import random
    import string
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"LEEH-{timestamp}-{random_suffix}"

def check_giveaway_claimed(transaction_ref, user_id):
    """Check if giveaway has already been claimed for this transaction"""
    if not os.path.exists('giveaway_claims.csv'):
        return False
    
    with open('giveaway_claims.csv', 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['Transaction_Ref'] == transaction_ref and int(row['User_ID']) == user_id:
                return True
    return False

def log_giveaway_claim(user_id, username, full_name, transaction_type, transaction_ref, amount, transaction_date, reward_choice, proof_file_id='', confirmed=True):
    """Log giveaway claim to CSV"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.isfile('giveaway_claims.csv')
    
    with open('giveaway_claims.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Claim_Timestamp', 'User_ID', 'Username', 'Full_Name', 'Transaction_Type', 
                           'Transaction_Ref', 'Amount', 'Transaction_Date', 'Reward_Choice', 'Proof_File_ID', 'Confirmed'])
        writer.writerow([timestamp, user_id, username, full_name, transaction_type, 
                        transaction_ref, amount, transaction_date, reward_choice, proof_file_id, confirmed])

# --- CRYPTO RATES FUNCTIONS ---
def get_multiple_crypto_prices(coin_symbols):
    """Get real-time prices for multiple cryptocurrencies from CoinGecko"""
    try:
        coin_ids = []
        symbol_to_id = {}
        for symbol in coin_symbols:
            if symbol in EXTENDED_COIN_IDS:
                coin_id = EXTENDED_COIN_IDS[symbol][0]
                coin_ids.append(coin_id)
                symbol_to_id[coin_id] = symbol
        
        if not coin_ids:
            return {}
        
        ids_str = ",".join(coin_ids)
        url = f'https://api.coingecko.com/api/v3/simple/price?ids={ids_str}&vs_currencies=usd&include_24hr_change=true'
        response = requests.get(url, timeout=15)
        data = response.json()
        
        prices = {}
        for coin_id, info in data.items():
            symbol = symbol_to_id.get(coin_id)
            if symbol:
                prices[symbol] = {
                    'price': info.get('usd', 0),
                    'change_24h': info.get('usd_24h_change', 0)
                }
        return prices
    except Exception as e:
        logger.error(f"Error fetching multiple prices: {e}")
        return {}

def format_rate_display(symbol, price_data):
    """Format a single coin rate for display"""
    if not price_data:
        return f"{symbol}: N/A"
    
    price = price_data.get('price', 0)
    change = price_data.get('change_24h', 0)
    name = EXTENDED_COIN_IDS.get(symbol, (symbol, symbol))[1]
    
    # Format price
    if price >= 1000:
        price_str = f"${price:,.0f}"
    elif price >= 1:
        price_str = f"${price:,.2f}"
    else:
        price_str = f"${price:.6f}"
    
    # Format change
    if change >= 0:
        change_str = f"🟢 +{change:.1f}%"
    else:
        change_str = f"🔴 {change:.1f}%"
    
    return f"{symbol} ({name})\n   {price_str} {change_str}"

# --- USER DATA PERSISTENCE ---
USER_DATA_FILE = 'user_data.json'

def load_user_data():
    """Load user data from JSON file"""
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user data: {e}")
            return {"users": {}}
    return {"users": {}}

def save_user_data(data):
    """Save user data to JSON file"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

def get_user_profile(user_id):
    """Get or create user profile with point expiry"""
    data = load_user_data()
    user_id_str = str(user_id)
    now = datetime.now()
    
    if user_id_str not in data["users"]:
        data["users"][user_id_str] = {
            "points": 0,
            "points_expiry": None,
            "last_checkin": None,
            "alerts": [],
            "predictions": {"wins": 0, "losses": 0}
        }
        save_user_data(data)
    else:
        # Check for point expiry
        profile = data["users"][user_id_str]
        expiry_str = profile.get("points_expiry")
        if expiry_str:
            expiry = datetime.fromisoformat(expiry_str)
            if now > expiry and profile.get("points", 0) > 0:
                profile["points"] = 0
                profile["points_expiry"] = None
                save_user_data(data)
                
    return data["users"][user_id_str]

def update_user_profile(user_id, update_dict):
    """Update user profile data"""
    data = load_user_data()
    user_id_str = str(user_id)
    if user_id_str not in data["users"]:
        get_user_profile(user_id)
        data = load_user_data()
    
    data["users"][user_id_str].update(update_dict)
    save_user_data(data)

# --- REFERRAL FEATURE ---
async def show_referral_info(update: Update, context: CallbackContext):
    """Show user's referral link and stats"""
    user = update.effective_user
    user_id_str = str(user.id)
    data = load_user_data()
    profile = data.get("users", {}).get(user_id_str, {})
    points = rewards_snapshot(user_id_str)["points"]
    referral_count = profile.get("referral_count", 0)

    try:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "LEEHExchangeBot"

    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id_str}"

    await update.message.reply_text(
        f"🔗 *Your Referral Link*\n\n"
        f"`{referral_link}`\n\n"
        f"Share this link with friends. When they join and complete a qualifying "
        f"transaction, you earn Leeh Points.\n\n"
        f"📊 *Your Stats*\n"
        f"• Friends Referred: *{referral_count}*\n"
        f"• Current Points Balance: *{points} LP*\n\n"
        f"💡 Use your points with the 🎟️ Use Points button to get discounts on orders.",
        parse_mode='Markdown'
    )


# --- LEEH REWARDS -----------------------------------------------------------
def _rewards_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Earn Points", callback_data="reward:earn"),
         InlineKeyboardButton("🎁 Redeem Rewards", callback_data="reward:redeem")],
        [InlineKeyboardButton("📊 My Progress", callback_data="reward:progress"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="reward:leaderboard")],
        [InlineKeyboardButton("📜 Rewards History", callback_data="reward:history")],
    ])


def _rewards_menu_text(user_id):
    details = rewards_snapshot(user_id)
    return (
        "🎁 Leeh Rewards\n\n"
        "Earn points by actively using LeehExchange and redeem them for real rewards.\n\n"
        f"Your Points: {details['points']} LP\n"
        f"Level: {details['level']}"
    )


async def start_rewards_menu(update: Update, context: CallbackContext):
    await update.message.reply_text(
        _rewards_menu_text(update.effective_user.id),
        reply_markup=_rewards_menu_markup(),
    )


def _reward_back_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Leeh Rewards", callback_data="reward:menu")]
    ])


async def handle_rewards_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data or ""

    if data == "reward:menu":
        await query.edit_message_text(
            _rewards_menu_text(user_id),
            reply_markup=_rewards_menu_markup(),
        )
        return

    if data == "reward:earn":
        actions = load_rewards_data().get("settings", {}).get("actions", {})
        lines = ["🎯 Earn Points\n", "Verified activity earns LP automatically:\n"]
        for action in actions.values():
            if action.get("enabled", True) and int(action.get("points", 0) or 0) > 0:
                lines.append(f"• {action.get('label', 'Reward action')}: +{int(action['points'])} LP")
        lines.append("\nPoints are only added after the backend verifies the action.")
        await query.edit_message_text("\n".join(lines), reply_markup=_reward_back_markup())
        return

    if data == "reward:progress":
        details = rewards_snapshot(user_id)
        next_level = details.get("next_level_points")
        next_text = f"{next_level} LP" if next_level else "Maximum level reached"
        await query.edit_message_text(
            "📊 My Progress\n\n"
            f"Balance: {details['points']} LP\n"
            f"Level: {details['level']}\n"
            f"Next level: {next_text}\n"
            f"Lifetime earned: {details['lifetime_earned']} LP\n"
            f"Trades completed: {details['trade_count']}\n"
            f"Trading volume: {details['trade_volume']:,.2f}\n"
            f"Active trading days: {details['trade_days']}\n"
            f"Qualified referrals: {details['qualified_referrals']}",
            reply_markup=_reward_back_markup(),
        )
        return

    if data == "reward:leaderboard":
        rows = rewards_leaderboard(10)
        if not rows:
            text = "🏆 Leaderboard\n\nNo verified rewards activity yet."
        else:
            text = "🏆 Leaderboard\n\n"
            users = load_user_data().get("users", {})
            for index, row in enumerate(rows, 1):
                profile = users.get(str(row["user_id"]), {})
                name = profile.get("username") or profile.get("full_name") or f"User {row['user_id']}"
                text += f"{index}. {name} — {row['lifetime_earned']} LP earned\n"
        await query.edit_message_text(text, reply_markup=_reward_back_markup())
        return

    if data == "reward:history":
        rows = rewards_history(user_id, 12)
        if not rows:
            text = "📜 Rewards History\n\nNo point movements yet."
        else:
            text = "📜 Rewards History\n\n"
            for row in rows:
                delta = int(row.get("delta", 0))
                sign = "+" if delta >= 0 else ""
                text += f"{row.get('timestamp', '')[:16]}  {sign}{delta} LP — {row.get('reason', 'Activity')}\n"
        await query.edit_message_text(text, reply_markup=_reward_back_markup())
        return

    if data == "reward:redeem":
        rewards = list_rewards(active_only=True)
        if not rewards:
            await query.edit_message_text(
                "🎁 Redeem Rewards\n\nNo rewards are available right now. Check back soon.",
                reply_markup=_reward_back_markup(),
            )
            return
        balance = rewards_snapshot(user_id)["points"]
        keyboard = [
            [InlineKeyboardButton(
                f"{reward.get('name', 'Reward')} · {reward.get('points_required', 0)} LP",
                callback_data=f"reward:view:{reward.get('id')}",
            )]
            for reward in rewards
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back to Leeh Rewards", callback_data="reward:menu")])
        await query.edit_message_text(
            f"🎁 Redeem Rewards\n\nYour balance: {balance} LP\nSelect a reward:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("reward:view:"):
        reward_id = data.split(":", 2)[2]
        reward = next((row for row in list_rewards(active_only=True) if row.get("id") == reward_id), None)
        if not reward:
            await query.edit_message_text("This reward is no longer available.", reply_markup=_reward_back_markup())
            return
        balance = rewards_snapshot(user_id)["points"]
        await query.edit_message_text(
            "🎁 Confirm Redemption\n\n"
            f"Reward: {reward.get('name', 'Reward')}\n"
            f"Details: {reward.get('description', '') or reward.get('value', '') or 'LeehExchange reward'}\n"
            f"Required: {reward.get('points_required', 0)} LP\n"
            f"Your balance: {balance} LP\n\n"
            "Your points are held immediately to prevent duplicate claims.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm", callback_data=f"reward:confirm:{reward_id}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="reward:redeem")],
            ]),
        )
        return

    if data.startswith("reward:confirm:"):
        reward_id = data.split(":", 2)[2]
        result = redeem_reward(user_id, reward_id)
        if not result.get("success"):
            await query.edit_message_text(
                f"❌ Redemption unavailable\n\n{result.get('error', 'Please try again.')}",
                reply_markup=_reward_back_markup(),
            )
            return
        redemption = result["redemption"]
        status_text = "pending admin review" if redemption.get("status") == "pending" else "approved"
        await query.edit_message_text(
            "✅ Redemption Submitted\n\n"
            f"{redemption.get('reward_name', 'Reward')} is {status_text}.\n"
            f"Reference: {redemption.get('id')}\n"
            f"Remaining balance: {result.get('balance', 0)} LP",
            reply_markup=_reward_back_markup(),
        )


# --- DAILY REWARDS FEATURE ---
async def claim_daily_reward(update: Update, context: CallbackContext):
    """Handle daily check-in reward with 24h expiry"""
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    now = datetime.now()
    last_checkin_str = profile.get("last_checkin")
    
    can_claim = True
    if last_checkin_str:
        last_checkin = datetime.fromisoformat(last_checkin_str)
        if now - last_checkin < timedelta(days=1):
            can_claim = False
            time_left = timedelta(days=1) - (now - last_checkin)
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            wait_time = f"{hours}h {minutes}m"
    
    if can_claim:
        reward_points = 50
        expiry_time = now + timedelta(days=10)
        result = award_action(
            user_id,
            "daily_checkin",
            f"daily-checkin:{user_id}:{now.date().isoformat()}",
        )
        new_points = result["balance"]
        if not result["awarded"]:
            await update.message.reply_text(
                "⏳ Already Claimed!\n\nYour daily reward has already been recorded."
            )
            return
        update_user_profile(user_id, {
            "points_expiry": expiry_time.isoformat(),
            "last_checkin": now.isoformat()
        })
        
        await update.message.reply_text(
            f"🎁 Daily Reward Claimed!\n\n"
            f"You've received {result['points']} Leeh Points.\n"
            f"Total Balance: {new_points} LP\n\n"
            f"⚠️ Note: These points expire in 10 days!\n"
            f"Accumulate more to qualify for big discounts!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"⏳ Already Claimed!\n\n"
            f"You've already claimed your reward today.\n"
            f"Please wait {wait_time} before your next claim.",
            parse_mode='Markdown'
        )

import random
import string

# --- GIVEAWAY CODES ---
# We will now use a set to track used codes in user_data.json
def generate_random_code():
    """Generate a single unique secure code"""
    parts = [
        ''.join(random.choices(string.ascii_lowercase + string.digits, k=4)),
        ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    ]
    return f"leeh-{parts[0]}-{parts[1]}"

# Initial 50 codes generation (only if not already in user_data)
def initialize_codes():
    data = load_user_data()
    if "giveaway_codes" not in data:
        new_codes = {}
        for _ in range(50):
            code = generate_random_code()
            new_codes[code] = {"used": False, "used_by": None, "used_at": None}
        data["giveaway_codes"] = new_codes
        save_user_data(data)

# Call initialization
try:
    initialize_codes()
except Exception as e:
    logger.error(f"Error initializing codes: {e}")

# --- POINT USAGE ---
ENTERING_DISCOUNT_CODE = range(28, 29)

async def use_points_for_discount(update: Update, context: CallbackContext):
    """Start discount activation by asking for code"""
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    points = rewards_snapshot(user_id)["points"]
    
    if points < 100:
        await update.message.reply_text(
            "❌ Insufficient Points\n\nYou need at least 100 Points and a secret one-time giveaway code to activate this discount."
        )
        return ConversationHandler.END
        
    await update.message.reply_text(
        "🎟️ Giveaway Activation\n\nPlease enter your Unique One-Time Giveaway Code to activate your 5% discount:"
    )
    return ENTERING_DISCOUNT_CODE

async def discount_code_entered(update: Update, context: CallbackContext):
    """Verify giveaway code and activate discount"""
    code = update.message.text.strip().lower()
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    points = rewards_snapshot(user_id)["points"]
    
    data = load_user_data()
    codes_data = data.get("giveaway_codes", {})
    
    if code in codes_data:
        if codes_data[code]["used"]:
            await update.message.reply_text(
                "⚠️ Code Already Used!\n\nThis giveaway code has already been claimed and cannot be used again."
            )
            return ENTERING_DISCOUNT_CODE
            
        # Mark code as used
        codes_data[code]["used"] = True
        codes_data[code]["used_by"] = user_id
        codes_data[code]["used_at"] = datetime.now().isoformat()
        save_user_data(data)
        
        # Mark points as 'used' for the next transaction in session
        context.user_data['use_points_discount'] = True
        
        await update.message.reply_text(
            f"✅ Code Accepted! Discount Activated!\n\n"
            f"Using {points} Points for a 5% discount on your next transaction.\n"
            f"Proceed to Buy/Sell now!",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
                [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")],
                [KeyboardButton("📈 Crypto Rates"), KeyboardButton("🎁 Daily Reward")],
                [KeyboardButton("🔔 Set Price Alert"), KeyboardButton("🎮 Play BTC Game")],
                [KeyboardButton("🎟️ Use Points")]
            ], resize_keyboard=True)
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Invalid Code!\n\nThat code is incorrect or does not exist. Please enter a valid one-time 'leeh' giveaway code:"
        )
        return ENTERING_DISCOUNT_CODE

# --- PRICE ALERTS FEATURE ---
(SETTING_ALERT_COIN, SETTING_ALERT_PRICE) = range(25, 27)

async def start_price_alert(update: Update, context: CallbackContext):
    """Start the price alert setup"""
    keyboard = []
    coins = list(EXTENDED_COIN_IDS.keys())[:10]
    for i in range(0, len(coins), 2):
        row = [InlineKeyboardButton(coins[i], callback_data=f"alert_coin_{coins[i]}")]
        if i + 1 < len(coins):
            row.append(InlineKeyboardButton(coins[i + 1], callback_data=f"alert_coin_{coins[i + 1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="alert_back_main")])
    
    await update.message.reply_text(
        "🔔 Price Alert System\n\nSelect the coin you want to monitor:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SETTING_ALERT_COIN

async def alert_coin_selected(update: Update, context: CallbackContext):
    """Handle coin selection for alert"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "alert_back_main":
        await start(update, context)
        return ConversationHandler.END
        
    coin = query.data.replace("alert_coin_", "")
    context.user_data['alert_coin'] = coin
    
    # Get current price for reference
    price = get_crypto_price(coin)
    context.user_data['alert_base_price'] = price
    price_text = format_price(price)
    
    await query.edit_message_text(
        f"🔔 {coin} Price Alert\n\nCurrent Price: {price_text}\n\n"
        f"Enter the target price (in USD). \n"
        f"If you enter a price HIGHER than current, we'll notify you when it goes UP.\n"
        f"If LOWER, we'll notify you when it goes DOWN:",
        parse_mode='Markdown'
    )
    return SETTING_ALERT_PRICE

async def alert_price_entered(update: Update, context: CallbackContext):
    """Handle target price input for alert"""
    try:
        target_price = float(update.message.text)
        coin = context.user_data['alert_coin']
        base_price = context.user_data.get('alert_base_price', 0)
        user_id = update.effective_user.id
        
        direction = "up" if target_price > base_price else "down"
        
        profile = get_user_profile(user_id)
        alerts = profile.get("alerts", [])
        alerts.append({
            "coin": coin, 
            "target": target_price, 
            "base": base_price,
            "direction": direction,
            "notified": False
        })
        update_user_profile(user_id, {"alerts": alerts})
        
        dir_text = "reaches or exceeds" if direction == "up" else "reaches or drops below"
        await update.message.reply_text(
            f"✅ Alert Set!\n\n"
            f"We'll notify you when {coin} {dir_text} ${target_price:,.2f}.",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
                [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")],
                [KeyboardButton("📈 Crypto Rates"), KeyboardButton("🎁 Daily Reward")],
                [KeyboardButton("🔔 Set Price Alert"), KeyboardButton("🎮 Play BTC Game")]
            ], resize_keyboard=True),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid numerical price.")
        return SETTING_ALERT_PRICE

# --- MINI-GAMES / PREDICTION FEATURE ---
(MAKING_PREDICTION) = range(27, 28)

async def start_prediction_game(update: Update, context: CallbackContext):
    """Start the prediction game"""
    keyboard = [
        [InlineKeyboardButton("📈 BTC Up", callback_data="predict_up"), 
         InlineKeyboardButton("📉 BTC Down", callback_data="predict_down")],
        [InlineKeyboardButton("⬅️ Back", callback_data="predict_back")]
    ]
    
    # Get current price for prediction reference
    price = get_crypto_price("BTC")
    context.user_data['prediction_base_price'] = price
    
    await update.message.reply_text(
        "🎮 BTC Prediction Game\n\n"
        f"Current Price: {format_price(price)}\n\n"
        "Will BTC be higher or lower in 1 minute?\n"
        "Win 20 Points for correct predictions!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return MAKING_PREDICTION

async def handle_prediction(update: Update, context: CallbackContext):
    """Process user prediction"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "predict_back":
        await start(update, context)
        return ConversationHandler.END
        
    prediction = "up" if query.data == "predict_up" else "down"
    base_price = context.user_data['prediction_base_price']
    user_id = update.effective_user.id
    
    await query.edit_message_text(f"⏳ Processing your prediction... Waiting 5 seconds for a quick result.")
    
    import asyncio
    await asyncio.sleep(5)
    
    new_price = get_crypto_price("BTC")
    win = False
    if prediction == "up" and new_price > base_price:
        win = True
    elif prediction == "down" and new_price < base_price:
        win = True
        
    profile = get_user_profile(user_id)
    stats = profile.get("predictions", {"wins": 0, "losses": 0})
    points = profile.get("points", 0)
    
    if win:
        stats["wins"] += 1
        reward_result = award_action(
            user_id,
            "prediction_win",
            f"prediction-win:{user_id}:{context.user_data.get('prediction_base_price')}:{datetime.now().strftime('%Y%m%d%H%M')}",
        )
        points = reward_result["balance"]
        # Keep the legacy expiry field for older screens and flows.
        expiry_time = datetime.now() + timedelta(days=10)
        update_user_profile(user_id, {
            "predictions": stats,
            "points_expiry": expiry_time.isoformat()
        })
        result_text = f"🎉 You Won!\n\nBTC moved from {format_price(base_price)} to {format_price(new_price)}.\nReceived {reward_result['points']} Leeh Points!"
    else:
        stats["losses"] += 1
        update_user_profile(user_id, {"predictions": stats})
        result_text = f"❌ You Lost!\n\nBTC moved from {format_price(base_price)} to {format_price(new_price)}.\nTry again!"
        
    await query.edit_message_text(
        f"🎮 Result:\n{result_text}\n\n"
        f"Total Wins: {stats['wins']} | Losses: {stats['losses']}\n"
        f"Points: {points}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Play Again", callback_data="predict_restart"), 
                                          InlineKeyboardButton("⬅️ Back", callback_data="predict_back")]]),
        parse_mode='Markdown'
    )
    return MAKING_PREDICTION

# --- PRICE ALERTS MONITORING ---
async def check_price_alerts(context: CallbackContext):
    """Background task to check price alerts with direction logic"""
    data = load_user_data()
    alerts_to_notify = []
    
    active_coins = set()
    for user_id, profile in data.get("users", {}).items():
        for alert in profile.get("alerts", []):
            if not alert.get("notified", False):
                active_coins.add(alert["coin"])
    
    if not active_coins:
        return

    prices = get_multiple_crypto_prices(list(active_coins))
    
    data_changed = False
    for user_id, profile in data.get("users", {}).items():
        user_alerts = profile.get("alerts", [])
        for alert in user_alerts:
            if alert.get("notified", False):
                continue
                
            coin = alert["coin"]
            target = alert["target"]
            direction = alert.get("direction", "up")
            current_price = prices.get(coin, {}).get("price")
            
            if current_price is None:
                continue

            hit = False
            if direction == "up" and current_price >= target:
                hit = True
            elif direction == "down" and current_price <= target:
                hit = True
                
            if hit:
                alert["notified"] = True
                data_changed = True
                alerts_to_notify.append((user_id, coin, target, current_price, direction))
    
    if data_changed:
        save_user_data(data)
        
    for user_id, coin, target, current_price, direction in alerts_to_notify:
        try:
            dir_icon = "📈" if direction == "up" else "📉"
            message = (
                f"{dir_icon} Target Hit!\n\n"
                f"Your price alert for {coin} has been triggered!\n"
                f"Target: ${target:,.2f}\n"
                f"Current Price: ${current_price:,.2f}\n\n"
                f"The price moved {'UP' if direction == 'up' else 'DOWN'} to your target! 🚀"
            )
            await context.bot.send_message(chat_id=int(user_id), text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")

# --- START COMMAND ---
async def start(update: Update, context: CallbackContext):
    """Start command handler with user recording and referral deep-link support"""
    user = update.effective_user
    user_id = user.id
    username = user.username or "NoUsername"
    first_name = user.first_name or "there"
    full_name = user.full_name or first_name

    # Rate limit guard for /start spam
    if is_rate_limited(user_id):
        return

    data = load_user_data()
    user_id_str = str(user_id)
    pending_msgs = []
    is_new_user = user_id_str not in data["users"]

    if is_new_user:
        data["users"][user_id_str] = {
            "username": username,
            "full_name": full_name,
            "points": 0,
            "points_expiry": None,
            "last_checkin": None,
            "alerts": [],
            "predictions": {"wins": 0, "losses": 0},
            "joined_at": datetime.now().isoformat(),
            "pending_broadcasts": [],
            "referred_by": None,
            "referral_count": 0,
        }
    else:
        data["users"][user_id_str]["username"] = username
        data["users"][user_id_str]["full_name"] = full_name
        if "joined_at" not in data["users"][user_id_str]:
            data["users"][user_id_str]["joined_at"] = datetime.now().isoformat()
        if "referred_by" not in data["users"][user_id_str]:
            data["users"][user_id_str]["referred_by"] = None
        if "referral_count" not in data["users"][user_id_str]:
            data["users"][user_id_str]["referral_count"] = 0
        pending_msgs = data["users"][user_id_str].get("pending_broadcasts", [])
        data["users"][user_id_str]["pending_broadcasts"] = []

    # ── Referral deep-link: /start ref_<referrer_id> ─────────────────────────
    args = context.args or []
    if args and args[0].startswith("ref_") and is_new_user:
        referrer_id_str = args[0][4:]
        if referrer_id_str != user_id_str and referrer_id_str in data.get("users", {}):
            data["users"][user_id_str]["referred_by"] = referrer_id_str
            ref_profile = data["users"][referrer_id_str]
            ref_profile["referral_count"] = ref_profile.get("referral_count", 0) + 1
            try:
                await context.bot.send_message(
                    chat_id=int(referrer_id_str),
                    text=f"🎉 Referral Connected!\n\n@{username} joined using your link.\nYou'll earn Leeh Points after their first qualifying transaction."
                )
            except Exception:
                pass

    save_user_data(data)

    if is_new_user:
        award_action(
            user_id,
            "account_registration",
            f"registration:{user_id_str}",
            {"username": username},
        )
    
    # Update user activity in CSV
    log_transaction(
        user_id=user_id,
        username=username,
        order_type='User Join',
        details=f"User {full_name} (@{username}) triggered start",
        amount="0"
    )
    
    keyboard = [
        [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
        [KeyboardButton("🎁 Buy Gift Card"), KeyboardButton("🎴 Sell Gift Card")],
        [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")],
        [KeyboardButton("📈 Crypto Rates"), KeyboardButton("🎁 Daily Reward")],
        [KeyboardButton("🔔 Set Price Alert"), KeyboardButton("🎮 Play BTC Game")],
        [KeyboardButton("🎁 Leeh Rewards"), KeyboardButton("🔗 My Referral")],
        [KeyboardButton("🎟️ Use Points")],
    ]

    hour = datetime.now().hour
    if hour < 12:
        time_greeting = "Good morning"
    elif hour < 17:
        time_greeting = "Good afternoon"
    else:
        time_greeting = "Good evening"

    welcome_text = (
        f"👋 {time_greeting}, {first_name}! Welcome to LEEH Exchange.\n\n"
        "Your one-stop platform for:\n"
        "- Cryptocurrency trading\n"
        "- Gift card buy & sell\n"
        "- Airtime top-ups\n"
        "- Data bundle purchases\n\n"
        "Choose an option below to get started:"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

    # Deliver any pending broadcast messages
    if pending_msgs:
        logger.info(f"Delivering {len(pending_msgs)} pending broadcasts to {user_id}")
        for msg_data in pending_msgs:
            try:
                # Handle both old string format and new dict format
                if isinstance(msg_data, dict):
                    text = msg_data.get('text', '')
                    image = msg_data.get('image')
                    
                    if image:
                        # Handle local file paths for uploaded images
                        if os.path.exists(image):
                            with open(image, 'rb') as photo:
                                await context.bot.send_photo(
                                    chat_id=user_id,
                                    photo=photo,
                                    caption=f"📢 **ADMIN BROADCAST**\n\n{text}",
                                    parse_mode='Markdown'
                                )
                        else:
                            # Assume it's a URL
                            await context.bot.send_photo(
                                chat_id=user_id,
                                photo=image,
                                caption=f"📢 **ADMIN BROADCAST**\n\n{text}",
                                parse_mode='Markdown'
                            )
                    else:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"📢 **ADMIN BROADCAST**\n\n{text}",
                            parse_mode='Markdown'
                        )
                else:
                    # Backward compatibility for simple string messages
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=f"📢 **ADMIN BROADCAST**\n\n{msg_data}", 
                        parse_mode='Markdown'
                    )
                # Small delay to prevent flood limits if many messages
                import asyncio
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error delivering pending broadcast to {user_id}: {e}")
    
    logger.info(f"User {user_id} (@{username}) started the bot")

# --- CRYPTO BUY FLOW ---
async def start_buy_crypto(update: Update, context: CallbackContext):
    """Start crypto buying process"""
    context.user_data['mode'] = 'buy'
    
    keyboard = []
    coins = list(COIN_WALLETS.keys())
    for i in range(0, len(coins), 2):
        row = [InlineKeyboardButton(coins[i], callback_data=f"buy_{coins[i]}")]
        if i + 1 < len(coins):
            row.append(InlineKeyboardButton(coins[i + 1], callback_data=f"buy_{coins[i + 1]}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    
    await update.message.reply_text(
        "🟢 Buy Cryptocurrency\n\nSelect the cryptocurrency you want to buy:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"User {update.effective_user.id} started crypto buying")
    return SELECTING_CRYPTO

async def crypto_selected(update: Update, context: CallbackContext):
    """Handle crypto selection — lock the quoted price for 10 minutes"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_main":
        await start(update, context)
        return ConversationHandler.END
    
    coin = query.data.replace("buy_", "").replace("sell_", "")
    context.user_data['selected_coin'] = coin
    
    # Lock quoted price with timestamp
    price = get_crypto_price(coin)
    context.user_data['locked_price'] = price
    context.user_data['locked_price_at'] = datetime.now().isoformat()
    price_text = format_price(price)
    
    mode = context.user_data.get('mode', 'buy')
    action = "buy" if mode == 'buy' else "sell"
    currency = "USD" if mode == 'buy' else coin
    
    await query.edit_message_text(
        f"💰 {coin} {action.capitalize()}\n\n"
        f"Locked Rate: {price_text} *(valid 10 min)*\n\n"
        f"Enter the amount you want to {action} (in {currency}):",
        parse_mode='Markdown'
    )
    
    return ENTERING_AMOUNT

async def amount_entered(update: Update, context: CallbackContext):
    """Handle amount input — refresh locked price if quote expired (>10 min)"""
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError

        context.user_data['amount'] = amount
        coin = context.user_data['selected_coin']

        # Quote expiry check
        locked_at_str = context.user_data.get('locked_price_at')
        if locked_at_str:
            try:
                locked_at = datetime.fromisoformat(locked_at_str)
                age_mins = (datetime.now() - locked_at).total_seconds() / 60
                if age_mins > 10:
                    new_price = get_crypto_price(coin)
                    context.user_data['locked_price'] = new_price
                    context.user_data['locked_price_at'] = datetime.now().isoformat()
                    await update.message.reply_text(
                        f"⚠️ Your rate quote expired after 10 minutes.\n"
                        f"Refreshed rate: {format_price(new_price)}\n\n"
                        f"Please continue — your order amount has been recorded."
                    )
            except Exception:
                pass

        await update.message.reply_text(
            f"📍 Wallet Address Required\n\n"
            f"Please enter your {coin} wallet address where you want to receive your coins:",
            parse_mode='Markdown'
        )

        return ENTERING_WALLET

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount!\n\n"
            "Please enter a valid number (e.g., 100, 500.50)"
        )
        return ENTERING_AMOUNT

async def wallet_entered(update: Update, context: CallbackContext):
    """Handle wallet address input and ask for email"""
    wallet_address = update.message.text.strip()
    
    if len(wallet_address) < 10:
        await update.message.reply_text(
            "❌ Invalid wallet address!\n\n"
            "Please enter a valid wallet address (at least 10 characters)"
        )
        return ENTERING_WALLET
        
    context.user_data['user_wallet'] = wallet_address
    
    await update.message.reply_text(
        "📧 Almost there!\n\n"
        "Please enter your email address so we can send you a confirmation notification when your order is processed:"
    )
    
    return ENTERING_EMAIL_BUY

async def email_entered_buy(update: Update, context: CallbackContext):
    """Handle email input for buy flow, then show payment instructions"""
    import re
    email = update.message.text.strip()
    
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        await update.message.reply_text(
            "❌ Invalid email address!\n\n"
            "Please enter a valid email address (e.g. yourname@example.com):"
        )
        return ENTERING_EMAIL_BUY
    
    context.user_data['user_email'] = email
    user = update.effective_user
    save_user_email(user.id, user.username or 'NoUsername', email)
    coin = context.user_data['selected_coin']
    amount = context.user_data['amount']
    wallet_address = context.user_data['user_wallet']
    
    await update.message.reply_text(
        f"📝 Order Summary\n\n"
        f"Coin: {coin}\n"
        f"Amount: ${amount:,.2f}\n"
        f"Your Wallet: {wallet_address}\n"
        f"Email: {email}\n\n"
        f"💳 Payment Instructions:{BANK_DETAILS}\n\n"
        f"📸 Please upload your payment screenshot to complete the order:",
        parse_mode='Markdown'
    )
    
    return UPLOADING_PROOF

async def proof_uploaded(update: Update, context: CallbackContext):
    """Handle proof upload for crypto"""
    if not update.message.photo:
        await update.message.reply_text(
            "📸 Payment Proof Required\n\n"
            "Please upload a screenshot of your payment as proof."
        )
        return UPLOADING_PROOF
    
    coin = context.user_data['selected_coin']
    amount = context.user_data['amount']
    user_wallet = context.user_data.get('user_wallet', 'Not provided')
    user_email = context.user_data.get('user_email', '')
    user = update.effective_user
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transaction_ref = generate_transaction_ref()
    
    context.user_data['transaction_ref'] = transaction_ref
    context.user_data['transaction_timestamp'] = timestamp
    
    mode = context.user_data.get('mode', 'buy')
    order_type = "Buy" if mode == 'buy' else "Sell"
    bank_details = context.user_data.get('bank_details', 'Not provided')
    
    log_transaction(
        user_id=user.id,
        username=user.username or 'NoUsername',
        order_type=order_type,
        details=f"{coin} (Wallet: {user_wallet})",
        amount=f"${amount:,.2f}",
        timestamp=timestamp,
        email=user_email
    )
    
    # Handle points discount for buy order
    discount_text = ""
    if context.user_data.get('use_points_discount'):
        points = rewards_snapshot(user.id)["points"]
        debit = adjust_points(
            user.id,
            -points,
            "5% discount activated with legacy giveaway code",
            actor="user",
            event_key=f"discount:{user.id}:{transaction_ref}",
        )
        points = points if debit.get("success") else 0
        discount_text = f"\n🎟️ DISCOUNT APPLIED: 5% OFF (Used {points} Points)"
        context.user_data['use_points_discount'] = False
    
    admin_message = (
        f"{'🟢' if mode == 'buy' else '🔴'} New Crypto {order_type} Order{discount_text}\n\n"
        f"📋 Ref: {transaction_ref}\n"
        f"👤 User: @{user.username or 'N/A'} (ID: {user.id})\n"
        f"📧 Email: {user_email or 'Not provided'}\n"
        f"💰 Coin: {coin}\n"
        f"💵 Amount: {amount} {coin if mode == 'sell' else f'${amount:,.2f}'}\n"
        f"📍 User Wallet: {user_wallet}\n"
        f"🏦 Our Wallet: {COIN_WALLETS[coin]}\n"
        f"⏰ Time: {timestamp}"
    )
    
    if mode == 'sell':
        admin_message += f"\n\n💳 Payout Details:\n{bank_details}"
    
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id)

    # Send receipt email immediately on order creation
    if user_email:
        locked_price = context.user_data.get('locked_price')
        price_line = f"Quoted Rate: {format_price(locked_price)}\n" if locked_price else ""
        send_confirmation_email(
            user_email,
            f"LEEH Exchange — Your {order_type} Order Has Been Received",
            f"Hi {user.first_name or 'there'},\n\n"
            f"We've received your {coin} {order_type.lower()} order.\n\n"
            f"Order Reference : {transaction_ref}\n"
            f"Coin            : {coin}\n"
            f"Amount          : {amount} {'USD' if mode == 'buy' else coin}\n"
            f"{price_line}"
            f"Status          : Pending Review\n\n"
            f"We will process your order shortly and send another email when it's approved.\n\n"
            f"Thank you for choosing LEEH Exchange!\n"
            f"— The LEEH Exchange Team"
        )

    await update.message.reply_text(
        f"✅ Order Received!\n\n"
        f"Your {coin} {order_type.lower()} order has been submitted successfully.\n"
        f"Reference: {transaction_ref}\n\n"
        f"📧 A receipt has been sent to {user_email}.\n\n"
        f"Thank you for using LEEH Exchange!"
    )

    logger.info(f"Crypto {order_type.lower()} order completed for user {user.id}")
    return ConversationHandler.END

# --- CRYPTO SELL FLOW ---
async def start_sell_crypto(update: Update, context: CallbackContext):
    """Start crypto selling process"""
    context.user_data['mode'] = 'sell'
    
    keyboard = []
    coins = list(COIN_WALLETS.keys())
    for i in range(0, len(coins), 2):
        row = [InlineKeyboardButton(coins[i], callback_data=f"sell_{coins[i]}")]
        if i + 1 < len(coins):
            row.append(InlineKeyboardButton(coins[i + 1], callback_data=f"sell_{coins[i + 1]}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    
    await update.message.reply_text(
        "🔴 Sell Cryptocurrency\n\nSelect the cryptocurrency you want to sell:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"User {update.effective_user.id} started crypto selling")
    return SELECTING_CRYPTO

async def sell_amount_entered(update: Update, context: CallbackContext):
    """Handle sell amount input"""
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        
        context.user_data['amount'] = amount
        coin = context.user_data['selected_coin']
        
        keyboard = [
            [InlineKeyboardButton("✅ I have made the payment", callback_data="sell_payment_done")]
        ]
        
        await update.message.reply_text(
            f"📤 Send Your {coin}\n\n"
            f"Amount: {amount} {coin}\n\n"
            f"Send to our wallet:\n`{COIN_WALLETS[coin]}`\n\n"
            f"⚠️ Important: After sending, click the button below to proceed.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SELL_CONFIRM_PAYMENT
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount!\n\n"
            f"Please enter a valid amount of {context.user_data['selected_coin']} to sell"
        )
        return ENTERING_AMOUNT

async def sell_payment_confirmed(update: Update, context: CallbackContext):
    """Handle sell payment confirmation"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📊 Receive Your Money\n\n"
        "How would you like to receive your payment?\n\n"
        "Please enter your details:\n"
        "- Bank name\n"
        "- Account number\n"
        "- Account holder name"
    )
    
    return SELL_BANK_DETAILS

async def sell_bank_details_entered(update: Update, context: CallbackContext):
    """Handle bank details input for selling, then ask for email"""
    bank_details = update.message.text.strip()
    
    if len(bank_details) < 5:
        await update.message.reply_text(
            "❌ Invalid details!\n\n"
            "Please enter valid bank details (at least 5 characters)"
        )
        return SELL_BANK_DETAILS
    
    context.user_data['bank_details'] = bank_details
    
    await update.message.reply_text(
        "📧 Almost done!\n\n"
        "Please enter your email address so we can send you a confirmation when your payment is processed:"
    )
    
    return ENTERING_EMAIL_SELL

async def email_entered_sell(update: Update, context: CallbackContext):
    """Handle email input for sell flow, then complete the order"""
    import re
    email = update.message.text.strip()
    
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        await update.message.reply_text(
            "❌ Invalid email address!\n\n"
            "Please enter a valid email address (e.g. yourname@example.com):"
        )
        return ENTERING_EMAIL_SELL
    
    context.user_data['user_email'] = email
    coin = context.user_data['selected_coin']
    amount = context.user_data['amount']
    bank_details = context.user_data.get('bank_details', 'Not provided')
    user = update.effective_user
    save_user_email(user.id, user.username or 'NoUsername', email)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transaction_ref = generate_transaction_ref()
    
    context.user_data['transaction_ref'] = transaction_ref
    context.user_data['transaction_timestamp'] = timestamp
    
    log_transaction(
        user_id=user.id,
        username=user.username or 'NoUsername',
        order_type='Sell',
        details=f"{coin} (Bank: {bank_details[:30]})",
        amount=f"{amount} {coin}",
        timestamp=timestamp,
        email=email
    )
    
    # Handle points discount for sell order
    discount_text = ""
    if context.user_data.get('use_points_discount'):
        points = rewards_snapshot(user.id)["points"]
        debit = adjust_points(
            user.id,
            -points,
            "5% discount activated with legacy giveaway code",
            actor="user",
            event_key=f"discount:{user.id}:{transaction_ref}",
        )
        points = points if debit.get("success") else 0
        discount_text = f"\n🎟️ DISCOUNT APPLIED: 5% OFF (Used {points} Points)"
        context.user_data['use_points_discount'] = False
    
    admin_message = (
        f"🔴 New Crypto Sell Order{discount_text}\n\n"
        f"📋 Ref: {transaction_ref}\n"
        f"👤 User: @{user.username or 'N/A'} (ID: {user.id})\n"
        f"📧 Email: {email}\n"
        f"💰 Coin: {coin}\n"
        f"💵 Amount: {amount} {coin}\n"
        f"🏦 Wallet: {COIN_WALLETS[coin]}\n"
        f"⏰ Time: {timestamp}\n\n"
        f"💳 Payout Details:\n{bank_details}"
    )
    
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)

    # Send receipt email immediately on order creation
    send_confirmation_email(
        email,
        "LEEH Exchange — Your Sell Order Has Been Received",
        f"Hi {user.first_name or 'there'},\n\n"
        f"We've received your {coin} sell order.\n\n"
        f"Order Reference : {transaction_ref}\n"
        f"Coin            : {coin}\n"
        f"Amount          : {amount} {coin}\n"
        f"Payout Account  : {bank_details[:60]}\n"
        f"Status          : Pending Review\n\n"
        f"We will process your payment shortly and send another email once it's sent.\n\n"
        f"Thank you for choosing LEEH Exchange!\n"
        f"— The LEEH Exchange Team"
    )

    await update.message.reply_text(
        f"✅ Order Received!\n\n"
        f"Your {coin} sell order has been submitted successfully.\n"
        f"Reference: {transaction_ref}\n"
        f"Amount: {amount} {coin}\n\n"
        f"📧 A receipt has been sent to {email}.\n\n"
        f"Thank you for using LEEH Exchange!"
    )

    logger.info(f"Crypto sell order completed for user {user.id}")
    return ConversationHandler.END

# --- GIFT CARD HELPERS ---
def _gc_brand_keyboard(prefix: str):
    """Build inline keyboard with gift card brand options."""
    keyboard = []
    for i in range(0, len(GIFT_CARD_BRANDS), 2):
        row = [InlineKeyboardButton(GIFT_CARD_BRANDS[i], callback_data=f"{prefix}_{GIFT_CARD_BRANDS[i]}")]
        if i + 1 < len(GIFT_CARD_BRANDS):
            row.append(InlineKeyboardButton(GIFT_CARD_BRANDS[i + 1], callback_data=f"{prefix}_{GIFT_CARD_BRANDS[i + 1]}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)


# --- SELL GIFT CARD FLOW ---
async def start_sell_giftcard(update: Update, context: CallbackContext):
    """Start gift card selling process"""
    await update.message.reply_text(
        "🎴 Sell Gift Card\n\nSelect the gift card brand you want to sell:",
        reply_markup=_gc_brand_keyboard("sgc")
    )
    logger.info(f"User {update.effective_user.id} started gift card selling")
    return SELL_GC_BRAND


async def sell_gc_brand_selected(update: Update, context: CallbackContext):
    """Handle gift card brand selection (sell)"""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_main":
        await start(update, context)
        return ConversationHandler.END

    brand = query.data.replace("sgc_", "")
    context.user_data['gc_brand'] = brand

    await query.edit_message_text(
        f"🎴 {brand} Gift Card\n\n"
        f"Enter the card value in USD (e.g. 50, 100, 250):"
    )
    return SELL_GC_VALUE


async def sell_gc_value_entered(update: Update, context: CallbackContext):
    """Handle gift card value (sell)"""
    try:
        value = float(update.message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid value!\n\nPlease enter a valid number (e.g. 50, 100):")
        return SELL_GC_VALUE

    context.user_data['gc_value'] = value
    await update.message.reply_text(
        "🌍 Card Country / Currency\n\n"
        "Enter the country or currency of the card (e.g. USA, UK, EUR, CAD):"
    )
    return SELL_GC_COUNTRY


async def sell_gc_country_entered(update: Update, context: CallbackContext):
    """Handle card country (sell)"""
    country = update.message.text.strip()
    if len(country) < 2:
        await update.message.reply_text("❌ Invalid input!\n\nPlease enter a valid country or currency:")
        return SELL_GC_COUNTRY

    context.user_data['gc_country'] = country
    await update.message.reply_text(
        "📸 Upload Card Image\n\n"
        "Please upload a clear photo of the gift card (front showing the code) so we can verify it."
    )
    return SELL_GC_PROOF


async def sell_gc_proof_uploaded(update: Update, context: CallbackContext):
    """Handle gift card image upload (sell)"""
    if not update.message.photo:
        await update.message.reply_text("📸 Please upload a clear photo of the gift card.")
        return SELL_GC_PROOF

    context.user_data['gc_photo_id'] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "🏦 Payout Details\n\n"
        "Please enter the bank account where you want your payment:\n"
        "- Bank name\n"
        "- Account number\n"
        "- Account holder name"
    )
    return SELL_GC_BANK


async def sell_gc_bank_entered(update: Update, context: CallbackContext):
    """Handle bank details (sell gift card)"""
    bank_details = update.message.text.strip()
    if len(bank_details) < 5:
        await update.message.reply_text("❌ Invalid details!\n\nPlease enter valid bank details (at least 5 characters):")
        return SELL_GC_BANK

    context.user_data['gc_bank'] = bank_details
    await update.message.reply_text(
        "📧 Almost done!\n\n"
        "Please enter your email address so we can send you a confirmation when your payment is processed:"
    )
    return SELL_GC_EMAIL


async def sell_gc_email_entered(update: Update, context: CallbackContext):
    """Finalize sell gift card order"""
    import re
    email = update.message.text.strip()
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        await update.message.reply_text("❌ Invalid email!\n\nPlease enter a valid email (e.g. you@example.com):")
        return SELL_GC_EMAIL

    user = update.effective_user
    brand = context.user_data['gc_brand']
    value = context.user_data['gc_value']
    country = context.user_data['gc_country']
    bank = context.user_data['gc_bank']
    photo_id = context.user_data['gc_photo_id']

    save_user_email(user.id, user.username or 'NoUsername', email)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transaction_ref = generate_transaction_ref()

    log_transaction(
        user_id=user.id,
        username=user.username or 'NoUsername',
        order_type='Sell',
        details=f"{brand} Gift Card ({country}) — Bank: {bank[:30]}",
        amount=f"${value:,.2f}",
        timestamp=timestamp,
        email=email
    )

    admin_message = (
        f"🎴 New Gift Card Sell Order\n\n"
        f"📋 Ref: {transaction_ref}\n"
        f"👤 User: @{user.username or 'N/A'} (ID: {user.id})\n"
        f"📧 Email: {email}\n"
        f"🎁 Brand: {brand}\n"
        f"🌍 Country: {country}\n"
        f"💵 Value: ${value:,.2f}\n"
        f"⏰ Time: {timestamp}\n\n"
        f"💳 Payout Details:\n{bank}"
    )

    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"Gift card image — Ref {transaction_ref}")

    # Receipt email on creation
    send_confirmation_email(
        email,
        "LEEH Exchange — Gift Card Sell Order Received",
        f"Hi {user.first_name or 'there'},\n\n"
        f"We've received your {brand} gift card sell request.\n\n"
        f"Order Reference : {transaction_ref}\n"
        f"Brand           : {brand}\n"
        f"Value           : ${value:,.2f}\n"
        f"Country/Region  : {country}\n"
        f"Status          : Pending Verification\n\n"
        f"We will verify the card and process your payment shortly.\n\n"
        f"Thank you for choosing LEEH Exchange!\n"
        f"— The LEEH Exchange Team"
    )

    await update.message.reply_text(
        f"✅ Order Submitted!\n\n"
        f"Your {brand} gift card sell request has been received.\n"
        f"Reference: {transaction_ref}\n"
        f"Value: ${value:,.2f}\n\n"
        f"📧 A receipt has been sent to {email}.\n\n"
        f"Thank you for using LEEH Exchange!"
    )

    logger.info(f"Gift card sell order completed for user {user.id}")
    return ConversationHandler.END


# --- BUY GIFT CARD FLOW ---
async def start_buy_giftcard(update: Update, context: CallbackContext):
    """Start gift card buying process"""
    await update.message.reply_text(
        "🎁 Buy Gift Card\n\nSelect the gift card brand you want to buy:",
        reply_markup=_gc_brand_keyboard("bgc")
    )
    logger.info(f"User {update.effective_user.id} started gift card buying")
    return BUY_GC_BRAND


async def buy_gc_brand_selected(update: Update, context: CallbackContext):
    """Handle gift card brand selection (buy)"""
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_main":
        await start(update, context)
        return ConversationHandler.END

    brand = query.data.replace("bgc_", "")
    context.user_data['gc_brand'] = brand

    await query.edit_message_text(
        f"🎁 {brand} Gift Card\n\n"
        f"Enter the card value you want to buy in USD (e.g. 25, 50, 100):"
    )
    return BUY_GC_VALUE


async def buy_gc_value_entered(update: Update, context: CallbackContext):
    """Handle desired gift card value (buy)"""
    try:
        value = float(update.message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid value!\n\nPlease enter a valid number (e.g. 25, 50):")
        return BUY_GC_VALUE

    context.user_data['gc_value'] = value
    await update.message.reply_text(
        "📧 Recipient Email\n\n"
        "Enter the email address where the gift card code should be delivered:"
    )
    return BUY_GC_RECIPIENT


async def buy_gc_recipient_entered(update: Update, context: CallbackContext):
    """Handle recipient email (buy)"""
    import re
    recipient = update.message.text.strip()
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', recipient):
        await update.message.reply_text("❌ Invalid email!\n\nPlease enter a valid recipient email:")
        return BUY_GC_RECIPIENT

    context.user_data['gc_recipient'] = recipient
    brand = context.user_data['gc_brand']
    value = context.user_data['gc_value']

    await update.message.reply_text(
        f"📝 Order Summary\n\n"
        f"Brand: {brand}\n"
        f"Value: ${value:,.2f}\n"
        f"Deliver to: {recipient}\n\n"
        f"💳 Payment Instructions:{BANK_DETAILS}\n\n"
        f"📸 Please upload your payment screenshot to complete the order:"
    )
    return BUY_GC_PROOF


async def buy_gc_proof_uploaded(update: Update, context: CallbackContext):
    """Handle payment proof upload (buy gift card)"""
    if not update.message.photo:
        await update.message.reply_text("📸 Please upload a screenshot of your payment.")
        return BUY_GC_PROOF

    context.user_data['gc_payment_photo_id'] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "📧 Almost done!\n\n"
        "Enter your contact email so we can send you a confirmation when your code is delivered:"
    )
    return BUY_GC_EMAIL


async def buy_gc_email_entered(update: Update, context: CallbackContext):
    """Finalize buy gift card order"""
    import re
    email = update.message.text.strip()
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        await update.message.reply_text("❌ Invalid email!\n\nPlease enter a valid email:")
        return BUY_GC_EMAIL

    user = update.effective_user
    brand = context.user_data['gc_brand']
    value = context.user_data['gc_value']
    recipient = context.user_data['gc_recipient']
    photo_id = context.user_data['gc_payment_photo_id']

    save_user_email(user.id, user.username or 'NoUsername', email)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transaction_ref = generate_transaction_ref()

    log_transaction(
        user_id=user.id,
        username=user.username or 'NoUsername',
        order_type='Buy',
        details=f"{brand} Gift Card → {recipient}",
        amount=f"${value:,.2f}",
        timestamp=timestamp,
        email=email
    )

    admin_message = (
        f"🎁 New Gift Card Buy Order\n\n"
        f"📋 Ref: {transaction_ref}\n"
        f"👤 User: @{user.username or 'N/A'} (ID: {user.id})\n"
        f"📧 Contact Email: {email}\n"
        f"📨 Deliver Code To: {recipient}\n"
        f"🎁 Brand: {brand}\n"
        f"💵 Value: ${value:,.2f}\n"
        f"⏰ Time: {timestamp}"
    )

    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"Payment proof — Ref {transaction_ref}")

    await update.message.reply_text(
        f"✅ Order Submitted!\n\n"
        f"Your {brand} gift card order has been received.\n"
        f"Reference: {transaction_ref}\n"
        f"Value: ${value:,.2f}\n\n"
        f"Once we verify your payment, the gift card code will be sent to {recipient}. "
        f"A confirmation will also be sent to {email}.\n\n"
        f"Thank you for using LEEH Exchange!"
    )

    logger.info(f"Gift card buy order completed for user {user.id}")
    return ConversationHandler.END


# --- AIRTIME FLOW ---
async def start_airtime(update: Update, context: CallbackContext):
    """Start airtime purchase"""
    keyboard = [
        [InlineKeyboardButton("MTN", callback_data="airtime_mtn")],
        [InlineKeyboardButton("Airtel", callback_data="airtime_airtel")],
        [InlineKeyboardButton("Glo", callback_data="airtime_glo")],
        [InlineKeyboardButton("9mobile", callback_data="airtime_9mobile")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "📱 Buy Airtime\n\nSelect your network:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"User {update.effective_user.id} started airtime purchase")
    return NETWORK_SELECT

async def airtime_network_selected(update: Update, context: CallbackContext):
    """Handle airtime network selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_main":
        await start(update, context)
        return ConversationHandler.END
    
    network = query.data.replace("airtime_", "").upper()
    context.user_data['network'] = network
    
    await query.edit_message_text(
        f"📱 {network} Airtime\n\n"
        f"Enter the amount (₦50 - ₦10,000):",
        parse_mode='Markdown'
    )
    
    logger.info(f"User {query.from_user.id} selected {network} for airtime")
    return AMOUNT_INPUT

async def airtime_amount_entered(update: Update, context: CallbackContext):
    """Handle airtime amount input"""
    try:
        amount = int(update.message.text)
        if amount < 50 or amount > 10000:
            await update.message.reply_text(
                "❌ Invalid amount!\n\n"
                "Amount must be between ₦50 and ₦10,000"
            )
            return AMOUNT_INPUT
        
        context.user_data['amount'] = amount
        
        await update.message.reply_text(
            "📞 Phone Number\n\n"
            "Enter the phone number to recharge:\n"
            "Format: 08012345678"
        )
        
        return PHONE_INPUT
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount!\n\n"
            "Please enter a valid number (e.g., 100, 500, 1000)"
        )
        return AMOUNT_INPUT

async def airtime_phone_entered(update: Update, context: CallbackContext):
    """Handle airtime phone input"""
    phone = update.message.text.strip()
    
    # Basic phone validation
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text(
            "❌ Invalid phone number!\n\n"
            "Please enter a valid phone number"
        )
        return PHONE_INPUT
    
    context.user_data['phone'] = phone
    network = context.user_data['network']
    amount = context.user_data['amount']
    
    await update.message.reply_text(
        f"✅ Airtime Order Summary\n\n"
        f"📱 Network: {network}\n"
        f"📞 Phone: {phone}\n"
        f"💰 Amount: ₦{amount:,}\n\n"
        f"💳 Payment Instructions:{BANK_DETAILS}\n\n"
        f"📸 Upload payment screenshot to proceed:",
        parse_mode='Markdown'
    )
    
    return PROOF_UPLOAD

async def airtime_proof_uploaded(update: Update, context: CallbackContext):
    """Handle airtime proof upload"""
    if not update.message.photo:
        await update.message.reply_text(
            "📸 Payment Proof Required\n\n"
            "Please upload a screenshot of your payment as proof."
        )
        return PROOF_UPLOAD
    
    user = update.effective_user
    network = context.user_data['network']
    amount = context.user_data['amount']
    phone = context.user_data['phone']
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transaction_ref = generate_transaction_ref()
    
    context.user_data['transaction_ref'] = transaction_ref
    context.user_data['transaction_timestamp'] = timestamp
    
    log_transaction(
        user_id=user.id,
        username=user.username or 'NoUsername',
        order_type='Airtime',
        details=network,
        amount=f"₦{amount:,} - {phone}",
        timestamp=timestamp
    )
    
    admin_message = (
        f"📱 New Airtime Order\n\n"
        f"📋 Ref: {transaction_ref}\n"
        f"👤 User: @{user.username or 'N/A'} ({user.id})\n"
        f"📱 Network: {network}\n"
        f"📞 Phone: {phone}\n"
        f"💰 Amount: ₦{amount:,}\n"
        f"⏰ Time: {timestamp}"
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_message,
        parse_mode='Markdown'
    )
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id
    )
    
    await update.message.reply_text(
        f"Payment Received!\n\n"
        f"Your airtime order has been submitted successfully.\n"
        f"Reference: {transaction_ref}\n"
        f"Your phone will be recharged shortly.\n\n"
        f"Thank you for using LEEH Exchange!"
    )
    
    logger.info(f"Airtime order completed for user {user.id}")
    
    await update.message.reply_text(
        "Congrats! You're eligible for a giveaway reward!\n"
        "Fill the short form below to claim your reward.\n\n"
        "Please enter your Full Name (as used in the transaction):"
    )
    return GIVEAWAY_FULLNAME

# --- DATA FLOW ---
async def start_data(update: Update, context: CallbackContext):
    """Start data purchase"""
    keyboard = [
        [InlineKeyboardButton("📦 SME Data", callback_data="data_sme")],
        [InlineKeyboardButton("🎁 Gifting Data", callback_data="data_gifting")],
        [InlineKeyboardButton("🌙 Night Plan", callback_data="data_night")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main")]
    ]
    
    await update.message.reply_text(
        "📶 Buy Data Plans\n\nSelect data type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    logger.info(f"User {update.effective_user.id} started data purchase")
    return DATA_TYPE_SELECT

async def data_type_selected(update: Update, context: CallbackContext):
    """Handle data type selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_main":
        await start(update, context)
        return ConversationHandler.END
    
    data_type = query.data.replace("data_", "").upper()
    context.user_data['data_type'] = data_type
    
    keyboard = [
        [InlineKeyboardButton("MTN", callback_data="data_net_mtn")],
        [InlineKeyboardButton("Airtel", callback_data="data_net_airtel")],
        [InlineKeyboardButton("Glo", callback_data="data_net_glo")],
        [InlineKeyboardButton("9mobile", callback_data="data_net_9mobile")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_data")]
    ]
    
    await query.edit_message_text(
        f"📶 {data_type} Data Plan\n\nSelect your network:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return DATA_NETWORK_SELECT

async def data_network_selected(update: Update, context: CallbackContext):
    """Handle data network selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_data":
        await start_data(update, context)
        return DATA_TYPE_SELECT
    
    network = query.data.replace("data_net_", "").upper()
    context.user_data['network'] = network
    data_type = context.user_data['data_type']
    
    await query.edit_message_text(
        f"📶 {network} {data_type} Data\n\n"
        f"Enter data size in MB (e.g., 500, 1024, 2048):\n"
        f"Range: 50MB - 50GB (50000MB)",
        parse_mode='Markdown'
    )
    
    logger.info(f"User {query.from_user.id} selected {network} for {data_type} data")
    return DATA_SIZE_INPUT

async def data_size_entered(update: Update, context: CallbackContext):
    """Handle data size input"""
    try:
        size_mb = int(update.message.text)
        if size_mb < 50 or size_mb > 50000:
            await update.message.reply_text(
                "❌ Invalid data size!\n\n"
                "Data size must be between 50MB and 50GB (50000MB)"
            )
            return DATA_SIZE_INPUT
        
        # Calculate price with profit markup
        price = calculate_data_price(size_mb)
        
        context.user_data['data_size'] = size_mb
        context.user_data['price'] = price
        
        await update.message.reply_text(
            f"📞 Phone Number\n\n"
            f"📦 Data Size: {size_mb}MB\n"
            f"💰 Price: ₦{price:,}\n\n"
            f"Enter the phone number to receive data:\n"
            f"Format: 08012345678"
        )
        
        return DATA_PHONE_INPUT
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid data size!\n\n"
            "Please enter a valid number in MB (e.g., 500, 1024, 2048)"
        )
        return DATA_SIZE_INPUT

async def data_phone_entered(update: Update, context: CallbackContext):
    """Handle data phone input"""
    phone = update.message.text.strip()
    
    # Basic phone validation
    if not phone.isdigit() or len(phone) < 10:
        await update.message.reply_text(
            "❌ Invalid phone number!\n\n"
            "Please enter a valid phone number"
        )
        return DATA_PHONE_INPUT
    
    context.user_data['phone'] = phone
    network = context.user_data['network']
    data_type = context.user_data['data_type']
    data_size = context.user_data['data_size']
    price = context.user_data['price']
    
    await update.message.reply_text(
        f"✅ Data Order Summary\n\n"
        f"📶 Network: {network}\n"
        f"📦 Type: {data_type}\n"
        f"📞 Phone: {phone}\n"
        f"📊 Size: {data_size}MB\n"
        f"💰 Amount: ₦{price:,}\n\n"
        f"💳 Payment Instructions:{BANK_DETAILS}\n\n"
        f"📸 Upload payment screenshot to proceed:",
        parse_mode='Markdown'
    )
    
    return DATA_PROOF_UPLOAD

async def data_proof_uploaded(update: Update, context: CallbackContext):
    """Handle data proof upload"""
    if not update.message.photo:
        await update.message.reply_text(
            "📸 Payment Proof Required\n\n"
            "Please upload a screenshot of your payment as proof."
        )
        return DATA_PROOF_UPLOAD
    
    user = update.effective_user
    network = context.user_data['network']
    data_type = context.user_data['data_type']
    data_size = context.user_data['data_size']
    price = context.user_data['price']
    phone = context.user_data['phone']
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    transaction_ref = generate_transaction_ref()
    
    context.user_data['transaction_ref'] = transaction_ref
    context.user_data['transaction_timestamp'] = timestamp
    
    log_transaction(
        user_id=user.id,
        username=user.username or 'NoUsername',
        order_type='Data',
        details=f"{network} {data_type}",
        amount=f"{data_size}MB - ₦{price:,} - {phone}",
        timestamp=timestamp
    )
    
    admin_message = (
        f"📶 New Data Order\n\n"
        f"📋 Ref: {transaction_ref}\n"
        f"👤 User: @{user.username or 'N/A'} ({user.id})\n"
        f"📶 Network: {network}\n"
        f"📦 Type: {data_type}\n"
        f"📞 Phone: {phone}\n"
        f"📊 Size: {data_size}MB\n"
        f"💰 Amount: ₦{price:,}\n"
        f"⏰ Time: {timestamp}"
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_message,
        parse_mode='Markdown'
    )
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id
    )
    
    await update.message.reply_text(
        f"Payment Received!\n\n"
        f"Your data order has been submitted successfully.\n"
        f"Reference: {transaction_ref}\n"
        f"Data will be sent to your phone shortly.\n\n"
        f"Thank you for using LEEH Exchange!"
    )
    
    logger.info(f"Data order completed for user {user.id}")
    
    await update.message.reply_text(
        "Congrats! You're eligible for a giveaway reward!\n"
        "Fill the short form below to claim your reward.\n\n"
        "Please enter your Full Name (as used in the transaction):"
    )
    return GIVEAWAY_FULLNAME

# --- GIVEAWAY CLAIM FORM ---
async def start_giveaway_form(update: Update, context: CallbackContext):
    """Start the giveaway claim form after transaction"""
    transaction_ref = context.user_data.get('transaction_ref', '')
    user_id = update.effective_user.id
    
    if transaction_ref and check_giveaway_claimed(transaction_ref, user_id):
        await update.message.reply_text(
            "You have already claimed this transaction's giveaway.",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
                [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")]
            ], resize_keyboard=True)
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Congrats! You're eligible for a giveaway reward!\n"
        "Fill the short form below to claim your reward.\n\n"
        "Please enter your Full Name (as used in the transaction):"
    )
    return GIVEAWAY_FULLNAME

async def giveaway_fullname_entered(update: Update, context: CallbackContext):
    """Handle full name input"""
    full_name = update.message.text.strip()
    if len(full_name) < 2:
        await update.message.reply_text("Please enter a valid full name:")
        return GIVEAWAY_FULLNAME
    
    context.user_data['giveaway_fullname'] = full_name
    
    await update.message.reply_text(
        "Please enter your Telegram Username (e.g. @username):"
    )
    return GIVEAWAY_USERNAME

async def giveaway_username_entered(update: Update, context: CallbackContext):
    """Handle username input"""
    username = update.message.text.strip()
    context.user_data['giveaway_username'] = username
    
    keyboard = [
        [InlineKeyboardButton("Buy Crypto", callback_data="giveaway_type_buy_crypto")],
        [InlineKeyboardButton("Sell Crypto", callback_data="giveaway_type_sell_crypto")],
        [InlineKeyboardButton("Gift Card", callback_data="giveaway_type_giftcard")],
        [InlineKeyboardButton("Airtime / Data", callback_data="giveaway_type_airtime_data")],
        [InlineKeyboardButton("Other", callback_data="giveaway_type_other")]
    ]
    
    await update.message.reply_text(
        "Select your Transaction Type:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GIVEAWAY_TYPE

async def giveaway_type_selected(update: Update, context: CallbackContext):
    """Handle transaction type selection"""
    query = update.callback_query
    await query.answer()
    
    type_map = {
        "giveaway_type_buy_crypto": "Buy Crypto",
        "giveaway_type_sell_crypto": "Sell Crypto",
        "giveaway_type_giftcard": "Gift Card",
        "giveaway_type_airtime_data": "Airtime / Data",
        "giveaway_type_other": "Other"
    }
    
    transaction_type = type_map.get(query.data, "Other")
    context.user_data['giveaway_transaction_type'] = transaction_type
    
    existing_ref = context.user_data.get('transaction_ref', '')
    
    if existing_ref:
        context.user_data['giveaway_reference'] = existing_ref
        await query.edit_message_text(
            f"Transaction Reference: {existing_ref}\n\n"
            "Enter the Amount involved in the transaction (e.g. $100 or N5000):"
        )
        return GIVEAWAY_AMOUNT
    else:
        await query.edit_message_text(
            "Enter your Transaction Reference / Order ID:"
        )
        return GIVEAWAY_REFERENCE

async def giveaway_reference_entered(update: Update, context: CallbackContext):
    """Handle transaction reference input"""
    reference = update.message.text.strip()
    context.user_data['giveaway_reference'] = reference
    
    await update.message.reply_text(
        "Enter the Amount involved in the transaction (e.g. $100 or N5000):"
    )
    return GIVEAWAY_AMOUNT

async def giveaway_amount_entered(update: Update, context: CallbackContext):
    """Handle amount input"""
    amount = update.message.text.strip()
    context.user_data['giveaway_amount'] = amount
    
    existing_date = context.user_data.get('transaction_timestamp', '')
    
    if existing_date:
        context.user_data['giveaway_date'] = existing_date
        await update.message.reply_text(
            f"Transaction Date: {existing_date}\n\n"
            "Please upload Proof of Transaction (screenshot or receipt image):"
        )
        return GIVEAWAY_PROOF
    else:
        await update.message.reply_text(
            "Enter the Date & Time of Transaction (e.g. 2025-12-17 10:30):"
        )
        return GIVEAWAY_DATE

async def giveaway_date_entered(update: Update, context: CallbackContext):
    """Handle date input"""
    date_text = update.message.text.strip()
    context.user_data['giveaway_date'] = date_text
    
    await update.message.reply_text(
        "Please upload Proof of Transaction (screenshot or receipt image):"
    )
    return GIVEAWAY_PROOF

async def giveaway_proof_uploaded(update: Update, context: CallbackContext):
    """Handle proof upload"""
    if not update.message.photo:
        await update.message.reply_text(
            "Please upload an image as proof of transaction:"
        )
        return GIVEAWAY_PROOF
    
    context.user_data['giveaway_proof_file_id'] = update.message.photo[-1].file_id
    
    keyboard = [
        [InlineKeyboardButton("Cashback", callback_data="reward_cashback")],
        [InlineKeyboardButton("Discount on next transaction", callback_data="reward_discount")],
        [InlineKeyboardButton("Bonus credit", callback_data="reward_bonus")],
        [InlineKeyboardButton("Any available reward", callback_data="reward_any")]
    ]
    
    await update.message.reply_text(
        "Select your Preferred Giveaway Reward (Optional):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GIVEAWAY_REWARD

async def giveaway_reward_selected(update: Update, context: CallbackContext):
    """Handle reward selection"""
    query = update.callback_query
    await query.answer()
    
    reward_map = {
        "reward_cashback": "Cashback",
        "reward_discount": "Discount on next transaction",
        "reward_bonus": "Bonus credit",
        "reward_any": "Any available reward"
    }
    
    reward = reward_map.get(query.data, "Any available reward")
    context.user_data['giveaway_reward'] = reward
    
    keyboard = [
        [InlineKeyboardButton("I Confirm - Submit", callback_data="giveaway_confirm_yes")],
        [InlineKeyboardButton("Cancel", callback_data="giveaway_confirm_no")]
    ]
    
    await query.edit_message_text(
        "Confirmation:\n\n"
        "\"I confirm that the information provided is correct and belongs to me.\"\n\n"
        "Click below to submit your giveaway claim:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GIVEAWAY_CONFIRM

async def giveaway_confirm_action(update: Update, context: CallbackContext):
    """Handle confirmation"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "giveaway_confirm_no":
        await query.edit_message_text(
            "Giveaway claim cancelled. You can claim later after another transaction."
        )
        return ConversationHandler.END
    
    user = update.effective_user
    full_name = context.user_data.get('giveaway_fullname', 'N/A')
    tg_username = context.user_data.get('giveaway_username', f'@{user.username}' if user.username else 'N/A')
    transaction_type = context.user_data.get('giveaway_transaction_type', 'N/A')
    reference = context.user_data.get('giveaway_reference', 'N/A')
    amount = context.user_data.get('giveaway_amount', 'N/A')
    transaction_date = context.user_data.get('giveaway_date', 'N/A')
    reward = context.user_data.get('giveaway_reward', 'Any available reward')
    proof_file_id = context.user_data.get('giveaway_proof_file_id')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    log_giveaway_claim(
        user_id=user.id,
        username=user.username or 'NoUsername',
        full_name=full_name,
        transaction_type=transaction_type,
        transaction_ref=reference,
        amount=amount,
        transaction_date=transaction_date,
        reward_choice=reward
    )
    
    admin_message = (
        "GIVEAWAY CLAIM SUBMISSION\n\n"
        f"Full Name: {full_name}\n"
        f"Telegram Username: {tg_username}\n"
        f"User ID: {user.id}\n"
        f"Transaction Type: {transaction_type}\n"
        f"Transaction Reference: {reference}\n"
        f"Amount: {amount}\n"
        f"Transaction Date: {transaction_date}\n"
        f"Preferred Reward: {reward}\n"
        f"Submission Time: {timestamp}"
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_message
    )
    
    if proof_file_id:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=proof_file_id,
            caption="Giveaway Claim - Transaction Proof"
        )
    
    await query.edit_message_text(
        "Submission received successfully!\n"
        "Our team will verify your details and contact you shortly.\n\n"
        "Thank you for participating in the LEEH Exchange giveaway!"
    )
    
    logger.info(f"Giveaway claim submitted by user {user.id}")
    return ConversationHandler.END

async def skip_giveaway(update: Update, context: CallbackContext):
    """Skip giveaway form"""
    await update.message.reply_text(
        "Giveaway claim skipped. You can always claim later!",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
            [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")]
        ], resize_keyboard=True)
    )
    return ConversationHandler.END

# --- MESSAGE HANDLERS ---
async def handle_message(update: Update, context: CallbackContext):
    """Handle text messages that aren't covered by ConversationHandlers"""
    await update.message.reply_text(
        "Please choose an option from the menu below.",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
            [KeyboardButton("🎁 Buy Gift Card"), KeyboardButton("🎴 Sell Gift Card")],
            [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")]
        ], resize_keyboard=True)
    )

# --- CRYPTO RATES FEATURE ---
async def show_crypto_rates_menu(update: Update, context: CallbackContext):
    """Show crypto rates category selection"""
    keyboard = []
    for category in COIN_CATEGORIES.keys():
        keyboard.append([InlineKeyboardButton(category, callback_data=f"rates_{category}")])
    keyboard.append([InlineKeyboardButton("📊 View All Top 40", callback_data="rates_all")])
    
    await update.message.reply_text(
        "📈 Crypto Rates\n\n"
        "Select a category to view live cryptocurrency prices:\n\n"
        "_Prices are fetched in real-time from CoinGecko_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_rates_callback(update: Update, context: CallbackContext):
    """Handle crypto rates category selection"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "rates_all":
        # Show all coins
        all_coins = list(EXTENDED_COIN_IDS.keys())
        await query.edit_message_text("⏳ Fetching prices for all 40 cryptocurrencies...")
        
        prices = get_multiple_crypto_prices(all_coins)
        
        if not prices:
            await query.edit_message_text(
                "❌ Unable to fetch prices. Please try again later.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="rates_all")]])
            )
            return
        
        # Format all prices
        message = "📊 All Cryptocurrency Rates\n\n"
        for symbol in all_coins:
            if symbol in prices:
                message += format_rate_display(symbol, prices[symbol]) + "\n\n"
        
        message += "_Updated just now • Powered by CoinGecko_"
        
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="rates_all")],
                    [InlineKeyboardButton("⬅️ Back to Categories", callback_data="rates_menu")]]
        
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "rates_menu":
        # Show category menu
        keyboard = []
        for category in COIN_CATEGORIES.keys():
            keyboard.append([InlineKeyboardButton(category, callback_data=f"rates_{category}")])
        keyboard.append([InlineKeyboardButton("📊 View All Top 40", callback_data="rates_all")])
        
        await query.edit_message_text(
            "📈 Crypto Rates\n\n"
            "Select a category to view live cryptocurrency prices:\n\n"
            "_Prices are fetched in real-time from CoinGecko_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data.startswith("rates_"):
        category = data.replace("rates_", "")
        
        if category in COIN_CATEGORIES:
            coins = COIN_CATEGORIES[category]
            await query.edit_message_text(f"⏳ Fetching {category} prices...")
            
            prices = get_multiple_crypto_prices(coins)
            
            if not prices:
                await query.edit_message_text(
                    "❌ Unable to fetch prices. Please try again later.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data=data)]])
                )
                return
            
            message = f"📈 {category}\n\n"
            for symbol in coins:
                if symbol in prices:
                    message += format_rate_display(symbol, prices[symbol]) + "\n\n"
            
            message += "_Updated just now • Powered by CoinGecko_"
            
            keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data=data)],
                        [InlineKeyboardButton("⬅️ Back to Categories", callback_data="rates_menu")]]
            
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def cancel(update: Update, context: CallbackContext):
    """Cancel current operation"""
    await update.message.reply_text(
        "Operation cancelled. Choose an option from the menu below:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("🟢 Buy Crypto"), KeyboardButton("🔴 Sell Crypto")],
            [KeyboardButton("🎁 Buy Gift Card"), KeyboardButton("🎴 Sell Gift Card")],
            [KeyboardButton("📱 Buy Airtime"), KeyboardButton("📶 Buy Data")],
            [KeyboardButton("📈 Crypto Rates")]
        ], resize_keyboard=True)
    )
    return ConversationHandler.END

# --- CONVERSATION HANDLERS ---
def setup_handlers(app):
    """Setup all conversation handlers"""
    
    # Buy crypto conversation
    buy_crypto_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🟢 Buy Crypto$"), start_buy_crypto)],
        states={
            SELECTING_CRYPTO: [CallbackQueryHandler(crypto_selected)],
            ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered)],
            ENTERING_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_entered)],
            ENTERING_EMAIL_BUY: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_entered_buy)],
            UPLOADING_PROOF: [MessageHandler(filters.PHOTO, proof_uploaded)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Sell crypto conversation
    sell_crypto_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔴 Sell Crypto$"), start_sell_crypto)],
        states={
            SELECTING_CRYPTO: [CallbackQueryHandler(crypto_selected)],
            ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_amount_entered)],
            SELL_CONFIRM_PAYMENT: [CallbackQueryHandler(sell_payment_confirmed)],
            SELL_BANK_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_bank_details_entered)],
            ENTERING_EMAIL_SELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email_entered_sell)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Airtime conversation
    airtime_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📱 Buy Airtime$"), start_airtime)],
        states={
            NETWORK_SELECT: [CallbackQueryHandler(airtime_network_selected)],
            AMOUNT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, airtime_amount_entered)],
            PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, airtime_phone_entered)],
            PROOF_UPLOAD: [MessageHandler(filters.PHOTO, airtime_proof_uploaded)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Data conversation
    data_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📶 Buy Data$"), start_data)],
        states={
            DATA_TYPE_SELECT: [CallbackQueryHandler(data_type_selected)],
            DATA_NETWORK_SELECT: [CallbackQueryHandler(data_network_selected)],
            DATA_SIZE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, data_size_entered)],
            DATA_PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, data_phone_entered)],
            DATA_PROOF_UPLOAD: [MessageHandler(filters.PHOTO, data_proof_uploaded)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    
    # Giveaway claim conversation
    giveaway_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎁 Claim Giveaway$"), start_giveaway_form)],
        states={
            GIVEAWAY_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, giveaway_fullname_entered)],
            GIVEAWAY_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, giveaway_username_entered)],
            GIVEAWAY_TYPE: [CallbackQueryHandler(giveaway_type_selected)],
            GIVEAWAY_REFERENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, giveaway_reference_entered)],
            GIVEAWAY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, giveaway_amount_entered)],
            GIVEAWAY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, giveaway_date_entered)],
            GIVEAWAY_PROOF: [MessageHandler(filters.PHOTO, giveaway_proof_uploaded)],
            GIVEAWAY_REWARD: [CallbackQueryHandler(giveaway_reward_selected)],
            GIVEAWAY_CONFIRM: [CallbackQueryHandler(giveaway_confirm_action)]
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("skip", skip_giveaway)],
        allow_reentry=True
    )
    
    # Sell gift card conversation
    sell_giftcard_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎴 Sell Gift Card$"), start_sell_giftcard)],
        states={
            SELL_GC_BRAND: [CallbackQueryHandler(sell_gc_brand_selected)],
            SELL_GC_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_gc_value_entered)],
            SELL_GC_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_gc_country_entered)],
            SELL_GC_PROOF: [MessageHandler(filters.PHOTO, sell_gc_proof_uploaded)],
            SELL_GC_BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_gc_bank_entered)],
            SELL_GC_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_gc_email_entered)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Buy gift card conversation
    buy_giftcard_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎁 Buy Gift Card$"), start_buy_giftcard)],
        states={
            BUY_GC_BRAND: [CallbackQueryHandler(buy_gc_brand_selected)],
            BUY_GC_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_gc_value_entered)],
            BUY_GC_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_gc_recipient_entered)],
            BUY_GC_PROOF: [MessageHandler(filters.PHOTO, buy_gc_proof_uploaded)],
            BUY_GC_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_gc_email_entered)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Create filter that excludes conversation entry points
    menu_filter = (
        filters.TEXT & 
        ~filters.COMMAND & 
        ~filters.Regex("^🟢 Buy Crypto$") &
        ~filters.Regex("^🔴 Sell Crypto$") &
        ~filters.Regex("^🎁 Buy Gift Card$") &
        ~filters.Regex("^🎴 Sell Gift Card$") &
        ~filters.Regex("^📱 Buy Airtime$") &
        ~filters.Regex("^📶 Buy Data$") &
        ~filters.Regex("^🎁 Claim Giveaway$") &
        ~filters.Regex("^📈 Crypto Rates$") &
        ~filters.Regex("^🎁 Daily Reward$") &
        ~filters.Regex("^🔔 Set Price Alert$") &
        ~filters.Regex("^🎮 Play BTC Game$") &
        ~filters.Regex("^🎟️ Use Points$") &
        ~filters.Regex("^🔗 My Referral$")
    )
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(buy_crypto_handler)
    app.add_handler(sell_crypto_handler)
    app.add_handler(buy_giftcard_handler)
    app.add_handler(sell_giftcard_handler)
    app.add_handler(airtime_handler)
    app.add_handler(data_handler)
    app.add_handler(giveaway_handler)
    
    # Crypto rates handlers
    app.add_handler(MessageHandler(filters.Regex("^📈 Crypto Rates$"), show_crypto_rates_menu))
    app.add_handler(CallbackQueryHandler(handle_rates_callback, pattern="^rates_"))
    
    # Daily reward handler
    app.add_handler(MessageHandler(filters.Regex("^🎁 Daily Reward$"), claim_daily_reward))
    
    # Point usage conversation
    discount_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎟️ Use Points$"), use_points_for_discount)],
        states={
            ENTERING_DISCOUNT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, discount_code_entered)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(discount_handler)
    
    # Set up alert monitoring job (check if JobQueue is available)
    if app.job_queue:
        app.job_queue.run_repeating(check_price_alerts, interval=60, first=10)
    else:
        logger.warning("JobQueue not available. Price alerts will not be monitored in background.")
    
    # Price alert conversation
    alert_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔔 Set Price Alert$"), start_price_alert)],
        states={
            SETTING_ALERT_COIN: [CallbackQueryHandler(alert_coin_selected)],
            SETTING_ALERT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_price_entered)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(alert_handler)
    
    # Game conversation
    game_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎮 Play BTC Game$"), start_prediction_game)],
        states={
            MAKING_PREDICTION: [CallbackQueryHandler(handle_prediction, pattern="^predict_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )
    app.add_handler(game_handler)
    
    app.add_handler(MessageHandler(filters.Regex("^🔗 My Referral$"), show_referral_info))
    app.add_handler(MessageHandler(menu_filter, handle_message))

# --- MAIN FUNCTION ---
async def log_unhandled_update_error(update, context):
    """Record errors from individual update handlers without stopping polling."""
    error = context.error
    if error:
        logger.error(
            "Unhandled Telegram update error",
            exc_info=(type(error), error, error.__traceback__),
        )
    else:
        logger.error("Telegram update handler failed without an exception detail")


def main():
    """Main function"""
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not configured; refusing to start the Telegram bot")
        raise SystemExit(2)

    print("🚀 Starting LEEH Exchange Bot...")

    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .persistence(persistence)
        .connect_timeout(15)
        .read_timeout(35)
        .write_timeout(35)
        .pool_timeout(15)
        .get_updates_connect_timeout(15)
        .get_updates_read_timeout(35)
        .get_updates_write_timeout(35)
        .get_updates_pool_timeout(15)
        .build()
    )
    setup_handlers(app)
    app.add_error_handler(log_unhandled_update_error)

    logger.info("LEEH Exchange Bot is running...")
    print("✅ Bot is running and waiting for messages...")

    app.run_polling(
        drop_pending_updates=False,
        bootstrap_retries=-1,
        timeout=20,
    )

if __name__ == '__main__':
    main()