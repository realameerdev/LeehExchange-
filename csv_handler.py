"""
CSV handling functions for LEEH Exchange Bot
Manages transaction logging and order history
"""

import csv
import os
from datetime import datetime
from telebot.types import InputFile

CSV_FILE = "transactions.csv"
CSV_HEADERS = ["UserID", "Username", "Type", "Coin", "Amount", "Wallet/Bank", "Timestamp"]

def initialize_csv():
    """Initialize CSV file with headers if it doesn't exist"""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)

def log_admin_activity(activity_type, details):
    """Log admin activities for audit trail"""
    try:
        file_path = 'admin_activity.csv'
        header = ['Timestamp', 'Activity', 'Details']
        file_exists = os.path.isfile(file_path)
        
        with open(file_path, mode='a', newline='', encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=header)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                'Timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Activity': activity_type,
                'Details': details
            })
    except Exception as e:
        print(f"Error logging admin activity: {e}")

def log_order(user_id, username, order_type, coin, amount, wallet_or_bank, timestamp=None):
    """
    Log an order to CSV file
    
    Args:
        user_id (int): Telegram user ID
        username (str): Telegram username
        order_type (str): 'Buy' or 'Sell'
        coin (str): Cryptocurrency symbol
        amount (str): Amount of cryptocurrency
        wallet_or_bank (str): Wallet address or bank details
        timestamp (str, optional): Timestamp, defaults to current time
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([user_id, username, order_type, coin, amount, wallet_or_bank, timestamp])
    except Exception as e:
        print(f"Error logging order: {e}")

def get_user_orders(user_id):
    """
    Get all orders for a specific user
    
    Args:
        user_id (int): Telegram user ID
    
    Returns:
        list: List of order dictionaries
    """
    orders = []
    try:
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if int(row['UserID']) == user_id:
                        orders.append(row)
    except Exception as e:
        print(f"Error reading orders: {e}")
    
    return orders

def format_user_orders(user_id):
    """
    Format user orders for display
    
    Args:
        user_id (int): Telegram user ID
    
    Returns:
        str: Formatted order history
    """
    orders = get_user_orders(user_id)
    
    if not orders:
        return "📋 **Your Order History**\n\nNo orders found yet."
    
    response = f"📋 **Your Order History** ({len(orders)} orders)\n\n"
    
    for order in orders:
        order_type = order['Type'].upper()
        emoji = "🟢" if order_type == "BUY" else "🔴"
        response += f"{emoji} **{order_type}** | {order['Coin']} | {order['Amount']}\n"
        response += f"📅 {order['Timestamp']}\n"
        response += f"💼 {order['Wallet/Bank'][:50]}{'...' if len(order['Wallet/Bank']) > 50 else ''}\n\n"
    
    return response

def create_user_orders_file(user_id):
    """
    Create a text file with user's orders
    
    Args:
        user_id (int): Telegram user ID
    
    Returns:
        str: Filename of created file
    """
    orders = get_user_orders(user_id)
    filename = f"orders_{user_id}.txt"
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"LEEH Exchange - Order History for User {user_id}\n")
            f.write("=" * 50 + "\n\n")
            
            if not orders:
                f.write("No orders found.\n")
            else:
                for order in orders:
                    f.write(f"[{order['Type'].upper()}] {order['Coin']} | {order['Amount']}\n")
                    f.write(f"Wallet/Bank: {order['Wallet/Bank']}\n")
                    f.write(f"Timestamp: {order['Timestamp']}\n")
                    f.write("-" * 30 + "\n\n")
        
        return filename
    except Exception as e:
        print(f"Error creating orders file: {e}")
        return None