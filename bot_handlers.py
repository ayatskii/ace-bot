from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging
import re
import sqlite3
import config
from datetime import datetime
from database import db

from gemini_api import (
    get_random_word_details, generate_ielts_writing_task, evaluate_writing,
    generate_speaking_question, generate_single_speaking_question, generate_ielts_strategies, explain_grammar_structure,
    get_topic_specific_words, evaluate_speaking_response, evaluate_speaking_response_for_simulation,
    extract_scores_from_evaluation, extract_writing_scores_from_evaluation, add_custom_word_to_dictionary
)
from audio_processor import audio_processor

logger = logging.getLogger(__name__)

# Add these new conversation states for full speaking simulation
FULL_SIM_PART_1 = 1
FULL_SIM_PART_2 = 2
FULL_SIM_PART_3 = 3

# Flashcard conversation states
FLASHCARD_DECK_NAME = 10
FLASHCARD_DECK_DESCRIPTION = 11
FLASHCARD_ADD_FRONT = 12
FLASHCARD_ADD_BACK = 13
FLASHCARD_ADD_TAGS = 14
FLASHCARD_STUDY_SESSION = 15
FLASHCARD_REVIEW_RATING = 16

# --- Group Chat Utility Functions ---
def is_group_chat(update: Update) -> bool:
    """Check if message comes from a group chat"""
    return update.effective_chat.type in ['group', 'supergroup']

def get_group_info(update: Update) -> dict:
    """Extract group information from update"""
    chat = update.effective_chat
    return {
        'group_id': chat.id,
        'group_title': chat.title or 'Unknown Group',
        'group_type': chat.type
    }

def extract_word_components(word_details: str) -> tuple:
    """Extract word, definition, translation, example from formatted text"""
    import re
    
    try:
        word_match = re.search(r'📝 Word: (.+)', word_details)
        definition_match = re.search(r'📖 Definition: (.+)', word_details)
        translation_match = re.search(r'🇷🇺 Translation: (.+)', word_details)
        example_match = re.search(r'💡 Example: (.+)', word_details)
        
        word = word_match.group(1).strip() if word_match else "Unknown"
        definition = definition_match.group(1).strip() if definition_match else ""
        translation = translation_match.group(1).strip() if translation_match else ""
        example = example_match.group(1).strip() if example_match else ""
        
        return (word, definition, translation, example)
    except Exception as e:
        logger.error(f"🔥 Failed to extract word components: {e}")
        return ("Unknown", "", "", "")

def get_random_word_for_group(group_id: int, max_attempts: int = 20) -> str:
    """Generate a random word that hasn't been sent to this group yet"""
    for attempt in range(max_attempts):
        word_details = get_random_word_details()
        word, _, _, _ = extract_word_components(word_details)
        
        if not db.is_word_sent_to_group(group_id, word):
            logger.info(f"✅ Generated unique word '{word}' for group {group_id} (attempt {attempt + 1})")
            return word_details
    
    # If all attempts failed, return a word anyway (fallback)
    logger.warning(f"⚠️ Could not find unique word for group {group_id} after {max_attempts} attempts, using fallback")
    return get_random_word_details()

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
GET_CUSTOM_WORD = 7
GET_CUSTOM_WORD_DEFINITION = 8
GET_CUSTOM_WORD_TRANSLATION = 9
GET_CUSTOM_WORD_EXAMPLE = 10
GET_CUSTOM_WORD_TOPIC = 11

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
    
    return formatted_text

# Add these utility functions for scoring and simulation
def calculate_weighted_overall_score(part_scores: dict) -> float:
    """Calculate weighted overall score based on IELTS importance"""
    PART_WEIGHTS = {
        1: 0.25,  # Part 1: 25% of total score
        2: 0.35,  # Part 2: 35% of total score (most important)
        3: 0.40   # Part 3: 40% of total score
    }
    
    total_score = 0
    total_weight = 0
    
    for part, score in part_scores.items():
        if score is not None and score > 0:
            total_score += score * PART_WEIGHTS[part]
            total_weight += PART_WEIGHTS[part]
    
    if total_weight == 0:
        return 0.0
    
    return round(total_score / total_weight, 1)

def determine_ielts_band(score: float) -> float:
    """Convert numerical score to IELTS band score"""
    if score >= 8.5:
        return 9.0
    elif score >= 7.5:
        return 8.0
    elif score >= 6.5:
        return 7.0
    elif score >= 5.5:
        return 6.0
    elif score >= 4.5:
        return 5.0
    elif score >= 3.5:
        return 4.0
    else:
        return 3.5

def generate_comprehensive_feedback(part_scores: dict, overall_band: float) -> str:
    """Generate comprehensive feedback based on part scores"""
    feedback_parts = []
    
    # Overall assessment
    if overall_band >= 8.0:
        feedback_parts.append("🎯 <b>Отличный результат!</b> Ваш уровень соответствует высоким требованиям IELTS.")
    elif overall_band >= 6.5:
        feedback_parts.append("✅ <b>Хороший результат!</b> Вы готовы к большинству университетских программ.")
    elif overall_band >= 5.5:
        feedback_parts.append("⚠️ <b>Удовлетворительный результат.</b> Рекомендуется дополнительная практика.")
    else:
        feedback_parts.append("📚 <b>Требуется улучшение.</b> Рекомендуется интенсивная подготовка.")
    
    # Part-specific feedback
    for part, score in part_scores.items():
        if score >= 7.0:
            feedback_parts.append(f"• <b>Часть {part}:</b> Сильная сторона")
        elif score >= 5.5:
            feedback_parts.append(f"• <b>Часть {part}:</b> Стабильная работа")
        else:
            feedback_parts.append(f"• <b>Часть {part}:</b> Требует внимания")
    
    return "\n".join(feedback_parts)

def calculate_simulation_time(context: CallbackContext) -> str:
    """Calculate total simulation time"""
    start_time = context.user_data.get('simulation_start_time', 0)
    if start_time == 0:
        return "Неизвестно"
    
    import time
    elapsed = int(time.time() - start_time)
    minutes = elapsed // 60
    seconds = elapsed % 60
    
    if minutes > 0:
        return f"{minutes} мин {seconds} сек"
    else:
        return f"{seconds} сек"

def calculate_overall_criteria_scores(part_scores: dict, part_evaluations: dict) -> dict:
    """Calculate overall scores for each IELTS criterion across all parts"""
    criteria_scores = {
        'fluency': [],
        'vocabulary': [],
        'grammar': [],
        'pronunciation': []
    }
    
    # Extract individual criterion scores from evaluations
    for part_num, evaluation in part_evaluations.items():
        if evaluation:
            # Try to extract scores from evaluation text
            scores = extract_scores_from_evaluation(evaluation)
            if scores:
                for criterion in criteria_scores.keys():
                    if criterion in scores:
                        criteria_scores[criterion].append(scores[criterion])
    
    # Calculate averages for each criterion
    overall_criteria = {}
    for criterion, scores in criteria_scores.items():
        if scores:
            overall_criteria[criterion] = round(sum(scores) / len(scores), 1)
        else:
            overall_criteria[criterion] = 0.0
    
    return overall_criteria

def generate_detailed_analysis(part_scores: dict, part_transcriptions: dict, 
                              part_evaluations: dict, overall_criteria: dict) -> str:
    """Generate detailed analysis with official IELTS criteria"""
    
    analysis = "📊 <b>ДЕТАЛЬНЫЙ АНАЛИЗ ПО КРИТЕРИЯМ IELTS</b>\n\n"
    
    # Overall performance summary
    total_score = sum(part_scores.values())
    avg_score = total_score / len(part_scores) if part_scores else 0
    
    analysis += f"🏆 <b>ОБЩАЯ ПРОИЗВОДИТЕЛЬНОСТЬ</b>\n"
    analysis += f"• Средний балл: {avg_score:.1f}/9\n"
    analysis += f"• Общий балл: {total_score}/27\n\n"
    
    # Official IELTS criteria analysis
    analysis += "📋 <b>ОФИЦИАЛЬНЫЕ КРИТЕРИИ IELTS SPEAKING</b>\n\n"
    
    # 1. Fluency and Coherence
    fluency_score = overall_criteria.get('fluency', 0)
    analysis += f"🎯 <b>1. Fluency and Coherence (Беглость и связность): {fluency_score}/9</b>\n"
    analysis += get_fluency_feedback(fluency_score)
    analysis += "\n"
    
    # 2. Lexical Resource
    vocab_score = overall_criteria.get('vocabulary', 0)
    analysis += f"📚 <b>2. Lexical Resource (Лексический запас): {vocab_score}/9</b>\n"
    analysis += get_vocabulary_feedback(vocab_score)
    analysis += "\n"
    
    # 3. Grammatical Range and Accuracy
    grammar_score = overall_criteria.get('grammar', 0)
    analysis += f"🔤 <b>3. Grammatical Range and Accuracy (Грамматика): {grammar_score}/9</b>\n"
    analysis += get_grammar_feedback(grammar_score)
    analysis += "\n"
    
    # 4. Pronunciation
    pron_score = overall_criteria.get('pronunciation', 0)
    analysis += f"🎤 <b>4. Pronunciation (Произношение): {pron_score}/9</b>\n"
    analysis += get_pronunciation_feedback(pron_score)
    analysis += "\n"
    
    # Part-by-part analysis
    analysis += "📊 <b>АНАЛИЗ ПО ЧАСТЯМ</b>\n\n"
    for part_num in sorted(part_scores.keys()):
        score = part_scores[part_num]
        transcription = part_transcriptions.get(part_num, "Недоступно")
        evaluation = part_evaluations.get(part_num, "Недоступно")
        
        analysis += f"<b>Часть {part_num}:</b> {score}/9\n"
        analysis += f"<i>Ответ: {transcription[:100]}{'...' if len(transcription) > 100 else ''}</i>\n"
        analysis += f"<i>Оценка: {evaluation[:200]}{'...' if len(evaluation) > 200 else ''}</i>\n\n"
    
    return analysis

def generate_detailed_analysis_with_questions(part_scores: dict, question_transcriptions: dict, 
                                            question_evaluations: dict, overall_criteria: dict, user_data: dict) -> str:
    """Generate detailed analysis with question-by-question breakdown"""
    
    analysis = "📊 <b>ДЕТАЛЬНЫЙ АНАЛИЗ ПО КРИТЕРИЯМ IELTS</b>\n\n"
    
    # Overall performance summary
    total_score = sum(part_scores.values())
    avg_score = total_score / len(part_scores) if part_scores else 0
    
    analysis += f"🏆 <b>ОБЩАЯ ПРОИЗВОДИТЕЛЬНОСТЬ</b>\n"
    analysis += f"• Средний балл: {avg_score:.1f}/9\n"
    analysis += f"• Общий балл: {total_score:.1f}/27\n\n"
    
    # Official IELTS criteria analysis
    analysis += "📋 <b>ОФИЦИАЛЬНЫЕ КРИТЕРИИ IELTS SPEAKING</b>\n\n"
    
    # 1. Fluency and Coherence
    fluency_score = overall_criteria.get('fluency', 0)
    analysis += f"🎯 <b>1. Fluency and Coherence (Беглость и связность): {fluency_score:.1f}/9</b>\n"
    analysis += get_fluency_feedback(fluency_score)
    analysis += "\n"
    
    # 2. Lexical Resource
    vocab_score = overall_criteria.get('vocabulary', 0)
    analysis += f"📚 <b>2. Lexical Resource (Лексический запас): {vocab_score:.1f}/9</b>\n"
    analysis += get_vocabulary_feedback(vocab_score)
    analysis += "\n"
    
    # 3. Grammatical Range and Accuracy
    grammar_score = overall_criteria.get('grammar', 0)
    analysis += f"🔤 <b>3. Grammatical Range and Accuracy (Грамматика): {grammar_score:.1f}/9</b>\n"
    analysis += get_grammar_feedback(grammar_score)
    analysis += "\n"
    
    # 4. Pronunciation
    pron_score = overall_criteria.get('pronunciation', 0)
    analysis += f"🎤 <b>4. Pronunciation (Произношение): {pron_score:.1f}/9</b>\n"
    analysis += get_pronunciation_feedback(pron_score)
    analysis += "\n"
    
    # Part-by-part analysis with question breakdown
    analysis += "📝 <b>ПОДРОБНЫЙ АНАЛИЗ ПО ЧАСТЯМ И ВОПРОСАМ</b>\n\n"
    
    part_names = {1: "Короткие вопросы", 2: "Карточка-монолог", 3: "Дискуссия"}
    total_questions_per_part = user_data.get('total_questions_per_part', {1: 3, 2: 1, 3: 3})
    question_scores = user_data.get('question_scores', {})
    
    for part_num in sorted(part_scores.keys()):
        part_score = part_scores[part_num]
        part_name = part_names.get(part_num, f"Часть {part_num}")
        total_questions = total_questions_per_part.get(part_num, 1)
        
        analysis += f"🎯 <b>Часть {part_num}: {part_name}</b>\n"
        analysis += f"<b>Средний результат части:</b> {part_score:.1f}/9\n\n"
        
        # Show individual questions within this part
        for q in range(1, total_questions + 1):
            question_key = f"part_{part_num}_q_{q}"
            q_score = question_scores.get(question_key, 0)
            q_transcription = question_transcriptions.get(question_key, "Недоступно")
            q_evaluation = question_evaluations.get(question_key, "Недоступно")
            
            analysis += f"<b>   🔹 Вопрос {q}:</b> {q_score:.1f}/9\n"
            
            # Show part of transcription
            if q_transcription != "Недоступно":
                analysis += f"   <b>Ваш ответ:</b>\n"
                analysis += f"   <i>«{q_transcription[:150]}{'...' if len(q_transcription) > 150 else ''}»</i>\n\n"
            
            # Show evaluation summary for this question
            if q_evaluation != "Недоступно":
                # Show a truncated version of the evaluation (first 100 characters)
                eval_summary = q_evaluation[:100] + "..." if len(q_evaluation) > 100 else q_evaluation
                analysis += f"   <b>Краткая оценка:</b>\n   <i>{eval_summary}</i>\n\n"
            
        analysis += "─────────────────\n\n"
    
    return analysis

def get_fluency_feedback(score: float) -> str:
    """Get feedback for fluency and coherence"""
    if score >= 8.0:
        return "Отличная беглость речи, логичная структура ответов"
    elif score >= 6.5:
        return "Хорошая беглость, иногда есть паузы, но в целом связно"
    elif score >= 5.5:
        return "Удовлетворительная беглость, заметны паузы и повторения"
    else:
        return "Требуется работа над беглостью и связностью речи"

def get_vocabulary_feedback(score: float) -> str:
    """Get feedback for lexical resource"""
    if score >= 8.0:
        return "Богатый словарный запас, точное использование слов"
    elif score >= 6.5:
        return "Хороший словарный запас, иногда есть неточности"
    elif score >= 5.5:
        return "Достаточный словарный запас для базовой коммуникации"
    else:
        return "Требуется расширение словарного запаса"

def get_grammar_feedback(score: float) -> str:
    """Get feedback for grammatical range and accuracy"""
    if score >= 8.0:
        return "Отличное владение грамматикой, разнообразные конструкции"
    elif score >= 6.5:
        return "Хорошее владение грамматикой, редкие ошибки"
    elif score >= 5.5:
        return "Удовлетворительное владение грамматикой, есть ошибки"
    else:
        return "Требуется работа над грамматическими правилами"

def get_pronunciation_feedback(score: float) -> str:
    """Get feedback for pronunciation"""
    if score >= 8.0:
        return "Отличное произношение, четкая артикуляция"
    elif score >= 6.5:
        return "Хорошее произношение, понятно для слушателя"
    elif score >= 5.5:
        return "Удовлетворительное произношение, иногда неясно"
    else:
        return "Требуется работа над произношением и интонацией"



    

    
    # General recommendations
    if score < 6.5:
        recommendations.append("• Увеличьте время практики speaking")
        recommendations.append("• Работайте с преподавателем или репетитором")
        recommendations.append("• Используйте приложения для изучения языка")
    




def determine_ielts_band(score: float) -> float:
    """Convert numerical score to IELTS band score"""
    if score >= 8.5:
        return 9.0
    elif score >= 8.0:
        return 8.5
    elif score >= 7.5:
        return 8.0
    elif score >= 7.0:
        return 7.5
    elif score >= 6.5:
        return 7.0
    elif score >= 6.0:
        return 6.5
    elif score >= 5.5:
        return 6.0
    elif score >= 5.0:
        return 5.5
    elif score >= 4.5:
        return 5.0
    else:
        return 4.0

def calculate_simulation_time(context: CallbackContext) -> str:
    """Calculate and format simulation time"""
    import time
    start_time = context.user_data.get('simulation_start_time', time.time())
    elapsed = int(time.time() - start_time)
    minutes = elapsed // 60
    seconds = elapsed % 60
    return f"{minutes}м {seconds}с"

def generate_comprehensive_feedback(part_scores: dict, overall_band: float) -> str:
    """Generate comprehensive feedback based on scores"""
    feedback = "🎯 <b>АНАЛИЗ РЕЗУЛЬТАТОВ:</b>\n\n"
    
    # Analyze strengths and weaknesses
    strengths = []
    weaknesses = []
    
    for part, score in part_scores.items():
        if score >= 7.0:
            strengths.append(f"Часть {part} ({score}/9)")
        elif score < 6.0:
            weaknesses.append(f"Часть {part} ({score}/9)")
    
    if strengths:
        feedback += f"✅ <b>Сильные стороны:</b> {', '.join(strengths)}\n\n"
    
    if weaknesses:
        feedback += f"🔧 <b>Требуют улучшения:</b> {', '.join(weaknesses)}\n\n"
    
    # Overall band interpretation
    if overall_band >= 8.0:
        feedback += "🏆 <b>Отличный результат!</b> Ваш уровень близок к носителю языка.\n"
    elif overall_band >= 7.0:
        feedback += "🎯 <b>Хороший результат!</b> Вы демонстрируете уверенное владение языком.\n"
    elif overall_band >= 6.0:
        feedback += "📈 <b>Удовлетворительный результат.</b> Есть потенциал для улучшения.\n"
    else:
        feedback += "📚 <b>Требуется дополнительная практика.</b> Рекомендуем больше тренироваться.\n"
    
    return feedback
    
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
            BotCommand("flashcards", "Study with spaced repetition flashcards"),
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
                 "➕ /customword - Добавить свое слово в словарь.\n"
                 "🤖 /aicustomword - Добавить слово с AI-помощью.\n"
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
        [InlineKeyboardButton("🎓 Flashcards", callback_data="flashcard_menu")],
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
            [InlineKeyboardButton("➕ Добавить свое слово", callback_data="custom_word_add")],
            [InlineKeyboardButton("🤖 AI-помощь для слова", callback_data="ai_enhanced_custom_word")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📖 Какой тип словаря вы хотите?", reply_markup=reply_markup)
        
    elif data == "menu_writing":
        # Handle writing menu selection - start writing conversation
        await start_writing_task(update, context)
        
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
            [InlineKeyboardButton("🎯 Полная симуляция экзамена", callback_data="full_speaking_sim")],
            [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
            [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
            [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
            [InlineKeyboardButton("📈 Статистика прогресса", callback_data="speaking_stats")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🗣️ <b>IELTS Speaking Practice</b>\n\n"
            "Выберите режим практики:\n\n"
            "🎯 <b>Полная симуляция</b> - пройдите все три части экзамена подряд\n"
            "📋 <b>Отдельные части</b> - практикуйте конкретную часть\n"
            "📊 <b>Аналитика</b> - отслеживайте свой прогресс",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
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
            
            # Add speaking statistics safely
            try:
                speaking_stats = db.get_user_speaking_stats(user.id)
                profile_text += f"\n\n🗣️ <b>Статистика говорения:</b>"
                profile_text += f"\n📊 Всего симуляций: {speaking_stats['total_simulations']}"
                profile_text += f"\n✅ Завершено: {speaking_stats['completed_simulations']}"
                if speaking_stats['average_overall_score'] > 0:
                    profile_text += f"\n📈 Средний балл: {speaking_stats['average_overall_score']:.1f}/9.0"
                if speaking_stats['best_overall_score'] > 0:
                    profile_text += f"\n🏆 Лучший результат: {speaking_stats['best_overall_score']:.1f}/9.0"
                if speaking_stats['total_practice_time_minutes'] > 0:
                    profile_text += f"\n⏱️ Время практики: {speaking_stats['total_practice_time_minutes']} мин"
                if speaking_stats['last_simulation_date']:
                    profile_text += f"\n🕐 Последняя симуляция: {speaking_stats['last_simulation_date']}"
                logger.info(f"✅ Speaking stats for user {user.id}: {speaking_stats}")
            except Exception as e:
                profile_text += f"\n\n🗣️ <b>Статистика говорения:</b>"
                profile_text += f"\n📊 Всего симуляций: 0"
                profile_text += f"\n✅ Завершено: 0"
                logger.error(f"🔥 Failed to get speaking stats: {e}")
            
            # Add writing statistics safely
            try:
                writing_stats = db.get_user_writing_stats(user.id)
                profile_text += f"\n\n✍️ <b>Статистика письма:</b>"
                profile_text += f"\n📝 Всего проверок: {writing_stats['total_evaluations']}"
                if writing_stats['average_overall_score'] > 0:
                    profile_text += f"\n📈 Средний балл: {writing_stats['average_overall_score']:.1f}/9.0"
                if writing_stats['best_overall_score'] > 0:
                    profile_text += f"\n🏆 Лучший результат: {writing_stats['best_overall_score']:.1f}/9.0"
                if writing_stats['last_evaluation_date']:
                    profile_text += f"\n🕐 Последняя проверка: {writing_stats['last_evaluation_date']}"
                logger.info(f"✅ Writing stats for user {user.id}: {writing_stats}")
            except Exception as e:
                profile_text += f"\n\n✍️ <b>Статистика письма:</b>"
                profile_text += f"\n📝 Всего проверок: 0"
                logger.error(f"🔥 Failed to get writing stats: {e}")
            
            logger.info(f"📝 Profile text created: {len(profile_text)} chars")
            
            keyboard = [
                [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("📊 Статистика говорения", callback_data="speaking_stats")],
                [InlineKeyboardButton("✍️ Статистика письма", callback_data="writing_stats")],
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
            [InlineKeyboardButton("🎓 Flashcards", callback_data="flashcard_menu")],
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
            [InlineKeyboardButton("🎓 Flashcards", callback_data="flashcard_menu")],
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
                     "➕ /customword - Добавить свое слово в словарь.\n"
                     "🤖 /aicustomword - Добавить слово с AI-помощью.\n"
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
        [InlineKeyboardButton("➕ Добавить свое слово", callback_data="custom_word_add")],
        [InlineKeyboardButton("🤖 AI-помощь для слова", callback_data="ai_enhanced_custom_word")],
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
    elif choice == "topic":
        logger.info(f"🎯 User {update.effective_user.id} chose topic-specific vocabulary")
        context.user_data['waiting_for_vocabulary_topic'] = True
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.answer()
        await query.edit_message_text(
            "📚 Пожалуйста, введите тему для словарных слов (например, 'окружающая среда', 'технологии', 'образование'):",
            reply_markup=reply_markup
        )
        return GET_VOCABULARY_TOPIC
    elif choice == "custom":
        logger.info(f"🎯 User {update.effective_user.id} chose custom word (conversation)")
        await start_custom_word_input(update, context)
        return GET_CUSTOM_WORD
    else:  # ai_enhanced
        logger.info(f"🎯 User {update.effective_user.id} chose AI-enhanced custom word (conversation)")
        context.user_data['ai_enhanced_mode'] = True
        await start_custom_word_input(update, context)
        return GET_CUSTOM_WORD

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
    elif choice == "topic":
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
    elif choice == "custom":
        logger.info(f"🎯 User {update.effective_user.id} chose custom word (global)")
        await start_custom_word_input(update, context)
    else:  # ai_enhanced
        logger.info(f"🎯 User {update.effective_user.id} chose AI-enhanced custom word (global)")
        context.user_data['ai_enhanced_mode'] = True
        await start_custom_word_input(update, context)

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

# --- CUSTOM WORD FUNCTIONS ---
@require_access
async def start_custom_word_input(update: Update, context: CallbackContext) -> int:
    """Start the custom word input process"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📝 <b>Добавление собственного слова</b>\n\n"
        "Пожалуйста, введите слово на английском языке, которое вы хотите добавить в свой словарь:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return GET_CUSTOM_WORD

@require_access
async def handle_custom_word_input(update: Update, context: CallbackContext) -> int:
    """Handle the custom word input"""
    word = update.message.text.strip()
    
    # Validate word input
    if not word or len(word) < 2:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректное слово (минимум 2 символа).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
        return ConversationHandler.END
    
    # Check if word already exists
    if db.word_exists_in_user_vocabulary(update.effective_user.id, word):
        await update.message.reply_text(
            f"⚠️ Слово '{word}' уже есть в вашем словаре!\n\n"
            f"Хотите добавить другое слово или перейти к существующему?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("➕ Добавить другое слово", callback_data="custom_word_add")],
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
        return ConversationHandler.END
    
    # Check if we're in AI-enhanced mode
    if context.user_data.get('ai_enhanced_mode'):
        # Use AI to generate word details
        await update.message.reply_text("🤖 Генерирую определение, перевод и пример для вашего слова...")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Generate AI-enhanced word details
        ai_response = add_custom_word_to_dictionary(word)
        
        # Parse the AI response to extract details
        import re
        
        definition_match = re.search(r'📖 <b>Определение:</b> (.+)', ai_response)
        translation_match = re.search(r'🇷🇺 <b>Перевод:</b> (.+)', ai_response)
        example_match = re.search(r'💡 <b>Пример:</b> (.+)', ai_response)
        topic_match = re.search(r'🏷️ <b>Тема:</b> (.+)', ai_response)
        
        definition = definition_match.group(1).strip() if definition_match else "AI-generated definition"
        translation = translation_match.group(1).strip() if translation_match else "AI-generated translation"
        example = example_match.group(1).strip() if example_match else "AI-generated example"
        topic = topic_match.group(1).strip() if topic_match else "AI-generated topic"
        
        # Save word to database
        success = db.save_word_to_user_vocabulary(
            user_id=update.effective_user.id,
            word=word,
            definition=definition,
            translation=translation,
            example=example,
            topic=topic
        )
        
        if success:
            # Get updated vocabulary count
            vocabulary_count = db.get_user_vocabulary_count(update.effective_user.id)
            
            # Create confirmation message
            confirmation_text = f"""
✅ <b>СЛОВО УСПЕШНО ДОБАВЛЕНО В СЛОВАРЬ (AI-улучшенное)</b>

📝 <b>Слово:</b> {word}
📖 <b>Определение:</b> {definition}
🇷🇺 <b>Перевод:</b> {translation}
💡 <b>Пример:</b> {example}
🏷️ <b>Тема:</b> {topic}

🎯 Слово сохранено в ваш личный словарь!
📚 Всего слов в словаре: {vocabulary_count}
            """.strip()
            
            keyboard = [
                [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
                [InlineKeyboardButton("🤖 Добавить еще слово с AI", callback_data="ai_enhanced_custom_word")],
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                confirmation_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            # Clear the AI-enhanced mode flag
            context.user_data.pop('ai_enhanced_mode', None)
            
            logger.info(f"✅ AI-enhanced word '{word}' saved to user {update.effective_user.id}'s vocabulary")
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении слова. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
                ])
            )
        
        return ConversationHandler.END
    
    # Store the word and ask for definition (manual mode)
    context.user_data['custom_word'] = word
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 <b>Слово:</b> {word}\n\n"
        "Теперь введите определение слова на английском языке:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return GET_CUSTOM_WORD_DEFINITION

@require_access
async def handle_custom_word_definition(update: Update, context: CallbackContext) -> int:
    """Handle the custom word definition input"""
    definition = update.message.text.strip()
    
    if not definition or len(definition) < 5:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректное определение (минимум 5 символов).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
        return ConversationHandler.END
    
    # Store the definition and ask for translation
    context.user_data['custom_word_definition'] = definition
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 <b>Слово:</b> {context.user_data['custom_word']}\n"
        f"📖 <b>Определение:</b> {definition}\n\n"
        "Теперь введите перевод слова на русский язык:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return GET_CUSTOM_WORD_TRANSLATION

@require_access
async def handle_custom_word_translation(update: Update, context: CallbackContext) -> int:
    """Handle the custom word translation input"""
    translation = update.message.text.strip()
    
    if not translation or len(translation) < 2:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректный перевод (минимум 2 символа).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
        return ConversationHandler.END
    
    # Store the translation and ask for example
    context.user_data['custom_word_translation'] = translation
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 <b>Слово:</b> {context.user_data['custom_word']}\n"
        f"📖 <b>Определение:</b> {context.user_data['custom_word_definition']}\n"
        f"🇷🇺 <b>Перевод:</b> {translation}\n\n"
        "Теперь введите пример предложения с этим словом:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return GET_CUSTOM_WORD_EXAMPLE

@require_access
async def handle_custom_word_example(update: Update, context: CallbackContext) -> int:
    """Handle the custom word example input"""
    example = update.message.text.strip()
    
    if not example or len(example) < 10:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректный пример (минимум 10 символов).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
        return ConversationHandler.END
    
    # Store the example and ask for topic
    context.user_data['custom_word_example'] = example
    
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📝 <b>Слово:</b> {context.user_data['custom_word']}\n"
        f"📖 <b>Определение:</b> {context.user_data['custom_word_definition']}\n"
        f"🇷🇺 <b>Перевод:</b> {context.user_data['custom_word_translation']}\n"
        f"💡 <b>Пример:</b> {example}\n\n"
        "Теперь введите тему для этого слова (например: 'окружающая среда', 'технологии', 'образование'):",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return GET_CUSTOM_WORD_TOPIC

@require_access
async def handle_custom_word_topic(update: Update, context: CallbackContext) -> int:
    """Handle the custom word topic input and save the word"""
    topic = update.message.text.strip()
    
    if not topic or len(topic) < 2:
        await update.message.reply_text(
            "❌ Пожалуйста, введите корректную тему (минимум 2 символа).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
        return ConversationHandler.END
    
    # Get all the stored data
    word = context.user_data['custom_word']
    definition = context.user_data['custom_word_definition']
    translation = context.user_data['custom_word_translation']
    example = context.user_data['custom_word_example']
    
    # Save word to database
    success = db.save_word_to_user_vocabulary(
        user_id=update.effective_user.id,
        word=word,
        definition=definition,
        translation=translation,
        example=example,
        topic=topic
    )
    
    if success:
        # Get updated vocabulary count
        vocabulary_count = db.get_user_vocabulary_count(update.effective_user.id)
        
        # Create confirmation message
        confirmation_text = f"""
✅ <b>СЛОВО УСПЕШНО ДОБАВЛЕНО В СЛОВАРЬ</b>

📝 <b>Слово:</b> {word}
📖 <b>Определение:</b> {definition}
🇷🇺 <b>Перевод:</b> {translation}
💡 <b>Пример:</b> {example}
🏷️ <b>Тема:</b> {topic}

🎯 Слово сохранено в ваш личный словарь!
📚 Всего слов в словаре: {vocabulary_count}
        """.strip()
        
        keyboard = [
            [InlineKeyboardButton("📖 Мой словарь", callback_data="profile_vocabulary")],
            [InlineKeyboardButton("➕ Добавить еще слово", callback_data="custom_word_add")],
            [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            confirmation_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Clear the stored data
        context.user_data.pop('custom_word', None)
        context.user_data.pop('custom_word_definition', None)
        context.user_data.pop('custom_word_translation', None)
        context.user_data.pop('custom_word_example', None)
        
        logger.info(f"✅ Custom word '{word}' saved to user {update.effective_user.id}'s vocabulary")
    else:
        await update.message.reply_text(
            "❌ Произошла ошибка при сохранении слова. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")]
            ])
        )
    
    return ConversationHandler.END

@require_access
async def handle_custom_word_add_callback(update: Update, context: CallbackContext) -> None:
    """Handle the custom word add button callback"""
    query = update.callback_query
    await query.answer()
    
    # Start the custom word input process
    await start_custom_word_input(update, context)

@require_access
async def handle_custom_word_add_from_menu(update: Update, context: CallbackContext) -> None:
    """Handle custom word add from the vocabulary menu"""
    query = update.callback_query
    await query.answer()
    
    # Start the custom word input process
    await start_custom_word_input(update, context)

@require_access
async def handle_ai_enhanced_custom_word(update: Update, context: CallbackContext) -> int:
    """Handle AI-enhanced custom word where user provides just the word and AI fills details"""
    query = update.callback_query
    await query.answer()
    
    # Ask user to provide just the word
    keyboard = [
        [InlineKeyboardButton("🔙 Назад к словарю", callback_data="menu_vocabulary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🤖 <b>AI-улучшенное добавление слова</b>\n\n"
        "Введите слово на английском языке, и я помогу создать полное определение с переводом, примером и темой:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # Set flag for AI-enhanced mode
    context.user_data['ai_enhanced_mode'] = True
    
    return GET_CUSTOM_WORD

@require_access
async def custom_word_command(update: Update, context: CallbackContext) -> int:
    """Command handler for /customword - starts custom word input process"""
    user = update.effective_user
    logger.info(f"🎯 User {user.id} started custom word command")
    
    # Start the custom word input process
    return await start_custom_word_input(update, context)

@require_access
async def ai_custom_word_command(update: Update, context: CallbackContext) -> int:
    """Command handler for /aicustomword - starts AI-enhanced custom word input process"""
    user = update.effective_user
    logger.info(f"🎯 User {user.id} started AI-enhanced custom word command")
    
    # Set AI-enhanced mode and start the process
    context.user_data['ai_enhanced_mode'] = True
    
    # Ask user to provide just the word
    keyboard = [
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 <b>AI-улучшенное добавление слова</b>\n\n"
        "Введите слово на английском языке, и я помогу создать полное определение с переводом, примером и темой:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    return GET_CUSTOM_WORD

# --- WRITING (Conversation) ---
@require_access
async def start_writing_task(update: Update, context: CallbackContext, force_new_message=False) -> int:
    # Get writing stats for quick preview
    user = update.effective_user
    try:
        writing_stats = db.get_user_writing_stats(user.id)
        if writing_stats['total_evaluations'] > 0:
            stats_preview = f"\n\n📊 <b>Ваша статистика:</b>\n"
            stats_preview += f"• Проверок: {writing_stats['total_evaluations']}\n"
            stats_preview += f"• Средний балл: {writing_stats['average_overall_score']:.1f}/9.0\n"
            stats_preview += f"• Лучший результат: {writing_stats['best_overall_score']:.1f}/9.0"
        else:
            stats_preview = "\n\n📊 <b>Ваша статистика:</b>\n• Пока нет данных"
    except Exception as e:
        stats_preview = "\n\n📊 <b>Ваша статистика:</b>\n• Не удалось загрузить"
        logger.error(f"🔥 Failed to get writing stats preview: {e}")
    
    keyboard = [
        [InlineKeyboardButton("Задание 2 (Эссе)", callback_data="writing_task_type_2")],
        [InlineKeyboardButton("📝 Проверить письмо", callback_data="writing_check")],
        [InlineKeyboardButton("📊 Статистика письма", callback_data="writing_stats")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"✍️ <b>IELTS Writing Practice</b>{stats_preview}\n\nВыберите действие:"
    
    if force_new_message:
        # Try to edit if possible, else send new message
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        elif hasattr(update, 'message') and update.message:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup, parse_mode='HTML')
        return GET_WRITING_TOPIC
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    elif hasattr(update, 'message') and update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
    
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
async def handle_writing_topic_input(update: Update, context: CallbackContext) -> int:
    """Handle writing topic input from users"""
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
    
    # Debug logging for state transition
    logger.info(f"✅ Writing task generated for user {update.effective_user.id}")
    logger.info(f"🔍 Debug: Setting current_writing_task_description: '{writing_task[:100]}...'")
    logger.info(f"🔍 Debug: User data keys: {list(context.user_data.keys())}")
    logger.info(f"🔍 Debug: Moving to GET_WRITING_SUBMISSION state")
    
    return GET_WRITING_SUBMISSION

# This function has been replaced by handle_writing_topic_input

@require_access
async def handle_writing_submission(update: Update, context: CallbackContext) -> int:
    student_writing = update.message.text
    task_description = context.user_data.get('current_writing_task_description', 'No specific task given.')
    
    # Debug logging for submission handling
    logger.info(f"✍️ Writing submission received for user {update.effective_user.id}")
    logger.info(f"🔍 Debug: Essay length: {len(student_writing)} characters")
    logger.info(f"🔍 Debug: Task description: '{task_description[:100]}...'")
    logger.info(f"🔍 Debug: User data keys: {list(context.user_data.keys())}")
    logger.info(f"🔍 Debug: Current conversation state: {context.user_data.get('_conversation_state', 'Unknown')}")
    
    await update.message.reply_text("📝 Проверяю ваше письмо, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    feedback = evaluate_writing(writing_text=student_writing, task_description=task_description)
    
    # Extract scores from the feedback for statistics
    scores = extract_writing_scores_from_evaluation(feedback)
    
    # Save the evaluation to database
    if scores['overall'] > 0:
        success = db.save_writing_evaluation(
            user_id=update.effective_user.id,
            task_description=task_description,
            essay_text=student_writing,
            overall_score=scores['overall'],
            task_response_score=scores['task_response'],
            coherence_cohesion_score=scores['coherence_cohesion'],
            lexical_resource_score=scores['lexical_resource'],
            grammatical_range_score=scores['grammatical_range'],
            evaluation_feedback=feedback
        )
        if success:
            logger.info(f"✅ Writing evaluation saved to database for user {update.effective_user.id}")
        else:
            logger.warning(f"⚠️ Failed to save writing evaluation to database for user {update.effective_user.id}")
    
    # Display the feedback
    await send_or_edit_safe_text(update, context, feedback)
    
    # Clear the writing task data
    context.user_data.pop('current_writing_task_description', None)
    context.user_data.pop('current_writing_topic', None)
    context.user_data.pop('selected_writing_task_type', None)
    
    # Show completion message with options
    completion_keyboard = [
        [InlineKeyboardButton("📊 Посмотреть статистику", callback_data="writing_stats")],
        [InlineKeyboardButton("✍️ Новое задание", callback_data="menu_writing")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main_menu")]
    ]
    completion_markup = InlineKeyboardMarkup(completion_keyboard)
    
    await update.message.reply_text(
        "✅ <b>Проверка письма завершена!</b>\n\n"
        "Ваше письмо было оценено и сохранено в статистике. "
        "Вы можете посмотреть свой прогресс или начать новое задание.",
        reply_markup=completion_markup,
        parse_mode='HTML'
    )
    
    logger.info(f"✅ Writing evaluation completed for user {update.effective_user.id}")
    return ConversationHandler.END

@require_access
async def handle_writing_submission_fallback(update: Update, context: CallbackContext) -> int:
    """Fallback handler for writing submissions when conversation handler fails"""
    logger.info(f"🔄 Writing submission fallback handler called for user {update.effective_user.id}")
    
    # Check if user has a writing task
    if context.user_data.get('current_writing_task_description'):
        logger.info(f"✅ Fallback: User has writing task, processing submission")
        return await handle_writing_submission(update, context)
    else:
        logger.warning(f"⚠️ Fallback: User has no writing task, ending conversation")
        await update.message.reply_text(
            "❌ Не удалось определить задание для письма. Пожалуйста, начните заново.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ Новое задание", callback_data="menu_writing")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main_menu")]
            ])
        )
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
            [InlineKeyboardButton("🎯 Полная симуляция экзамена", callback_data="full_speaking_sim")],
            [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
            [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
            [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
            [InlineKeyboardButton("📊 История симуляций", callback_data="speaking_history")],
            [InlineKeyboardButton("📈 Статистика прогресса", callback_data="speaking_stats")],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id, 
            text="🗣️ <b>IELTS Speaking Practice</b>\n\n"
                 "Выберите режим практики:\n\n"
                 "🎯 <b>Полная симуляция</b> - пройдите все три части экзамена подряд\n"
                 "📋 <b>Отдельные части</b> - практикуйте конкретную часть\n"
                 "📊 <b>Аналитика</b> - отслеживайте свой прогресс",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return
    if update.message:
        target = update.message
    elif update.callback_query:
        target = update.callback_query.message
    else:
        return
    keyboard = [
        [InlineKeyboardButton("🎯 Полная симуляция экзамена", callback_data="full_speaking_sim")],
        [InlineKeyboardButton("Part 1: Короткие вопросы", callback_data="speaking_part_1")],
        [InlineKeyboardButton("Part 2: Карточка-монолог", callback_data="speaking_part_2")],
        [InlineKeyboardButton("Part 3: Дискуссия", callback_data="speaking_part_3")],
        [InlineKeyboardButton("📈 Статистика прогресса", callback_data="speaking_stats")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await target.reply_text(
        "🗣️ <b>IELTS Speaking Practice</b>\n\n"
        "Выберите режим практики:\n\n"
        "🎯 <b>Полная симуляция</b> - пройдите все три части экзамена подряд\n"
        "📋 <b>Отдельные части</b> - практикуйте конкретную часть\n"
        "📊 <b>Аналитика</b> - отслеживайте свой прогресс",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

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
    
    # Show question with confirmation options
    confirmation_message = (
        f"{speaking_prompt}\n\n"
        f"🎤 <b>Готовы записать голосовой ответ?</b>\n\n"
        f"Выберите один из вариантов:"
    )
    
    # Create confirmation buttons
    keyboard = [
        [InlineKeyboardButton("🎤 Записать голосовой ответ", callback_data=f"confirm_voice_{part_number_str}")],
        [InlineKeyboardButton("⏭️ Пропустить вопрос", callback_data=f"speaking_part_{part_number_str}")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send confirmation message
    try:
        await query.edit_message_text(
            text=confirmation_message, 
            parse_mode='HTML', 
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending new one: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=confirmation_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Set user state to expect confirmation (NOT voice message yet)
    context.user_data['waiting_for_speaking_confirmation'] = True
    logger.info(f"🎤 User {user.id} viewing speaking question for {part_for_api}, awaiting confirmation")

@require_access
async def handle_voice_confirmation(update: Update, context: CallbackContext) -> None:
    """Handle voice recording confirmation"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    # Extract part number from callback data
    part_number = query.data.split('_')[-1]
    part_for_api = f"Part {part_number}"
    
    # Get stored speaking prompt
    speaking_prompt = context.user_data.get('current_speaking_prompt', 'No prompt available')
    
    # Voice response instructions
    voice_instructions = (
        f"{speaking_prompt}\n\n"
        f"🎤 <b>ГОЛОСОВОЙ ОТВЕТ АКТИВИРОВАН</b>\n\n"
        f"✅ Теперь запишите голосовое сообщение с вашим ответом на английском языке.\n"
        f"🔊 Бот автоматически транскрибирует речь и оценит ваш ответ по шкале IELTS (1-9)!\n\n"
        f"💡 <i>Говорите четко и уверенно, как на настоящем экзамене IELTS.</i>\n\n"
        f"⏱️ <b>Рекомендуемое время:</b>\n"
        f"• Part 1: 30-60 секунд на вопрос\n"
        f"• Part 2: 1-2 минуты\n"
        f"• Part 3: 30-90 секунд на вопрос"
    )
    
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отменить запись", callback_data=f"speaking_part_{part_number}")],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_main_menu")],
    ])
    
    try:
        await query.edit_message_text(
            text=voice_instructions, 
            parse_mode='HTML', 
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending new one: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=voice_instructions,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # NOW enable voice message recording
    context.user_data['waiting_for_voice_response'] = True
    context.user_data.pop('waiting_for_speaking_confirmation', None)
    logger.info(f"🎤 User {user.id} confirmed voice recording for {part_for_api}")

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
    user = update.effective_user
    logger.info(f"🎯 Writing Check Essay: User {user.id} submitted essay for evaluation")
    
    await update.message.reply_text("📝 Проверяю ваше письмо, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    feedback = evaluate_writing(writing_text=essay_text, task_description=task_description)
    
    # Extract scores from the feedback
    scores = extract_writing_scores_from_evaluation(feedback)
    
    # Save the evaluation to database
    if scores['overall'] > 0:
        success = db.save_writing_evaluation(
            user_id=user.id,
            task_description=task_description,
            essay_text=essay_text,
            overall_score=scores['overall'],
            task_response_score=scores['task_response'],
            coherence_cohesion_score=scores['coherence_cohesion'],
            lexical_resource_score=scores['lexical_resource'],
            grammatical_range_score=scores['grammatical_range'],
            evaluation_feedback=feedback
        )
        if success:
            logger.info(f"✅ Writing evaluation saved to database for user {user.id}")
        else:
            logger.warning(f"⚠️ Failed to save writing evaluation to database for user {user.id}")
    
    # Use send_or_edit_safe_text to ensure proper markdown formatting with fallback
    reply_markup = None
    await send_or_edit_safe_text(update, context, feedback, reply_markup)
    logger.info(f"✅ Writing evaluation completed for user {user.id}")
    
    # Clear the writing check data
    context.user_data.pop('current_writing_check_task', None)
    
    # Show completion message with options
    completion_keyboard = [
        [InlineKeyboardButton("📊 Посмотреть статистику", callback_data="writing_stats")],
        [InlineKeyboardButton("📝 Проверить еще одно письмо", callback_data="writing_check")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main_menu")]
    ]
    completion_markup = InlineKeyboardMarkup(completion_keyboard)
    
    await update.message.reply_text(
        "✅ <b>Проверка письма завершена!</b>\n\n"
        "Ваше письмо было оценено и сохранено в статистике. "
        "Вы можете посмотреть свой прогресс или проверить другое письмо.",
        reply_markup=completion_markup,
        parse_mode='HTML'
    )
    
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
    
    # Check if user is in writing submission mode (for conversation handler access)
    if context.user_data.get('current_writing_task_description'):
        logger.info(f"✍️ User {user.id} is in writing submission mode (global) - task: '{context.user_data['current_writing_task_description'][:50]}...'")
        logger.info(f"🔍 Debug: Global handler processing writing submission")
        logger.info(f"🔍 Debug: User data keys: {list(context.user_data.keys())}")
        logger.info(f"🔍 Debug: Processing via global handler (conversation handler may have failed)")
        await handle_writing_submission(update, context)
        return
    
    # Additional check: if user has writing topic but no task description, they might be in the middle of generation
    if context.user_data.get('current_writing_topic') and not context.user_data.get('current_writing_task_description'):
        logger.info(f"🔄 User {user.id} has writing topic but no task yet - waiting for generation")
        await update.message.reply_text(
            "⏳ Пожалуйста, подождите, пока генерируется задание для письма...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")]
            ])
        )
        return
    
    # Check if admin is searching for users
    if context.user_data.get('waiting_for_admin_search'):
        logger.info(f"🔍 Admin {user.id} is searching for users")
        context.user_data.pop('waiting_for_admin_search', None)
        await handle_admin_search_input(update, context)
        return
    
    # If not in any specific mode, check if this might be a writing submission
    # This is a safety net for when the conversation handler fails
    if len(update.message.text) > 50:  # Likely an essay submission
        logger.info(f"🔍 User {user.id} sent long text ({len(update.message.text)} chars) - checking if it's a writing submission")
        
        # Check if user has any writing-related data
        if (context.user_data.get('current_writing_topic') or 
            context.user_data.get('selected_writing_task_type') or
            context.user_data.get('current_writing_task_description')):
            
            logger.info(f"✅ Long text detected with writing context - treating as writing submission")
            if context.user_data.get('current_writing_task_description'):
                await handle_writing_submission(update, context)
            else:
                await update.message.reply_text(
                    "⏳ Задание для письма еще генерируется. Пожалуйста, подождите...",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")]
                    ])
                )
            return
    
    # If not in any specific mode, ignore the text
    # This prevents the global handler from interfering with conversation handlers
    logger.info(f"❌ User {user.id} not in any specific mode, ignoring text input")
    return

# --- GLOBAL CANCEL & ERROR HANDLER ---
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def debug_conversation_state(update: Update, context: CallbackContext) -> None:
    """Debug function to check current conversation state"""
    user = update.effective_user
    logger.info(f"🔍 Debug: User {user.id} conversation state check")
    logger.info(f"🔍 Debug: User data keys: {list(context.user_data.keys())}")
    logger.info(f"🔍 Debug: Current writing topic: {context.user_data.get('current_writing_topic', 'None')}")
    logger.info(f"🔍 Debug: Current writing task: {context.user_data.get('current_writing_task_description', 'None')[:100] if context.user_data.get('current_writing_task_description') else 'None'}")
    
    await update.message.reply_text(
        f"🔍 <b>Debug Info:</b>\n\n"
        f"User ID: {user.id}\n"
        f"Writing Topic: {context.user_data.get('current_writing_topic', 'None')}\n"
        f"Writing Task: {context.user_data.get('current_writing_task_description', 'None')[:100] if context.user_data.get('current_writing_task_description') else 'None'}...\n"
        f"User Data Keys: {', '.join(context.user_data.keys())}",
        parse_mode='HTML'
    )

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

# --- Full Speaking Simulation Functions ---

async def display_single_question(update: Update, context: CallbackContext) -> None:
    """Display a single question based on current part and question number"""
    current_part = context.user_data.get('current_part', 1)
    question_num = context.user_data.get('current_question_in_part', 1)
    total_questions = context.user_data.get('total_questions_per_part', {}).get(current_part, 1)
    
    # Generate single question for current part
    question = generate_single_speaking_question(f"Part {current_part}")
    context.user_data['current_question'] = question
    
    # Format question display with progress indicator
    question_text = format_question_display(current_part, question_num, total_questions, question)
    
    # Create navigation buttons
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить вопрос", callback_data="skip_question")],
        [InlineKeyboardButton("❌ Выйти из симуляции", callback_data="abandon_full_sim")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send question
    if update.callback_query:
        await update.callback_query.edit_message_text(question_text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(question_text, reply_markup=reply_markup, parse_mode='HTML')

def format_question_display(part: int, question_num: int, total_questions: int, question: str) -> str:
    """Format question display with progress and instructions"""
    part_names = {1: "Короткие вопросы", 2: "Карточка-монолог", 3: "Дискуссия"}
    time_limits = {1: "30-60 секунд", 2: "1-2 минуты", 3: "30-90 секунд"}
    
    progress = f"{question_num}/{total_questions}"
    
    return f"""🎯 <b>IELTS Speaking Part {part}: {part_names[part]}</b>
📊 <b>Прогресс:</b> {progress}

{question}

🎤 <b>Запишите голосовой ответ ({time_limits[part]})</b>"""

async def move_to_next_question(update: Update, context: CallbackContext) -> int:
    """Move to next question within current part or to next part"""
    current_part = context.user_data.get('current_part', 1)
    current_question = context.user_data.get('current_question_in_part', 1)
    total_questions = context.user_data.get('total_questions_per_part', {}).get(current_part, 1)
    
    if current_question < total_questions:
        # More questions in current part
        context.user_data['current_question_in_part'] += 1
        await display_single_question(update, context)
        return get_current_state(current_part)
    else:
        # Move to next part
        return await move_to_next_part(update, context)

async def move_to_next_part(update: Update, context: CallbackContext) -> int:
    """Move to next part of the simulation"""
    current_part = context.user_data.get('current_part', 1)
    
    # Calculate part average score
    total_questions_in_part = context.user_data.get('total_questions_per_part', {}).get(current_part, 1)
    part_question_scores = [
        context.user_data.get('question_scores', {}).get(f"part_{current_part}_q_{q}", 0)
        for q in range(1, total_questions_in_part + 1)
    ]
    part_average = sum(part_question_scores) / len(part_question_scores) if part_question_scores else 0
    context.user_data.setdefault('part_scores', {})[current_part] = part_average
    
    # Save part summary to database
    session_id = context.user_data.get('simulation_session_id')
    if session_id:
        combined_transcription = " | ".join([
            context.user_data.get('question_transcriptions', {}).get(f"part_{current_part}_q_{q}", "")
            for q in range(1, total_questions_in_part + 1)
        ])
        combined_evaluation = " | ".join([
            context.user_data.get('question_evaluations', {}).get(f"part_{current_part}_q_{q}", "")
            for q in range(1, total_questions_in_part + 1)
        ])
        
        db.save_part_response(
            session_id, current_part, f"Part {current_part} Combined Questions", 
            combined_transcription, {'overall': part_average}, combined_evaluation
        )
    
    if current_part < 3:
        # Move to next part
        context.user_data['current_part'] += 1
        context.user_data['current_question_in_part'] = 1
        
        part_names = {2: "Карточка-монолог", 3: "Дискуссия"}
        part_name = part_names[context.user_data['current_part']]
        
        transition_msg = (
            f"✅ <b>Часть {current_part} завершена!</b>\n\n"
            f"➡️ <b>Переходим к части {context.user_data['current_part']}: {part_name}</b>\n\n"
            f"<i>Подготавливаю следующий вопрос...</i>"
        )
        
        if update.message:
            await update.message.reply_text(transition_msg, parse_mode='HTML')
        elif update.callback_query:
            await update.callback_query.edit_message_text(transition_msg, parse_mode='HTML')
        
        # Small delay for better UX
        import asyncio
        await asyncio.sleep(1)
        
        await display_single_question(update, context)
        return get_current_state(context.user_data['current_part'])
    else:
        # All parts completed
        return await complete_simulation(update, context)

def get_current_state(part_number: int) -> int:
    """Get conversation handler state for current part"""
    state_map = {1: FULL_SIM_PART_1, 2: FULL_SIM_PART_2, 3: FULL_SIM_PART_3}
    return state_map.get(part_number, FULL_SIM_PART_1)

async def handle_skip_question(update: Update, context: CallbackContext) -> int:
    """Handle skipping current question"""
    query = update.callback_query
    await query.answer()
    
    current_part = context.user_data.get('current_part', 1)
    current_question = context.user_data.get('current_question_in_part', 1)
    
    # Store empty/skipped response
    question_key = f"part_{current_part}_q_{current_question}"
    context.user_data.setdefault('question_scores', {})[question_key] = 0  # Score 0 for skipped
    context.user_data.setdefault('question_transcriptions', {})[question_key] = "[Вопрос пропущен]"
    context.user_data.setdefault('question_evaluations', {})[question_key] = "Вопрос был пропущен пользователем."
    
    await query.edit_message_text("⏭ <b>Вопрос пропущен.</b>\n\nПереходим к следующему...", parse_mode='HTML')
    
    # Small delay for better UX
    import asyncio
    await asyncio.sleep(1)
    
    return await move_to_next_question(update, context)

async def handle_retry_question(update: Update, context: CallbackContext) -> int:
    """Handle retrying current question"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔄 <b>Попробуем еще раз!</b>\n\n<i>Покажу вопрос заново...</i>", 
        parse_mode='HTML'
    )
    
    # Small delay for better UX
    import asyncio
    await asyncio.sleep(1)
    
    # Redisplay current question
    await display_single_question(update, context)
    
    current_part = context.user_data.get('current_part', 1)
    return get_current_state(current_part)

async def complete_simulation(update: Update, context: CallbackContext) -> int:
    """Complete the simulation and show final results"""
    completion_msg = (
        "🏁 <b>Все части завершены!</b>\n\n"
        "⏳ Рассчитываю общий результат и готовлю детальный анализ по всем критериям IELTS..."
    )
    
    if update.message:
        await update.message.reply_text(completion_msg, parse_mode='HTML')
    elif update.callback_query:
        await update.callback_query.edit_message_text(completion_msg, parse_mode='HTML')
    
    # Calculate and show final results
    await calculate_and_show_final_results(update, context)
    return ConversationHandler.END

async def start_full_speaking_simulation(update: Update, context: CallbackContext) -> int:
    """Start a full speaking simulation session"""
    user = update.effective_user
    
    if not check_user_access(user.id):
        return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    try:
        # Create database session
        session_id = db.create_speaking_simulation(user.id)
        if not session_id:
            await query.edit_message_text(
                "❌ Не удалось создать сессию симуляции. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="menu_speaking")]
                ])
            )
            return ConversationHandler.END
        
        # Initialize simulation context with question-based structure
        import time
        context.user_data.update({
            'full_simulation_mode': True,
            'simulation_session_id': session_id,
            'simulation_start_time': time.time(),
            'current_part': 1,
            'current_question_in_part': 1,
            'total_questions_per_part': {1: 3, 2: 1, 3: 3},  # Part 1: 3 questions, Part 2: 1 cue card, Part 3: 3 questions
            'question_scores': {},  # Store scores for each question
            'question_transcriptions': {},  # Store transcriptions for each question
            'question_evaluations': {},  # Store evaluations for each question
            'part_scores': {},  # Final part scores (average of questions)
            'user_id': user.id,
            'current_question': None  # Current question text
        })
        
        # Show simulation start message
        start_message = (
            f"🎯 <b>ПОЛНАЯ СИМУЛЯЦИЯ IELTS SPEAKING</b>\n\n"
            f"📋 <b>Структура экзамена:</b>\n"
            f"• Часть 1: Короткие вопросы (3 вопроса)\n"
            f"• Часть 2: Карточка-монолог (1 задание)\n"
            f"• Часть 3: Дискуссия (3 вопроса)\n\n"
            f"<i>💡 <b>Важно:</b> Оценки будут показаны только в конце симуляции.\n"
            f"Каждый вопрос оценивается отдельно, и вы получите детальный анализ.</i>\n\n"
            f"🚀 <b>Начинаем с первого вопроса...</b>"
        )
        
        await query.edit_message_text(start_message, parse_mode='HTML')
        
        # Small delay for better UX
        import asyncio
        await asyncio.sleep(2)
        
        # Display first question
        await display_single_question(update, context)
        
        logger.info(f"🎯 User {user.id} started full speaking simulation {session_id}")
        return FULL_SIM_PART_1
        
    except Exception as e:
        logger.error(f"🔥 Error starting full simulation for user {user.id}: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при запуске симуляции. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="menu_speaking")]
            ])
        )
        return ConversationHandler.END

async def handle_simulation_response(update: Update, context: CallbackContext) -> int:
    """Handle voice response for any part of the simulation"""
    if not update.message.voice:
        await update.message.reply_text(
            "🎤 Пожалуйста, отправьте голосовое сообщение для ответа на вопрос.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭ Пропустить вопрос", callback_data="skip_question")],
                [InlineKeyboardButton("❌ Выйти из симуляции", callback_data="abandon_full_sim")]
            ])
        )
        current_part = context.user_data.get('current_part', 1)
        return get_current_state(current_part)
    
    try:
        # Process voice message
        transcription = await process_voice_message_for_simulation(update, context)
        if not transcription:
            await update.message.reply_text(
                "❌ Не удалось обработать голосовое сообщение. Попробуйте еще раз.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Повторить", callback_data="retry_current_question")],
                    [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_question")],
                    [InlineKeyboardButton("❌ Выйти", callback_data="abandon_full_sim")]
                ])
            )
            current_part = context.user_data.get('current_part', 1)
            return get_current_state(current_part)
        
        # Get current question and part info
        current_question = context.user_data.get('current_question', 'Unknown question')
        current_part = context.user_data.get('current_part', 1)
        question_num = context.user_data.get('current_question_in_part', 1)
        
        # Evaluate response
        evaluation = evaluate_speaking_response_for_simulation(
            current_question, transcription, f"Part {current_part}"
        )
        
        # Extract scores
        scores = extract_scores_from_evaluation(evaluation)
        
        # Store response data for this specific question
        question_key = f"part_{current_part}_q_{question_num}"
        context.user_data.setdefault('question_scores', {})[question_key] = scores.get('overall', 0)
        context.user_data.setdefault('question_transcriptions', {})[question_key] = transcription
        context.user_data.setdefault('question_evaluations', {})[question_key] = evaluation
        
        # Show simple confirmation message
        confirmation_msg = (
            f"✅ <b>Ответ записан!</b>\n\n"
            f"📝 <b>Ваш ответ:</b> <i>{transcription[:100]}{'...' if len(transcription) > 100 else ''}</i>\n\n"
            f"<i>💡 Ответ оценен и сохранен. Переходим к следующему вопросу...</i>"
        )
        
        await update.message.reply_text(confirmation_msg, parse_mode='HTML')
        
        # Small delay for better UX
        import asyncio
        await asyncio.sleep(1)
        
        # Move to next question or part
        return await move_to_next_question(update, context)
        
    except Exception as e:
        logger.error(f"🔥 Error handling simulation response: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке ответа. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить", callback_data="retry_current_question")],
                [InlineKeyboardButton("❌ Выйти", callback_data="abandon_full_sim")]
            ])
        )
        current_part = context.user_data.get('current_part', 1)
        return get_current_state(current_part)

# Keep these for backward compatibility but redirect to the new handler
async def handle_full_sim_part_1(update: Update, context: CallbackContext) -> int:
    """Handle Part 1 response"""
    return await handle_simulation_response(update, context)

async def handle_full_sim_part_2(update: Update, context: CallbackContext) -> int:
    """Handle Part 2 response"""
    return await handle_simulation_response(update, context)

async def handle_full_sim_part_3(update: Update, context: CallbackContext) -> int:
    """Handle Part 3 response"""
    return await handle_simulation_response(update, context)

async def handle_full_sim_part_response(update: Update, context: CallbackContext, 
                                      part_number: int, next_state: int) -> int:
    """DEPRECATED: Generic handler for individual question responses within parts
    
    This function has been replaced by handle_simulation_response() which supports
    single question display mode. Kept for backward compatibility only.
    """
    user = update.effective_user
    
    try:
        # Process voice message
        transcription = await process_voice_message_for_simulation(update, context)
        if not transcription:
            return next_state - 1  # Stay in current state
        
        # Get stored prompt and current question info
        speaking_prompt = context.user_data.get('current_speaking_prompt', 'Unknown prompt')
        current_question_key = context.user_data.get('current_question_key', f'part_{part_number}_q_1')
        current_question_in_part = context.user_data.get('current_question_in_part', 1)
        total_questions_in_part = context.user_data.get('total_questions_per_part', {}).get(part_number, 1)
        
        # Evaluate response
        evaluation = evaluate_speaking_response_for_simulation(
            speaking_prompt, transcription, f"Part {part_number}"
        )
        
        # Extract scores
        scores = extract_scores_from_evaluation(evaluation)
        
        # Store response data for this specific question
        context.user_data['question_scores'][current_question_key] = scores['overall']
        context.user_data['question_transcriptions'][current_question_key] = transcription
        context.user_data['question_evaluations'][current_question_key] = evaluation
        
        # Show simple question completion message (NO feedback, NO scores)
        completion_msg = (
            f"✅ <b>Вопрос {current_question_in_part} записан!</b>\n\n"
            f"<i>💡 Ваш ответ сохранен. Все оценки и анализ будут показаны в конце симуляции.</i>\n\n"
        )
        
        # Check if more questions in current part
        if current_question_in_part < total_questions_in_part:
            # Move to next question in same part
            next_question_num = current_question_in_part + 1
            context.user_data['current_question_in_part'] = next_question_num
            next_question_key = f"part_{part_number}_q_{next_question_num}"
            context.user_data['current_question_key'] = next_question_key
            
            # Generate next question for same part
            if part_number == 2:
                # Part 2 only has one cue card, so this shouldn't happen
                next_prompt = context.user_data['current_speaking_prompt']
            else:
                next_prompt = generate_single_speaking_question(part=f"Part {part_number}")
            
            context.user_data['current_speaking_prompt'] = next_prompt
            
            part_name = "Короткие вопросы" if part_number == 1 else "Дискуссия"
            completion_msg += (
                f"➡️ <b>Следующий вопрос части {part_number}: {part_name}</b>\n"
                f"❓ <b>Вопрос {next_question_num} из {total_questions_in_part}</b>\n\n"
                f"{next_prompt}\n\n"
                f"🎤 <b>Запишите голосовой ответ</b>\n"
                f"⏱️ <b>Рекомендуемое время:</b> 30-60 секунд"
            )
            
            keyboard = [
                [InlineKeyboardButton("⏭️ Пропустить вопрос", callback_data=f"skip_question_{part_number}")],
                [InlineKeyboardButton("❌ Отменить симуляцию", callback_data="abandon_full_sim")]
            ]
            
            await update.message.reply_text(
                text=completion_msg,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return next_state - 1  # Stay in same part state
            
        else:
            # Current part completed, calculate part average and check if simulation is done
            part_question_scores = [
                context.user_data['question_scores'].get(f"part_{part_number}_q_{q}", 0)
                for q in range(1, total_questions_in_part + 1)
            ]
            part_average = sum(part_question_scores) / len(part_question_scores) if part_question_scores else 0
            context.user_data['part_scores'][part_number] = part_average
            
            # Save part summary to database (using average score)
            session_id = context.user_data['simulation_session_id']
            combined_transcription = " | ".join([
                context.user_data['question_transcriptions'].get(f"part_{part_number}_q_{q}", "")
                for q in range(1, total_questions_in_part + 1)
            ])
            combined_evaluation = " | ".join([
                context.user_data['question_evaluations'].get(f"part_{part_number}_q_{q}", "")
                for q in range(1, total_questions_in_part + 1)
            ])
            
            db.save_part_response(
                session_id, part_number, f"Part {part_number} Combined Questions", 
                combined_transcription, {'overall': part_average}, combined_evaluation
            )
            
            if next_state is None:
                # Last part completed, show completion message
                completion_msg += (
                    f"🏁 <b>Все части завершены!</b>\n\n"
                    f"⏳ Рассчитываю общий результат и готовлю детальный анализ по всем критериям IELTS..."
                )
                keyboard = [
                    [InlineKeyboardButton("⏳ Обрабатываю...", callback_data="processing")]
                ]
                
                await update.message.reply_text(
                    text=completion_msg,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                # Calculate final results and end conversation
                await calculate_and_show_final_results(update, context)
                return ConversationHandler.END
            else:
                # Move to next part
                next_part = part_number + 1
                context.user_data['current_part'] = next_part
                context.user_data['current_question_in_part'] = 1
                next_question_key = f"part_{next_part}_q_1"
                context.user_data['current_question_key'] = next_question_key
                
                # Generate first question of next part
                next_part_prompt = generate_single_speaking_question(part=f"Part {next_part}")
                context.user_data['current_speaking_prompt'] = next_part_prompt
                
                # Get part info
                part_names = {2: "Карточка-монолог", 3: "Дискуссия"}
                part_name = part_names.get(next_part, f"Часть {next_part}")
                total_questions_next = context.user_data.get('total_questions_per_part', {}).get(next_part, 1)
                
                completion_msg += (
                    f"➡️ <b>Переходим к части {next_part}: {part_name}</b>\n"
                    f"❓ <b>Вопрос 1 из {total_questions_next}</b>\n\n"
                    f"{next_part_prompt}\n\n"
                    f"🎤 <b>Запишите голосовой ответ</b>\n"
                    f"⏱️ <b>Рекомендуемое время:</b> "
                    f"{'1-2 минуты' if next_part == 2 else '30-90 секунд'}"
                )
                
                keyboard = [
                    [InlineKeyboardButton("⏭️ Пропустить часть", callback_data=f"skip_part_{next_part}")],
                    [InlineKeyboardButton("❌ Отменить симуляцию", callback_data="abandon_full_sim")]
                ]
                
                await update.message.reply_text(
                    text=completion_msg,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                return next_state
        
    except Exception as e:
        logger.error(f"🔥 Error processing part {part_number} response: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка при обработке вопроса. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить", callback_data=f"retry_question_{part_number}")],
                [InlineKeyboardButton("❌ Отменить", callback_data="abandon_full_sim")]
            ])
        )
        return next_state - 1

async def process_voice_message_for_simulation(update: Update, context: CallbackContext) -> str:
    """Process voice message for simulation mode"""
    user = update.effective_user
    
    try:
        # Get voice file
        voice = update.message.voice
        if not voice:
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте голосовое сообщение.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Отменить", callback_data="abandon_full_sim")]
                ])
            )
            return None
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            "🔄 <b>Обрабатываю голосовое сообщение...</b>\n\n"
            "📥 Загружаю аудио файл...",
            parse_mode='HTML'
        )
        
        # Download and transcribe
        file_info = await context.bot.get_file(voice.file_id)
        file_url = file_info.file_path
        
        # Update processing message
        await processing_msg.edit_text(
            "🔄 <b>Обрабатываю голосовое сообщение...</b>\n\n"
            "✅ Аудио файл загружен\n"
            "🎤 Распознаю речь...",
            parse_mode='HTML'
        )
        
        # Create temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
            temp_path = temp_file.name
        
        # Download file
        if not await audio_processor.download_voice_file(file_url, temp_path):
            await processing_msg.edit_text(
                "❌ <b>Ошибка обработки</b>\n\n"
                "Не удалось загрузить голосовое сообщение.\n"
                "Попробуйте еще раз.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Отменить", callback_data="abandon_full_sim")]
                ])
            )
            return None
        
        # Update processing message
        await processing_msg.edit_text(
            "🔄 <b>Обрабатываю голосовое сообщение...</b>\n\n"
            "✅ Аудио файл загружен\n"
            "✅ Файл сохранен\n"
            "🎤 Распознаю речь...",
            parse_mode='HTML'
        )
        
        # Transcribe
        transcription = audio_processor.transcribe_audio(temp_path)
        
        # Clean up
        import os
        os.unlink(temp_path)
        
        if not transcription:
            await processing_msg.edit_text(
                "❌ <b>Ошибка распознавания</b>\n\n"
                "Не удалось распознать речь в сообщении.\n"
                "Попробуйте говорить четче и громче.",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Отменить", callback_data="abandon_full_sim")]
                ])
            )
            return None
        
        # Success message
        await processing_msg.edit_text(
            "✅ <b>Речь успешно распознана!</b>\n\n"
            "📝 <b>Ваш ответ:</b>\n"
            f"<i>«{transcription[:150]}{'...' if len(transcription) > 150 else ''}»</i>\n\n"
            "⏳ Оцениваю ответ по критериям IELTS...",
            parse_mode='HTML'
        )
        
        return transcription
        
    except Exception as e:
        logger.error(f"🔥 Error processing voice message: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке голосового сообщения.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Отменить", callback_data="abandon_full_sim")]
            ])
        )
        return None

async def calculate_and_show_final_results(update: Update, context: CallbackContext) -> None:
    """Calculate final simulation results and display them"""
    try:
        # Calculate weighted overall score
        part_scores = context.user_data['part_scores']
        overall_score = calculate_weighted_overall_score(part_scores)
        
        # Determine IELTS band
        overall_band = determine_ielts_band(overall_score)
        
        # Complete simulation in database with complete feedback
        session_id = context.user_data['simulation_session_id']
        
        # Generate the complete results message first
        feedback = generate_comprehensive_feedback(part_scores, overall_band)
        
        # Generate detailed analysis immediately
        # For detailed analysis, use question-level data but display by parts
        question_transcriptions = context.user_data.get('question_transcriptions', {})
        question_evaluations = context.user_data.get('question_evaluations', {})
        
        # Convert question data to part data for analysis
        part_transcriptions = {}
        part_evaluations = {}
        for part_num in [1, 2, 3]:
            if part_num in part_scores:
                total_questions = context.user_data.get('total_questions_per_part', {}).get(part_num, 1)
                part_transcriptions[part_num] = " | ".join([
                    question_transcriptions.get(f"part_{part_num}_q_{q}", "")
                    for q in range(1, total_questions + 1)
                ])
                part_evaluations[part_num] = " | ".join([
                    question_evaluations.get(f"part_{part_num}_q_{q}", "")
                    for q in range(1, total_questions + 1)
                ])
        
        overall_criteria = calculate_overall_criteria_scores(part_scores, part_evaluations)
        
        detailed_analysis = generate_detailed_analysis_with_questions(
            part_scores, question_transcriptions, question_evaluations, overall_criteria, context.user_data
        )
        
        # Create complete results message
        results_message = (
            f"🏆 <b>СИМУЛЯЦИЯ ЗАВЕРШЕНА!</b>\n\n"
            f"🏆 <b>ОБЩИЙ РЕЗУЛЬТАТ: {overall_band}/9</b>\n\n"
            f"📊 <b>ДЕТАЛЬНАЯ ОЦЕНКА ПО ЧАСТЯМ:</b>\n"
            f"• Часть 1: {part_scores.get(1, 'N/A')}/9\n"
            f"• Часть 2: {part_scores.get(2, 'N/A')}/9\n"
            f"• Часть 3: {part_scores.get(3, 'N/A')}/9\n\n"
            f"📋 <b>ОБЩАЯ ОЦЕНКА:</b>\n"
            f"{feedback}\n\n"
            f"⏱️ <b>Время симуляции:</b> "
            f"{calculate_simulation_time(context)}\n\n"
            f"{'='*50}\n\n"
            f"{detailed_analysis}"
        )
        
        # Save to database with complete feedback
        db.complete_simulation(
            session_id=session_id,
            total_score=overall_score,
            overall_band=overall_band,
            complete_feedback=results_message
        )
        
        # Show complete results with full analysis immediately
        keyboard = [
            [InlineKeyboardButton("🔄 Новая симуляция", callback_data="restart_full_sim")],
            [InlineKeyboardButton("📈 Статистика", callback_data="speaking_stats")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")]
        ]
        
        # Handle both message and callback query contexts
        if update.message:
            await update.message.reply_text(
                text=results_message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                text=results_message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Fallback: send new message to user
            user_id = context.user_data.get('user_id')
            if user_id:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=results_message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        
        # Clear simulation data
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"🔥 Error calculating final results: {e}")
        
        # Handle error message based on context
        error_message = "❌ Произошла ошибка при расчете результатов. Обратитесь к администратору."
        error_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")]
        ])
        
        if update.message:
            await update.message.reply_text(
                error_message,
                reply_markup=error_keyboard
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                error_message,
                reply_markup=error_keyboard
            )
        else:
            # Fallback: send error message to user
            user_id = context.user_data.get('user_id')
            if user_id:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=error_message,
                    reply_markup=error_keyboard
                )

async def skip_full_sim_part(update: Update, context: CallbackContext) -> int:
    """Skip a part in full simulation"""
    query = update.callback_query
    await query.answer()
    
    part_number = int(query.data.split('_')[-1])
    next_state = part_number + 1
    
    if next_state > 3:
        # Skip to final evaluation
        await calculate_and_show_final_results(update, context)
        return ConversationHandler.END
    
    # Generate next part question
    next_part_prompt = generate_single_speaking_question(part=f"Part {next_state}")
    context.user_data['current_speaking_prompt'] = next_part_prompt
    context.user_data['current_part'] = next_state
    
    # Mark current part as skipped
    context.user_data['part_scores'][part_number] = 0
    
    completion_msg = (
        f"⏭️ <b>Часть {part_number} пропущена</b>\n\n"
        f"🔄 <b>Переходим к части {next_state}</b>\n\n"
        f"{next_part_prompt}\n\n"
        f"🎤 <b>Запишите голосовой ответ</b>\n"
        f"⏱️ <b>Рекомендуемое время:</b> "
        f"{'1-2 минуты' if next_state == 2 else '30-90 секунд'}"
    )
    
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить часть", callback_data=f"skip_part_{next_state}")],
        [InlineKeyboardButton("❌ Отменить симуляцию", callback_data="abandon_full_sim")]
    ]
    
    await query.edit_message_text(
        text=completion_msg,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return next_state

async def abandon_full_simulation(update: Update, context: CallbackContext) -> int:
    """Abandon full simulation"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Mark simulation as abandoned in database
        session_id = context.user_data.get('simulation_session_id')
        if session_id:
            db.abandon_simulation(session_id)
        
        # Clear context
        context.user_data.clear()
        
        await query.edit_message_text(
            "❌ <b>Симуляция отменена</b>\n\n"
            "Вы можете начать новую симуляцию в любое время.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Новая симуляция", callback_data="full_speaking_sim")],
                [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")]
            ]),
            parse_mode='HTML'
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"🔥 Error abandoning simulation: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при отмене симуляции.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Главное меню", callback_data="back_to_main_menu")]
            ])
        )
        return ConversationHandler.END

async def restart_full_simulation(update: Update, context: CallbackContext) -> int:
    """Restart full simulation"""
    query = update.callback_query
    await query.answer()
    
    # Clear previous simulation data
    context.user_data.clear()
    
    # Start new simulation
    return await start_full_speaking_simulation(update, context)



async def cancel_full_simulation(update: Update, context: CallbackContext) -> int:
    """Cancel full simulation via command"""
    await update.message.reply_text(
        "❌ <b>Симуляция отменена</b>\n\n"
        "Вы можете начать новую симуляцию командой /speaking",
        parse_mode='HTML'
    )
    
    # Clear context
    context.user_data.clear()
    
    return ConversationHandler.END



async def handle_speaking_stats(update: Update, context: CallbackContext) -> None:
    """Show user's speaking statistics"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get user's speaking statistics
        stats = db.get_user_speaking_stats(user.id)
        
        stats_text = "📈 <b>Ваша статистика IELTS Speaking</b>\n\n"
        stats_text += f"🎯 <b>Всего симуляций:</b> {stats['total_simulations']}\n"
        stats_text += f"✅ <b>Завершено:</b> {stats['completed_simulations']}\n"
        stats_text += f"🏆 <b>Лучший результат:</b> {stats['best_overall_score']}/9\n"
        stats_text += f"📊 <b>Средний результат:</b> {stats['average_overall_score']:.1f}/9\n"
        
        if stats['last_simulation_date']:
            last_date = stats['last_simulation_date'].split()[0] if isinstance(stats['last_simulation_date'], str) else str(stats['last_simulation_date']).split()[0]
            stats_text += f"📅 <b>Последняя симуляция:</b> {last_date}\n"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Новая симуляция", callback_data="full_speaking_sim")],
            [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
            [InlineKeyboardButton("🔙 Назад к говорению", callback_data="menu_speaking")]
        ]
        
        await query.edit_message_text(
            text=stats_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"🔥 Error showing speaking stats for user {user.id}: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при загрузке статистики. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="menu_speaking")]
            ])
        )

@require_access
async def handle_writing_stats(update: Update, context: CallbackContext) -> None:
    """Show user's writing statistics"""
    user = update.effective_user
    query = update.callback_query
    await query.answer()
    
    try:
        # Get user's writing statistics
        stats = db.get_user_writing_stats(user.id)
        
        stats_text = "✍️ <b>Ваша статистика IELTS Writing</b>\n\n"
        
        if stats['total_evaluations'] > 0:
            stats_text += f"📊 <b>Общая статистика:</b>\n"
            stats_text += f"• Всего проверок: {stats['total_evaluations']}\n"
            stats_text += f"• Средний балл: {stats['average_overall_score']:.1f}/9.0\n"
            stats_text += f"• Лучший результат: {stats['best_overall_score']:.1f}/9.0\n"
            
            if stats['last_evaluation_date']:
                last_date = stats['last_evaluation_date'].split()[0] if isinstance(stats['last_evaluation_date'], str) else str(stats['last_evaluation_date']).split()[0]
                stats_text += f"• Последняя проверка: {last_date}\n"
            
            # Add detailed criterion scores if available
            if stats['average_task_response_score'] > 0:
                stats_text += f"\n📋 <b>Детальные критерии:</b>\n"
                stats_text += f"• Task Response: {stats['average_task_response_score']:.1f}/9.0\n"
                stats_text += f"• Coherence & Cohesion: {stats['average_coherence_cohesion_score']:.1f}/9.0\n"
                stats_text += f"• Lexical Resource: {stats['average_lexical_resource_score']:.1f}/9.0\n"
                stats_text += f"• Grammatical Range: {stats['average_grammatical_range_score']:.1f}/9.0\n"

        else:
            stats_text += "📊 <b>Общая статистика:</b>\n"
            stats_text += "• Пока нет данных о проверках письма\n"
            stats_text += "• Начните проверку письма для получения статистики\n"
        
        keyboard = [
            [InlineKeyboardButton("📝 Проверить письмо", callback_data="writing_check")],
            [InlineKeyboardButton("🔙 Назад к профилю", callback_data="menu_profile")],
            [InlineKeyboardButton("🔙 Назад к письму", callback_data="menu_writing")]
        ]
        
        await query.edit_message_text(
            text=stats_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"🔥 Error showing writing stats for user {user.id}: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при загрузке статистики письма. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="menu_writing")]
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
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_topic_input)
        ],
        GET_WRITING_SUBMISSION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_submission),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$'),
        ],
        GET_WRITING_CHECK_TASK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_check_task_input),
        ],
        GET_WRITING_CHECK_ESSAY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_check_essay_input),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        # Add a fallback for any text input to ensure writing submissions are handled
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_writing_submission_fallback)
    ],
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
    entry_points=[
        CommandHandler("vocabulary", start_vocabulary_selection),
        CommandHandler("customword", custom_word_command),
        CommandHandler("aicustomword", ai_custom_word_command),
        CallbackQueryHandler(start_custom_word_input, pattern=r'^custom_word_add$'),
        CallbackQueryHandler(handle_ai_enhanced_custom_word, pattern=r'^ai_enhanced_custom_word$')
    ],
    states={
        GET_VOCABULARY_TOPIC: [
            CallbackQueryHandler(handle_vocabulary_choice_callback, pattern=r'^vocabulary_(random|topic|custom|ai_enhanced)$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic_and_generate_vocabulary)
        ],
        GET_CUSTOM_WORD: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_word_input),
            CallbackQueryHandler(menu_button_callback, pattern=r'^menu_vocabulary$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$')
        ],
        GET_CUSTOM_WORD_DEFINITION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_word_definition),
            CallbackQueryHandler(menu_button_callback, pattern=r'^menu_vocabulary$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$')
        ],
        GET_CUSTOM_WORD_TRANSLATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_word_translation),
            CallbackQueryHandler(menu_button_callback, pattern=r'^menu_vocabulary$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$')
        ],
        GET_CUSTOM_WORD_EXAMPLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_word_example),
            CallbackQueryHandler(menu_button_callback, pattern=r'^menu_vocabulary$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$')
        ],
        GET_CUSTOM_WORD_TOPIC: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_word_topic),
            CallbackQueryHandler(menu_button_callback, pattern=r'^menu_vocabulary$'),
            CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$')
        ],
    },
    fallbacks=[
        CallbackQueryHandler(menu_button_callback, pattern=r'^menu_vocabulary$'),
        CallbackQueryHandler(menu_button_callback, pattern=r'^back_to_main_menu$'),
        CommandHandler("cancel", cancel)
    ],
    name="vocabulary_conversation",
    persistent=False,
    per_message=False
)

# Custom word conversation handler is now integrated into vocabulary_conversation_handler

# AI-enhanced custom word conversation handler is now integrated into vocabulary_conversation_handler

# Full speaking simulation conversation handler
full_speaking_simulation_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_full_speaking_simulation, pattern=r'^full_speaking_sim$')
    ],
    states={
        FULL_SIM_PART_1: [
            MessageHandler(filters.VOICE, handle_simulation_response),
            CallbackQueryHandler(handle_skip_question, pattern=r'^skip_question$'),
            CallbackQueryHandler(handle_retry_question, pattern=r'^retry_current_question$'),
            CallbackQueryHandler(abandon_full_simulation, pattern=r'^abandon_full_sim$'),
            # Keep old patterns for backward compatibility
            CallbackQueryHandler(skip_full_sim_part, pattern=r'^skip_part_1$')
        ],
        FULL_SIM_PART_2: [
            MessageHandler(filters.VOICE, handle_simulation_response),
            CallbackQueryHandler(handle_skip_question, pattern=r'^skip_question$'),
            CallbackQueryHandler(handle_retry_question, pattern=r'^retry_current_question$'),
            CallbackQueryHandler(abandon_full_simulation, pattern=r'^abandon_full_sim$'),
            # Keep old patterns for backward compatibility
            CallbackQueryHandler(skip_full_sim_part, pattern=r'^skip_part_2$')
        ],
        FULL_SIM_PART_3: [
            MessageHandler(filters.VOICE, handle_simulation_response),
            CallbackQueryHandler(handle_skip_question, pattern=r'^skip_question$'),
            CallbackQueryHandler(handle_retry_question, pattern=r'^retry_current_question$'),
            CallbackQueryHandler(abandon_full_simulation, pattern=r'^abandon_full_sim$'),
            # Keep old patterns for backward compatibility
            CallbackQueryHandler(skip_full_sim_part, pattern=r'^skip_part_3$')
        ]
    },
    fallbacks=[
        CallbackQueryHandler(abandon_full_simulation, pattern=r'^abandon_full_sim$'),
        CommandHandler("cancel", cancel_full_simulation)
    ],
    name="full_speaking_simulation",
    persistent=False,
    per_message=False
)

# --- GROUP CHAT COMMANDS ---
async def handle_group_word_command(update: Update, context: CallbackContext) -> None:
    """Handle /word command in group chats"""
    # Check if this is a group chat
    if not is_group_chat(update):
        await update.message.reply_text(
            "📱 <b>Эта команда работает только в групповых чатах!</b>\n\n"
            "Для личного изучения словаря используйте команду /menu и выберите 'Словарь'.",
            parse_mode='HTML'
        )
        return
    
    group_info = get_group_info(update)
    user = update.effective_user
    
    try:
        # Add group to database if not exists
        db.add_group_chat(group_info['group_id'], group_info['group_title'], group_info['group_type'])
        
        # Show typing action
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Generate unique word for this group
        word_details = get_random_word_for_group(group_info['group_id'])
        
        # Extract word components
        word, definition, translation, example = extract_word_components(word_details)
        
        # Save word to group history
        success = db.save_word_to_group(
            group_info['group_id'], word, definition, translation, example, user.id
        )
        
        if success:
            # Send word to group with additional info
            group_word_message = (
                f"{word_details}\n\n"
                f"👥 <b>Группа:</b> {group_info['group_title']}\n"
                f"👤 <b>Запросил:</b> {user.first_name}\n"
                f"🎯 <i>Каждое слово уникально для этой группы!</i>"
            )
            
            await update.message.reply_text(group_word_message, parse_mode='HTML')
            logger.info(f"✅ Sent word '{word}' to group {group_info['group_id']} by user {user.id}")
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении слова. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    except Exception as e:
        logger.error(f"🔥 Error in group word command: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при генерации слова. Попробуйте позже.",
            parse_mode='HTML'
        )

async def handle_group_stats_command(update: Update, context: CallbackContext) -> None:
    """Show statistics for group word usage (admin only)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    try:
        if is_group_chat(update):
            # Show stats for current group
            group_info = get_group_info(update)
            stats = db.get_group_stats(group_info['group_id'])
            
            stats_message = (
                f"📊 <b>СТАТИСТИКА ГРУППЫ</b>\n\n"
                f"👥 <b>Группа:</b> {stats.get('group_title', 'Unknown')}\n"
                f"🆔 <b>ID:</b> <code>{stats.get('group_id')}</code>\n"
                f"📝 <b>Отправлено слов:</b> {stats.get('word_count', 0)}\n"
                f"📅 <b>Последняя активность:</b> {stats.get('last_activity', 'N/A')}\n"
            )
        else:
            # Show global stats
            stats = db.get_group_stats()
            all_groups = db.get_all_groups(limit=10)
            
            stats_message = (
                f"📊 <b>ГЛОБАЛЬНАЯ СТАТИСТИКА ГРУПП</b>\n\n"
                f"👥 <b>Всего групп:</b> {stats.get('total_groups', 0)}\n"
                f"🔥 <b>Активных групп:</b> {stats.get('active_groups', 0)}\n"
                f"📝 <b>Всего слов отправлено:</b> {stats.get('total_words_sent', 0)}\n\n"
                f"<b>📋 ТОП-10 АКТИВНЫХ ГРУПП:</b>\n"
            )
            
            for i, group in enumerate(all_groups[:10], 1):
                group_id, title, group_type, added_at, last_activity, word_count = group
                stats_message += f"{i}. {title[:20]}... ({word_count} слов)\n"
        
        await update.message.reply_text(stats_message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"🔥 Error in group stats command: {e}")
        await update.message.reply_text("❌ Ошибка при получении статистики.")

async def handle_group_reset_command(update: Update, context: CallbackContext) -> None:
    """Reset word history for a group (admin only)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    if not is_group_chat(update):
        await update.message.reply_text("❌ Эта команда работает только в групповых чатах.")
        return
    
    try:
        group_info = get_group_info(update)
        
        # Get current stats before clearing
        stats = db.get_group_stats(group_info['group_id'])
        word_count = stats.get('word_count', 0)
        
        if word_count == 0:
            await update.message.reply_text("ℹ️ В этой группе нет слов для очистки.")
            return
        
        # Clear words
        success = db.clear_group_words(group_info['group_id'])
        
        if success:
            reset_message = (
                f"✅ <b>ИСТОРИЯ СЛОВ ОЧИЩЕНА</b>\n\n"
                f"👥 <b>Группа:</b> {group_info['group_title']}\n"
                f"🗑️ <b>Удалено слов:</b> {word_count}\n"
                f"👤 <b>Очистил:</b> {user.first_name}\n\n"
                f"🎯 <i>Теперь можно снова получать все слова!</i>"
            )
            await update.message.reply_text(reset_message, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Ошибка при очистке истории слов.")
    
    except Exception as e:
        logger.error(f"🔥 Error in group reset command: {e}")
        await update.message.reply_text("❌ Ошибка при очистке истории слов.")

async def handle_group_history_command(update: Update, context: CallbackContext) -> None:
    """Show recent words sent to this group"""
    if not is_group_chat(update):
        await update.message.reply_text("❌ Эта команда работает только в групповых чатах.")
        return
    
    try:
        group_info = get_group_info(update)
        recent_words = db.get_group_sent_words(group_info['group_id'], limit=10)
        
        if not recent_words:
            await update.message.reply_text(
                "📝 <b>История слов пуста</b>\n\n"
                "Используйте команду /word чтобы получить первое слово!",
                parse_mode='HTML'
            )
            return
        
        history_message = (
            f"📚 <b>ПОСЛЕДНИЕ СЛОВА В ГРУППЕ</b>\n"
            f"👥 <b>{group_info['group_title']}</b>\n\n"
        )
        
        for i, (word, definition, translation, example, sent_at, sent_by_user_id) in enumerate(recent_words[:5], 1):
            history_message += (
                f"<b>{i}. {word.title()}</b>\n"
                f"   📖 {definition[:50]}{'...' if len(definition) > 50 else ''}\n"
                f"   🇷🇺 {translation}\n"
                f"   📅 {sent_at[:10]}\n\n"
            )
        
        history_message += f"📝 <i>Показано {min(len(recent_words), 5)} из {len(recent_words)} слов</i>"
        
        await update.message.reply_text(history_message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"🔥 Error in group history command: {e}")
        await update.message.reply_text("❌ Ошибка при получении истории слов.")

async def handle_group_autosend_command(update: Update, context: CallbackContext) -> None:
    """Enable/disable auto-send for current group (admin only)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    if not is_group_chat(update):
        await update.message.reply_text("❌ Эта команда работает только в групповых чатах.")
        return
    
    try:
        group_info = get_group_info(update)
        
        # Get current settings
        settings = db.get_group_settings(group_info['group_id'])
        current_status = settings.get('auto_send_enabled', False)
        
        # Toggle auto-send
        new_status = not current_status
        
        # Update settings
        success = db.update_group_settings(
            group_info['group_id'],
            auto_send_enabled=new_status,
            send_interval_hours=24  # Daily
        )
        
        if success:
            if new_status:
                status_message = (
                    f"✅ <b>АВТООТПРАВКА ВКЛЮЧЕНА</b>\n\n"
                    f"👥 <b>Группа:</b> {group_info['group_title']}\n"
                    f"🕐 <b>Интервал:</b> Каждый день\n"
                    f"<i>💡 Бот будет автоматически отправлять уникальные слова в эту группу каждый день!</i>"
                )
            else:
                status_message = (
                    f"❌ <b>АВТООТПРАВКА ОТКЛЮЧЕНА</b>\n\n"
                    f"👥 <b>Группа:</b> {group_info['group_title']}\n"
                    f"📝 <b>Статус:</b> Автоматическая отправка слов отключена\n\n"
                    f"<i>💡 Используйте команду /word для ручного получения слов</i>"
                )
            
            await update.message.reply_text(status_message, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ Ошибка при изменении настроек автоотправки.")
    
    except Exception as e:
        logger.error(f"🔥 Error in autosend command: {e}")
        await update.message.reply_text("❌ Ошибка при настройке автоотправки.")

# --- AUTO-SEND FUNCTIONALITY ---
async def auto_send_words_to_groups(context: CallbackContext) -> None:
    """Send words automatically to groups with auto-send enabled"""
    from datetime import datetime, timedelta
    
    try:
        # Get all groups with auto-send enabled
        groups_with_autosend = db.get_groups_with_auto_send()
        
        logger.info(f"🔄 Checking auto-send for {len(groups_with_autosend)} groups")
        
        for group in groups_with_autosend:
            group_id = group[0]
            group_title = group[1]
            last_auto_send = group[2]
            send_interval_hours = group[3]
            
            # Check if it's time to send a word
            if should_send_word_to_group(last_auto_send, send_interval_hours):
                try:
                    # Generate unique word for this group
                    word_details = get_random_word_for_group(group_id)
                    
                    # Extract word components
                    word, definition, translation, example = extract_word_components(word_details)
                    
                    # Save word to group history (using system user ID = 0)
                    success = db.save_word_to_group(
                        group_id, word, definition, translation, example, 0  # System user
                    )
                    
                    if success:
                        # Send auto word message
                        auto_word_message = (
                            f"🕐 <b>СЛОВО ДНЯ</b> (автоматическая отправка)\n\n"
                            f"{word_details}\n\n"
                            f"👥 <b>Группа:</b> {group_title}\n"
                            f"🤖 <b>Отправлено автоматически</b>\n"
                            f"🎯 <i>Каждое слово уникально для этой группы!</i>"
                        )
                        
                        # Send message to group
                        await context.bot.send_message(
                            chat_id=group_id,
                            text=auto_word_message,
                            parse_mode='HTML'
                        )
                        
                        # Update last auto send time
                        db.update_group_settings(
                            group_id,
                            last_auto_send=datetime.now().isoformat()
                        )
                        
                        logger.info(f"✅ Auto-sent word '{word}' to group {group_id} ({group_title})")
                    else:
                        logger.error(f"🔥 Failed to save auto word for group {group_id}")
                
                except Exception as e:
                    logger.error(f"🔥 Error auto-sending to group {group_id}: {e}")
    
    except Exception as e:
        logger.error(f"🔥 Error in auto_send_words_to_groups: {e}")

def should_send_word_to_group(last_auto_send: str, send_interval_hours: int) -> bool:
    """Check if it's time to send a word to a group"""
    from datetime import datetime, timedelta
    
    if not last_auto_send:
        # Never sent before, send now
        return True
    
    try:
        last_send_time = datetime.fromisoformat(last_auto_send)
        now = datetime.now()
        time_diff = now - last_send_time
        
        # Check if enough time has passed
        return time_diff >= timedelta(hours=send_interval_hours)
    
    except Exception as e:
        logger.error(f"🔥 Error checking send time: {e}")
        return False

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

def add_user_to_permanent_whitelist(user_id: int) -> bool:
    """Add user ID permanently to config.py whitelist"""
    try:
        config_file_path = 'config.py'
        
        # Read current config file
        with open(config_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Find the AUTHORIZED_USER_IDS section
        import re
        pattern = r'(AUTHORIZED_USER_IDS\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            start, current_ids, end = match.groups()
            
            # Check if user_id already exists
            if str(user_id) in current_ids:
                return True  # Already exists
            
            # Add new user_id
            if current_ids.strip():
                new_ids = current_ids.rstrip() + f'\n    {user_id},'
            else:
                new_ids = f'\n    {user_id},'
            
            # Replace in content
            new_content = content.replace(match.group(0), f'{start}{new_ids}\n{end}')
            
            # Write back to file
            with open(config_file_path, 'w', encoding='utf-8') as file:
                file.write(new_content)
            
            # Update runtime config
            try:
                config.AUTHORIZED_USER_IDS.append(user_id)
            except Exception:
                pass
            
            return True
        
    except Exception as e:
        logger.error(f"Failed to add user {user_id} to permanent whitelist: {e}")
        return False


def remove_user_from_permanent_whitelist(user_id: int) -> bool:
    """Remove user ID permanently from config.py whitelist"""
    try:
        config_file_path = 'config.py'
        
        # Read current config file
        with open(config_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Find and remove the user_id
        import re
        pattern = rf'\s*{user_id},?\s*\n?'
        new_content = re.sub(pattern, '', content)
        
        # Write back to file
        with open(config_file_path, 'w', encoding='utf-8') as file:
            file.write(new_content)
        
        # Update runtime config
        try:
            if user_id in config.AUTHORIZED_USER_IDS:
                config.AUTHORIZED_USER_IDS.remove(user_id)
        except Exception:
            pass
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to remove user {user_id} from permanent whitelist: {e}")
        return False


def add_username_to_permanent_whitelist(username: str) -> bool:
    """Add username permanently to config.py whitelist"""
    try:
        config_file_path = 'config.py'
        
        with open(config_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Find the AUTHORIZED_USERNAMES section
        import re
        pattern = r'(AUTHORIZED_USERNAMES\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            start, current_usernames, end = match.groups()
            
            # Check if username already exists
            if f'"{username}"' in current_usernames:
                return True
            
            # Add new username
            if current_usernames.strip():
                new_usernames = current_usernames.rstrip() + f',\n    "{username}",'
            else:
                new_usernames = f'\n    "{username}",'
            
            # Replace in content
            new_content = content.replace(match.group(0), f'{start}{new_usernames}\n{end}')
            
            with open(config_file_path, 'w', encoding='utf-8') as file:
                file.write(new_content)
            
            # Update runtime config
            try:
                config.AUTHORIZED_USERNAMES.append(username)
            except Exception:
                pass
            
            return True
        
    except Exception as e:
        logger.error(f"Failed to add username {username} to permanent whitelist: {e}")
        return False


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

══════════════════════════
🚀 <b>ОСНОВНЫЕ КОМАНДЫ</b>
══════════════════════════

<b>🔧 Панель управления:</b>
• <code>/admin</code> - Открыть админ-панель
• <code>/testdb</code> - Проверить подключение к базе данных
• <code>/whitelist</code> - Показать статус whitelist

══════════════════════════
👥 <b>УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ</b>
══════════════════════════

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

══════════════════════════
🔐 <b>УПРАВЛЕНИЕ WHITELIST</b>
══════════════════════════

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

══════════════════════════
📊 <b>МОНИТОРИНГ И СТАТИСТИКА</b>
══════════════════════════

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

══════════════════════════
🛡️ <b>БЕЗОПАСНОСТЬ И ЛУЧШИЕ ПРАКТИКИ</b>
══════════════════════════

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

"""

    keyboard = [
        [InlineKeyboardButton("🔙 Назад к админ-панели", callback_data="admin_panel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send as single message (admin instructions should fit in one message)
    try:
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')
    except Exception as e:
        # If edit fails (message too long), send truncated version
        logger.warning(f"Admin help message too long, truncating: {e}")
        short_help = """📖 <b>ИНСТРУКЦИЯ АДМИНИСТРАТОРА</b>

🚀 <b>Основные команды:</b>
• <code>/admin</code> - Админ-панель
• <code>/adminhelp</code> - Быстрая справка

👥 <b>Управление пользователями:</b>
• <code>/block_ID</code> - Блокировка
• <code>/unblock_ID</code> - Разблокировка
• <code>/delete_ID</code> - Удаление (необратимо!)

🔐 <b>Управление доступом:</b>
• <code>/adduser_ID</code> - Добавить по ID
• <code>/addusername_name</code> - Добавить по username
• <code>/removeuser_ID</code> - Удалить по ID
• <code>/removeusername_name</code> - Удалить по username

🔍 <b>Поиск:</b> Админ-панель → "Поиск пользователя"
📊 <b>Статистика:</b> Админ-панель → "Подробная статистика"

⚠️ <b>Важно:</b> Удаление пользователей необратимо!"""
        
        await query.edit_message_text(short_help, reply_markup=reply_markup, parse_mode='HTML')

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
    """Add user to whitelist permanently (admin only)"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])

        # Check if user already has access
        if target_user_id in config.AUTHORIZED_USER_IDS:
            await update.message.reply_text(f"ℹ️ User {target_user_id} already has permanent access.")
            return

        # Add to permanent whitelist
        if add_user_to_permanent_whitelist(target_user_id):
            # Also add to database
            try:
                db.add_user(target_user_id)
            except Exception as e:
                logger.error(f"Failed to add user {target_user_id} to DB: {e}")

            await update.message.reply_text(
                f"✅ User {target_user_id} added to permanent whitelist!\n\n"
                f"🔄 The user now has permanent access to the bot.\n"
                f"📝 User ID added to config.py and will persist after bot restart."
            )

            logger.info(f"Admin {update.effective_user.id} permanently added user {target_user_id} to whitelist")
        else:
            await update.message.reply_text(f"❌ Failed to add user {target_user_id} to permanent whitelist.")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid command format. Use: /adduser_123456")

@require_admin
async def admin_remove_user_command(update: Update, context: CallbackContext) -> None:
    """Remove user from whitelist permanently (admin only)"""
    command_text = update.message.text
    try:
        target_user_id = int(command_text.split('_')[1])

        if target_user_id == update.effective_user.id:
            await update.message.reply_text("❌ You cannot remove yourself from the whitelist!")
            return

        # Remove from permanent whitelist
        if remove_user_from_permanent_whitelist(target_user_id):
            await update.message.reply_text(
                f"✅ User {target_user_id} removed from permanent whitelist!\n\n"
                f"🚫 The user no longer has access to the bot.\n"
                f"📝 User ID removed from config.py permanently."
            )
            logger.info(f"Admin {update.effective_user.id} permanently removed user {target_user_id} from whitelist")
        else:
            await update.message.reply_text(f"❌ Failed to remove user {target_user_id} from permanent whitelist.")

    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid command format. Use: /removeuser_123456")

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
