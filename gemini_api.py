import logging
import google.generativeai as genai

import config

logger = logging.getLogger(__name__)

model = None

def initialize_gemini():
    """Initializes the Gemini model with the API key and a system instruction."""
    global model
    try:
        generation_config = {"temperature": 0.9}
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction="You are an elite IELTS tutor and examiner with a 9.0 score. Your responses must be accurate, professional, and directly address the user's request without any unnecessary conversational text."
        )
        logger.info("✅ Gemini API model initialized successfully.")
    except Exception as e:
        logger.error(f"🔥 Failed to initialize Gemini API: {e}")
        raise

def generate_text(prompt: str) -> str:
    """Sends a prompt to the initialized Gemini model and returns the text response."""
    if not model:
        logger.error("🔥 Gemini model not initialized. Call initialize_gemini() first.")
        return "Error: The AI model is not available. Please contact the administrator."

    try:
        logger.info(f"➡️ Sending prompt to Gemini: '{prompt[:80]}...'")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"🔥 An error occurred while generating text with Gemini: {e}")
        return "Sorry, I encountered an error while processing your request."

def get_random_word_details(word_level="IELTS Band 7-9 (C1/C2)") -> str:
    """Generates a single, random, high-level vocabulary word."""
    prompt = f"""
    Generate one advanced English vocabulary word suitable for a {word_level} student, relevant to a common IELTS topic (e.g., environment, technology, society).

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

    **Your output must strictly follow this exact format with clear sections and proper spacing:**

    📊 IELTS WRITING ASSESSMENT REPORT

    🎯 Overall Band Score: [Your calculated score]

    📝 Examiner's General Comments:
    [Your brief summary of the essay's overall performance]

    ────────────────────────────────────────
    📋 DETAILED CRITERION-BASED ASSESSMENT
    ────────────────────────────────────────

    📌 Task Response (TR): Band [Score]
    💬 Justification: [Your detailed justification]

    📌 Coherence & Cohesion (CC): Band [Score]
    💬 Justification: [Your detailed justification]

    📌 Lexical Resource (LR): Band [Score]
    💬 Justification: [Your detailed justification]

    📌 Grammatical Range & Accuracy (GRA): Band [Score]
    💬 Justification: [Your detailed justification]

    ────────────────────────────────────────
    🎯 KEY STRENGTHS & ACTIONABLE RECOMMENDATIONS
    ────────────────────────────────────────

    ✅ What You Did Well:
    • [Strength 1]
    • [Strength 2]

    🔧 Top Priorities for Improvement:
    • [Priority 1 with actionable advice]
    • [Priority 2 with actionable advice]

    **Do not add any other text, explanations, or concluding phrases. Use only the format above.**
    """
    return generate_text(prompt)

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
    """Constructs a prompt for a fully formatted message with IELTS strategies."""
    section_name = section.strip().capitalize()
    
    # Create task-specific prompts
    task_prompts = {
        # Listening task types
        "truefalse": f"Create specific strategies for IELTS {section_name} True/False questions. Focus on identifying keywords, understanding synonyms, and recognizing when information is contradicted or not mentioned.",
        "multiplechoice": f"Create specific strategies for IELTS {section_name} Multiple Choice questions. Focus on reading all options before listening, identifying distractors, and understanding the exact meaning of each option.",
        "notes": f"Create specific strategies for IELTS {section_name} Note Completion tasks. Focus on predicting word types, listening for specific information, and understanding the structure of notes.",
        
        # Reading task types
        "shortanswer": f"Create specific strategies for IELTS {section_name} Short Answer questions. Focus on scanning for keywords, understanding question types, and writing concise answers within word limits.",
        "headings": f"Create specific strategies for IELTS {section_name} Matching Headings tasks. Focus on understanding main ideas, identifying topic sentences, and recognizing paragraph structure.",
        "summary": f"Create specific strategies for IELTS {section_name} Summary Completion tasks. Focus on understanding context, predicting word types, and maintaining grammatical accuracy."
    }
    
    # Get the specific prompt or use a general one
    specific_prompt = task_prompts.get(task_type, f"Create general strategies for IELTS {section_name} section")
    
    prompt = f"""
    {specific_prompt}

    **Your output must strictly follow this exact format with clear sections and proper spacing:**

    💡 TOP STRATEGIES FOR IELTS {section_name.upper()} - {task_type.replace('_', ' ').upper()}

    ────────────────────────────────────────
    🎯 ESSENTIAL STRATEGIES
    ────────────────────────────────────────

    1. 📌 [Strategy Name]
       💬 [Detailed explanation of the strategy with specific tips for this task type]

    2. 📌 [Strategy Name]
       💬 [Detailed explanation of the strategy with specific tips for this task type]

    3. 📌 [Strategy Name]
       💬 [Detailed explanation of the strategy with specific tips for this task type]

    4. 📌 [Strategy Name]
       💬 [Detailed explanation of the strategy with specific tips for this task type]

    5. 📌 [Strategy Name]
       💬 [Detailed explanation of the strategy with specific tips for this task type]

    **Do not add any concluding text or additional explanations. Use only the format above.**
    """
    return generate_text(prompt)

def explain_grammar_structure(grammar_topic: str) -> str:
    """Constructs a prompt to get a detailed explanation of a grammar topic."""
    prompt = f"""
    Explain the English grammar topic: "{grammar_topic}".

    **Your output must strictly follow this exact format with clear sections and proper spacing:**

    📖 GRAMMAR EXPLANATION: {grammar_topic.upper()}

    ────────────────────────────────────────
    📚 COMPREHENSIVE GUIDE
    ────────────────────────────────────────

    1. 📝 What it is:
       💬 [Simple, clear definition of the grammar structure]

    2. 🔧 How to Form It:
       💬 [Grammatical formula and structure with examples]

    3. 🎯 When to Use It:
       💬 [Key use cases and situations where this grammar is appropriate]

    4. 💡 Examples:
       • [First clear example sentence]
       • [Second clear example sentence]
       • [Third clear example sentence]

    ────────────────────────────────────────
    ⚠️ Common Mistakes to Avoid:
    ────────────────────────────────────────
    • [Common mistake 1]
    • [Common mistake 2]

    **Keep the explanation clear, concise, and practical for IELTS preparation. Do not add any concluding text.**
    """
    return generate_text(prompt)