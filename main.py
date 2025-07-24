# main.py
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
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

    # --- Standard Command Handlers ---
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("menu", bot_handlers.menu_command))
    application.add_handler(CommandHandler("speaking", bot_handlers.handle_speaking_command))
    application.add_handler(CommandHandler("info", bot_handlers.handle_info_command))
    logger.info("✅ Command handlers registered.")

    # --- Global Text Input Handlers (for topic selection) ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.handle_global_text_input))
    logger.info("✅ Global text input handlers registered.")

    # --- Conversation Handlers (for multi-step interactions) ---
    application.add_handler(bot_handlers.writing_conversation_handler)
    application.add_handler(bot_handlers.grammar_conversation_handler)
    application.add_handler(bot_handlers.vocabulary_conversation_handler)
    logger.info("✅ Conversation handlers registered.")

    # --- Callback Query Handlers (for all inline buttons) ---
    # Handlers for initial menu selections
    application.add_handler(CallbackQueryHandler(bot_handlers.speaking_part_callback, pattern=r'^speaking_part_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.info_section_callback, pattern=r'^info_(listening|reading)_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.menu_button_callback, pattern=r'^menu_'))
    # Add global handlers for vocabulary and writing buttons
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_vocabulary_choice_callback, pattern=r'^vocabulary_(random|topic)$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_writing_task_type_callback, pattern=r'^writing_task_type_\d$'))
    
    # Handlers for "Regenerate" buttons
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_vocabulary_callback, pattern=r'^regenerate_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_topic_vocabulary_callback, pattern=r'^regenerate_topic_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_writing_task_callback, pattern=r'^regenerate_writing_task$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_speaking_callback, pattern=r'^regenerate_speaking_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.regenerate_info_callback, pattern=r'^regenerate_info_'))
    logger.info("✅ Callback query handlers registered.")

    # --- Error Handler ---
    application.add_error_handler(bot_handlers.error_handler)

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()