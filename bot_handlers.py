from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging
import re
import config

from gemini_api import (
    get_random_word_details, generate_ielts_writing_task, evaluate_writing,
    generate_speaking_question, generate_ielts_strategies, explain_grammar_structure,
    get_topic_specific_words
)

logger = logging.getLogger(__name__)

# --- Conversation States ---
GET_WRITING_TOPIC = 1
GET_WRITING_SUBMISSION = 2
GET_GRAMMAR_TOPIC = 3
GET_VOCABULARY_TOPIC = 4
GET_WRITING_CHECK_TASK = 5
GET_WRITING_CHECK_ESSAY = 6

# --- Utility Functions ---
def format_info_text(text: str) -> str:
    """Formats info/strategies text for better mobile display."""
    if not text: return ""
    
    # Convert common Markdown patterns to HTML
    formatted_text = text
    
    # Convert **bold** to <b>bold</b>
    formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', formatted_text)
    
    # Convert *italic* to <i>italic</i>
    formatted_text = re.sub(r'\*([^*\n]+?)\*', r'<i>\1</i>', formatted_text)
    
    # Replace problematic characters for mobile display
    # Replace long dashes with shorter ones for better mobile compatibility
    formatted_text = formatted_text.replace('─', '-')
    formatted_text = formatted_text.replace('━', '-')
    formatted_text = formatted_text.replace('═', '=')
    
    # Convert bullet points to HTML bullets
    formatted_text = formatted_text.replace('•', '•')
    
    # Keep line breaks as \n (Telegram HTML mode doesn't support <br>)
    # Don't convert \n to <br> - Telegram will handle line breaks automatically
    
    return formatted_text

def format_grammar_text(text: str) -> str:
    """Formats grammar text for Telegram HTML parse mode - simplified approach."""
    if not text: return ""
    
    formatted_text = text
    
    # Step 1: Convert all **text** to <b>text</b>
    formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', formatted_text)
    
    # Step 2: Convert all remaining *text* to <i>text</i>
    formatted_text = re.sub(r'\*([^*\n]+?)\*', r'<i>\1</i>', formatted_text)
    
    # Step 3: Remove any remaining asterisks
    formatted_text = formatted_text.replace('*', '')
    
    # Step 4: Clean up character replacements
    formatted_text = formatted_text.replace('─', '-')
    formatted_text = formatted_text.replace('━', '-')
    formatted_text = formatted_text.replace('═', '=')
    
    # Step 5: Preserve bullet points and structure
    formatted_text = formatted_text.replace('•', '•')
    
    # Step 6: Fix spacing issues around bullet points and examples
    formatted_text = re.sub(r'\n\s*\*\s+', '\n• ', formatted_text)
    
    # Step 7: Ensure proper line breaks for readability
    formatted_text = re.sub(r'\n{3,}', '\n\n', formatted_text)
    
    return formatted_text

def escape_grammar_markdown_v2(text: str) -> str:
    """Escapes text for MarkdownV2 format while preserving formatting for grammar explanations."""
    if not text: return ""
    
    # Escape special characters for MarkdownV2, but be very careful with formatting
    escaped_text = text
    
    # First, escape backslashes
    escaped_text = escaped_text.replace('\\', '\\\\')
    
    # Escape special characters that are not part of our formatting
    escaped_text = escaped_text.replace('[', '\\[')
    escaped_text = escaped_text.replace(']', '\\]')
    escaped_text = escaped_text.replace('(', '\\(')
    escaped_text = escaped_text.replace(')', '\\)')
    escaped_text = escaped_text.replace('~', '\\~')
    escaped_text = escaped_text.replace('`', '\\`')
    escaped_text = escaped_text.replace('>', '\\>')
    escaped_text = escaped_text.replace('#', '\\#')
    escaped_text = escaped_text.replace('+', '\\+')
    
    # Don't escape dashes, dots, equals, pipes, braces, or exclamation marks
    # These often cause more problems than they solve
    
    # Handle underscores and asterisks very carefully
    # Only escape underscores and asterisks that are not part of formatting
    # This is tricky, so we'll use a more conservative approach
    
    # Escape all underscores and asterisks, then restore the ones we want for formatting
    escaped_text = escaped_text.replace('_', '\\_')
    escaped_text = escaped_text.replace('*', '\\*')
    
    # Now restore the formatting we want
    # Restore __bold__ formatting (double underscores)
    escaped_text = re.sub(r'\\_\\_(.*?)\\_\\_', r'__\1__', escaped_text)
    # Restore _italic_ formatting (single underscores)
    escaped_text = re.sub(r'\\_(.*?)\\_', r'_\1_', escaped_text)
    
    return escaped_text

def escape_markdown_v2(text: str) -> str:
    """Escapes text for MarkdownV2 format to prevent parsing errors."""
    # Escape special characters for MarkdownV2
    escaped_text = text.replace('\\', '\\\\')
    escaped_text = escaped_text.replace('_', '\\_')
    escaped_text = escaped_text.replace('*', '\\*')
    escaped_text = escaped_text.replace('[', '\\[')
    escaped_text = escaped_text.replace(']', '\\]')
    escaped_text = escaped_text.replace('(', '\\(')
    escaped_text = escaped_text.replace(')', '\\)')
    escaped_text = escaped_text.replace('~', '\\~')
    escaped_text = escaped_text.replace('`', '\\`')
    escaped_text = escaped_text.replace('>', '\\>')
    escaped_text = escaped_text.replace('#', '\\#')
    escaped_text = escaped_text.replace('+', '\\+')
    escaped_text = escaped_text.replace('-', '\\-')
    escaped_text = escaped_text.replace('=', '\\=')
    escaped_text = escaped_text.replace('|', '\\|')
    escaped_text = escaped_text.replace('{', '\\{')
    escaped_text = escaped_text.replace('}', '\\}')
    escaped_text = escaped_text.replace('.', '\\.')
    escaped_text = escaped_text.replace('!', '\\!')
    
    # Handle bold formatting - escape asterisks but preserve ** for bold
    escaped_text = escaped_text.replace('**', '\\*\\*')
    
    # Handle any other potential formatting issues
    # Replace any unescaped asterisks that might be used for emphasis
    escaped_text = re.sub(r'(?<!\\)\*(?!\*)', r'\\*', escaped_text)
    
    return escaped_text

async def send_long_message(update: Update, context: CallbackContext, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = None):
    """Sends a long message by splitting it into multiple parts if needed."""
    max_length = 4000  # Leave some buffer for safety
    
    if len(text) <= max_length:
        # Message is short enough, send normally
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(text=text, parse_mode=parse_mode, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text=text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Parse mode failed ({parse_mode}), falling back to plain text: {e}")
            # Remove all HTML tags for fallback
            plain_text = re.sub(r'<[^>]+>', '', text)
            if update.callback_query:
                await update.callback_query.edit_message_text(text=plain_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text=plain_text, reply_markup=reply_markup)
    else:
        # Split the message logic with better error handling
        parts = []
        current_part = ""
        
        lines = text.split('\n')
        
        for line in lines:
            if len(current_part + line + '\n') > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line + '\n'
                else:
                    parts.append(line[:max_length])
                    current_part = line[max_length:] + '\n'
            else:
                current_part += line + '\n'
        
        if current_part.strip():
            parts.append(current_part.strip())
        
        # Send parts with improved error handling
        for i, part in enumerate(parts):
            try:
                if i == 0:  # First part with reply markup
                    if update.callback_query:
                        await update.callback_query.edit_message_text(text=part, parse_mode=parse_mode, reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(text=part, parse_mode=parse_mode, reply_markup=reply_markup)
                else:  # Subsequent parts
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=part,
                        parse_mode=parse_mode
                    )
            except Exception as e:
                logger.warning(f"Parse mode failed for part {i}, falling back to plain text: {e}")
                plain_part = re.sub(r'<[^>]+>', '', part)
                if i == 0:
                    if update.callback_query:
                        await update.callback_query.edit_message_text(text=plain_part, reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(text=plain_part, reply_markup=reply_markup)
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=plain_part
                    )

async def send_or_edit_safe_text(update: Update, context: CallbackContext, text: str, reply_markup: InlineKeyboardMarkup = None):
    """A helper to send text with MarkdownV2, falling back to plain text on error."""
    try:
        safe_text = escape_markdown_v2(text)
        if update.callback_query:
            await update.callback_query.edit_message_text(text=safe_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=safe_text, parse_mode='MarkdownV2', reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"MarkdownV2 parsing failed, falling back to plain text: {e}")
        if update.callback_query:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=text, reply_markup=reply_markup)

async def setup_bot_menu_button(context: CallbackContext) -> None:
    """Sets up the bot menu button with main commands"""
    try:
        from telegram import BotCommand
        
        commands = [
            BotCommand("start", "Start the bot and get welcome message"),
            BotCommand("menu", "Open the interactive main menu"),
            BotCommand("help", "Show help information"),
            BotCommand("vocabulary", "Get vocabulary words"),
            BotCommand("writing", "Get IELTS writing tasks"),
            BotCommand("speaking", "Get IELTS speaking questions"),
            BotCommand("info", "Get IELTS strategies and tips"),
            BotCommand("grammar", "Get grammar explanations"),
        ]
        
        await context.bot.set_my_commands(commands)
        logger.info("✅ Bot menu button commands set successfully.")
    except Exception as e:
        logger.error(f"🔥 Failed to set bot menu button: {e}")

async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    welcome_message = (f"👋 Привет, {user.first_name}!\n\nЯ ваш помощник по подготовке к IELTS...")
    
    keyboard = [
        [InlineKeyboardButton("📋 Меню", callback_data="menu_help")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_button")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = ("Вот команды, которые вы можете использовать:\n\n"
                 "📋 /menu - Открыть интерактивное главное меню\n"
                 "🧠 /vocabulary - Получить словарные слова (случайные или по теме).\n"
                 "✍️ /writing - Получить задание IELTS по письму.\n"
                 "🗣️ /speaking - Получить карточку IELTS для говорения.\n"
                 "ℹ️ /info - Получить советы и стратегии для конкретных типов заданий.\n"
                 "📖 /grammar - Получить объяснение грамматической темы.")
    await update.message.reply_text(help_text)

async def menu_command(update: Update, context: CallbackContext, force_new_message=False) -> None:
    """Sends an interactive main menu with buttons for all main features."""
    keyboard = [
        [InlineKeyboardButton("🧠 Словарь", callback_data="menu_vocabulary")],
        [InlineKeyboardButton("✍️ Письмо", callback_data="menu_writing")],
        [InlineKeyboardButton("🗣️ Говорение", callback_data="menu_speaking")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="menu_info")],
        [InlineKeyboardButton("📖 Грамматика", callback_data="menu_grammar")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if force_new_message:
        chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text="📋 <b>Главное меню</b>\n\nВыберите раздел для начала:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "📋 <b>Главное меню</b>\n\nВыберите раздел для начала:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

async def menu_button_callback(update: Update, context: CallbackContext) -> None:
    """Handle main menu button presses"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Add logging to debug the callback data
    logger.info(f"🔍 Menu button callback received data: '{data}' from user {user.id}")
    
    if data == "menu_vocabulary":
        # Handle vocabulary menu selection
        keyboard = [
            [InlineKeyboardButton("🎲 Случайное слово", callback_data="vocabulary_random")],
            [InlineKeyboardButton("📚 Слова по теме", callback_data="vocabulary_topic")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        
    elif data == "menu_writing":
        # Handle writing menu selection
        keyboard = [
            [InlineKeyboardButton("Задание 2 (Эссе)", callback_data="writing_task_type_2")],
            [InlineKeyboardButton("📝 Проверить письмо", callback_data="writing_check")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
        
    elif data == "menu_grammar":
        # Handle grammar menu selection
        context.user_data['waiting_for_grammar_topic'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📖 Какую грамматическую тему вы хотите объяснить?\n\n"
            "Например: 'Present Perfect', 'использование артиклей' или 'фразовые глаголы'.",
            reply_markup=reply_markup
        )
        
    elif data == "menu_speaking":
        # Handle speaking menu selection
        keyboard = [
            [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
            [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
            [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🗣️ Выберите часть устного экзамена для практики:", reply_markup=reply_markup)
        
    elif data == "menu_info":
        # Handle info menu selection
        keyboard = [
            [InlineKeyboardButton("🎧 Listening - True/False", callback_data="info_listening_truefalse")],
            [InlineKeyboardButton("🎧 Listening - Multiple Choice", callback_data="info_listening_multiplechoice")],
            [InlineKeyboardButton("🎧 Listening - Note Completion", callback_data="info_listening_notes")],
            [InlineKeyboardButton("📖 Reading - Short Answer", callback_data="info_reading_shortanswer")],
            [InlineKeyboardButton("📖 Reading - True/False/NG", callback_data="info_reading_truefalse")],
            [InlineKeyboardButton("📖 Reading - Multiple Choice", callback_data="info_reading_multiplechoice")],
            [InlineKeyboardButton("📖 Reading - Matching Headings", callback_data="info_reading_headings")],
            [InlineKeyboardButton("📖 Reading - Summary Completion", callback_data="info_reading_summary")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("ℹ️ Choose the specific IELTS task type you want strategies for:", reply_markup=reply_markup)
        
    elif data == "back_to_main_menu":
        # Handle back to main menu
        keyboard = [
            [InlineKeyboardButton("🧠 Словарь", callback_data="menu_vocabulary")],
            [InlineKeyboardButton("✍️ Письмо", callback_data="menu_writing")],
            [InlineKeyboardButton("🗣️ Говорение", callback_data="menu_speaking")],
            [InlineKeyboardButton("ℹ️ Информация", callback_data="menu_info")],
            [InlineKeyboardButton("📖 Грамматика", callback_data="menu_grammar")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📋 <b>Главное меню</b>\n\nВыберите раздел для начала:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    else:
        logger.warning(f"❌ Unknown menu option received: '{data}' from user {user.id}")
        await query.edit_message_text(f"Unknown menu option: {data}")

async def handle_start_buttons(update: Update, context: CallbackContext) -> None:
    """Handle buttons from the start command"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "menu_help":
        # Create and send the main menu directly
        keyboard = [
            [InlineKeyboardButton("🧠 Словарь", callback_data="menu_vocabulary")],
            [InlineKeyboardButton("✍️ Письмо", callback_data="menu_writing")],
            [InlineKeyboardButton("🗣️ Говорение", callback_data="menu_speaking")],
            [InlineKeyboardButton("ℹ️ Информация", callback_data="menu_info")],
            [InlineKeyboardButton("📖 Грамматика", callback_data="menu_grammar")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📋 <b>Главное меню</b>\n\nВыберите раздел для начала:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    elif data == "help_button":
        help_text = ("Вот команды, которые вы можете использовать:\n\n"
                     "📋 /menu - Открыть интерактивное главное меню\n"
                     "🧠 /vocabulary - Получить словарные слова (случайные или по теме).\n"
                     "✍️ /writing - Получить задание IELTS по письму.\n"
                     "🗣️ /speaking - Получить карточку IELTS для говорения.\n"
                     "ℹ️ /info - Получить советы и стратегии для конкретных типов заданий.\n"
                     "📖 /grammar - Получить объяснение грамматической темы.")
        await query.edit_message_text(help_text)

# --- VOCABULARY (Conversation) ---
async def start_vocabulary_selection(update: Update, context: CallbackContext, force_new_message=False) -> int:
    if force_new_message:
        chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat_id
        keyboard = [
            [InlineKeyboardButton("🎲 Случайное слово", callback_data="vocabulary_random")],
            [InlineKeyboardButton("📚 Слова по теме", callback_data="vocabulary_topic")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, text="📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        return GET_VOCABULARY_TOPIC
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    logger.info(f"🎯 Vocabulary command triggered by user {update.effective_user.id}")
    keyboard = [
        [InlineKeyboardButton("🎲 Случайное слово", callback_data="vocabulary_random")],
        [InlineKeyboardButton("📚 Слова по теме", callback_data="vocabulary_topic")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await target.reply_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
    logger.info(f"✅ Vocabulary options sent to user {update.effective_user.id}, returning state {GET_VOCABULARY_TOPIC}")
    return GET_VOCABULARY_TOPIC

async def handle_vocabulary_choice_callback(update: Update, context: CallbackContext) -> None:
    """Handle vocabulary choice"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    choice = query.data.split('_')[1]  # random or topic
    
    if choice == "random":
        logger.info(f"🎯 User {update.effective_user.id} chose random vocabulary")
        await query.edit_message_text("🎲 Генерирую случайное слово...")
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
        word_details = get_random_word_details()
        reply_markup = None
        await send_or_edit_safe_text(update, context, word_details, reply_markup)
        await menu_command(update, context, force_new_message=True)
    else:  # topic
        logger.info(f"🎯 User {update.effective_user.id} chose topic-specific vocabulary")
        context.user_data['waiting_for_vocabulary_topic'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📚 Пожалуйста, введите тему для словарных слов (например, 'окружающая среда', 'технологии', 'образование'):",
            reply_markup=reply_markup
        )

async def get_topic_and_generate_vocabulary(update: Update, context: CallbackContext) -> int:
    topic = update.message.text
    context.user_data['current_vocabulary_topic'] = topic
    logger.info(f"🎯 Vocabulary: User {update.effective_user.id} requested topic-specific words for: '{topic}'")
    
    await update.message.reply_text(f"📚 Генерирую полезные словарные слова для '{topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    vocabulary_words = get_topic_specific_words(topic=topic, count=10)
    reply_markup = None
    await send_or_edit_safe_text(update, context, vocabulary_words, reply_markup)
    logger.info(f"✅ Topic-specific vocabulary generated for user {update.effective_user.id}, ending conversation")
    await menu_command(update, context, force_new_message=True)
    return ConversationHandler.END

# --- VOCABULARY (Legacy - keeping for backward compatibility) ---
async def handle_vocabulary_command(update: Update, context: CallbackContext) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    word_details = get_random_word_details()
    reply_markup = None
    await send_or_edit_safe_text(update, context, word_details, reply_markup)
    await menu_command(update, context, force_new_message=True)

async def handle_vocabulary_topic_input(update: Update, context: CallbackContext) -> None:
    """Handle vocabulary topic input from users, works globally"""
    topic = update.message.text
    context.user_data['current_vocabulary_topic'] = topic
    logger.info(f"🎯 Vocabulary: User {update.effective_user.id} requested topic-specific words for: '{topic}'")
    
    await update.message.reply_text(f"📚 Генерирую полезные словарные слова для '{topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    vocabulary_words = get_topic_specific_words(topic=topic, count=10)
    reply_markup = None
    await send_or_edit_safe_text(update, context, vocabulary_words, reply_markup)
    logger.info(f"✅ Topic-specific vocabulary generated for user {update.effective_user.id}")
    await menu_command(update, context, force_new_message=True)

# --- WRITING (Conversation) ---
async def start_writing_task(update: Update, context: CallbackContext, force_new_message=False) -> int:
    if force_new_message:
        chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat_id
        keyboard = [
            [InlineKeyboardButton("Задание 2 (Эссе)", callback_data="writing_task_type_2")],
            [InlineKeyboardButton("📝 Проверить письмо", callback_data="writing_check")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, text="✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
        return GET_WRITING_TOPIC
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    logger.info(f"🎯 Writing command triggered by user {update.effective_user.id}")
    keyboard = [
        [InlineKeyboardButton("Задание 2 (Эссе)", callback_data="writing_task_type_2")],
        [InlineKeyboardButton("📝 Проверить письмо", callback_data="writing_check")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await target.reply_text("✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
    logger.info(f"✅ Writing task options sent to user {update.effective_user.id}, returning state {GET_WRITING_TOPIC}")
    return GET_WRITING_TOPIC

async def handle_writing_task_type_callback(update: Update, context: CallbackContext) -> None:
    """Handle writing task type selection"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    task_type_choice = query.data.split('_')[-1]
    context.user_data['selected_writing_task_type'] = f"Task {task_type_choice}"
    context.user_data['waiting_for_writing_topic'] = True
    logger.info(f"🎯 User {update.effective_user.id} selected writing task type: {context.user_data['selected_writing_task_type']}")
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"✅ Вы выбрали {context.user_data['selected_writing_task_type']}. Теперь, пожалуйста, расскажите мне тему для вашего письменного задания.",
        reply_markup=reply_markup
    )
    logger.info(f"✅ User {update.effective_user.id} needs to provide topic, staying in state {GET_WRITING_TOPIC}")

async def handle_writing_topic_input(update: Update, context: CallbackContext) -> None:
    """Handle writing topic input from users, works globally"""
    user_topic = update.message.text
    selected_task_type = context.user_data.get('selected_writing_task_type', 'Task 2')
    context.user_data['current_writing_topic'] = user_topic
    logger.info(f"🎯 Writing: User {update.effective_user.id} provided topic: '{user_topic}' for {selected_task_type}")
    
    await update.message.reply_text(f"✅ Отлично! Генерирую {selected_task_type} на тему: '{user_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    writing_task = generate_ielts_writing_task(task_type=selected_task_type, topic=user_topic)
    context.user_data['current_writing_task_description'] = writing_task
    
    reply_markup = None
    message_text = (f"Вот ваше {selected_task_type}:\n\n{writing_task}\n\n"
                    "Пожалуйста, напишите ваш ответ и отправьте его мне.")
    await send_or_edit_safe_text(update, context, message_text, reply_markup)
    logger.info(f"✅ Writing task generated for user {update.effective_user.id}")
    await menu_command(update, context, force_new_message=True)

async def get_topic_and_generate_writing(update: Update, context: CallbackContext) -> int:
    user_topic = update.message.text
    selected_task_type = context.user_data.get('selected_writing_task_type', 'Task 2')
    context.user_data['current_writing_topic'] = user_topic
    logger.info(f"🎯 Writing: User {update.effective_user.id} provided topic: '{user_topic}' for {selected_task_type}")
    
    await update.message.reply_text(f"✅ Great! Generating a {selected_task_type} task on the topic: '{user_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    writing_task = generate_ielts_writing_task(task_type=selected_task_type, topic=user_topic)
    context.user_data['current_writing_task_description'] = writing_task
    
    reply_markup = None
    message_text = (f"Here is your {selected_task_type}:\n\n{writing_task}\n\n"
                    "Please write your response and send it to me.")
    await send_or_edit_safe_text(update, context, message_text, reply_markup)
    logger.info(f"✅ Writing task generated for user {update.effective_user.id}, moving to submission state")
    await menu_command(update, context, force_new_message=True)
    return GET_WRITING_SUBMISSION

async def handle_writing_submission(update: Update, context: CallbackContext) -> int:
    student_writing = update.message.text
    task_description = context.user_data.get('current_writing_task_description', 'No specific task given.')
    
    await update.message.reply_text("Checking your writing, please wait...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    feedback = evaluate_writing(writing_text=student_writing, task_description=task_description)
    message_text = f"Here's the feedback on your writing:\n\n{feedback}"
    await send_or_edit_safe_text(update, context, message_text)
    
    context.user_data.clear()
    await menu_command(update, context, force_new_message=True)
    return ConversationHandler.END

async def handle_writing_check_callback(update: Update, context: CallbackContext) -> None:
    """Handle the 'Check Writing' button press - starts the writing check conversation"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    
    # Set the user in writing check task mode
    context.user_data['waiting_for_writing_check_task'] = True
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📝 Для проверки вашего письма мне нужна информация о задании.\n\n"
        "Пожалуйста, опишите задание IELTS Writing Task, которое вы выполняли.\n"
        "Например: 'Напишите эссе о преимуществах и недостатках социальных сетей'",
        reply_markup=reply_markup
    )

# --- SPEAKING ---
async def handle_speaking_command(update: Update, context: CallbackContext, force_new_message=False) -> None:
    if force_new_message:
        chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat_id
        keyboard = [
            [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
            [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
            [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, text="🗣️ Выберите часть устного экзамена для практики:", reply_markup=reply_markup)
        return
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    keyboard = [
        [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
        [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
        [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await target.reply_text("🗣️ Выберите часть устного экзамена для практики:", reply_markup=reply_markup)

async def speaking_part_callback(update: Update, context: CallbackContext) -> None:
    """Handle speaking part selection"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    part_data = query.data
    part_number_str = part_data.split('_')[-1]
    part_for_api = f"Part {part_number_str}"
    context.user_data['current_speaking_part'] = part_for_api
    await query.edit_message_text(text=f"Отлично! 👍 Генерирую вопросы для {part_for_api}...")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    speaking_prompt = generate_speaking_question(part=part_for_api)
    reply_markup = None
    await send_or_edit_safe_text(update, context, speaking_prompt, reply_markup)
    await menu_command(update, context, force_new_message=True)

# --- IELTS INFO ---
async def handle_info_command(update: Update, context: CallbackContext, force_new_message=False) -> None:
    if force_new_message:
        chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat_id
        keyboard = [
            [InlineKeyboardButton("🎧 Listening - True/False", callback_data="info_listening_truefalse")],
            [InlineKeyboardButton("🎧 Listening - Multiple Choice", callback_data="info_listening_multiplechoice")],
            [InlineKeyboardButton("🎧 Listening - Note Completion", callback_data="info_listening_notes")],
            [InlineKeyboardButton("📖 Reading - Short Answer", callback_data="info_reading_shortanswer")],
            [InlineKeyboardButton("📖 Reading - True/False/NG", callback_data="info_reading_truefalse")],
            [InlineKeyboardButton("📖 Reading - Multiple Choice", callback_data="info_reading_multiplechoice")],
            [InlineKeyboardButton("📖 Reading - Matching Headings", callback_data="info_reading_headings")],
            [InlineKeyboardButton("📖 Reading - Summary Completion", callback_data="info_reading_summary")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, text="ℹ️ Choose the specific IELTS task type you want strategies for:", reply_markup=reply_markup)
        return
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    keyboard = [
        [InlineKeyboardButton("🎧 Listening - True/False", callback_data="info_listening_truefalse")],
        [InlineKeyboardButton("🎧 Listening - Multiple Choice", callback_data="info_listening_multiplechoice")],
        [InlineKeyboardButton("🎧 Listening - Note Completion", callback_data="info_listening_notes")],
        [InlineKeyboardButton("📖 Reading - Short Answer", callback_data="info_reading_shortanswer")],
        [InlineKeyboardButton("📖 Reading - True/False/NG", callback_data="info_reading_truefalse")],
        [InlineKeyboardButton("📖 Reading - Multiple Choice", callback_data="info_reading_multiplechoice")],
        [InlineKeyboardButton("📖 Reading - Matching Headings", callback_data="info_reading_headings")],
        [InlineKeyboardButton("📖 Reading - Summary Completion", callback_data="info_reading_summary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await target.reply_text("ℹ️ Choose the specific IELTS task type you want strategies for:", reply_markup=reply_markup)

async def info_section_callback(update: Update, context: CallbackContext) -> None:
    """Handle info section selection"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    
    # Extract section and task type from callback data
    # Format: info_listening_truefalse -> section: listening, task_type: truefalse
    callback_parts = query.data.split('_')
    section = callback_parts[1]  # listening or reading
    task_type = '_'.join(callback_parts[2:])  # truefalse, multiplechoice, etc.
    
    context.user_data['current_info_section'] = section
    context.user_data['current_info_task_type'] = task_type
    
    # Create a user-friendly task type name
    task_type_names = {
        'truefalse': 'True/False',
        'multiplechoice': 'Multiple Choice',
        'notes': 'Note Completion',
        'shortanswer': 'Short Answer',
        'headings': 'Matching Headings',
        'summary': 'Summary Completion'
    }
    
    task_name = task_type_names.get(task_type, task_type.replace('_', ' ').title())
    section_name = section.capitalize()
    
    await query.edit_message_text(text=f"Great! Fetching strategies for {section_name} - {task_name}...")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    strategies_text = generate_ielts_strategies(section=section, task_type=task_type)
    
    # Format the strategies text for better mobile display
    formatted_strategies = format_info_text(strategies_text)
    reply_markup = None
    
    await query.edit_message_text(
        text=formatted_strategies,
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    await menu_command(update, context, force_new_message=True)

# --- GRAMMAR (Conversation) ---
async def start_grammar_explanation(update: Update, context: CallbackContext, force_new_message=False) -> int:
    if force_new_message:
        chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat_id
        context.user_data['waiting_for_grammar_topic'] = True
        await context.bot.send_message(
            chat_id=chat_id,
            text="📖 Какую грамматическую тему вы хотите объяснить?\n\nНапример: 'Present Perfect', 'использование артиклей' или 'фразовые глаголы'."
        )
        return GET_GRAMMAR_TOPIC
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    logger.info(f"🎯 Grammar command triggered by user {update.effective_user.id}")
    context.user_data['waiting_for_grammar_topic'] = True
    await target.reply_text(
        "📖 Какую грамматическую тему вы хотите объяснить?\n\n"
        "Например: 'Present Perfect', 'использование артиклей' или 'фразовые глаголы'."
    )
    logger.info(f"✅ Grammar prompt sent to user {update.effective_user.id}, returning state {GET_GRAMMAR_TOPIC}")
    return GET_GRAMMAR_TOPIC

async def get_grammar_topic(update: Update, context: CallbackContext) -> int:
    grammar_topic = update.message.text
    context.user_data['current_grammar_topic'] = grammar_topic
    # Clear the waiting flag to prevent conflicts with global handler
    context.user_data.pop('waiting_for_grammar_topic', None)
    logger.info(f"🎯 Grammar (Conversation Handler): User {update.effective_user.id} requested explanation for: '{grammar_topic}'")
    
    await update.message.reply_text(f"Конечно! Генерирую объяснение для '{grammar_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    explanation = explain_grammar_structure(grammar_topic=grammar_topic)
    
    # Format the explanation for HTML
    formatted_explanation = format_grammar_text(explanation)
    logger.info(f"🔍 Formatted explanation: {formatted_explanation[:200]}...")
    
    reply_markup = None
    # Check if the explanation is empty
    if not formatted_explanation.strip():
        await update.message.reply_text("❌ Sorry, I couldn't generate an explanation for this grammar topic.")
    else:
        # Use HTML parse mode for better formatting
        await send_long_message(update, context, formatted_explanation, reply_markup, parse_mode='HTML')
    logger.info(f"✅ Grammar explanation generated for user {update.effective_user.id}, ending conversation")
    await menu_command(update, context, force_new_message=True)
    return ConversationHandler.END

async def handle_grammar_topic_input(update: Update, context: CallbackContext) -> None:
    """Handle grammar topic input from users, works globally"""
    grammar_topic = update.message.text
    context.user_data['current_grammar_topic'] = grammar_topic
    logger.info(f"🎯 Grammar (Global Handler): User {update.effective_user.id} requested explanation for: '{grammar_topic}'")
    
    await update.message.reply_text(f"Конечно! Генерирую объяснение для '{grammar_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    explanation = explain_grammar_structure(grammar_topic=grammar_topic)
    
    # Format the explanation for HTML
    formatted_explanation = format_grammar_text(explanation)
    logger.info(f"🔍 Formatted explanation: {formatted_explanation[:200]}...")
    
    reply_markup = None
    # Check if the explanation is empty
    if not formatted_explanation.strip():
        await update.message.reply_text("❌ Sorry, I couldn't generate an explanation for this grammar topic.")
    else:
        # Use HTML parse mode for better formatting
        await send_long_message(update, context, formatted_explanation, reply_markup, parse_mode='HTML')
    logger.info(f"✅ Grammar explanation generated for user {update.effective_user.id}")
    await menu_command(update, context, force_new_message=True)

async def handle_writing_check_task_input(update: Update, context: CallbackContext) -> None:
    """Handle writing check task input from users - first step of writing check"""
    task_description = update.message.text
    context.user_data['current_writing_check_task'] = task_description
    logger.info(f"🎯 Writing Check Task: User {update.effective_user.id} provided task: '{task_description}'")
    
    # Set the user in writing check essay mode
    context.user_data['waiting_for_writing_check_essay'] = True
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Задание получено: '{task_description}'\n\n"
        "Теперь пожалуйста, вставьте ваше эссе для проверки:",
        reply_markup=reply_markup
    )

async def handle_writing_check_essay_input(update: Update, context: CallbackContext) -> None:
    """Handle writing check essay input from users - second step of writing check"""
    essay_text = update.message.text
    task_description = context.user_data.get('current_writing_check_task', 'No task provided')
    logger.info(f"🎯 Writing Check Essay: User {update.effective_user.id} submitted essay for evaluation")
    
    await update.message.reply_text("📝 Проверяю ваше письмо, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    feedback = evaluate_writing(writing_text=essay_text, task_description=task_description)
    
    # Format the feedback with escape_markdown_v2
    formatted_feedback = escape_markdown_v2(feedback)
    await update.message.reply_text(
        text=formatted_feedback,
        parse_mode='MarkdownV2'
    )
    logger.info(f"✅ Writing evaluation completed for user {update.effective_user.id}")
    
    # Clear the writing check data
    context.user_data.pop('current_writing_check_task', None)
    context.user_data.pop('waiting_for_writing_check_essay', None)
    
    await menu_command(update, context, force_new_message=True)

async def handle_global_text_input(update: Update, context: CallbackContext) -> None:
    """Handle text input globally for vocabulary, grammar, and writing topics"""
    user = update.effective_user
    
    text = update.message.text
    logger.info(f"🔍 Global text input handler called for user {user.id} with text: '{text[:50]}...'")
    
    # Check if user is in vocabulary topic selection mode
    if context.user_data.get('waiting_for_vocabulary_topic'):
        logger.info(f"📚 User {user.id} is in vocabulary topic selection mode")
        context.user_data.pop('waiting_for_vocabulary_topic', None)
        await handle_vocabulary_topic_input(update, context)
        return
    
    # Check if user is in grammar topic selection mode  
    if context.user_data.get('waiting_for_grammar_topic'):
        logger.info(f"📖 User {user.id} is in grammar topic selection mode")
        context.user_data.pop('waiting_for_grammar_topic', None)
        await handle_grammar_topic_input(update, context)
        return
    
    # Check if user is in writing topic selection mode
    if context.user_data.get('waiting_for_writing_topic'):
        logger.info(f"✍️ User {user.id} is in writing topic selection mode")
        context.user_data.pop('waiting_for_writing_topic', None)
        await handle_writing_topic_input(update, context)
        return
    
    # Check if user is in writing check mode
    if context.user_data.get('waiting_for_writing_check_task'):
        logger.info(f"📝 User {user.id} is in writing check task mode")
        context.user_data.pop('waiting_for_writing_check_task', None)
        await handle_writing_check_task_input(update, context)
        return
    
    # Check if user is in writing check essay mode
    if context.user_data.get('waiting_for_writing_check_essay'):
        logger.info(f"📝 User {user.id} is in writing check essay mode")
        context.user_data.pop('waiting_for_writing_check_essay', None)
        await handle_writing_check_essay_input(update, context)
        return
    
    # If not in any specific mode, ignore the text
    # This prevents the global handler from interfering with conversation handlers
    logger.info(f"❌ User {user.id} not in any specific mode, ignoring text input")
    return

# --- GLOBAL CANCEL & ERROR HANDLER ---
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(f"Update '{update}' caused error '{context.error}'")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("An error occurred! Please try again later or type /start.")

# --- Conversation Handlers Setup (for main.py) ---
writing_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("writing", start_writing_task)],
    states={
        GET_WRITING_TOPIC: [
            CallbackQueryHandler(handle_writing_task_type_callback, pattern=r'^writing_task_type_\d$'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic_and_generate_writing)
        ],
        GET_WRITING_SUBMISSION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_submission),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="writing_conversation",
    persistent=False
)

grammar_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("grammar", start_grammar_explanation)],
    states={
        GET_GRAMMAR_TOPIC: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_grammar_topic),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="grammar_conversation",
    persistent=False
)

vocabulary_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("vocabulary", start_vocabulary_selection)],
    states={
        GET_VOCABULARY_TOPIC: [
            CallbackQueryHandler(handle_vocabulary_choice_callback, pattern=r'^vocabulary_(random|topic)$'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic_and_generate_vocabulary)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="vocabulary_conversation",
    persistent=False
)
