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