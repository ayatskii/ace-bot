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

    The output must strictly adhere to the following format, with each element separated by a pipe symbol (|):
    Word | English Definition | Russian Translation | Example Sentence

    **Do not include any other text, explanations, or introductory phrases.**
    """
    return generate_text(prompt)

def get_topic_specific_words(topic: str, count: int = 10) -> str:
    """Generates a list of topic-specific vocabulary words."""
    prompt = f"""
    List {count} essential, high-level vocabulary words related to the IELTS topic "{topic}".
    For each word, provide its English definition, Russian translation, and an example sentence.

    The output must be a numbered list. Each item must strictly adhere to the following format, with each element separated by a pipe symbol (|):
    Word | English Definition | Russian Translation | Example Sentence

    **Do not include any other text, explanations, or introductory phrases.**
    """
    return generate_text(prompt)

def generate_ielts_writing_task(task_type: str, topic: str) -> str:
    """Generates a realistic IELTS Writing Task prompt with a strict format."""
    if "task 1" in task_type.lower():
        prompt = f"""
        Generate one IELTS Academic Writing Task 1 prompt related to the topic of "{topic}".
        The prompt must describe a visual data representation (like a chart, graph, or diagram).

        **The output must only be the text prompt itself, starting with a description of the visual and ending with the standard instruction to summarize it. Do not include any other text.**
        """
    else: # Default to Task 2
        prompt = f"""
        Generate one IELTS Writing Task 2 essay question on the topic of "{topic}".
        The question should present a clear argument, problem, or discussion point.

        **The output must only be the essay question itself, ending with the standard instruction to write at least 250 words. Do not include any other text.**
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

    **Your output must strictly follow the format below. Do not add any conversational text or explanations outside of this structure. Do not use any special characters like asterisks (*) or underscores (_) for formatting.**

    IELTS Writing Task 2 Assessment Report

    Overall Band Score: [Your calculated score]

    Examiner's General Comments:
    [Your brief summary]

    ---
    Detailed Criterion-Based Assessment

    Task Response (TR): Band [Score]
    Justification: [Your justification]

    Coherence & Cohesion (CC): Band [Score]
    Justification: [Your justification]

    Lexical Resource (LR): Band [Score]
    Justification: [Your justification]

    Grammatical Range & Accuracy (GRA): Band [Score]
    Justification: [Your justification]

    ---
    Key Strengths & Actionable Recommendations

    What You Did Well:
    - [Strength 1]
    - [Strength 2]

    Top Priorities for Improvement:
    - [Priority 1 with actionable advice]
    - [Priority 2 with actionable advice]
    """
    return generate_text(prompt)

def generate_speaking_question(part: str, topic: str = "a common topic") -> str:
    """Constructs a strict prompt to generate only the IELTS speaking questions."""
    if "part 2" in part.lower():
        prompt = f"""
        Generate one IELTS Speaking Part 2 cue card on the topic of "{topic}".
        **The output must *only* be the text for the cue card itself, starting with "Describe..." and including the bullet points. Do not add any other text.**
        """
    elif "part 3" in part.lower():
        prompt = f"""
        Generate exactly 3-4 IELTS Speaking Part 3 discussion questions related to the topic of "{topic}".
        **The output must be a numbered list containing only the questions. Do not provide any introductory or concluding text.**
        """
    else: # Default to Part 1
        prompt = f"""
        Generate exactly 3-4 IELTS Speaking Part 1 questions on the topic of "{topic}".
        **The output must be a numbered list containing only the questions. Do not include any explanation or preamble.**
        """
    return generate_text(prompt)

def generate_ielts_strategies(section: str) -> str:
    """Constructs a prompt for a fully formatted message with IELTS strategies."""
    section_name = section.strip().capitalize()
    prompt = f"""
    Create a complete message providing the top 3-5 strategies for the IELTS {section_name} section.

    **The message must start with the title "💡 Top Strategies for IELTS {section_name}" and contain nothing before it. After the strategies, do not add any concluding text.**
    The strategies should be a numbered list, with each point having its own heading. Use plain text formatting - do not use any special characters like asterisks (*) or underscores (_) for formatting.
    
    Format each strategy as:
    1. Strategy Name
    [Detailed explanation of the strategy]
    
    Keep the content informative and practical for IELTS preparation.
    """
    return generate_text(prompt)

def explain_grammar_structure(grammar_topic: str) -> str:
    """Constructs a prompt to get a detailed explanation of a grammar topic."""
    prompt = f"""
    Explain the English grammar topic: "{grammar_topic}".

    **Your output must strictly follow the structure below, using plain text. Do not add any conversational text before or after the structured explanation. Do not use any special characters like asterisks (*) or underscores (_) for formatting.**

    1. What it is: [Simple definition]
    2. How to Form It: [Grammatical formula]
    3. When to Use It: [Key use cases]
    4. Examples: [At least three clear example sentences]
    
    Keep the explanation clear, concise, and practical for IELTS preparation.
    """
    return generate_text(prompt)