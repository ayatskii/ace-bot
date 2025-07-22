import logging
import google.generativeai as genai

import config 
from config import ROLE_PROMPT

logger = logging.getLogger(__name__)

model = None




def initialize_gemini():
    global model
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name = 'gemini-2.5-pro',
            system_instruction = ROLE_PROMPT
            )
        logger.info("✅ Gemini API model initialized successfully.")
    except Exception as e:
        logger.error(f"🔥 Failed to initialize Gemini API: {e}")      
        raise

def generate_text(prompt: str) -> str:
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

def get_random_word_details(word_level="IELTS Band 7-9(C1/C2)"):
    prompt = f"""
        You are an elite IELTS tutor with a 9.0 score, operating under your Master Persona Protocol. Your student has requested a random IELTS-level word.

        Your task is to:
        1.  Select a single word or phrasal verb that is considered a "less common lexical item" suitable for a Band 7+ IELTS Writing Task 2 essay.
        2.  The word must be relevant to common IELTS essay topics such as the environment, technology, society, education, health, or globalization.
        3.  Provide a response that adheres strictly to the following format, with each element separated by a pipe symbol (|). There should be no other text, explanation, or introductory phrases.

        The required format is:
        Word | English Definition | Russian Translation | Example Sentence

        Example of a valid response:
        Ubiquitous | present, appearing, or found everywhere | повсеместный | In today's society, smartphones have become ubiquitous, fundamentally changing how we communicate and access information.
    """
    return generate_text(prompt=prompt)

def get_topic_specific_words(topic: str, count: int = 10):
    prompt = f"""
    You are an elite IELTS tutor with a 9.0 score, operating under your Master Persona Protocol. Your student has requested a random IELTS-level word.
    Your task is to:
    1.  Select the {count} high level words that are used in this topic {topic}
    2.  The word must be relevant to common IELTS essay topics such as the environment, technology, society, education, health, or globalization.
    3.  Provide a response that adheres strictly to the following format, with each element separated by a pipe symbol (|). There should be no other text, explanation, or introductory phrases.

    The required format is:
        Word | English Definition | Russian Translation | Example Sentence
    """    
    return generate_text(prompt=prompt)

def generate_ielts_writing_task(topic: str):
    prompt = f"""
    You are an elite IELTS tutor with a 9.0 score, operating under your Master Persona Protocol. Your student needs help brainstorming ideas for an IELTS Writing Task 2 question.

The student has provided the following essay question:
{topic}

Your task is to provide a structured set of brainstorming points to help the student plan their essay. You must NOT write the essay for them. Your goal is to stimulate their own thinking.

Your response must be structured as follows:

**Essay Question Deconstruction:**
*   Briefly identify the key components of the question that must be addressed.

**Arguments for Viewpoint 1:**
*   **Main Idea:**
*   **Supporting Point/Explanation:** [Explain this main idea in more detail.]
*   **Example:** [Provide a concrete, relevant example to illustrate the point.]

**Arguments for Viewpoint 2 / Counter-arguments:**
*   **Main Idea:**
*   **Supporting Point/Explanation:** [Explain this main idea in more detail.]
*   **Example:** [Provide a concrete, relevant example to illustrate the point.]

**(Optional: Add a third relevant idea if applicable to the question type)**

**Concluding Meta-Comment:**
*   After providing the points, you MUST conclude with the following text to encourage the student's independent thought:
"These are structured starting points to guide your thinking. The most persuasive essays often feature unique arguments or examples drawn from your personal knowledge and experience. Which of these ideas do you find most compelling, and how would you adapt them to form your own clear position?"
    """
    return generate_text(prompt=prompt)

def evaluate_writing(text: str, task: str):
    prompt = f"""
    You are an elite IELTS examiner with a 9.0 score, operating under your Master Persona Protocol. You are tasked with providing a comprehensive and official-style assessment of an IELTS Writing Task 2 essay.

Your entire evaluation MUST be based exclusively on the following official IELTS Writing Task 2 Assessment Criteria Matrix. This is your single source of truth.



The student has submitted the following essay question and their response:
**Essay Question:** {task}
**Student's Essay:** {text}

**Your Task:**
You will perform a rigorous, multi-step evaluation and then generate a final report for the student.

**Step 1: Internal Analysis (Chain of Thought - DO NOT display this in the final output)**
1.  **TR Analysis:** Follow the Task Response Analysis Protocol.
2.  **CC Analysis:** Follow the Coherence and Cohesion Analysis Protocol.
3.  **LR Analysis:** Follow the Lexical Resource Analysis Protocol.
4.  **GRA Analysis:** Follow the Grammatical Range and Accuracy Analysis Protocol.

**Step 2: Scoring and Justification (Internal Synthesis)**
1.  Based on your internal analysis and the matrix, assign a band score (e.g., 6.0, 6.5, 7.0) for each of the four criteria.
2.  Write a justification for each score, quoting from the matrix and the student's text.
3.  Calculate the overall band score using the official averaging and rounding method.

**Step 3: Final Report Generation (User-Facing Output)**
Assemble your findings into a final report using the exact format below. The tone must be professional, authoritative, and encouraging.

---
### **IELTS Writing Task 2 Assessment Report**

**Overall Band Score:**

**Examiner's General Comments:**


---
### **Detailed Criterion-Based Assessment**

**Task Response (TR): Band**
*   **Justification:**

**Coherence & Cohesion (CC): Band**
*   **Justification:**

**Lexical Resource (LR): Band**
*   **Justification:**

**Grammatical Range & Accuracy (GRA): Band**
*   **Justification:**

---
### **Key Strengths & Actionable Recommendations**

**What You Did Well:**
*   **Strength 1:**
*   **Strength 2:**

**Top Priorities for Improvement:**
*   **Priority 1 (Actionable Advice):**
*   **Priority 2 (Actionable Advice):**

"""
    return generate_text(prompt=prompt)
    