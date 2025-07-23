from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging
import re

from gemini_api import (
    get_random_word_details, generate_ielts_writing_task, evaluate_writing,
    generate_speaking_question, generate_ielts_strategies, explain_grammar_structure
)

logger = logging.getLogger(__name__)

# --- Conversation States ---
GET_WRITING_TOPIC = 1
GET_WRITING_SUBMISSION = 2
GET_GRAMMAR_TOPIC = 3

# --- Utility Functions ---
def escape_markdown_v2(text: str) -> str:
    """Escapes all special characters for Telegram's MarkdownV2 parse mode."""
    if not text: return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def get_common_buttons(generate_again_callback: str = None) -> InlineKeyboardMarkup:
    """Generates an InlineKeyboardMarkup with an optional 'Generate Again' button."""
    if not generate_again_callback: return None
    keyboard = [[InlineKeyboardButton("🔄 Generate Again", callback_data=generate_again_callback)]]
    return InlineKeyboardMarkup(keyboard)

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

# --- Core Command Handlers ---
async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    welcome_message = (f"👋 Hello, {user.first_name}!\n\nI am your IELTS preparation assistant...")
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = ("Here are the commands you can use:\n\n"
                 "🧠 /vocabulary - Get new vocabulary words.\n"
                 "✍️ /writing - Get an IELTS writing task.\n"
                 "🗣️ /speaking - Get an IELTS speaking card.\n"
                 "ℹ️ /info - Get tips and strategies.\n"
                 "📖 /grammar - Get an explanation of a grammar topic.")
    await update.message.reply_text(help_text)

# --- VOCABULARY ---
async def handle_vocabulary_command(update: Update, context: CallbackContext) -> None:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    word_details = get_random_word_details()
    reply_markup = get_common_buttons(generate_again_callback="regenerate_vocabulary")
    await send_or_edit_safe_text(update, context, word_details, reply_markup)

async def regenerate_vocabulary_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="🔄 Generating a new word...", reply_markup=None)
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    word_details = get_random_word_details()
    reply_markup = get_common_buttons(generate_again_callback="regenerate_vocabulary")
    await send_or_edit_safe_text(update, context, word_details, reply_markup)

# --- WRITING (Conversation) ---
async def start_writing_task(update: Update, context: CallbackContext) -> int:
    logger.info(f"🎯 Writing command triggered by user {update.effective_user.id}")
    keyboard = [
        [InlineKeyboardButton("Task 1 (Report/Letter)", callback_data="writing_task_type_1")],
        [InlineKeyboardButton("Task 2 (Essay)", callback_data="writing_task_type_2")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✍️ Which type of writing task do you need?", reply_markup=reply_markup)
    logger.info(f"✅ Writing task options sent to user {update.effective_user.id}, returning state {GET_WRITING_TOPIC}")
    return GET_WRITING_TOPIC

async def handle_writing_task_type_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    task_type_choice = query.data.split('_')[-1]
    context.user_data['selected_writing_task_type'] = f"Task {task_type_choice}"
    logger.info(f"🎯 User {update.effective_user.id} selected writing task type: {context.user_data['selected_writing_task_type']}")
    await query.edit_message_text(f"✅ You chose {context.user_data['selected_writing_task_type']}. Now, please tell me the topic for your writing task.")
    logger.info(f"✅ User {update.effective_user.id} needs to provide topic, staying in state {GET_WRITING_TOPIC}")
    return GET_WRITING_TOPIC

async def get_topic_and_generate_writing(update: Update, context: CallbackContext) -> int:
    user_topic = update.message.text
    selected_task_type = context.user_data.get('selected_writing_task_type', 'Task 2')
    context.user_data['current_writing_topic'] = user_topic
    logger.info(f"🎯 Writing: User {update.effective_user.id} provided topic: '{user_topic}' for {selected_task_type}")
    
    await update.message.reply_text(f"✅ Great! Generating a {selected_task_type} task on the topic: '{user_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    writing_task = generate_ielts_writing_task(task_type=selected_task_type, topic=user_topic)
    context.user_data['current_writing_task_description'] = writing_task
    
    reply_markup = get_common_buttons(generate_again_callback="regenerate_writing_task")
    message_text = (f"Here is your {selected_task_type}:\n\n{writing_task}\n\n"
                    "Please write your response and send it to me.")
    await send_or_edit_safe_text(update, context, message_text, reply_markup)
    logger.info(f"✅ Writing task generated for user {update.effective_user.id}, moving to submission state")
    return GET_WRITING_SUBMISSION

async def regenerate_writing_task_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    selected_task_type = context.user_data.get('selected_writing_task_type', 'Task 2')
    user_topic = context.user_data.get('current_writing_topic', 'general')
    await query.edit_message_text(text=f"🔄 Regenerating {selected_task_type} on '{user_topic}'...", reply_markup=None)
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    
    new_writing_task = generate_ielts_writing_task(task_type=selected_task_type, topic=user_topic)
    context.user_data['current_writing_task_description'] = new_writing_task
    
    reply_markup = get_common_buttons(generate_again_callback="regenerate_writing_task")
    message_text = (f"Here is your new {selected_task_type}:\n\n{new_writing_task}\n\n"
                    "Please write your response and send it to me.")
    await send_or_edit_safe_text(update, context, message_text, reply_markup)
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
    return ConversationHandler.END

# --- SPEAKING ---
async def handle_speaking_command(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
        [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
        [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗣️ Выберите часть устного экзамена для практики:", reply_markup=reply_markup)

async def speaking_part_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    part_data = query.data
    part_number_str = part_data.split('_')[-1]
    part_for_api = f"Part {part_number_str}"
    context.user_data['current_speaking_part'] = part_for_api
    await query.edit_message_text(text=f"Отлично! 👍 Генерирую вопросы для {part_for_api}...")
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    speaking_prompt = generate_speaking_question(part=part_for_api)
    reply_markup = get_common_buttons(generate_again_callback=f"regenerate_speaking_{part_number_str}")
    await send_or_edit_safe_text(update, context, speaking_prompt, reply_markup)

async def regenerate_speaking_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    part_number_str = query.data.split('_')[-1]
    part_for_api = context.user_data.get('current_speaking_part', f"Part {part_number_str}")
    await query.edit_message_text(text=f"🔄 Regenerating questions for {part_for_api}...", reply_markup=None)
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    new_speaking_prompt = generate_speaking_question(part=part_for_api)
    reply_markup = get_common_buttons(generate_again_callback=f"regenerate_speaking_{part_number_str}")
    await send_or_edit_safe_text(update, context, new_speaking_prompt, reply_markup)

# --- IELTS INFO ---
async def handle_info_command(update: Update, context: CallbackContext) -> None:
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
    await update.message.reply_text("ℹ️ Choose the specific IELTS task type you want strategies for:", reply_markup=reply_markup)

async def info_section_callback(update: Update, context: CallbackContext) -> None:
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
    reply_markup = get_common_buttons(generate_again_callback=f"regenerate_info_{section}_{task_type}")
    await send_or_edit_safe_text(update, context, strategies_text, reply_markup)

async def regenerate_info_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    # Extract section and task type from callback data or user_data
    callback_parts = query.data.split('_')
    if len(callback_parts) >= 4:  # regenerate_info_listening_truefalse
        section = callback_parts[2]  # listening
        task_type = '_'.join(callback_parts[3:])  # truefalse
    else:  # fallback to user_data
        section = context.user_data.get('current_info_section', 'listening')
        task_type = context.user_data.get('current_info_task_type', 'general')
    
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

    await query.edit_message_text(text=f"🔄 Regenerating strategies for {section_name} - {task_name}...", reply_markup=None)
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")

    new_strategies_text = generate_ielts_strategies(section=section, task_type=task_type)
    reply_markup = get_common_buttons(generate_again_callback=f"regenerate_info_{section}_{task_type}")
    await send_or_edit_safe_text(update, context, new_strategies_text, reply_markup)

# --- GRAMMAR (Conversation) ---
async def start_grammar_explanation(update: Update, context: CallbackContext) -> int:
    logger.info(f"🎯 Grammar command triggered by user {update.effective_user.id}")
    await update.message.reply_text(
        "📖 What grammar topic would you like an explanation for?\n\n"
        "For example: 'Present Perfect', 'using articles', or 'phrasal verbs'."
    )
    logger.info(f"✅ Grammar prompt sent to user {update.effective_user.id}, returning state {GET_GRAMMAR_TOPIC}")
    return GET_GRAMMAR_TOPIC

async def get_grammar_topic(update: Update, context: CallbackContext) -> int:
    grammar_topic = update.message.text
    context.user_data['current_grammar_topic'] = grammar_topic
    logger.info(f"🎯 Grammar: User {update.effective_user.id} requested explanation for: '{grammar_topic}'")
    
    await update.message.reply_text(f"Sure! Generating an explanation for '{grammar_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    explanation = explain_grammar_structure(grammar_topic=grammar_topic)
    reply_markup = get_common_buttons(generate_again_callback="regenerate_grammar")
    await send_or_edit_safe_text(update, context, explanation, reply_markup)
    logger.info(f"✅ Grammar explanation generated for user {update.effective_user.id}, ending conversation")
    return ConversationHandler.END

async def regenerate_grammar_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    grammar_topic = context.user_data.get('current_grammar_topic', 'general grammar')
    await query.edit_message_text(text=f"🔄 Regenerating explanation for '{grammar_topic}'...", reply_markup=None)
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
    new_explanation = explain_grammar_structure(grammar_topic=grammar_topic)
    reply_markup = get_common_buttons(generate_again_callback="regenerate_grammar")
    await send_or_edit_safe_text(update, context, new_explanation, reply_markup)
    return ConversationHandler.END

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
            CallbackQueryHandler(regenerate_writing_task_callback, pattern=r'^regenerate_writing_task$')
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
            CallbackQueryHandler(regenerate_grammar_callback, pattern=r'^regenerate_grammar$')
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    name="grammar_conversation",
    persistent=False
)