import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import config 
import bot_handlers
from gemini_api import initialize_gemini


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    logger.info("🚀 Starting bot...")

    initialize_gemini()

    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    logger.info("📝 Registering command handlers...")
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("vocabulary", bot_handlers.handle_vocabulary_command))
    application.add_handler(CommandHandler("writing", bot_handlers.handle_writing_command))
    application.add_handler(CommandHandler("speaking", bot_handlers.handle_speaking_command))
    application.add_handler(CommandHandler("info", bot_handlers.handle_ielts_info_command))
    application.add_handler(CommandHandler("grammar", bot_handlers.handle_grammar_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.handle_text_input))
    logger.info("🗣️ Registered conversational text handler.")


    application.add_error_handler(bot_handlers.error_handler)
    logger.info("🛡️ Registered error handler.")

    application.run_polling()
    logger.info("✅ Bot is up and running. Listening for messages...")
    
if __name__ == '__main__':
    main()    