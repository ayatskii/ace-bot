# main.py
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import logging
import config
import bot_handlers
from gemini_api import initialize_gemini

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Sets up and runs the bot."""
    initialize_gemini()
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # --- Conversation Handlers (for multi-step interactions) ---
    application.add_handler(bot_handlers.writing_conversation_handler)
    application.add_handler(bot_handlers.grammar_conversation_handler)
    logger.info("✅ Conversation handlers registered.")

    # --- Standard Command Handlers ---
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("vocabulary", bot_handlers.handle_vocabulary_command))
    application.add_handler(CommandHandler("speaking", bot_handlers.handle_speaking_command))
    application.add_handler(CommandHandler("info", bot_handlers.handle_info_command))
    logger.info("✅ Command handlers registered.")

    # --- Callback Query Handlers (for all inline buttons) ---
    # Handlers for initial menu selections
    application.add_handler(CallbackQueryHandler(bot_handlers.speaking_part_callback, pattern=r'^speaking_part_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.info_section_callback, pattern=r'^info_(listening|reading)$'))
    
    # Handlers for "Regenerate" buttons
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_vocabulary_callback, pattern=r'^regenerate_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_writing_task_callback, pattern=r'^regenerate_writing_task$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_speaking_callback, pattern=r'^regenerate_speaking_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_info_callback, pattern=r'^regenerate_info_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_grammar_callback, pattern=r'^regenerate_grammar$'))
    logger.info("✅ Callback query handlers registered.")

    # --- Error Handler ---
    application.add_error_handler(bot_handlers.error_handler)

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()