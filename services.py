"""
Service functions for LEEH Exchange Bot
Handles API calls and business logic
"""

import requests
import logging
from config import COINGECKO_IDS

logger = logging.getLogger(__name__)

def get_crypto_price(coin_symbol):
    """
    Fetch real-time cryptocurrency price from CoinGecko API
    
    Args:
        coin_symbol (str): Cryptocurrency symbol (e.g., 'BTC', 'ETH')
    
    Returns:
        float or str: Current price in USD, or 'N/A' if failed
    """
    try:
        # Get the CoinGecko ID for the coin
        coin_id = COINGECKO_IDS.get(coin_symbol.upper())
        if not coin_id:
            logger.warning(f"Unknown coin symbol: {coin_symbol}")
            return "N/A"
        
        # Make API request to CoinGecko
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        price = data.get(coin_id, {}).get('usd')
        
        if price is not None:
            logger.info(f"Successfully fetched price for {coin_symbol}: ${price}")
            return price
        else:
            logger.warning(f"Price not found in response for {coin_symbol}")
            return "N/A"
            
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed for {coin_symbol}: {e}")
        return "N/A"
    except Exception as e:
        logger.error(f"Unexpected error fetching price for {coin_symbol}: {e}")
        return "N/A"

def format_price(price):
    """
    Format price for display
    
    Args:
        price (float or str): Price value
    
    Returns:
        str: Formatted price string
    """
    if price == "N/A":
        return "Price unavailable"
    
    try:
        price_float = float(price)
        if price_float >= 1:
            return f"${price_float:,.2f}"
        else:
            return f"${price_float:.6f}"
    except (ValueError, TypeError):
        return "Price unavailable"

def validate_amount(amount_str):
    """
    Validate if the amount string is a valid number
    
    Args:
        amount_str (str): Amount as string
    
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        amount = float(amount_str)
        return amount > 0
    except (ValueError, TypeError):
        return False

def format_order_details(order_data, order_type):
    """
    Format order details for admin notification
    
    Args:
        order_data (dict): Order information
        order_type (str): 'buy' or 'sell'
    
    Returns:
        str: Formatted order details
    """
    if order_type == "buy":
        return f"""
📥 **New Buy Order**

💰 Coin: **{order_data.get('coin', 'N/A')}**
💵 Amount: **{order_data.get('amount', 'N/A')}**
🏦 Wallet: `{order_data.get('wallet', 'N/A')}`
👤 User: @{order_data.get('username', 'N/A')} ({order_data.get('user_id', 'N/A')})

⏰ Payment proof has been submitted for review.
"""
    else:  # sell
        return f"""
📤 **New Sell Order**

💰 Coin: **{order_data.get('coin', 'N/A')}**
💵 Amount Sent: **{order_data.get('amount', 'N/A')}**
🏦 Bank Details: 
{order_data.get('bank_details', 'N/A')}
👤 User: @{order_data.get('username', 'N/A')} ({order_data.get('user_id', 'N/A')})

⏰ Waiting for payment processing.
"""
