#!/usr/bin/env python3
"""
LEEH Exchange Bot - Main entry point
A Telegram bot for cryptocurrency exchange with buy/sell flows and real-time pricing
"""

import os
import time
import logging
from config import bot, user_state
from handlers import setup_handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main function to start the bot"""
    try:
        # Setup all message handlers
        setup_handlers(bot, user_state)
        
        logger.info("LEEH Exchange Bot is starting...")
        logger.info("Bot is running and waiting for messages...")
        
        # Clear any pending updates first to avoid conflicts
        try:
            bot.get_updates(offset=-1)
        except Exception as e:
            logger.warning(f"Could not clear pending updates: {e}")
        
        # Start the bot with infinity polling and conflict handling
        bot.infinity_polling(
            timeout=10, 
            long_polling_timeout=5,
            allowed_updates=None,
            skip_pending=True
        )
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        
        # Try alternative polling method if main method fails
        try:
            logger.info("Attempting alternative polling method...")
            while True:
                try:
                    updates = bot.get_updates(timeout=10)
                    for update in updates:
                        bot.process_new_updates([update])
                except Exception as poll_error:
                    logger.error(f"Polling error: {poll_error}")
                    time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as alt_error:
            logger.error(f"Alternative polling failed: {alt_error}")
            raise

if __name__ == "__main__":
    main()
