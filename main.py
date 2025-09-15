# main.py
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import logging
import config
import bot_handlers
import flashcard_handlers
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
    application.add_handler(bot_handlers.full_speaking_simulation_handler)
    application.add_handler(flashcard_handlers.flashcard_conversation_handler)
    logger.info("✅ Conversation handlers registered.")

    # --- Standard Command Handlers (PRIVATE ONLY) ---
    application.add_handler(CommandHandler("start", bot_handlers.start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("help", bot_handlers.help_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("menu", bot_handlers.menu_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("speaking", bot_handlers.handle_speaking_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("info", bot_handlers.handle_info_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("debug", bot_handlers.debug_conversation_state, filters=filters.ChatType.PRIVATE))  # Debug command
    application.add_handler(CommandHandler("flashcards", flashcard_handlers.handle_flashcard_menu, filters=filters.ChatType.PRIVATE))  # Flashcard command

    # --- Group Chat Command Handlers (GROUPS ONLY) ---
    application.add_handler(CommandHandler("word", bot_handlers.handle_group_word_command, 
                                     filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
    application.add_handler(CommandHandler("autosend", bot_handlers.handle_group_autosend_command, 
                                     filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))

    # --- Admin Command Handlers (PRIVATE ONLY) ---
    application.add_handler(CommandHandler("admin", bot_handlers.admin_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("adminhelp", bot_handlers.admin_help_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("testdb", bot_handlers.test_db_command, filters=filters.ChatType.PRIVATE))  # Debug command
    application.add_handler(CommandHandler("whitelist", bot_handlers.admin_whitelist_status_command, filters=filters.ChatType.PRIVATE))  # Whitelist status
    # Dynamic admin commands for user management (PRIVATE ONLY)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/block_\d+$'), bot_handlers.admin_block_user_command))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/unblock_\d+$'), bot_handlers.admin_unblock_user_command))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/delete_\d+$'), bot_handlers.admin_delete_user_command))
    # Whitelist management commands (PRIVATE ONLY)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/adduser_\d+$'), bot_handlers.admin_add_user_command))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/removeuser_\d+$'), bot_handlers.admin_remove_user_command))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/addusername_.+$'), bot_handlers.admin_add_username_command))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^/removeusername_.+$'), bot_handlers.admin_remove_username_command))

    # --- Move group management to private (optional but recommended) ---
    application.add_handler(CommandHandler("groupstats", bot_handlers.handle_group_stats_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("resetgroup", bot_handlers.handle_group_reset_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("grouphistory", bot_handlers.handle_group_history_command, filters=filters.ChatType.PRIVATE))
    
    logger.info("✅ Command handlers registered.")

    # --- Global Text Input Handlers (PRIVATE ONLY) ---
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT & ~filters.COMMAND), bot_handlers.handle_global_text_input))

    # --- Voice Message Handler (PRIVATE ONLY) ---
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.VOICE, bot_handlers.handle_voice_message))
    
    logger.info("✅ Global text input and voice message handlers registered.")

    # --- Callback Query Handlers (for all inline buttons) ---
    # Handlers for initial menu selections
    application.add_handler(CallbackQueryHandler(bot_handlers.speaking_part_callback, pattern=r'^speaking_part_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_voice_confirmation, pattern=r'^confirm_voice_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.info_section_callback, pattern=r'^info_(listening|reading)_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_start_buttons, pattern=r'^(menu_help|help_button)$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.menu_button_callback, pattern=r'^menu_(vocabulary|writing|speaking|info|grammar|profile)$|^back_to_main_menu$'))
    # Add global handlers for vocabulary and writing buttons (for menu-based access)
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_vocabulary_choice_global, pattern=r'^vocabulary_(random|topic|custom|ai_enhanced)$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_writing_task_type_global, pattern=r'^writing_task_type_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_writing_check_global, pattern=r'^writing_check$'))
    # Add handlers for personalization features
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_save_word_to_vocabulary, pattern=r'^save_word_to_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_profile_vocabulary, pattern=r'^profile_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_clear_vocabulary, pattern=r'^clear_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_confirm_clear_vocabulary, pattern=r'^confirm_clear_vocabulary$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_custom_word_add_callback, pattern=r'^custom_word_add$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_custom_word_add_from_menu, pattern=r'^custom_word_add_from_menu$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_ai_enhanced_custom_word, pattern=r'^ai_enhanced_custom_word$'))
    
    # Add handlers for admin features
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_panel_callback, pattern=r'^admin_panel$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_users, pattern=r'^admin_users$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_search, pattern=r'^admin_search$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_detailed_stats, pattern=r'^admin_stats$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_help, pattern=r'^admin_help$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_admin_users_pagination, pattern=r'^admin_users_page_\d+$'))
    
    # Add handlers for full speaking simulation
    application.add_handler(CallbackQueryHandler(bot_handlers.restart_full_simulation, pattern=r'^restart_full_sim$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.abandon_full_simulation, pattern=r'^abandon_full_sim$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.skip_full_sim_part, pattern=r'^skip_part_\d$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_speaking_stats, pattern=r'^speaking_stats$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_writing_stats, pattern=r'^writing_stats$'))
    
    # Add flashcard callback handlers
    application.add_handler(CallbackQueryHandler(flashcard_handlers.handle_flashcard_menu, pattern=r'^flashcard_menu$'))
    application.add_handler(CallbackQueryHandler(flashcard_handlers.handle_flashcard_study, pattern=r'^flashcard_study$'))
    application.add_handler(CallbackQueryHandler(flashcard_handlers.handle_add_random_words, pattern=r'^flashcard_add_random$'))
    
    logger.info("✅ Callback query handlers registered.")

    # --- Wrong-context helpers for common private commands attempted in groups ---
    async def wrong_context_handler(update: Update, context):
        if update.message:
            await update.message.reply_text(
                "🤖 This command only works in private chats!\n👆 Click my name and message me directly."
            )

    application.add_handler(CommandHandler("start", wrong_context_handler, 
                                     filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
    application.add_handler(CommandHandler("menu", wrong_context_handler, 
                                     filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))
    application.add_handler(CommandHandler("speaking", wrong_context_handler, 
                                     filters=filters.ChatType.GROUP | filters.ChatType.SUPERGROUP))

    # --- Error Handler ---
    application.add_error_handler(bot_handlers.error_handler)

    # --- Setup Auto-Send Job Scheduler ---
    if config.ENABLE_GROUP_FEATURES and config.ENABLE_AUTO_SEND:
        job_queue = application.job_queue
        
        # Run auto-send check every hour (configurable)
        job_queue.run_repeating(
            bot_handlers.auto_send_words_to_groups,
            interval=config.AUTO_SEND_CHECK_INTERVAL,
            first=60,  # Start after 1 minute
            name="auto_send_words"
        )
        
        # Run at specific time daily (configurable)
        from datetime import time
        job_queue.run_daily(
            bot_handlers.auto_send_words_to_groups,
            time=time(hour=config.DAILY_SEND_TIME_HOUR, minute=config.DAILY_SEND_TIME_MINUTE),
            name="daily_word_send"
        )
        
        logger.info(f"✅ Auto-send job scheduler initialized (checks every {config.AUTO_SEND_CHECK_INTERVAL}s, daily at {config.DAILY_SEND_TIME_HOUR}:{config.DAILY_SEND_TIME_MINUTE:02d})")

    # --- Ignore all non-command messages in groups (ADD THIS LAST) ---
    async def ignore_group_messages(update: Update, context):
        # Silently ignore
        return

    application.add_handler(MessageHandler(
        (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP) & ~filters.COMMAND,
        ignore_group_messages
    ))

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()