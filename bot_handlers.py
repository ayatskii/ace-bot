from telegram import Update
from telegram.ext import CallbackContext, ConversationHandler
import logging
from gemini_api import get_random_word_details, generate_ielts_writing_task, get_topic_specific_words, evaluate_writing

logger = logging.getLogger(__name__)

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
        "🗣️ /speaking - Get an IELTS speaking prompt.\n"
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

async def handle_writing_command(update, context):
    """Starts the writing task conversation."""
    await update.message.reply_text("Please tell me if you want Task 1 or Task 2.")
    # Store the initial task type choice context if needed later
    # context.user_data['current_task'] = 'writing_task'
    return ASK_WRITING_SUBMISSION # Transition to the state where we expect task type

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

