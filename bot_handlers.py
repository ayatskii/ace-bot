from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging
import re
import sqlite3
import config
from database import db

from gemini_api import (
    get_random_word_details, generate_ielts_writing_task, evaluate_writing,
    generate_speaking_question, generate_ielts_strategies, explain_grammar_structure,
    get_topic_specific_words, evaluate_speaking_response
)
from audio_processor import audio_processor

logger = logging.getLogger(__name__)

# --- Admin Utility Functions ---
def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in config.ADMIN_USER_IDS and config.ENABLE_ADMIN_PANEL

def check_user_access(user_id: int) -> bool:
    """Check if user has access to the bot"""
    # If user is blocked, deny access
    if db.is_user_blocked(user_id):
        return False
    
    # Admins always have access (even if not in whitelist)
    if is_admin(user_id):
        return True
    
    # If whitelist is enabled, check if user is authorized
    if config.ENABLE_WHITELIST:
        return user_id in config.AUTHORIZED_USER_IDS
    
    # If whitelist is disabled, allow all non-blocked users
    return True

def check_username_access(username: str) -> bool:
    """Check if username has access to the bot"""
    if not username or not config.ENABLE_WHITELIST:
        return False
    return username.lower() in [u.lower() for u in config.AUTHORIZED_USERNAMES]

async def send_access_denied_message(update: Update, context: CallbackContext) -> None:
    """Send access denied message to blocked users"""
    user = update.effective_user
    
    if db.is_user_blocked(user.id):
        await update.message.reply_text(
            "🚫 <b>Доступ заблокирован</b>\n\n"
            "Ваш доступ к боту был ограничен администратором.\n"
            "Если вы считаете, что это ошибка, обратитесь к администратору.",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "🚫 <b>Доступ ограничен</b>\n\n"
            "У вас нет доступа к этому боту.\n"
            "Обратитесь к администратору для получения доступа.",
            parse_mode='HTML'
        )

def require_access(func):
    """Decorator to check user access before executing function"""
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user = update.effective_user
        
        # Check user access (ID or username)
        has_id_access = check_user_access(user.id)
        has_username_access = check_username_access(user.username) if user.username else False
        
        if not (has_id_access or has_username_access):
            await send_access_denied_message(update, context)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def require_admin(func):
    """Decorator to check admin access before executing function"""
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user = update.effective_user
        if not is_admin(user.id):
            await update.message.reply_text(
                "🚫 <b>Доступ запрещен</b>\n\n"
                "Эта функция доступна только администраторам.",
                parse_mode='HTML'
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Utility Functions for Word Parsing ---
def parse_word_details(word_details: str) -> dict:
    """Parse word details from Gemini API response"""
    import re
    
    word_match = re.search(r'📝 Word: (.+)', word_details, re.IGNORECASE)
    definition_match = re.search(r'📖 Definition: (.+)', word_details, re.IGNORECASE)
    translation_match = re.search(r'🇷🇺 Translation: (.+)', word_details, re.IGNORECASE)
    example_match = re.search(r'💡 Example: (.+)', word_details, re.IGNORECASE)
    
    return {
        'word': word_match.group(1).strip() if word_match else 'Unknown',
        'definition': definition_match.group(1).strip() if definition_match else '',
        'translation': translation_match.group(1).strip() if translation_match else '',
        'example': example_match.group(1).strip() if example_match else ''
    }

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
    
    # Handle bold formatting - preserve ** for bold in MarkdownV2
    # First, temporarily replace ** with a placeholder
    escaped_text = escaped_text.replace('**', 'BOLD_PLACEHOLDER')
    
    # Escape all remaining single asterisks
    escaped_text = escaped_text.replace('*', '\\*')
    
    # Restore bold formatting
    escaped_text = escaped_text.replace('BOLD_PLACEHOLDER', '*')
    
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
    """A helper to send text with MarkdownV2, falling back to plain text on error, and splitting long messages."""
    max_length = 4000  # Leave some buffer for safety
    
    if len(text) <= max_length:
        # Message is short enough, send normally with markdown formatting
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
    else:
        # Split the message and send with markdown formatting
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
        
        # Send parts with markdown formatting
        for i, part in enumerate(parts):
            try:
                safe_part = escape_markdown_v2(part)
                if i == 0:  # First part with reply markup
                    if update.callback_query:
                        await update.callback_query.edit_message_text(text=safe_part, parse_mode='MarkdownV2', reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(text=safe_part, parse_mode='MarkdownV2', reply_markup=reply_markup)
                else:  # Subsequent parts
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=safe_part,
                        parse_mode='MarkdownV2'
                    )
            except Exception as e:
                logger.warning(f"MarkdownV2 parsing failed for part {i}, falling back to plain text: {e}")
                if i == 0:
                    if update.callback_query:
                        await update.callback_query.edit_message_text(text=part, reply_markup=reply_markup)
                    else:
                        await update.message.reply_text(text=part, reply_markup=reply_markup)
                else:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=part
                    )

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
    
    # Add user to database (always add, access control happens later)
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Check user access (ID or username)
    has_id_access = check_user_access(user.id)
    has_username_access = check_username_access(user.username) if user.username else False
    
    if not (has_id_access or has_username_access):
        await send_access_denied_message(update, context)
        return
    
    welcome_message = (f"👋 Привет, {user.first_name}!\n\nЯ ваш помощник по подготовке к IELTS...")
    
    keyboard = [
        [InlineKeyboardButton("📋 Меню", callback_data="menu_help")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help_button")],
    ]
    
    # Add admin panel button for admins
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

@require_access
async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = ("Вот команды, которые вы можете использовать:\n\n"
                 "📋 /menu - Открыть интерактивное главное меню\n"
                 "🧠 /vocabulary - Получить словарные слова (случайные или по теме).\n"
                 "✍️ /writing - Получить задание IELTS по письму.\n"
                 "🗣️ /speaking - Получить карточку IELTS для говорения.\n"
                 "ℹ️ /info - Получить советы и стратегии для конкретных типов заданий.\n"
                 "📖 /grammar - Получить объяснение грамматической темы.")
    await update.message.reply_text(help_text)

@require_access
async def menu_command(update: Update, context: CallbackContext, force_new_message=False) -> None:
    """Sends an interactive main menu with buttons for all main features."""
    user = update.effective_user
    if user:
        db.update_user_activity(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🧠 Словарь", callback_data="menu_vocabulary")],
        [InlineKeyboardButton("✍️ Письмо", callback_data="menu_writing")],
        [InlineKeyboardButton("🗣️ Говорение", callback_data="menu_speaking")],
        [InlineKeyboardButton("ℹ️ Информация", callback_data="menu_info")],
        [InlineKeyboardButton("📖 Грамматика", callback_data="menu_grammar")],
        [InlineKeyboardButton("👤 Мой профиль", callback_data="menu_profile")],
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

@require_access
async def menu_button_callback(update: Update, context: CallbackContext) -> None:
    """Handle main menu button presses"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # Add logging to debug the callback data
    logger.info(f"🔍 Menu button callback received data: '{data}' from user {user.id}")
    
    if data == "menu_vocabulary":
        # Handle vocabulary menu selection - direct approach to avoid conversation handler conflicts
        keyboard = [
            [InlineKeyboardButton("🎲 Случайное слово", callback_data="vocabulary_random")],
            [InlineKeyboardButton("📚 Слова по теме", callback_data="vocabulary_topic")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        
    elif data == "menu_writing":
        # Handle writing menu selection - direct approach to avoid conversation handler conflicts
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
        
    elif data == "menu_profile":
        # Handle profile menu selection - ULTRA SAFE VERSION
        logger.info(f"👤 Profile menu requested by user {user.id}")
        
        # Create the absolute minimum safe profile
        try:
            profile_text = f"👤 <b>Мой профиль</b>\n\n"
            profile_text += f"🆔 ID: {user.id}\n"
            profile_text += f"👋 Имя: {user.first_name or 'Не указано'}"
            
            # Add last name safely
            try:
                if user.last_name:
                    profile_text += f" {user.last_name}"
            except:
                pass
            
            # Add username safely
            try:
                if user.username:
                    profile_text += f"\n📧 Username: @{user.username}"
            except:
                pass
            
            # Add vocabulary count safely
            try:
                vocabulary_count = db.get_user_vocabulary_count(user.id)
                profile_text += f"\n📚 Слов в словаре: {vocabulary_count}"
                logger.info(f"✅ Vocabulary count for user {user.id}: {vocabulary_count}")
            except Exception as e:
                profile_text += f"\n📚 Слов в словаре: 0"
                logger.error(f"🔥 Failed to get vocabulary count: {e}")
            
            # Skip registration date for now to avoid errors
            logger.info(f"📝 Profile text created: {len(profile_text)} chars")
            
            keyboard = [
                [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            logger.info(f"📝 Attempting to send profile to user {user.id}")
            await query.edit_message_text(profile_text, reply_markup=reply_markup, parse_mode='HTML')
            logger.info(f"✅ Profile menu sent successfully to user {user.id}")
            
        except Exception as e:
            logger.error(f"🔥 Critical error in profile menu for user {user.id}: {e}")
            import traceback
            logger.error(f"🔥 Full traceback: {traceback.format_exc()}")
            
            # Ultra-safe fallback - absolute minimum
            try:
                fallback_text = f"👤 Мой профиль\n\nID: {user.id}\nИмя: {user.first_name}\n\n⚠️ Профиль временно недоступен"
                keyboard = [
                    [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(fallback_text, reply_markup=reply_markup)
                logger.info(f"✅ Fallback profile sent to user {user.id}")
            except Exception as fallback_error:
                logger.error(f"🔥 Even fallback failed: {fallback_error}")
                try:
                    await query.answer("❌ Ошибка профиля. Попробуйте позже.")
                except:
                    logger.error(f"🔥 Could not even send error message to user {user.id}")
        
    elif data == "back_to_main_menu":
        # Handle back to main menu
        keyboard = [
            [InlineKeyboardButton("🧠 Словарь", callback_data="menu_vocabulary")],
            [InlineKeyboardButton("✍️ Письмо", callback_data="menu_writing")],
            [InlineKeyboardButton("🗣️ Говорение", callback_data="menu_speaking")],
            [InlineKeyboardButton("ℹ️ Информация", callback_data="menu_info")],
            [InlineKeyboardButton("📖 Грамматика", callback_data="menu_grammar")],
            [InlineKeyboardButton("👤 Мой профиль", callback_data="menu_profile")],
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

@require_access
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
            [InlineKeyboardButton("👤 Мой профиль", callback_data="menu_profile")],
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
@require_access
async def start_vocabulary_selection(update: Update, context: CallbackContext, force_new_message=False) -> int:
    keyboard = [
        [InlineKeyboardButton("🎲 Случайное слово", callback_data="vocabulary_random")],
        [InlineKeyboardButton("📚 Слова по теме", callback_data="vocabulary_topic")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if force_new_message:
        # Try to edit if possible, else send new message
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        else:
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text="📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        return GET_VOCABULARY_TOPIC
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
    elif hasattr(update, 'message') and update.message:
        await update.message.reply_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
    return GET_VOCABULARY_TOPIC

@require_access
async def handle_vocabulary_choice_callback(update: Update, context: CallbackContext) -> int:
    """Handle vocabulary choice - for conversation handler"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    choice = query.data.split('_')[1]  # random or topic
    
    if choice == "random":
        logger.info(f"🎯 User {update.effective_user.id} chose random vocabulary")
        await query.edit_message_text("🎲 Генерирую случайное слово...")
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
        word_details = get_random_word_details()
        
        # Store the word details for potential saving
        context.user_data['last_random_word'] = word_details
        
        # Add button to save word to personal vocabulary
        keyboard = [
            [InlineKeyboardButton("➕ Добавить в мой словарь", callback_data="save_word_to_vocabulary")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_safe_text(update, context, word_details, reply_markup)
        return ConversationHandler.END
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
        return GET_VOCABULARY_TOPIC

@require_access
async def handle_vocabulary_choice_global(update: Update, context: CallbackContext) -> None:
    """Handle vocabulary choice - for global handler (menu-based access)"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    choice = query.data.split('_')[1]  # random or topic
    
    if choice == "random":
        logger.info(f"🎯 User {update.effective_user.id} chose random vocabulary (global)")
        await query.edit_message_text("🎲 Генерирую случайное слово...")
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
        word_details = get_random_word_details()
        
        # Store the word details for potential saving
        context.user_data['last_random_word'] = word_details
        
        # Add button to save word to personal vocabulary
        keyboard = [
            [InlineKeyboardButton("➕ Добавить в мой словарь", callback_data="save_word_to_vocabulary")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_or_edit_safe_text(update, context, word_details, reply_markup)
    else:  # topic
        logger.info(f"🎯 User {update.effective_user.id} chose topic-specific vocabulary (global)")
        context.user_data['waiting_for_vocabulary_topic'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📚 Пожалуйста, введите тему для словарных слов (например, 'окружающая среда', 'технологии', 'образование'):",
            reply_markup=reply_markup
        )

@require_access
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
@require_access
async def handle_vocabulary_command(update: Update, context: CallbackContext) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    word_details = get_random_word_details()
    reply_markup = None
    await send_or_edit_safe_text(update, context, word_details, reply_markup)
    await menu_command(update, context, force_new_message=True)

@require_access
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
@require_access
async def start_writing_task(update: Update, context: CallbackContext, force_new_message=False) -> int:
    keyboard = [
        [InlineKeyboardButton("Задание 2 (Эссе)", callback_data="writing_task_type_2")],
        [InlineKeyboardButton("📝 Проверить письмо", callback_data="writing_check")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if force_new_message:
        # Try to edit if possible, else send new message
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text("✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text("✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
        else:
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text="✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
        return GET_WRITING_TOPIC
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text("✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
    elif hasattr(update, 'message') and update.message:
        await update.message.reply_text("✍️ Какой тип письменного задания вам нужен?", reply_markup=reply_markup)
    return GET_WRITING_TOPIC

@require_access
async def handle_writing_task_type_callback(update: Update, context: CallbackContext) -> int:
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
    return GET_WRITING_TOPIC

@require_access
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

@require_access
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

@require_access
async def handle_writing_submission(update: Update, context: CallbackContext) -> int:
    student_writing = update.message.text
    task_description = context.user_data.get('current_writing_task_description', 'No specific task given.')
    
    await update.message.reply_text("Checking your writing, please wait...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    feedback = evaluate_writing(writing_text=student_writing, task_description=task_description)
    await send_or_edit_safe_text(update, context, feedback)
    
    context.user_data.clear()
    await menu_command(update, context, force_new_message=True)
    return ConversationHandler.END

@require_access
async def handle_writing_check_callback(update: Update, context: CallbackContext) -> int:
    """Handle the 'Check Essay' button press - starts the writing check conversation"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    
    # End any existing conversation
    if context.user_data.get('waiting_for_writing_topic'):
        context.user_data.pop('waiting_for_writing_topic', None)
    if context.user_data.get('selected_writing_task_type'):
        context.user_data.pop('selected_writing_task_type', None)
    if context.user_data.get('current_writing_topic'):
        context.user_data.pop('current_writing_topic', None)
    
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
    
    return GET_WRITING_CHECK_TASK

# --- SPEAKING ---
@require_access
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

@require_access
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
    
    # Store the speaking prompt for later evaluation
    context.user_data['current_speaking_prompt'] = speaking_prompt
    
    # Add voice response instructions
    voice_instructions = (
        "\n\n🎤 <b>ГОЛОСОВОЙ ОТВЕТ:</b>\n"
        "Запишите голосовое сообщение с вашим ответом на английском языке.\n"
        "Бот автоматически транскрибирует речь и оценит ваш ответ по шкале IELTS (1-9)!\n\n"
        "💡 <i>Говорите четко и уверенно, как на настоящем экзамене IELTS.</i>"
    )
    
    full_response = speaking_prompt + voice_instructions
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ])
    
    # Send message with HTML formatting for voice instructions
    try:
        await query.edit_message_text(text=full_response, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        # If edit fails, send new message
        logger.warning(f"Failed to edit message, sending new one: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=full_response,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Set user state to expect voice message
    context.user_data['waiting_for_voice_response'] = True
    logger.info(f"🎤 User {user.id} ready to submit voice response for {part_for_api}")

# --- IELTS INFO ---
@require_access
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

@require_access
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
@require_access
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

@require_access
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

@require_access
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

@require_access
async def handle_writing_check_task_input(update: Update, context: CallbackContext) -> int:
    """Handle writing check task input from users - first step of writing check"""
    task_description = update.message.text
    context.user_data['current_writing_check_task'] = task_description
    logger.info(f"🎯 Writing Check Task: User {update.effective_user.id} provided task: '{task_description}'")
    
    # Set the user in writing check essay mode for global handler
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
    
    return GET_WRITING_CHECK_ESSAY

@require_access
async def handle_writing_check_essay_input(update: Update, context: CallbackContext) -> int:
    """Handle writing check essay input from users - second step of writing check"""
    essay_text = update.message.text
    task_description = context.user_data.get('current_writing_check_task', 'No task provided')
    logger.info(f"🎯 Writing Check Essay: User {update.effective_user.id} submitted essay for evaluation")
    
    await update.message.reply_text("📝 Проверяю ваше письмо, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    feedback = evaluate_writing(writing_text=essay_text, task_description=task_description)
    
    # Use send_or_edit_safe_text to ensure proper markdown formatting with fallback
    reply_markup = None
    await send_or_edit_safe_text(update, context, feedback, reply_markup)
    logger.info(f"✅ Writing evaluation completed for user {update.effective_user.id}")
    
    # Clear the writing check data
    context.user_data.pop('current_writing_check_task', None)
    
    await menu_command(update, context, force_new_message=True)
    return ConversationHandler.END

@require_access
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
    
    # Check if user is in writing check mode (for menu-based access)
    if context.user_data.get('waiting_for_writing_check_task'):
        logger.info(f"📝 User {user.id} is in writing check task mode (global)")
        context.user_data.pop('waiting_for_writing_check_task', None)
        await handle_writing_check_task_input(update, context)
        return
    
    # Check if user is in writing check essay mode (for menu-based access)
    if context.user_data.get('waiting_for_writing_check_essay'):
        logger.info(f"📝 User {user.id} is in writing check essay mode (global)")
        context.user_data.pop('waiting_for_writing_check_essay', None)
        await handle_writing_check_essay_input(update, context)
        return
    
    # Check if admin is searching for users
    if context.user_data.get('waiting_for_admin_search'):
        logger.info(f"🔍 Admin {user.id} is searching for users")
        context.user_data.pop('waiting_for_admin_search', None)
        await handle_admin_search_input(update, context)
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

@require_access
async def handle_voice_message(update: Update, context: CallbackContext) -> None:
    """Handle voice messages for speaking practice evaluation"""
    user = update.effective_user
    
    # Check if user is expecting a voice response
    if not context.user_data.get('waiting_for_voice_response'):
        await update.message.reply_text(
            "🎤 Чтобы записать голосовой ответ, сначала выберите задание по говорению в меню.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗣️ Говорение", callback_data="menu_speaking")],
                [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")],
            ])
        )
        return
    
    try:
        # Get voice message details
        voice = update.message.voice
        if not voice:
            await update.message.reply_text("❌ Ошибка: голосовое сообщение не найдено.")
            return
        
        # Show processing message
        processing_message = await update.message.reply_text(
            "🎤 Обрабатываю ваше голосовое сообщение...\n"
            "⏳ Транскрибирую речь и готовлю оценку..."
        )
        
        # Get file URL from Telegram
        voice_file = await context.bot.get_file(voice.file_id)
        file_url = voice_file.file_path
        
        logger.info(f"🎤 Processing voice message from user {user.id}. Duration: {voice.duration}s")
        
        # Transcribe the voice message
        transcription = await audio_processor.process_voice_message(file_url)
        
        if not transcription:
            # Check if it's due to Eleven Labs not being available
            if not hasattr(audio_processor, 'client') or audio_processor.client is None:
                await processing_message.edit_text(
                    "❌ Функция распознавания речи недоступна.\n"
                    "Обратитесь к администратору для настройки API ключа Eleven Labs.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")],
                    ])
                )
            else:
                await processing_message.edit_text(
                    "❌ Не удалось распознать речь в голосовом сообщении.\n"
                    "Попробуйте записать сообщение еще раз, говоря четче.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Попробовать снова", callback_data="menu_speaking")],
                        [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")],
                    ])
                )
            return
        
        # Get stored speaking context
        speaking_prompt = context.user_data.get('current_speaking_prompt', 'Unknown prompt')
        speaking_part = context.user_data.get('current_speaking_part', 'Part 1')
        
        logger.info(f"🎤 Transcription successful for user {user.id}. Length: {len(transcription)} chars")
        
        # Update processing message
        await processing_message.edit_text(
            "✅ Речь распознана успешно!\n"
            "🤖 Анализирую ваш ответ по критериям IELTS..."
        )
        
        # Evaluate the speaking response
        evaluation = evaluate_speaking_response(speaking_prompt, transcription, speaking_part)
        
        # Prepare final response
        final_response = (
            f"🎤 <b>ВАША РЕЧЬ:</b>\n"
            f"<i>«{transcription[:200]}{'...' if len(transcription) > 200 else ''}»</i>\n\n"
            f"{evaluation}"
        )
        
        # Create reply markup
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Попробовать еще раз", callback_data="menu_speaking")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")],
        ])
        
        # Send the evaluation as single message (Telegram limit is 4096 chars)
        try:
            await update.message.reply_text(
                text=final_response, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
        except Exception as e:
            # If message is too long, truncate the transcription and try again
            logger.warning(f"Message too long, truncating: {e}")
            truncated_transcription = transcription[:100] + "..." if len(transcription) > 100 else transcription
            final_response_short = (
                f"🎤 <b>ВАША РЕЧЬ:</b>\n"
                f"<i>«{truncated_transcription}»</i>\n\n"
                f"{evaluation}"
            )
            await update.message.reply_text(
                text=final_response_short, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
        
        # Clear voice response state
        context.user_data.pop('waiting_for_voice_response', None)
        context.user_data.pop('current_speaking_prompt', None)
        context.user_data.pop('current_speaking_part', None)
        
        logger.info(f"✅ Voice message evaluation completed for user {user.id}")
        
        # Delete the processing message
        try:
            await processing_message.delete()
        except:
            pass  # Ignore if message already deleted or can't be deleted
        
    except Exception as e:
        logger.error(f"🔥 Error processing voice message for user {user.id}: {e}")
        
        try:
            await processing_message.edit_text(
                "❌ Произошла ошибка при обработке голосового сообщения.\n"
                "Попробуйте еще раз позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data="menu_speaking")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")],
                ])
            )
        except:
            # If we can't edit the processing message, send a new one
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке голосового сообщения.\n"
                "Попробуйте еще раз позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data="menu_speaking")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")],
                ])
            )

# --- Conversation Handlers Setup (for main.py) ---
writing_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("writing", start_writing_task)],
    states={
        GET_WRITING_TOPIC: [
            CallbackQueryHandler(handle_writing_task_type_callback, pattern=r'^writing_task_type_\d$'),
            CallbackQueryHandler(handle_writing_check_callback, pattern=r'^writing_check$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic_and_generate_writing)
        ],
        GET_WRITING_SUBMISSION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_submission),
        ],
        GET_WRITING_CHECK_TASK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_check_task_input),
        ],
        GET_WRITING_CHECK_ESSAY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_check_essay_input),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="writing_conversation",
    persistent=False,
    per_message=False
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
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic_and_generate_vocabulary)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="vocabulary_conversation",
    persistent=False,
    per_message=False
)

@require_access
async def handle_writing_task_type_global(update: Update, context: CallbackContext) -> None:
    """Handle writing task type selection - for global handler (menu-based access)"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    task_type_choice = query.data.split('_')[-1]
    context.user_data['selected_writing_task_type'] = f"Task {task_type_choice}"
    context.user_data['waiting_for_writing_topic'] = True
    logger.info(f"🎯 User {update.effective_user.id} selected writing task type: {context.user_data['selected_writing_task_type']} (global)")
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"✅ Вы выбрали {context.user_data['selected_writing_task_type']}. Теперь, пожалуйста, расскажите мне тему для вашего письменного задания.",
        reply_markup=reply_markup
    )

@require_access
async def handle_save_word_to_vocabulary(update: Update, context: CallbackContext) -> None:
    """Handle saving word to user's personal vocabulary"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    word_details = context.user_data.get('last_random_word', '')
    if not word_details:
        await query.edit_message_text("❌ Нет слова для сохранения. Попробуйте получить новое случайное слово.")
        return
    
    # Parse word details
    parsed_word = parse_word_details(word_details)
    
    # Check if word already exists
    if db.word_exists_in_user_vocabulary(user.id, parsed_word['word']):
        await query.edit_message_text(
            f"⚠️ Слово '{parsed_word['word']}' уже есть в вашем словаре!\n\n"
            f"📖 Перейти в мой словарь или выбрать новое слово?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("🎲 Новое слово", callback_data="vocabulary_random")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
            ])
        )
        return
    
    # Save word to database
    success = db.save_word_to_user_vocabulary(
        user_id=user.id,
        word=parsed_word['word'],
        definition=parsed_word['definition'],
        translation=parsed_word['translation'],
        example=parsed_word['example'],
        topic="random"
    )
    
    if success:
        vocabulary_count = db.get_user_vocabulary_count(user.id)
        await query.edit_message_text(
            f"✅ Слово '{parsed_word['word']}' успешно добавлено в ваш словарь!\n\n"
            f"📚 Всего слов в словаре: {vocabulary_count}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("🎲 Новое слово", callback_data="vocabulary_random")],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
            ])
        )
    else:
        await query.edit_message_text(
            "❌ Произошла ошибка при сохранении слова. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
            ])
        )

@require_access
async def handle_profile_vocabulary(update: Update, context: CallbackContext) -> None:
    """Handle viewing user's personal vocabulary"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    words = db.get_user_vocabulary(user.id, limit=20)  # Show last 20 words
    vocabulary_count = db.get_user_vocabulary_count(user.id)
    
    if not words:
        await query.edit_message_text(
            "📖 <b>Мой словарь</b>\n\n"
            "📝 Ваш словарь пока пуст.\n"
            "Добавьте слова, используя функцию 'Случайное слово'!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 Случайное слово", callback_data="vocabulary_random")],
                [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
            ]),
            parse_mode='HTML'
        )
        return
    
    # Format vocabulary list
    vocabulary_text = f"📖 <b>Мой словарь</b> ({vocabulary_count} слов)\n\n"
    
    for i, (word, definition, translation, example, topic, saved_at) in enumerate(words, 1):
        vocabulary_text += f"<b>{i}. {word.upper()}</b>\n"
        if definition:
            vocabulary_text += f"📖 {definition}\n"
        if translation:
            vocabulary_text += f"🇷🇺 {translation}\n"
        if example:
            vocabulary_text += f"💡 {example}\n"
        vocabulary_text += f"📅 {saved_at[:10]}\n\n"
    
    if vocabulary_count > 20:
        vocabulary_text += f"<i>... и еще {vocabulary_count - 20} слов</i>\n"
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Очистить словарь", callback_data="clear_vocabulary")],
        [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Split long message if needed
    await send_long_message(update, context, vocabulary_text, reply_markup, parse_mode='HTML')

@require_access
async def handle_clear_vocabulary(update: Update, context: CallbackContext) -> None:
    """Handle clearing user's vocabulary with confirmation"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    vocabulary_count = db.get_user_vocabulary_count(user.id)
    
    if vocabulary_count == 0:
        await query.edit_message_text(
            "📖 Ваш словарь уже пуст!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
            ])
        )
        return
    
    await query.edit_message_text(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы уверены, что хотите удалить все {vocabulary_count} слов из вашего словаря?\n\n"
        f"<i>Это действие нельзя отменить!</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear_vocabulary")],
            [InlineKeyboardButton("❌ Отмена", callback_data="profile_vocabulary")],
        ]),
        parse_mode='HTML'
    )

@require_access
async def handle_confirm_clear_vocabulary(update: Update, context: CallbackContext) -> None:
    """Handle confirmed vocabulary clearing"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    try:
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_words WHERE user_id = ?', (user.id,))
            deleted_count = cursor.rowcount
            conn.commit()
            
        await query.edit_message_text(
            f"✅ Словарь очищен!\n\n"
            f"Удалено слов: {deleted_count}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 Добавить новые слова", callback_data="vocabulary_random")],
                [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
            ])
        )
        logger.info(f"✅ User {user.id} cleared their vocabulary ({deleted_count} words)")
        
    except Exception as e:
        logger.error(f"🔥 Failed to clear vocabulary for user {user.id}: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при очистке словаря.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
            ])
        )

# === ADMIN FUNCTIONS ===

@require_admin
async def admin_command(update: Update, context: CallbackContext) -> None:
    """Handle /admin command"""
    await show_admin_panel(update, context)

@require_admin
async def admin_help_command(update: Update, context: CallbackContext) -> None:
    """Handle /adminhelp command - show full admin instructions"""
    help_text = """📖 <b>БЫСТРАЯ СПРАВКА ДЛЯ АДМИНИСТРАТОРА</b>

🚀 <b>Основные команды:</b>
• <code>/admin</code> - Админ-панель
• <code>/adminhelp</code> - Эта справка
• <code>/testdb</code> - Проверка БД
• <code>/whitelist</code> - Статус whitelist

👥 <b>Управление пользователями:</b>
• <code>/block_ID</code> - Заблокировать
• <code>/unblock_ID</code> - Разблокировать  
• <code>/delete_ID</code> - Удалить (необратимо!)

🔐 <b>Управление доступом:</b>
• <code>/adduser_ID</code> - Добавить по ID
• <code>/addusername_name</code> - Добавить по username
• <code>/removeuser_ID</code> - Удалить по ID
• <code>/removeusername_name</code> - Удалить по username

💡 <b>Полная инструкция:</b> /admin → "📖 Инструкция для админа"

⚠️ <b>Помните:</b> Команды удаления необратимы! Используйте блокировку вместо удаления когда это возможно."""

    await update.message.reply_text(help_text, parse_mode='HTML')

async def test_db_command(update: Update, context: CallbackContext) -> None:
    """Test database functionality - for debugging"""
    user = update.effective_user
    
    try:
        # Test basic database operations
        test_results = []
        
        # Test 1: User info
        try:
            user_info = db.get_user_info(user.id)
            test_results.append(f"✅ User info: {user_info is not None}")
        except Exception as e:
            test_results.append(f"❌ User info error: {str(e)[:50]}")
        
        # Test 2: Vocabulary count
        try:
            vocab_count = db.get_user_vocabulary_count(user.id)
            test_results.append(f"✅ Vocabulary count: {vocab_count}")
        except Exception as e:
            test_results.append(f"❌ Vocabulary count error: {str(e)[:50]}")
        
        # Test 3: Database connection
        try:
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                test_results.append(f"✅ Tables: {len(tables)} found")
        except Exception as e:
            test_results.append(f"❌ Database connection error: {str(e)[:50]}")
        
        test_text = f"🔧 <b>Database Test Results</b>\n\n" + "\n".join(test_results)
        await update.message.reply_text(test_text, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Test failed: {e}")

async def show_admin_panel(update: Update, context: CallbackContext) -> None:
    """Show the main admin panel"""
    user = update.effective_user
    stats = db.get_user_stats()
    
    admin_text = f"⚙️ <b>Админ-панель</b>\n\n"
    admin_text += f"👤 Администратор: {user.first_name}\n"
    admin_text += f"🆔 ID: {user.id}\n\n"
    admin_text += f"📊 <b>Статистика:</b>\n"
    admin_text += f"• Всего пользователей: {stats.get('total_users', 0)}\n"
    admin_text += f"• Активных: {stats.get('active_users', 0)}\n"
    admin_text += f"• Заблокированных: {stats.get('blocked_users', 0)}\n"
    admin_text += f"• С сохраненными словами: {stats.get('users_with_words', 0)}\n"
    admin_text += f"• Всего слов в базе: {stats.get('total_words', 0)}\n"
    admin_text += f"• Новых за сегодня: {stats.get('new_users_today', 0)}\n"
    
    keyboard = [
        [InlineKeyboardButton("👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("🔍 Поиск пользователя", callback_data="admin_search")],
        [InlineKeyboardButton("📊 Подробная статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📖 Инструкция для админа", callback_data="admin_help")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_admin_panel_callback(update: Update, context: CallbackContext) -> None:
    """Handle admin panel button clicks"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("🚫 Доступ запрещен.")
        return
    
    await show_admin_panel(update, context)

async def handle_admin_users(update: Update, context: CallbackContext) -> None:
    """Show user management panel"""
    query = update.callback_query
    await query.answer()
    
    # Reset pagination when first accessing users panel
    context.user_data['admin_users_offset'] = 0
    await show_admin_users_page(update, context, offset=0)

async def show_admin_users_page(update: Update, context: CallbackContext, offset: int = 0) -> None:
    """Show users page with pagination"""
    limit = 10
    users = db.get_all_users(limit=limit, offset=offset)
    total_users = db.get_user_stats().get('total_users', 0)
    
    users_text = f"👥 <b>Управление пользователями</b>\n\n"
    users_text += f"📊 Показано: {offset + 1}-{min(offset + limit, total_users)} из {total_users}\n\n"
    
    if not users:
        users_text += "📝 Пользователи не найдены.\n"
    else:
        for user_id, username, first_name, last_name, is_active, is_blocked, created_at, last_activity in users:
            status_emoji = "🚫" if is_blocked else "✅"
            name = first_name or "Без имени"
            if last_name:
                name += f" {last_name}"
            username_text = f"@{username}" if username else "Без username"
            
            users_text += f"{status_emoji} <b>{name}</b>\n"
            users_text += f"🆔 {user_id} | {username_text}\n"
            users_text += f"📅 Регистрация: {created_at[:10]}\n\n"
    
    # Build pagination buttons
    keyboard = []
    pagination_row = []
    
    # Previous page button
    if offset > 0:
        pagination_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_users_page_{offset - limit}"))
    
    # Next page button
    if offset + limit < total_users:
        pagination_row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin_users_page_{offset + limit}"))
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Action buttons
    keyboard.extend([
        [InlineKeyboardButton("🔍 Поиск пользователя", callback_data="admin_search")],
        [InlineKeyboardButton("🔙 Назад к админ-панели", callback_data="admin_panel")],
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await send_long_message(update, context, users_text, reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(users_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_admin_search(update: Update, context: CallbackContext) -> None:
    """Handle admin search request"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['waiting_for_admin_search'] = True
    
    search_text = "🔍 <b>Поиск пользователя</b>\n\n"
    search_text += "Введите один из параметров для поиска:\n"
    search_text += "• Telegram ID (например: 123456789)\n"
    search_text += "• Username (например: @username или username)\n"
    search_text += "• Имя пользователя\n"
    
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="admin_users")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(search_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_admin_users_pagination(update: Update, context: CallbackContext) -> None:
    """Handle pagination for admin users"""
    query = update.callback_query
    await query.answer()
    
    # Extract offset from callback data
    callback_data = query.data
    offset = int(callback_data.split('_')[-1])
    
    await show_admin_users_page(update, context, offset=offset)

async def handle_admin_detailed_stats(update: Update, context: CallbackContext) -> None:
    """Handle detailed statistics panel"""
    query = update.callback_query
    await query.answer()
    
    # Get basic stats
    stats = db.get_user_stats()
    
    # Get additional detailed statistics
    try:
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            
            # Most active users by vocabulary count
            cursor.execute('''
                SELECT u.first_name, u.username, u.user_id, COUNT(uw.word) as word_count
                FROM users u
                LEFT JOIN user_words uw ON u.user_id = uw.user_id
                WHERE u.is_active = 1 AND u.is_blocked = 0
                GROUP BY u.user_id
                ORDER BY word_count DESC
                LIMIT 5
            ''')
            top_users = cursor.fetchall()
            

            
            # Most popular saved words
            cursor.execute('''
                SELECT word, COUNT(*) as save_count
                FROM user_words
                GROUP BY word
                ORDER BY save_count DESC
                LIMIT 5
            ''')
            popular_words = cursor.fetchall()
            
            # Users by activity (last activity)
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN last_activity >= datetime('now', '-1 day') THEN 1 ELSE 0 END) as last_24h,
                    SUM(CASE WHEN last_activity >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_7d,
                    SUM(CASE WHEN last_activity >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as last_30d
                FROM users
                WHERE is_active = 1 AND is_blocked = 0
            ''')
            activity_stats = cursor.fetchone()
            
    except Exception as e:
        logger.error(f"🔥 Failed to get detailed stats: {e}")
        top_users = []
        popular_words = []
        activity_stats = (0, 0, 0)
    
    # Build detailed statistics text
    stats_text = f"📊 <b>Подробная статистика</b>\n\n"
    
    # Basic stats
    stats_text += f"👥 <b>Общая статистика:</b>\n"
    stats_text += f"• Всего пользователей: {stats.get('total_users', 0)}\n"
    stats_text += f"• Активных: {stats.get('active_users', 0)}\n"
    stats_text += f"• Заблокированных: {stats.get('blocked_users', 0)}\n"
    stats_text += f"• С сохраненными словами: {stats.get('users_with_words', 0)}\n"
    stats_text += f"• Всего слов в базе: {stats.get('total_words', 0)}\n\n"
    
    # Activity stats
    if activity_stats:
        stats_text += f"📈 <b>Активность пользователей:</b>\n"
        stats_text += f"• За 24 часа: {activity_stats[0]}\n"
        stats_text += f"• За 7 дней: {activity_stats[1]}\n"
        stats_text += f"• За 30 дней: {activity_stats[2]}\n\n"
    
    # Top users by vocabulary
    if top_users:
        stats_text += f"🏆 <b>Топ пользователей по словарю:</b>\n"
        for i, (name, username, user_id, word_count) in enumerate(top_users, 1):
            name_display = name or "Без имени"
            username_display = f"@{username}" if username else f"ID:{user_id}"
            stats_text += f"{i}. {name_display} ({username_display}): {word_count} слов\n"
        stats_text += "\n"
    
    # Popular words
    if popular_words:
        stats_text += f"📚 <b>Популярные слова:</b>\n"
        for word, count in popular_words:
            stats_text += f"• {word}: {count} сохранений\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Назад к админ-панели", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_long_message(update, context, stats_text, reply_markup, parse_mode='HTML')

async def handle_admin_help(update: Update, context: CallbackContext) -> None:
    """Show comprehensive admin instructions"""
    query = update.callback_query
    await query.answer()
    
    help_text = """📖 <b>ПОЛНАЯ ИНСТРУКЦИЯ ДЛЯ АДМИНИСТРАТОРА</b>

═══════════════════════════════════════════════════════
🚀 <b>ОСНОВНЫЕ КОМАНДЫ</b>
═══════════════════════════════════════════════════════

<b>🔧 Панель управления:</b>
• <code>/admin</code> - Открыть админ-панель
• <code>/testdb</code> - Проверить подключение к базе данных
• <code>/whitelist</code> - Показать статус whitelist

═══════════════════════════════════════════════════════
👥 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>
═══════════════════════════════════════════════════════

<b>🔍 Поиск пользователей:</b>
• В админ-панели → "🔍 Поиск пользователя"
• Поиск по: ID, username, имени
• Пример: <code>@username</code>, <code>John</code>, <code>123456789</code>

<b>🚫 Блокировка/разблокировка:</b>
• <code>/block_123456</code> - Заблокировать пользователя по ID
• <code>/unblock_123456</code> - Разблокировать пользователя по ID

<b>🗑️ Удаление пользователей:</b>
• <code>/delete_123456</code> - Удалить пользователя и все его данные
• ⚠️ <b>Осторожно!</b> Действие необратимо!

═══════════════════════════════════════════════════════
🔐 <b>УПРАВЛЕНИЕ WHITELIST</b>
═══════════════════════════════════════════════════════

<b>➕ Добавление доступа:</b>
• <code>/adduser_123456</code> - Добавить пользователя по Telegram ID
• <code>/addusername_username</code> - Добавить пользователя по username (без @)

<b>➖ Удаление доступа:</b>
• <code>/removeuser_123456</code> - Удалить пользователя по ID
• <code>/removeusername_username</code> - Удалить пользователя по username

<b>📋 Примеры:</b>
• <code>/adduser_546321644</code>
• <code>/addusername_johnsmith</code>
• <code>/removeuser_546321644</code>
• <code>/removeusername_johnsmith</code>

═══════════════════════════════════════════════════════
📊 <b>МОНИТОРИНГ И СТАТИСТИКА</b>
═══════════════════════════════════════════════════════

<b>📈 Доступная статистика:</b>
• Общее количество пользователей
• Активные/заблокированные пользователи
• Пользователи с сохраненными словами
• Активность за 24ч/7д/30д
• Топ пользователей по словарному запасу
• Популярные сохраненные слова

<b>🔄 Обновление данных:</b>
• Все статистики обновляются в реальном времени
• Кнопка "Обновить" для принудительного обновления

═══════════════════════════════════════════════════════
🛡️ <b>БЕЗОПАСНОСТЬ И ЛУЧШИЕ ПРАКТИКИ</b>
═══════════════════════════════════════════════════════

<b>⚠️ Важные правила:</b>
• Никогда не удаляйте пользователей без крайней необходимости
• Блокировка - более безопасная альтернатива удалению
• Регулярно проверяйте статистику на подозрительную активность
• Осторожно с командами удаления - они необратимы

<b>🔍 Поиск проблемных пользователей:</b>
• Используйте поиск для быстрого доступа к конкретным пользователям
• Проверяйте дату регистрации и последней активности
• Обращайте внимание на пользователей без имени

<b>📝 Логирование:</b>
• Все административные действия логируются
• Проверяйте логи для отслеживания изменений
• Время блокировки и ID администратора сохраняются

═══════════════════════════════════════════════════════
🚨 <b>ЭКСТРЕННЫЕ СИТУАЦИИ</b>
═══════════════════════════════════════════════════════

<b>🔧 Если бот не отвечает:</b>
1. Проверьте <code>/testdb</code>
2. Перезапустите бота
3. Проверьте логи на ошибки

<b>🛑 При массовом спаме:</b>
1. Быстро заблокируйте проблемного пользователя
2. Используйте поиск для поиска связанных аккаунтов
3. При необходимости отключите регистрацию новых пользователей

<b>📞 Техническая поддержка:</b>
• Сохраняйте ID проблемных пользователей
• Делайте скриншоты ошибок
• Записывайте время возникновения проблем

═══════════════════════════════════════════════════════
✨ <b>ДОПОЛНИТЕЛЬНЫЕ ВОЗМОЖНОСТИ</b>
═══════════════════════════════════════════════════════

<b>📄 Пагинация:</b>
• Пользователи отображаются по 10 на страницу
• Используйте кнопки ⬅️➡️ для навигации

<b>🎯 Быстрые действия:</b>
• Клик по результату поиска показывает полную информацию
• Команды блокировки доступны прямо из результатов поиска

<b>💡 Советы:</b>
• Используйте поиск вместо пролистывания всех пользователей
• Регулярно проверяйте подробную статистику
• Ведите записи важных административных решений"""

    keyboard = [
        [InlineKeyboardButton("🔙 Назад к админ-панели", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_long_message(update, context, help_text, reply_markup, parse_mode='HTML')

async def handle_admin_search_input(update: Update, context: CallbackContext) -> None:
    """Handle admin search input"""
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    query = update.message.text.strip()
    context.user_data.pop('waiting_for_admin_search', None)
    
    # Clean username query
    if query.startswith('@'):
        query = query[1:]
    
    users = db.search_users(query)
    
    search_text = f"🔍 <b>Результаты поиска: '{query}'</b>\n\n"
    
    if not users:
        search_text += "📝 Пользователи не найдены.\n"
        keyboard = [
            [InlineKeyboardButton("🔍 Новый поиск", callback_data="admin_search")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_users")],
        ]
    else:
        for user_id, username, first_name, last_name, is_active, is_blocked, created_at, last_activity in users:
            status_emoji = "🚫" if is_blocked else "✅"
            name = first_name or "Без имени"
            if last_name:
                name += f" {last_name}"
            username_text = f"@{username}" if username else "Без username"
            
            search_text += f"{status_emoji} <b>{name}</b>\n"
            search_text += f"🆔 {user_id} | {username_text}\n"
            search_text += f"📅 {created_at[:10]} | 🕒 {last_activity[:10]}\n"
            
            # Add management buttons for each user
            vocab_count = db.get_user_vocabulary_count(user_id)
            search_text += f"📚 Словарь: {vocab_count} слов\n"
            search_text += f"Действия: /block_{user_id} | /unblock_{user_id} | /delete_{user_id}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔍 Новый поиск", callback_data="admin_search")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_users")],
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await send_long_message(update, context, search_text, reply_markup, parse_mode='HTML')

@require_admin
async def admin_block_user_command(update: Update, context: CallbackContext) -> None:
    """Handle /block_<user_id> command"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])
        admin_id = update.effective_user.id
        
        if target_user_id == admin_id:
            await update.message.reply_text("❌ Вы не можете заблокировать себя!")
            return
        
        if is_admin(target_user_id):
            await update.message.reply_text("❌ Вы не можете заблокировать другого администратора!")
            return
        
        success = db.block_user(target_user_id, admin_id)
        
        if success:
            await update.message.reply_text(f"✅ Пользователь {target_user_id} заблокирован.")
        else:
            await update.message.reply_text(f"❌ Не удалось заблокировать пользователя {target_user_id}.")
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /block_<user_id>")

@require_admin
async def admin_unblock_user_command(update: Update, context: CallbackContext) -> None:
    """Handle /unblock_<user_id> command"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])
        
        success = db.unblock_user(target_user_id)
        
        if success:
            await update.message.reply_text(f"✅ Пользователь {target_user_id} разблокирован.")
        else:
            await update.message.reply_text(f"❌ Не удалось разблокировать пользователя {target_user_id}.")
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /unblock_<user_id>")

@require_admin 
async def admin_delete_user_command(update: Update, context: CallbackContext) -> None:
    """Handle /delete_<user_id> command"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])
        admin_id = update.effective_user.id
        
        if target_user_id == admin_id:
            await update.message.reply_text("❌ Вы не можете удалить себя!")
            return
        
        if is_admin(target_user_id):
            await update.message.reply_text("❌ Вы не можете удалить другого администратора!")
            return
        
        # Get user info before deletion
        user_info = db.get_user_info(target_user_id)
        if not user_info:
            await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден.")
            return
        
        vocab_count = db.get_user_vocabulary_count(target_user_id)
        success = db.delete_user(target_user_id)
        
        if success:
            name = user_info[2] or "Без имени"
            await update.message.reply_text(
                f"✅ Пользователь удален:\n"
                f"🆔 {target_user_id}\n"
                f"👤 {name}\n"
                f"📚 Удалено слов: {vocab_count}"
            )
        else:
            await update.message.reply_text(f"❌ Не удалось удалить пользователя {target_user_id}.")
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /delete_<user_id>")

@require_admin
async def admin_add_user_command(update: Update, context: CallbackContext) -> None:
    """Handle /adduser_<user_id> command"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])
        
        # Add to whitelist programmatically (for session only)
        if target_user_id not in config.AUTHORIZED_USER_IDS:
            config.AUTHORIZED_USER_IDS.append(target_user_id)
            await update.message.reply_text(
                f"✅ Пользователь {target_user_id} добавлен в whitelist!\n"
                f"⚠️ Чтобы сохранить навсегда, добавьте его ID в config.py"
            )
        else:
            await update.message.reply_text(f"⚠️ Пользователь {target_user_id} уже в whitelist!")
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /adduser_<user_id>")

@require_admin
async def admin_remove_user_command(update: Update, context: CallbackContext) -> None:
    """Handle /removeuser_<user_id> command"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])
        
        if target_user_id == update.effective_user.id:
            await update.message.reply_text("❌ Вы не можете удалить себя из whitelist!")
            return
        
        # Remove from whitelist programmatically (for session only)
        if target_user_id in config.AUTHORIZED_USER_IDS:
            config.AUTHORIZED_USER_IDS.remove(target_user_id)
            await update.message.reply_text(
                f"✅ Пользователь {target_user_id} удален из whitelist!\n"
                f"⚠️ Чтобы сохранить навсегда, удалите его ID из config.py"
            )
        else:
            await update.message.reply_text(f"⚠️ Пользователь {target_user_id} не найден в whitelist!")
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /removeuser_<user_id>")

@require_admin
async def admin_whitelist_status_command(update: Update, context: CallbackContext) -> None:
    """Handle /whitelist command - show whitelist status"""
    status_text = f"🔐 <b>Статус Whitelist</b>\n\n"
    status_text += f"📊 Состояние: {'🟢 Включен' if config.ENABLE_WHITELIST else '🔴 Выключен'}\n"
    status_text += f"👥 Авторизованных пользователей: {len(config.AUTHORIZED_USER_IDS)}\n"
    status_text += f"🏷️ Авторизованных usernames: {len(config.AUTHORIZED_USERNAMES)}\n\n"
    
    if config.AUTHORIZED_USER_IDS:
        status_text += f"📋 <b>ID пользователей:</b>\n"
        for user_id in config.AUTHORIZED_USER_IDS:
            admin_mark = " (Админ)" if is_admin(user_id) else ""
            status_text += f"• {user_id}{admin_mark}\n"
    
    if config.AUTHORIZED_USERNAMES:
        status_text += f"\n📋 <b>Usernames:</b>\n"
        for username in config.AUTHORIZED_USERNAMES:
            status_text += f"• @{username}\n"
    
    status_text += f"\n💡 <b>Управление:</b>\n"
    status_text += f"• /adduser_123456 - Добавить по ID\n"
    status_text += f"• /removeuser_123456 - Удалить по ID\n"
    status_text += f"• /addusername_username - Добавить по username\n"
    status_text += f"• /removeusername_username - Удалить по username\n"
    
    await update.message.reply_text(status_text, parse_mode='HTML')

@require_admin
async def admin_add_username_command(update: Update, context: CallbackContext) -> None:
    """Handle /addusername_<username> command"""
    command_text = update.message.text
    try:
        parts = command_text.split('_', 1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Неверный формат команды. Используйте: /addusername_username")
            return
            
        target_username = parts[1].lower().replace('@', '')  # Remove @ if present
        
        # Add to username whitelist programmatically (for session only)
        if target_username not in [u.lower() for u in config.AUTHORIZED_USERNAMES]:
            config.AUTHORIZED_USERNAMES.append(target_username)
            await update.message.reply_text(
                f"✅ Username @{target_username} добавлен в whitelist!\n"
                f"⚠️ Чтобы сохранить навсегда, добавьте username в config.py"
            )
        else:
            await update.message.reply_text(f"⚠️ Username @{target_username} уже в whitelist!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

@require_admin
async def admin_remove_username_command(update: Update, context: CallbackContext) -> None:
    """Handle /removeusername_<username> command"""
    command_text = update.message.text
    try:
        parts = command_text.split('_', 1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Неверный формат команды. Используйте: /removeusername_username")
            return
            
        target_username = parts[1].lower().replace('@', '')  # Remove @ if present
        
        # Remove from username whitelist programmatically (for session only)
        usernames_lower = [u.lower() for u in config.AUTHORIZED_USERNAMES]
        if target_username in usernames_lower:
            # Find and remove the original case username
            for username in config.AUTHORIZED_USERNAMES:
                if username.lower() == target_username:
                    config.AUTHORIZED_USERNAMES.remove(username)
                    break
            await update.message.reply_text(
                f"✅ Username @{target_username} удален из whitelist!\n"
                f"⚠️ Чтобы сохранить навсегда, удалите username из config.py"
            )
        else:
            await update.message.reply_text(f"⚠️ Username @{target_username} не найден в whitelist!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

@require_access
async def handle_writing_check_global(update: Update, context: CallbackContext) -> None:
    """Handle the 'Check Essay' button press - for global handler (menu-based access)"""
    user = update.effective_user
    
    query = update.callback_query
    await query.answer()
    
    # End any existing conversation
    if context.user_data.get('waiting_for_writing_topic'):
        context.user_data.pop('waiting_for_writing_topic', None)
    if context.user_data.get('selected_writing_task_type'):
        context.user_data.pop('selected_writing_task_type', None)
    if context.user_data.get('current_writing_topic'):
        context.user_data.pop('current_writing_topic', None)
    
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
