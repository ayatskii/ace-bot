# flashcard_handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging
from datetime import datetime
from database import db
from bot_handlers import require_access

logger = logging.getLogger(__name__)

# Flashcard conversation states
FLASHCARD_DECK_NAME = 10
FLASHCARD_DECK_DESCRIPTION = 11
FLASHCARD_ADD_FRONT = 12
FLASHCARD_ADD_BACK = 13
FLASHCARD_ADD_TAGS = 14
FLASHCARD_STUDY_SESSION = 15
FLASHCARD_REVIEW_RATING = 16

def parse_word_details(word_details: str) -> dict:
    """Parse word details from Gemini API response"""
    try:
        lines = word_details.strip().split('\n')
        parsed = {
            'word': '',
            'definition': '',
            'translation': '',
            'example': ''
        }
        
        for line in lines:
            line = line.strip()
            if 'Word:' in line:
                parsed['word'] = line.split('Word:')[1].strip()
            elif 'Definition:' in line:
                parsed['definition'] = line.split('Definition:')[1].strip()
            elif 'Translation:' in line:
                parsed['translation'] = line.split('Translation:')[1].strip()
            elif 'Example:' in line:
                parsed['example'] = line.split('Example:')[1].strip()
        
        return parsed
    except Exception as e:
        logger.error(f"Error parsing word details: {e}")
        return {
            'word': 'Unknown',
            'definition': 'No definition available',
            'translation': 'Нет перевода',
            'example': 'No example available'
        }

# === FLASHCARD SYSTEM HANDLERS ===

@require_access
async def handle_flashcard_menu(update: Update, context: CallbackContext) -> None:
    """Main flashcard menu"""
    user = update.effective_user
    
    # Get user vocabulary stats
    user_vocabulary = db.get_user_vocabulary(user.id, limit=50)
    vocabulary_count = db.get_user_vocabulary_count(user.id)
    
    text = (
        f"🎓 <b>СИСТЕМА FLASHCARDS</b>\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"📖 Слов в словаре: {vocabulary_count}\n"
        f"🎯 Доступно для изучения: {len(user_vocabulary)}\n"
        f"🎲 Используем ваш словарь + случайные слова\n\n"
        f"<i>💡 Выберите действие:</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 Изучать карточки", callback_data="flashcard_study")],
        [InlineKeyboardButton("🎲 Добавить случайные слова", callback_data="flashcard_add_random")],
        [InlineKeyboardButton("📚 Мой словарь", callback_data="profile_vocabulary")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

@require_access
async def handle_flashcard_study(update: Update, context: CallbackContext) -> None:
    """Start a study session using user vocabulary and random words"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    # Show loading message
    await query.edit_message_text(
        "🔄 <b>Подготавливаем карточки для изучения...</b>\n\n"
        "📚 Загружаем ваши слова из словаря\n"
        "🎲 Добавляем случайные слова IELTS\n"
        "🔀 Перемешиваем карточки\n\n"
        "<i>⏳ Это займет несколько секунд...</i>",
        parse_mode='HTML'
    )
    
    # Add a small delay for better UX
    import asyncio
    await asyncio.sleep(1)
    
    # Get user's vocabulary words
    user_vocabulary = db.get_user_vocabulary(user.id, limit=50)
    
    # Convert user vocabulary to flashcard format
    vocabulary_cards = []
    for word, definition, translation, example, topic, saved_at in user_vocabulary:
        vocabulary_cards.append({
            'id': f"vocab_{hash(word + str(user.id))}",  # Create unique ID
            'type': 'vocabulary',
            'front': word.upper(),
            'back': definition or f"Definition for {word}",
            'translation': translation or "",
            'example': example or "",
            'topic': topic or "vocabulary",
            'source': 'user_vocabulary'
        })
    
    # If user has fewer than 10 vocabulary words, add random words
    if len(vocabulary_cards) < 10:
        from gemini_api import get_random_word_details
        import re
        
        needed_cards = 10 - len(vocabulary_cards)
        for i in range(needed_cards):
            try:
                word_details = get_random_word_details()
                parsed = parse_word_details(word_details)
                
                vocabulary_cards.append({
                    'id': f"random_{i}_{user.id}",
                    'type': 'vocabulary',
                    'front': parsed['word'].upper(),
                    'back': parsed['definition'],
                    'translation': parsed['translation'],
                    'example': parsed['example'],
                    'topic': "random",
                    'source': 'random_word'
                })
            except Exception as e:
                logger.error(f"Failed to generate random word: {e}")
    
    if not vocabulary_cards:
        keyboard = [
            [InlineKeyboardButton("🎲 Добавить случайные слова", callback_data="flashcard_add_random")],
            [InlineKeyboardButton("🔙 Назад", callback_data="flashcard_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📚 <b>Пока нет слов для изучения!</b>\n\n"
            "💡 Добавьте слова в свой словарь или создайте колоду карточек.\n\n"
            "<i>Используйте /vocabulary для добавления слов в словарь</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return
    
    # Shuffle cards for variety
    import random
    random.shuffle(vocabulary_cards)
    
    # Limit to 15 cards per session
    vocabulary_cards = vocabulary_cards[:15]
    
    # Start study session
    context.user_data['study_session'] = {
        'cards': vocabulary_cards,
        'current_index': 0,
        'session_start': datetime.now(),
        'card_start_time': datetime.now(),
        'correct_count': 0,
        'total_count': len(vocabulary_cards)
    }
    
    await show_current_card(update, context)
    return FLASHCARD_STUDY_SESSION

async def show_current_card(update: Update, context: CallbackContext) -> None:
    """Show the current flashcard front"""
    session = context.user_data.get('study_session', {})
    cards = session.get('cards', [])
    current_index = session.get('current_index', 0)
    
    if current_index >= len(cards):
        await end_study_session(update, context)
        return
    
    card = cards[current_index]
    front_text = card.get('front', 'Unknown word')
    source = card.get('source', 'unknown')
    topic = card.get('topic', 'vocabulary')
    
    # Update card start time
    session['card_start_time'] = datetime.now()
    context.user_data['study_session'] = session
    
    progress = f"{current_index + 1}/{len(cards)}"
    source_emoji = "📖" if source == "user_vocabulary" else "🎲"
    source_text = "Ваш словарь" if source == "user_vocabulary" else "Случайное слово"
    
    text = (
        f"📚 <b>Карточка {progress}</b>\n"
        f"{source_emoji} <b>Источник:</b> {source_text}\n"
        f"🏷️ <b>Тема:</b> {topic}\n\n"
        f"❓ <b>Что означает это слово?</b>\n\n"
        f"<b>{front_text}</b>\n\n"
        f"<i>💡 Попробуйте вспомнить определение, затем нажмите 'Показать ответ'!</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("👁 Показать ответ", callback_data="flashcard_show_answer")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data="flashcard_skip")],
        [InlineKeyboardButton("❌ Закончить", callback_data="flashcard_end_session")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def show_card_answer(update: Update, context: CallbackContext) -> None:
    """Show the flashcard back and rating buttons"""
    query = update.callback_query
    await query.answer()
    
    session = context.user_data.get('study_session', {})
    cards = session.get('cards', [])
    current_index = session.get('current_index', 0)
    
    card = cards[current_index]
    front_text = card.get('front', 'Unknown word')
    back_text = card.get('back', 'No definition')
    translation = card.get('translation', '')
    example = card.get('example', '')
    source = card.get('source', 'unknown')
    topic = card.get('topic', 'vocabulary')
    
    progress = f"{current_index + 1}/{len(cards)}"
    source_emoji = "📖" if source == "user_vocabulary" else "🎲"
    source_text = "Ваш словарь" if source == "user_vocabulary" else "Случайное слово"
    
    text = (
        f"📚 <b>Карточка {progress}</b>\n"
        f"{source_emoji} <b>Источник:</b> {source_text}\n\n"
        f"❓ <b>Слово:</b> {front_text}\n\n"
        f"✅ <b>Определение:</b>\n{back_text}\n"
    )
    
    if translation:
        text += f"\n🇷🇺 <b>Перевод:</b> {translation}\n"
    
    if example:
        text += f"\n💡 <b>Пример:</b>\n<i>{example}</i>\n"
    
    text += f"\n<b>🎯 Как хорошо вы знали ответ?</b>"
    
    keyboard = [
        [InlineKeyboardButton("😰 Не знал", callback_data="flashcard_rate_1")],
        [InlineKeyboardButton("😐 Сложно", callback_data="flashcard_rate_2")],
        [InlineKeyboardButton("😊 Хорошо", callback_data="flashcard_rate_3")],
        [InlineKeyboardButton("😎 Легко", callback_data="flashcard_rate_4")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_card_rating(update: Update, context: CallbackContext, rating: int) -> None:
    """Handle card rating and move to next card"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    session = context.user_data.get('study_session', {})
    cards = session.get('cards', [])
    current_index = session.get('current_index', 0)
    
    # Calculate time spent on this card
    card_start_time = session.get('card_start_time', datetime.now())
    time_spent = int((datetime.now() - card_start_time).total_seconds())
    
    # Get card info
    card = cards[current_index]
    word = card.get('front', '').strip()
    source = card.get('source', 'unknown')
    
    # For user vocabulary words, update their progress or save for future flashcard sessions
    if source == 'user_vocabulary' and word:
        # Save word learning progress (simple tracking for now)
        logger.info(f"User {user.id} rated word '{word}' as {rating}")
    
    # Track correct answers
    if rating >= 3:  # Good or Easy
        session['correct_count'] = session.get('correct_count', 0) + 1
    
    # Move to next card
    session['current_index'] = current_index + 1
    context.user_data['study_session'] = session
    
    # Show brief feedback
    rating_text = {
        1: "Изучим еще раз!",
        2: "Нужно повторить",
        3: "Отлично знаете!",
        4: "Превосходно!"
    }
    
    feedback = f"✅ {rating_text.get(rating, 'Записано!')}"
    
    # Show next card or end session
    if current_index + 1 >= len(cards):
        await query.edit_message_text(
            f"{feedback}\n\n🏁 <b>Сессия завершена!</b>\n\n"
            f"<i>Подготавливаем результаты...</i>",
            parse_mode='HTML'
        )
        await end_study_session(update, context)
    else:
        await query.edit_message_text(f"{feedback}\n\n⏳ <i>Загружаем следующую карточку...</i>", parse_mode='HTML')
        import asyncio
        await asyncio.sleep(1)  # Brief pause
        await show_current_card(update, context)

async def end_study_session(update: Update, context: CallbackContext) -> None:
    """End study session and show results"""
    session = context.user_data.get('study_session', {})
    
    if not session:
        return ConversationHandler.END
    
    session_start = session.get('session_start', datetime.now())
    total_time = int((datetime.now() - session_start).total_seconds())
    correct_count = session.get('correct_count', 0)
    total_count = session.get('total_count', 0)
    
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0
    
    text = (
        f"🎉 <b>СЕССИЯ ЗАВЕРШЕНА!</b>\n\n"
        f"📊 <b>Результаты:</b>\n"
        f"⏱ Время: {total_time // 60}м {total_time % 60}с\n"
        f"✅ Правильно: {correct_count}/{total_count}\n"
        f"🎯 Точность: {accuracy:.0f}%\n\n"
        f"<i>🔥 Отличная работа! Продолжайте в том же духе!</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("📚 Еще карточки", callback_data="flashcard_study")],
        [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
        [InlineKeyboardButton("🎓 Flashcards меню", callback_data="flashcard_menu")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Clear session data
    context.user_data.pop('study_session', None)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    
    return ConversationHandler.END

@require_access
async def handle_create_deck(update: Update, context: CallbackContext) -> None:
    """Start deck creation process"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="flashcard_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📚 <b>СОЗДАНИЕ НОВОЙ КОЛОДЫ</b>\n\n"
        "Введите название для вашей новой колоды карточек:\n\n"
        "<i>💡 Например: 'Английские слова IELTS', 'История России', 'Математика 10 класс'</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    return FLASHCARD_DECK_NAME

async def handle_deck_name_input(update: Update, context: CallbackContext) -> None:
    """Handle deck name input"""
    deck_name = update.message.text.strip()
    
    if len(deck_name) < 3:
        await update.message.reply_text(
            "❌ Название слишком короткое. Минимум 3 символа.\n\n"
            "Попробуйте еще раз:"
        )
        return FLASHCARD_DECK_NAME
    
    if len(deck_name) > 100:
        await update.message.reply_text(
            "❌ Название слишком длинное. Максимум 100 символов.\n\n"
            "Попробуйте еще раз:"
        )
        return FLASHCARD_DECK_NAME
    
    context.user_data['new_deck_name'] = deck_name
    
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить", callback_data="flashcard_skip_description")],
        [InlineKeyboardButton("❌ Отмена", callback_data="flashcard_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Отлично! Название: <b>{deck_name}</b>\n\n"
        f"📝 Теперь введите описание колоды (необязательно):\n\n"
        f"<i>💡 Опишите, что будет в этой колоде</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    return FLASHCARD_DECK_DESCRIPTION

async def handle_deck_description_input(update: Update, context: CallbackContext) -> None:
    """Handle deck description input"""
    description = update.message.text.strip()
    
    if len(description) > 500:
        await update.message.reply_text(
            "❌ Описание слишком длинное. Максимум 500 символов.\n\n"
            "Попробуйте еще раз:"
        )
        return FLASHCARD_DECK_DESCRIPTION
    
    await create_deck_with_data(update, context, description)

async def handle_skip_description(update: Update, context: CallbackContext) -> None:
    """Handle skipping description"""
    query = update.callback_query
    await query.answer()
    
    await create_deck_with_data(update, context, "")

async def create_deck_with_data(update: Update, context: CallbackContext, description: str) -> None:
    """Create the deck with collected data"""
    user = update.effective_user
    deck_name = context.user_data.get('new_deck_name')
    
    # Create deck in database
    deck_id = db.create_deck(user.id, deck_name, description)
    
    if deck_id:
        text = (
            f"🎉 <b>КОЛОДА СОЗДАНА!</b>\n\n"
            f"📚 <b>Название:</b> {deck_name}\n"
            f"📝 <b>Описание:</b> {description or 'Без описания'}\n\n"
            f"<i>💡 Теперь добавьте карточки в колоду!</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить карточку", callback_data=f"flashcard_add_card_{deck_id}")],
            [InlineKeyboardButton("📋 Мои колоды", callback_data="flashcard_my_decks")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="flashcard_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Clear temporary data
        context.user_data.pop('new_deck_name', None)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        text = "❌ Ошибка при создании колоды. Попробуйте еще раз."
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="flashcard_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    return ConversationHandler.END

async def handle_add_random_words(update: Update, context: CallbackContext) -> None:
    """Add random words to user's vocabulary for flashcard practice"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎲 <b>Добавляем случайные слова...</b>\n\n"
        "🤖 Генерируем полезные слова для изучения IELTS\n"
        "📚 Уровень: IELTS Band 7-9 (C1/C2)\n"
        "🎯 Количество: 10 слов\n\n"
        "<i>⏳ Это займет 10-15 секунд...</i>",
        parse_mode='HTML'
    )
    
    try:
        from gemini_api import get_random_word_details
        
        words_added = 0
        for i in range(10):  # Add 10 random words
            try:
                word_details = get_random_word_details()
                parsed = parse_word_details(word_details)
                
                if parsed['word'] and parsed['definition']:
                    success = db.save_word_to_user_vocabulary(
                        user_id=user.id,
                        word=parsed['word'],
                        definition=parsed['definition'],
                        translation=parsed['translation'],
                        example=parsed['example'],
                        topic="random"
                    )
                    
                    if success:
                        words_added += 1
            except Exception as e:
                logger.error(f"Failed to add random word {i}: {e}")
        
        if words_added > 0:
            text = (
                f"✅ <b>Успешно добавлено слов: {words_added}</b>\n\n"
                f"📚 Теперь у вас есть слова для изучения!\n"
                f"🎯 Начните изучение карточек!"
            )
            
            keyboard = [
                [InlineKeyboardButton("📖 Начать изучение", callback_data="flashcard_study")],
                [InlineKeyboardButton("📚 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("🔙 Назад", callback_data="flashcard_menu")]
            ]
        else:
            text = (
                "❌ <b>Не удалось добавить слова</b>\n\n"
                "💡 Попробуйте добавить слова вручную через /vocabulary"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад", callback_data="flashcard_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error adding random words: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="flashcard_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❌ Ошибка при добавлении слов. Попробуйте позже.",
            reply_markup=reply_markup
        )

# Conversation handler for flashcards
flashcard_conversation_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(handle_create_deck, pattern="^flashcard_create_deck$"),
        CallbackQueryHandler(handle_flashcard_study, pattern="^flashcard_study$"),
        CallbackQueryHandler(handle_add_random_words, pattern="^flashcard_add_random$"),
    ],
    states={
        FLASHCARD_DECK_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deck_name_input),
            CallbackQueryHandler(handle_flashcard_menu, pattern="^flashcard_menu$"),
        ],
        FLASHCARD_DECK_DESCRIPTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deck_description_input),
            CallbackQueryHandler(handle_skip_description, pattern="^flashcard_skip_description$"),
            CallbackQueryHandler(handle_flashcard_menu, pattern="^flashcard_menu$"),
        ],
        FLASHCARD_STUDY_SESSION: [
            CallbackQueryHandler(show_card_answer, pattern="^flashcard_show_answer$"),
            CallbackQueryHandler(lambda u, c: handle_card_rating(u, c, 1), pattern="^flashcard_rate_1$"),
            CallbackQueryHandler(lambda u, c: handle_card_rating(u, c, 2), pattern="^flashcard_rate_2$"),
            CallbackQueryHandler(lambda u, c: handle_card_rating(u, c, 3), pattern="^flashcard_rate_3$"),
            CallbackQueryHandler(lambda u, c: handle_card_rating(u, c, 4), pattern="^flashcard_rate_4$"),
            CallbackQueryHandler(lambda u, c: handle_card_rating(u, c, 2), pattern="^flashcard_skip$"),  # Skip = Hard
            CallbackQueryHandler(end_study_session, pattern="^flashcard_end_session$"),
            # Add handlers for end session buttons
            CallbackQueryHandler(handle_flashcard_study, pattern="^flashcard_study$"),
            CallbackQueryHandler(handle_flashcard_menu, pattern="^flashcard_menu$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(handle_flashcard_menu, pattern="^flashcard_menu$"),
        CallbackQueryHandler(handle_flashcard_study, pattern="^flashcard_study$"),
        CallbackQueryHandler(handle_add_random_words, pattern="^flashcard_add_random$"),
        CommandHandler("cancel", handle_flashcard_menu),
    ],
)
