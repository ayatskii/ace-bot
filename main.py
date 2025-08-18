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

    # --- Setup Bot Menu Button ---
    async def post_init(application: Application) -> None:
        await bot_handlers.setup_bot_menu_button(application)
    
    application.post_init = post_init

    # --- Conversation Handlers (for multi-step interactions) ---
    application.add_handler(bot_handlers.writing_conversation_handler)
    application.add_handler(bot_handlers.grammar_conversation_handler)
    application.add_handler(bot_handlers.vocabulary_conversation_handler)
    logger.info("✅ Conversation handlers registered.")

    # --- Standard Command Handlers ---
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("menu", bot_handlers.menu_command))
    application.add_handler(CommandHandler("speaking", bot_handlers.handle_speaking_command))
    application.add_handler(CommandHandler("info", bot_handlers.handle_info_command))
    
    # --- Admin Command Handlers ---
    application.add_handler(CommandHandler("admin", bot_handlers.admin_command))
    application.add_handler(CommandHandler("testdb", bot_handlers.test_db_command))  # Debug command
    application.add_handler(CommandHandler("whitelist", bot_handlers.admin_whitelist_status_command))  # Whitelist status
    # Dynamic admin commands for user management
    application.add_handler(MessageHandler(filters.Regex(r'^/block_\d+$'), bot_handlers.admin_block_user_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/unblock_\d+$'), bot_handlers.admin_unblock_user_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/delete_\d+$'), bot_handlers.admin_delete_user_command))
    # Whitelist management commands
    application.add_handler(MessageHandler(filters.Regex(r'^/adduser_\d+$'), bot_handlers.admin_add_user_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/removeuser_\d+$'), bot_handlers.admin_remove_user_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/addusername_.+$'), bot_handlers.admin_add_username_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/removeusername_.+$'), bot_handlers.admin_remove_username_command))
    
    logger.info("✅ Command handlers registered.")

    # --- Global Text Input Handlers (for topic selection) ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.handle_global_text_input))
    
    # --- Voice Message Handler (for speaking practice) ---
    application.add_handler(MessageHandler(filters.VOICE, bot_handlers.handle_voice_message))
    
    logger.info("✅ Global text input and voice message handlers registered.")

    # --- Callback Query Handlers (for all inline buttons) ---
    # Handlers for initial menu selections
    application.add_handler(CallbackQueryHandler(bot_handlers.speaking_part_callback, pattern=r'^speaking_part_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.info_section_callback, pattern=r'^info_(listening|reading)_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_start_buttons, pattern=r'^(menu_help|help_button)$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.menu_button_callback, pattern=r'^menu_(vocabulary|writing|speaking|info|grammar|profile)$|^back_to_main_menu$'))
    # Add global handlers for vocabulary and writing buttons (for menu-based access)
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_vocabulary_choice_global, pattern=r'^vocabulary_(random|topic)$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_writing_task_type_global, pattern=r'^writing_task_type_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_writing_check_global, pattern=r'^writing_check$'))
    # Add handlers for personalization features
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_save_word_to_vocabulary, pattern=r'^save_word_to_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_profile_vocabulary, pattern=r'^profile_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_clear_vocabulary, pattern=r'^clear_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_confirm_clear_vocabulary, pattern=r'^confirm_clear_vocabulary$'))
    
    # Add handlers for admin features
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_panel_callback, pattern=r'^admin_panel$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_users, pattern=r'^admin_users$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_search, pattern=r'^admin_search$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_detailed_stats, pattern=r'^admin_stats$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_users_pagination, pattern=r'^admin_users_page_\d+$'))
    
    logger.info("✅ Callback query handlers registered.")

    # --- Error Handler ---
    application.add_error_handler(bot_handlers.error_handler)

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()