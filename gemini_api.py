import logging
import google.generativeai as genai
import time
import hashlib
import random
import os

import config

logger = logging.getLogger(__name__)

model = None
writing_model = None

def initialize_gemini():
    """Initializes the Gemini model with the API key and a system instruction."""
    global model, writing_model
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        
        generation_config = genai.GenerationConfig(
            temperature=0.9,
            top_p=0.95,
            top_k=50
        )
        
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction="You are an elite IELTS tutor and examiner with a 9.0 score. Your responses must be accurate, professional, and directly address the user's request without any unnecessary conversational text. When the user interface is in Russian, provide your responses in Russian as well.",
            generation_config=generation_config
        )
        
        writing_config = genai.GenerationConfig(
            temperature=0.7,
            top_p=0.8,
            top_k=40
        )
        
        writing_model = genai.GenerativeModel(
            model_name='gemini-2.5-pro',
            system_instruction="You are an elite IELTS tutor and examiner with a 9.0 score. Your responses must be accurate, professional, and directly address the user's request without any unnecessary conversational text. When the user interface is in Russian, provide your responses in Russian as well.",
            generation_config=writing_config
        )
        
        logger.info("✅ Gemini API models initialized successfully.")
    except Exception as e:
        logger.error(f"🔥 Failed to initialize Gemini API: {e}")
        raise


def generate_text_with_retry(prompt: str, max_retries: int = 3, base_delay: float = 1.0) -> str:
    """Sends a prompt to the initialized Gemini model with retry logic for empty responses."""
    if not model:
        logger.error("🔥 Gemini model not initialized. Call initialize_gemini() first.")
        return "Error: The AI model is not available. Please contact the administrator."

    for attempt in range(max_retries):
        try:
            logger.info(f"➡️ Sending prompt to Gemini (attempt {attempt + 1}/{max_retries}): '{prompt[:80]}...'")
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Check if response is empty or too short
            if not response_text or len(response_text) < 10:
                logger.warning(f"⚠️ Empty or too short response received (attempt {attempt + 1}): '{response_text[:100]}...'")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"🔄 Retrying in {delay} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"🔥 All {max_retries} attempts failed to get a valid response")
                    return "Sorry, I couldn't generate a proper response. Please try again."
            
            logger.info(f"✅ Successfully generated response on attempt {attempt + 1}")
            return response_text
            
        except Exception as e:
            logger.error(f"🔥 An error occurred while generating text with Gemini (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.info(f"🔄 Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                return "Sorry, I encountered an error while processing your request."


def generate_text(prompt: str) -> str:
    """Sends a prompt to the initialized Gemini model and returns the text response."""
    return generate_text_with_retry(prompt)


def generate_writing_text_with_retry(prompt: str, max_retries: int = 3, base_delay: float = 1.0) -> str:
    """Sends a prompt to the writing-specific Gemini model with retry logic for empty responses."""
    if not writing_model:
        logger.error("🔥 Writing Gemini model not initialized. Call initialize_gemini() first.")
        return "Error: The AI model is not available. Please contact the administrator."

    for attempt in range(max_retries):
        try:
            logger.info(f"➡️ Sending writing prompt to Gemini Pro (attempt {attempt + 1}/{max_retries}): '{prompt[:80]}...'")
            response = writing_model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Check if response is empty or too short
            if not response_text or len(response_text) < 10:
                logger.warning(f"⚠️ Empty or too short writing response received (attempt {attempt + 1}): '{response_text[:100]}...'")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"🔄 Retrying writing generation in {delay} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"🔥 All {max_retries} attempts failed to get a valid writing response")
                    return "Sorry, I couldn't generate a proper writing evaluation. Please try again."
            
            logger.info(f"✅ Successfully generated writing response on attempt {attempt + 1}")
            return response_text
            
        except Exception as e:
            logger.error(f"🔥 An error occurred while generating writing text with Gemini Pro (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.info(f"🔄 Retrying writing generation in {delay} seconds...")
                time.sleep(delay)
            else:
                return "Sorry, I encountered an error while processing your writing evaluation."


def generate_writing_text(prompt: str) -> str:
    """Sends a prompt to the writing-specific Gemini model and returns the text response."""
    return generate_writing_text_with_retry(prompt)

def get_random_word_details(word_level="IELTS Band 7-9 (C1/C2)") -> str:
    entropy_sources = [
        str(time.time()),
        str(random.randint(1, 1000000)),
        os.urandom(8).hex(),
        str(hash(time.time()))
    ]
    combined_entropy = ''.join(entropy_sources)
    seed = hashlib.sha256(combined_entropy.encode()).hexdigest()[:12]
    
    prompt = f"""
    Generate one advanced English vocabulary word suitable for a {word_level} student, relevant to a common IELTS topic (e.g., environment, technology, society). Use this unique seed for maximum variation: {seed}.

    **Your output must strictly follow this exact format with clear sections and proper spacing:**

    🎯 VOCABULARY WORD OF THE DAY

    📝 Word: [the vocabulary word]
    📖 Definition: [clear English definition]
    🇷🇺 Translation: [Russian translation]
    💡 Example: [example sentence showing proper usage]

    **Do not include any other text, explanations, or introductory phrases. Use only the format above.**
    """
    return generate_text(prompt)

def get_topic_specific_words(topic: str, count: int = 10) -> str:
    """Generates a list of topic-specific vocabulary words."""
    prompt = f"""
    List {count} essential, high-level vocabulary words related to the IELTS topic "{topic}".
    For each word, provide its English definition, Russian translation, and an example sentence.
    
    **Your output must strictly follow this exact format with clear sections and proper spacing:**

    📚 ESSENTIAL VOCABULARY: {topic.upper()}

    [For each word, use this format:]
    1. 📝 [Word]
       📖 Definition: [clear English definition]
       🇷🇺 Translation: [Russian translation]
       💡 Example: [example sentence showing proper usage]

    2. 📝 [Word]
       📖 Definition: [clear English definition]
       🇷🇺 Translation: [Russian translation]
       💡 Example: [example sentence showing proper usage]

    [Continue this format for all {count} words]

    **Do not include any other text, explanations, or introductory phrases. Use only the format above.**
    """
    return generate_text(prompt)

def generate_ielts_writing_task(task_type: str, topic: str) -> str:
    """Generates a realistic IELTS Writing Task prompt with a strict format."""
    if "task 1" in task_type.lower():
        prompt = f"""
        Generate one IELTS Academic Writing Task 1 prompt related to the topic of "{topic}".
        The prompt must describe a visual data representation (like a chart, graph, or diagram).

        **Your output must strictly follow this exact format:**

        ✍️ IELTS WRITING TASK 1

        📊 Task Description:
        [Describe the visual data - chart, graph, or diagram related to {topic}]

        📋 Instructions:
        Summarize the information by selecting and reporting the main features, and make comparisons where relevant.

        ⏰ Time: 20 minutes
        📝 Word Count: At least 150 words

        **Do not include any other text, explanations, or introductory phrases. Use only the format above.**
        """
    else: # Default to Task 2
        prompt = f"""
        Generate one IELTS Writing Task 2 essay question on the topic of "{topic}".
        The question should present a clear argument, problem, or discussion point.

        **Your output must strictly follow this exact format:**

        ✍️ IELTS WRITING TASK 2

        🤔 Essay Question:
        [The essay question or statement related to {topic}]

        📋 Instructions:
        Write at least 250 words. You should spend about 40 minutes on this task.

        **Do not include any other text, explanations, or introductory phrases. Use only the format above.**
        """
    # Use the existing, working generate_text function
    return generate_text(prompt)

def evaluate_writing(writing_text: str, task_description: str) -> str:
    """Generates a comprehensive evaluation of an IELTS essay."""
    prompt = f"""
    Task: Provide a comprehensive assessment of an IELTS Writing Task 2 essay.
    Essay Question: {task_description}
    Student's Essay: {writing_text}

    Instructions: Evaluate the essay based on the four official IELTS criteria (Task Response, Coherence & Cohesion, Lexical Resource, Grammatical Range & Accuracy).

    Your output must strictly follow this exact format with clear sections and proper spacing:

    📊 IELTS WRITING ASSESSMENT REPORT

    🎯 Overall Band Score: [Your calculated score]

    📝 Examiner's General Comments:
    [Your brief summary of the essay's overall performance]

    ────────────────────
    📋 DETAILED CRITERION-BASED ASSESSMENT
    ────────────────────

    📌 Task Response (TR): Band [Score]
    💬 Justification: [Your detailed justification]

    📌 Coherence & Cohesion (CC): Band [Score]
    💬 Justification: [Your detailed justification]

    📌 Lexical Resource (LR): Band [Score]
    💬 Justification: [Your detailed justification]

    📌 Grammatical Range & Accuracy (GRA): Band [Score]
    💬 Justification: [Your detailed justification]

    ────────────────────
    🎯 KEY STRENGTHS & ACTIONABLE RECOMMENDATIONS
    ────────────────────

    ✅ What You Did Well:
    • [Strength 1]
    • [Strength 2]

    🔧 Top Priorities for Improvement:
    • [Priority 1 with actionable advice]
    • [Priority 2 with actionable advice]

    **Do not add any other text, explanations, or concluding phrases. Use only the format above.**
    """
    return generate_writing_text(prompt)

def generate_speaking_question(part: str, topic: str = "a common topic") -> str:
    """Constructs a strict prompt to generate only the IELTS speaking questions."""
    if "part 2" in part.lower():
        prompt = f"""
        Generate one IELTS Speaking Part 2 cue card on the topic of "{topic}".

        **Your output must strictly follow this exact format:**

        🗣️ IELTS SPEAKING PART 2

        📋 Cue Card:
        Describe [the topic related to {topic}]

        You should say:
        • [First bullet point]
        • [Second bullet point]
        • [Third bullet point]
        • [Fourth bullet point]

        And explain [what you should explain]

        ⏰ Preparation Time: 1 minute
        🎤 Speaking Time: 1-2 minutes

        **Do not add any other text, explanations, or introductory phrases. Use only the format above.**
        """
    elif "part 3" in part.lower():
        prompt = f"""
        Generate exactly 3-4 IELTS Speaking Part 3 discussion questions related to the topic of "{topic}".

        **Your output must strictly follow this exact format:**

        🗣️ IELTS SPEAKING PART 3

        💭 Discussion Questions:

        1. [First discussion question related to {topic}]

        2. [Second discussion question related to {topic}]

        3. [Third discussion question related to {topic}]

        4. [Fourth discussion question related to {topic}]

        ⏰ Time: 4-5 minutes
        🎯 Focus: In-depth discussion and analysis

        **Do not provide any introductory or concluding text. Use only the format above.**
        """
    else: # Default to Part 1
        prompt = f"""
        Generate exactly 3-4 IELTS Speaking Part 1 questions on the topic of "{topic}".

        **Your output must strictly follow this exact format:**

        🗣️ IELTS SPEAKING PART 1

        💬 Personal Questions:

        1. [First personal question about {topic}]

        2. [Second personal question about {topic}]

        3. [Third personal question about {topic}]

        4. [Fourth personal question about {topic}]

        ⏰ Time: 4-5 minutes
        🎯 Focus: Personal experiences and opinions

        **Do not include any explanation or preamble. Use only the format above.**
        """
    return generate_text(prompt)

def generate_ielts_strategies(section: str, task_type: str = "general") -> str:
    """Constructs a prompt for a fully formatted message with IELTS strategies in Russian."""
    section_name = section.strip().capitalize()
    
    # Create task-specific prompts in Russian
    task_prompts = {
        # Listening task types
        "truefalse": f"Создай конкретные стратегии для вопросов Правда/Ложь в IELTS {section_name}. Сосредоточься на определении ключевых слов, понимании синонимов и распознавании, когда информация противоречит или не упоминается.",
        "multiplechoice": f"Создай конкретные стратегии для вопросов Множественного выбора в IELTS {section_name}. Сосредоточься на чтении всех вариантов перед прослушиванием, определении отвлекающих факторов и понимании точного значения каждого варианта.",
        "notes": f"Создай конкретные стратегии для заданий Заполнения заметок в IELTS {section_name}. Сосредоточься на предсказании типов слов, прослушивании конкретной информации и понимании структуры заметок.",
        
        # Reading task types
        "shortanswer": f"Создай конкретные стратегии для вопросов Кратких ответов в IELTS {section_name}. Сосредоточься на сканировании ключевых слов, понимании типов вопросов и написании кратких ответов в пределах лимита слов.",
        "headings": f"Создай конкретные стратегии для заданий Соответствия заголовков в IELTS {section_name}. Сосредоточься на понимании основных идей, определении тематических предложений и распознавании структуры абзацев.",
        "summary": f"Создай конкретные стратегии для заданий Заполнения резюме в IELTS {section_name}. Сосредоточься на понимании контекста, предсказании типов слов и поддержании грамматической точности."
    }
    
    # Get the specific prompt or use a general one
    specific_prompt = task_prompts.get(task_type, f"Создай общие стратегии для секции IELTS {section_name}")
    
    prompt = f"""
    {specific_prompt} 


    **Твой вывод должен строго следовать этому точному формату с четкими разделами и правильными интервалами:**


    💡 ТОПОВЫЕ СТРАТЕГИИ ДЛЯ IELTS {section_name.upper()} - {task_type.replace('_', ' ').upper()}


    ────────────────────────────────────────
    🎯 ОСНОВНЫЕ СТРАТЕГИИ
    ────────────────────────────────────────


    1. 📌 [Название стратегии]
       💬 [Подробное объяснение стратегии с конкретными советами для этого типа задания]


    2. 📌 [Название стратегии]
       💬 [Подробное объяснение стратегии с конкретными советами для этого типа задания]


    3. 📌 [Название стратегии]
       💬 [Подробное объяснение стратегии с конкретными советами для этого типа задания]


    4. 📌 [Название стратегии]
       💬 [Подробное объяснение стратегии с конкретными советами для этого типа задания]


    5. 📌 [Название стратегии]
       💬 [Подробное объяснение стратегии с конкретными советами для этого типа задания]


    **Не добавляй никакого заключительного текста или дополнительных объяснений. Используй только указанный выше формат.**
    """
    return generate_text(prompt)


def explain_grammar_structure(grammar_topic: str) -> str:
    """Constructs a prompt to get a detailed explanation of a grammar topic in Russian."""
    prompt = f"""
    Объясни грамматическую тему английского языка: "{grammar_topic}".

    **Твой ответ должен строго следовать этому формату с четкими разделами и правильными отступами:**

    📖 ОБЪЯСНЕНИЕ ГРАММАТИКИ: {grammar_topic.upper()}

    ────────────────────────────────────────
    📚 ПОДРОБНОЕ РУКОВОДСТВО
    ────────────────────────────────────────

    1. 📝 Что это такое:
       💬 [Простое, четкое определение грамматической структуры]

    2. 🔧 Как это образуется:
       💬 [Грамматическая формула и структура с примерами]

    3. 🎯 Когда использовать:
       💬 [Ключевые случаи использования и ситуации, где эта грамматика уместна]

    4. 💡 Примеры:
       • [Первый четкий пример предложения]
       • [Второй четкий пример предложения]
       • [Третий четкий пример предложения]

    ────────────────────────────────────────
    ⚠️ Распространенные ошибки:
    ────────────────────────────────────────
    • [Распространенная ошибка 1]
    • [Распространенная ошибка 2]

    **Сделай объяснение ясным, кратким и практичным для подготовки к IELTS. Не добавляй никакого заключительного текста. Если грамматическая тема указана на русском языке, объясни её на русском языке.**
    """
    return generate_text(prompt)

def evaluate_speaking_response(speaking_prompt: str, user_transcription: str, part: str) -> str:
    """Evaluates IELTS speaking response based on official criteria and provides band score."""
    prompt = f"""
    Task: Evaluate an IELTS Speaking {part} response according to the official IELTS Speaking band descriptors.
    
    Speaking Prompt: {speaking_prompt}
    Student's Response: {user_transcription}
    
    Instructions: Assess the response based on the four official IELTS Speaking criteria:
    1. Fluency and Coherence (FC)
    2. Lexical Resource (LR) 
    3. Grammatical Range and Accuracy (GRA)
    4. Pronunciation (P)
    
                    **Your output must be CONCISE and fit in one message. Follow this exact format:**

                🎤 <b>IELTS SPEAKING - {part.upper()}</b>

                🎯 <b>Балл:</b> [Score]/9

                📝 <b>Краткая оценка:</b>
                [Brief 1-2 sentence summary]

                <b>📊 АНАЛИЗ ПО КРИТЕРИЯМ:</b>

                🗣️ <b>Беглость (FC):</b> [Score] - [Brief 1 sentence evaluation]
                📚 <b>Лексика (LR):</b> [Score] - [Brief 1 sentence evaluation]  
                🔤 <b>Грамматика (GRA):</b> [Score] - [Brief 1 sentence evaluation]
                🎵 <b>Произношение (P):</b> [Score] - [Brief 1 sentence evaluation]

                <b>🎯 РЕКОМЕНДАЦИИ:</b>
                ✅ <b>Сильные стороны:</b> [1-2 key strengths in one sentence]
                🔧 <b>Улучшить:</b> [2-3 specific improvement areas with actionable advice in 1-2 sentences]
                💡 <b>Совет:</b> [One concrete practice recommendation]

                **Keep response under 2000 characters total. Be concise but helpful. Respond in Russian. Use only HTML tags shown above.**
    """
    return generate_writing_text(prompt)

def evaluate_speaking_response_for_simulation(speaking_prompt: str, 
                                           user_transcription: str, 
                                           part: str) -> str:
    """Enhanced evaluation for simulation mode with structured scoring"""
    prompt = f"""
    Task: Evaluate an IELTS Speaking {part} response according to the official IELTS Speaking band descriptors.
    
    Speaking Prompt: {speaking_prompt}
    Student's Response: {user_transcription}
    
    Instructions: Assess the response based on the four official IELTS Speaking criteria:
    1. Fluency and Coherence (FC)
    2. Lexical Resource (LR) 
    3. Grammatical Range and Accuracy (GRA)
    4. Pronunciation (P)
    
    **Your output must be CONCISE and follow this exact format:**

    🎤 <b>IELTS SPEAKING - {part.upper()}</b>

    🎯 <b>Балл:</b> [Score]/9

    📝 <b>Краткая оценка:</b>
    [Brief 1-2 sentence summary]

    <b>📊 АНАЛИЗ ПО КРИТЕРИЯМ:</b>

    🗣️ <b>Беглость (FC):</b> [Score] - [Brief 1 sentence evaluation]
    📚 <b>Лексика (LR):</b> [Score] - [Brief 1 sentence evaluation]  
    🔤 <b>Грамматика (GRA):</b> [Score] - [Brief 1 sentence evaluation]
    🎵 <b>Произношение (P):</b> [Score] - [Brief 1 sentence evaluation]

python main.py
    <b>🎯 РЕКОМЕНДАЦИИ:</b>
    ✅ <b>Сильные стороны:</b> [1-2 key strengths in one sentence]
    🔧 <b>Улучшить:</b> [2-3 specific improvement areas with actionable advice in 1-2 sentences]
    💡 <b>Совет:</b> [One concrete practice recommendation]

    **Keep response under 2000 characters total. Be concise but helpful. Respond in Russian. Use only HTML tags shown above.**
    """
    return generate_writing_text(prompt)

def extract_scores_from_evaluation(evaluation_text: str) -> dict:
    """Extract numerical scores from evaluation text"""
    import re
    
    scores = {
        'overall': 0.0,
        'fluency': 0.0,
        'vocabulary': 0.0,
        'grammar': 0.0,
        'pronunciation': 0.0,
        'summary': ''
    }
    
    try:
        # Extract overall score
        overall_match = re.search(r'🎯 <b>Балл:</b> ([\d.]+)/9', evaluation_text)
        if overall_match:
            scores['overall'] = float(overall_match.group(1))
        
        # Extract individual criterion scores
        fluency_match = re.search(r'🗣️ <b>Беглость \(FC\):</b> ([\d.]+)', evaluation_text)
        if fluency_match:
            scores['fluency'] = float(fluency_match.group(1))
        
        vocabulary_match = re.search(r'📚 <b>Лексика \(LR\):</b> ([\d.]+)', evaluation_text)
        if vocabulary_match:
            scores['vocabulary'] = float(vocabulary_match.group(1))
        
        grammar_match = re.search(r'🔤 <b>Грамматика \(GRA\):</b> ([\d.]+)', evaluation_text)
        if grammar_match:
            scores['grammar'] = float(grammar_match.group(1))
        
        pronunciation_match = re.search(r'🎵 <b>Произношение \(P\):</b> ([\d.]+)', evaluation_text)
        if pronunciation_match:
            scores['pronunciation'] = float(pronunciation_match.group(1))
        
        # Extract summary
        summary_match = re.search(r'📝 <b>Краткая оценка:</b>\n([^<]+)', evaluation_text)
        if summary_match:
            scores['summary'] = summary_match.group(1).strip()
        
    except Exception as e:
        logger.error(f"🔥 Error extracting scores from evaluation: {e}")
    
    return scores

def extract_writing_scores_from_evaluation(evaluation_text: str) -> dict:
    """Extract numerical scores from writing evaluation text"""
    import re
    
    scores = {
        'overall': 0.0,
        'task_response': 0.0,
        'coherence_cohesion': 0.0,
        'lexical_resource': 0.0,
        'grammatical_range': 0.0,
        'summary': ''
    }
    
    try:
        # Extract overall score
        overall_match = re.search(r'🎯 Overall Band Score: ([\d.]+)', evaluation_text)
        if overall_match:
            scores['overall'] = float(overall_match.group(1))
        
        # Extract individual criterion scores
        task_response_match = re.search(r'📌 Task Response \(TR\): Band ([\d.]+)', evaluation_text)
        if task_response_match:
            scores['task_response'] = float(task_response_match.group(1))
        
        coherence_match = re.search(r'📌 Coherence & Cohesion \(CC\): Band ([\d.]+)', evaluation_text)
        if coherence_match:
            scores['coherence_cohesion'] = float(coherence_match.group(1))
        
        lexical_match = re.search(r'📌 Lexical Resource \(LR\): Band ([\d.]+)', evaluation_text)
        if lexical_match:
            scores['lexical_resource'] = float(lexical_match.group(1))
        
        grammar_match = re.search(r'📌 Grammatical Range & Accuracy \(GRA\): Band ([\d.]+)', evaluation_text)
        if grammar_match:
            scores['grammatical_range'] = float(grammar_match.group(1))
        
        # Extract summary
        summary_match = re.search(r'📝 Examiner\'s General Comments:\n([^<]+)', evaluation_text)
        if summary_match:
            scores['summary'] = summary_match.group(1).strip()
        
    except Exception as e:
        logger.error(f"🔥 Error extracting writing scores from evaluation: {e}")
    
    return scores

def add_custom_word_to_dictionary(word: str, definition: str = None, translation: str = None, 
                                example: str = None, topic: str = None) -> str:
    """Add a custom word to the user's dictionary with AI-enhanced details if needed"""
    
    # If user provided all details, just return a formatted confirmation
    if definition and translation and example:
        return f"""
✅ <b>СЛОВО УСПЕШНО ДОБАВЛЕНО В СЛОВАРЬ</b>

📝 <b>Слово:</b> {word}
📖 <b>Определение:</b> {definition}
🇷🇺 <b>Перевод:</b> {translation}
💡 <b>Пример:</b> {example}
🏷️ <b>Тема:</b> {topic if topic else 'Пользовательская'}

🎯 Слово сохранено в ваш личный словарь!
        """.strip()
    
    # If user provided incomplete information, use AI to enhance it
    prompt = f"""
    Пользователь хочет добавить слово "{word}" в свой словарь для изучения IELTS.
    
    Пользователь предоставил:
    - Определение: {definition if definition else 'Не указано'}
    - Перевод: {translation if translation else 'Не указан'}
    - Пример: {example if example else 'Не указан'}
    - Тема: {topic if topic else 'Не указана'}
    
    Пожалуйста, дополни недостающую информацию и улучши существующую, чтобы создать полное определение слова для изучения IELTS.
    
    **Твой вывод должен строго следовать этому точному формату:**

    ✅ <b>СЛОВО УСПЕШНО ДОБАВЛЕНО В СЛОВАРЬ</b>

    📝 <b>Слово:</b> {word}
    📖 <b>Определение:</b> [четкое английское определение]
    🇷🇺 <b>Перевод:</b> [русский перевод]
    💡 <b>Пример:</b> [пример предложения]
    🏷️ <b>Тема:</b> [тема для IELTS]

    🎯 Слово сохранено в ваш личный словарь!
    
    **Не добавляй никакого другого текста или объяснений. Используй только указанный выше формат.**
    """
    
    return generate_text(prompt)

# === FLASHCARD GENERATION FUNCTIONS ===

def generate_flashcard_from_topic(topic: str, difficulty: str = "IELTS Band 7-9", card_type: str = "vocabulary") -> dict:
    """Generate a flashcard for a specific topic and difficulty"""
    
    if card_type == "vocabulary":
        prompt = f"""
        Create a vocabulary flashcard for {topic} at {difficulty} level.
        
        Generate a word that is:
        - Relevant to {topic}
        - Appropriate for {difficulty} students
        - Useful for IELTS exam preparation
        
        Format your response exactly as:
        
        FRONT: [English word or phrase]
        BACK: [Definition in English]
        TRANSLATION: [Russian translation]
        EXAMPLE: [Example sentence using the word]
        TAGS: {topic}, {difficulty}, vocabulary
        DIFFICULTY: [1-5 scale where 1=easy, 5=very hard]
        """
    
    elif card_type == "grammar":
        prompt = f"""
        Create a grammar flashcard for {topic} at {difficulty} level.
        
        Format your response exactly as:
        
        FRONT: [Grammar rule or question about {topic}]
        BACK: [Explanation with example]
        TRANSLATION: [Russian explanation if needed]
        EXAMPLE: [Example sentences showing correct usage]
        TAGS: {topic}, {difficulty}, grammar
        DIFFICULTY: [1-5 scale where 1=easy, 5=very hard]
        """
    
    elif card_type == "speaking":
        prompt = f"""
        Create a speaking practice flashcard for {topic} at {difficulty} level.
        
        Format your response exactly as:
        
        FRONT: [Speaking question about {topic}]
        BACK: [Sample answer with key vocabulary and structures]
        TRANSLATION: [Key Russian vocabulary if needed]
        EXAMPLE: [Additional phrases for this topic]
        TAGS: {topic}, {difficulty}, speaking
        DIFFICULTY: [1-5 scale where 1=easy, 5=very hard]
        """
    
    try:
        response = generate_text_with_retry(prompt)
        return parse_flashcard_response(response)
    except Exception as e:
        logger.error(f"🔥 Failed to generate flashcard: {e}")
        return {
            'front': f"Study {topic}",
            'back': f"Learn more about {topic} for {difficulty}",
            'translation': "",
            'example': "",
            'tags': f"{topic}, {difficulty}",
            'difficulty': 3
        }

def parse_flashcard_response(response: str) -> dict:
    """Parse AI response into flashcard components"""
    try:
        lines = response.strip().split('\n')
        flashcard = {
            'front': '',
            'back': '',
            'translation': '',
            'example': '',
            'tags': '',
            'difficulty': 3
        }
        
        for line in lines:
            line = line.strip()
            if line.startswith('FRONT:'):
                flashcard['front'] = line.replace('FRONT:', '').strip()
            elif line.startswith('BACK:'):
                flashcard['back'] = line.replace('BACK:', '').strip()
            elif line.startswith('TRANSLATION:'):
                flashcard['translation'] = line.replace('TRANSLATION:', '').strip()
            elif line.startswith('EXAMPLE:'):
                flashcard['example'] = line.replace('EXAMPLE:', '').strip()
            elif line.startswith('TAGS:'):
                flashcard['tags'] = line.replace('TAGS:', '').strip()
            elif line.startswith('DIFFICULTY:'):
                try:
                    diff_text = line.replace('DIFFICULTY:', '').strip()
                    flashcard['difficulty'] = int(diff_text[0]) if diff_text[0].isdigit() else 3
                except:
                    flashcard['difficulty'] = 3
        
        return flashcard
    except Exception as e:
        logger.error(f"🔥 Failed to parse flashcard response: {e}")
        return {
            'front': 'Error generating card',
            'back': 'Please try again',
            'translation': '',
            'example': '',
            'tags': '',
            'difficulty': 3
        }