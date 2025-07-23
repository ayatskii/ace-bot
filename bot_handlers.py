from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters
import logging
from gemini_api import get_random_word_details, generate_ielts_writing_task, get_topic_specific_words, evaluate_writing, generate_speaking_question, generate_ielts_strategies, explain_grammar_structure

logger = logging.getLogger(__name__)

GET_WRITING_TOPIC = 1
GET_GRAMMAR_TOPIC = 2


# Add this to the top of bot_handlers.py
import re

def escape_markdown_v2(text: str) -> str:
    """Escapes text for Telegram's MarkdownV2 parse mode."""
    # The characters that need escaping are: _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    welcome_message = (
        f"👋 Hello, {user.first_name}!\n\n"
        "I am your IELTS preparation assistant, powered by ACE.\n\n"
        "You can use me to practice vocabulary, writing, speaking, and more.\n\n"
        "Type /help to see all available commands."
    )
    await update.message.reply_text(welcome_message)

async def help_command(update:Update, context: CallbackContext) -> None:
    help_text = (
        "Here are the commands you can use:\n\n"
        "🧠 /vocabulary - Get new vocabulary words.\n"
        "✍️ /writing - Get an IELTS writing task.\n"
        "🗣️ /speaking - Get an IELTS speaking card.\n"
        "ℹ️ /info - Get tips and strategies for IELTS sections.\n"
        "📖 /grammar - Get an explanation of a grammar topic.\n"
        "🆘 /help - Show this help message again."
    )
    await update.message.reply_text(help_text)

async def handle_vocabulary_command(update:Update, context: CallbackContext) -> None:
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    word_details = get_random_word_details()
    await update.message.reply_text(word_details, parse_mode='Markdown')

async def handle_writing_command(update:Update, context: CallbackContext) -> None:
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("Coming Soon!!")

async def handle_speaking_command(update:Update, context: CallbackContext) -> None:
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("Coming Soon!!")

async def handle_ielts_info_command(update:Update, context: CallbackContext) -> None:
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("Coming Soon!!")

async def handle_grammar_command(update:Update, context: CallbackContext) -> None:
    context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("Coming Soon!!")

async def handle_text_input(update: Update, context: CallbackContext) -> None:
    """Handles general text input for conversational flows."""
    # This is a placeholder response.
    # Later, you will add logic here to check if the user is in the middle
    # of a writing submission, a grammar query, etc.
    update.message.reply_text("I've received your text. Conversational features are coming soon!")    

async def error_handler(update:Update, context: CallbackContext) -> None:
    logger.error(f"Update '{update}' caused error '{context.error}'")

ASK_WRITING_SUBMISSION = 1
ASK_GRAMMAR_TOPIC = 2    

async def start_writing_task(update: Update, context: CallbackContext) -> int:
    """Starts the writing task conversation and asks for a topic."""
    await update.message.reply_text("💬 Please tell me the topic for your writing task.")
    
    # Transition to the GET_TOPIC state to wait for the user's answer
    return GET_WRITING_TOPIC

async def get_topic(update: Update, context: CallbackContext) -> int:
    """Saves the user's topic and generates the task."""
    user_topic = update.message.text
    
    # Save the topic in the context for later use
    context.user_data['writing_topic'] = user_topic
    
    await update.message.reply_text(f"✅ Great! Generating a writing task on the topic: '{user_topic}'")
    
    # --- Now you can call your Gemini API function ---
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    writing_task = generate_ielts_writing_task(topic=user_topic)
    await update.message.reply_text(writing_task, parse_mode='Markdown')
    
    # End the conversation
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# Add these two functions to bot_handlers.py

async def handle_speaking_command(update: Update, context: CallbackContext) -> None:
    """Sends a message with three inline buttons for choosing a speaking part."""
    keyboard = [
        [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
        [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
        [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите часть устного экзамена для практики:", reply_markup=reply_markup)

async def speaking_part_callback(update: Update, context: CallbackContext) -> None:
    """Parses the CallbackQuery and generates the speaking questions."""
    query = update.callback_query

    # Answer the callback query to remove the "loading" state from the button
    await query.answer()

    # The callback_data will be "speaking_part_1", "speaking_part_2", etc.
    part_data = query.data
    part_number_str = part_data.split('_')[-1]  # Extracts "1", "2", or "3"
    part_for_api = f"Part {part_number_str}"

    # Let the user know the bot is working by editing the original message
    await query.edit_message_text(text=f"Отлично! 👍 Генерирую вопросы для {part_for_api}...")

    # Call your Gemini API function
    speaking_prompt = generate_speaking_question(part=part_for_api)

    speaking_prompt = escape_markdown_v2(speaking_prompt)

    # Send the generated content back to the user by editing the message again
    await query.edit_message_text(text=speaking_prompt, parse_mode='MarkdownV2')

async def receive_writing_task_type(update, context):
    """Receives the user's choice of Task 1 or Task 2 and then generates the task."""
    user_choice = update.message.text.strip().lower()
    task_type = None
    if "task 1" in user_choice:
        task_type = "Task 1"
    elif "task 2" in user_choice:
        task_type = "Task 2"
    else:
        await update.message.reply_text("Invalid task type. Please say 'Task 1' or 'Task 2'.")
        return ASK_WRITING_SUBMISSION # Stay in the same state to re-prompt

    task_description = await generate_ielts_writing_task(task_type=task_type)
    context.user_data['current_writing_task_description'] = task_description # Store for feedback
    await update.message.reply_text(f"Here is your {task_type}:\n\n{task_description}\n\nPlease write your response and send it to me.")
    return ConversationHandler.END

async def handle_writing_submission(update, context):
    student_writing = update.message.text
    task_description = context.user_data.get('current_writing_task_description', 'No specific task given.')
    
    await update.message.reply_text("Checking your writing, please wait...")
    feedback = await evaluate_writing(student_writing, task_description)
    await update.message.reply_text(f"Here's the feedback on your writing:\n\n{feedback}")
    context.user_data.pop('current_writing_task_description', None)

async def handle_grammar_command(update, context):
    await update.message.reply_text("What grammar topic would you like to learn about? E.g., 'Present Perfect', 'Conditional Sentences', 'Passive Voice'.")
    return ASK_GRAMMAR_TOPIC # Transition to the state where we expect grammar topic

# async def handle_grammar_input(update, context):
#     """Receives the user's grammar topic and provides explanation."""
#     grammar_topic = update.message.text
#     await update.message.reply_text(f"Getting explanation for '{grammar_topic}', please wait...")
#     explanation = await grammar_module.explain_grammar_structure(grammar_topic)
#     await update.message.reply_text(f"Here's an explanation of '{grammar_topic}':\n\n{explanation}")
#     return ConversationHandler.END # End the    

async def handle_info_command(update: Update, context: CallbackContext) -> None:
    """Sends a message with inline buttons for Listening and Reading sections."""
    keyboard = [
        [
            InlineKeyboardButton("🎧 Listening Strategies", callback_data="info_listening"),
        ],
        [
            InlineKeyboardButton("📖 Reading Strategies", callback_data="info_reading"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose the section you want tips for:", reply_markup=reply_markup)


# In bot_handlers.py

async def info_section_callback(update: Update, context: CallbackContext) -> None:
    """Parses the user's section choice and sends the AI-generated strategies."""
    query = update.callback_query
    await query.answer()

    section = query.data.split('_')[1]

    await query.edit_message_text(text=f"Great! Fetching top strategies for the {section.capitalize()} section...")

    # Get the fully formatted message directly from the API
    strategies_text = generate_ielts_strategies(section=section)
    
    # ✅ Send the AI's response directly. It already contains the title and formatting.
    await query.edit_message_text(text=strategies_text, parse_mode='Markdown')

async def start_grammar_explanation(update: Update, context: CallbackContext) -> int:
    """Asks the user for a grammar topic."""
    await update.message.reply_text(
        "📖 What grammar topic would you like an explanation for?\n\n"
        "For example: 'Present Perfect', 'using articles', or 'phrasal verbs'."
    )
    # Transition to the state where we wait for the topic
    return GET_GRAMMAR_TOPIC


async def get_grammar_topic(update: Update, context: CallbackContext) -> int:
    """Fetches the grammar explanation from the AI and ends the conversation."""
    grammar_topic = update.message.text
    
    await update.message.reply_text(f"Sure! Generating an explanation for '{grammar_topic}'...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Call your Gemini API function
    explanation = explain_grammar_structure(grammar_topic=grammar_topic)

    await update.message.reply_text(explanation, parse_mode='MarkdownV2')
    
    # End the conversation
    return ConversationHandler.END

grammar_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("grammar", start_grammar_explanation)],
    states={
        GET_GRAMMAR_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_grammar_topic)],
    },
    # You can reuse the 'cancel' function from your other conversation handler
    fallbacks=[CommandHandler("cancel", cancel)],
)

writing_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("writing", start_writing_task)],
    states={
        GET_WRITING_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
