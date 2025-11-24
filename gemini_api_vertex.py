import logging
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig
import time
import hashlib
import random
import os

import config

logger = logging.getLogger(__name__)

model = None
writing_model = None

# System instruction to be prepended to prompts
SYSTEM_INSTRUCTION = """You are an elite IELTS tutor and examiner with a 9.0 score. Your responses must be accurate, professional, and directly address the user's request without any unnecessary conversational text. When the user interface is in Russian, provide your responses in Russian as well."""

def initialize_gemini():
    """Initializes the Gemini models via Vertex AI with the configured project and region."""
    global model, writing_model
    try:
        # Initialize Vertex AI with project and region from config
        vertexai.init(
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_REGION
        )
        
        # Configure generation settings for flash model (general use)
        generation_config = GenerationConfig(
            temperature=0.9,
            top_p=0.95,
            top_k=50
        )
        
        # Initialize the general-purpose flash model
        model = GenerativeModel(
            model_name='gemini-2.0-flash-exp',
            generation_config=generation_config,
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        # Configure generation settings for pro model (writing evaluation)
        writing_config = GenerationConfig(
            temperature=0.7,
            top_p=0.8,
            top_k=40
        )
        
        # Initialize the writing-specific pro model
        writing_model = GenerativeModel(
            model_name='gemini-2.0-flash-exp',
            generation_config=writing_config,
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        logger.info(f"✅ Vertex AI Gemini models initialized successfully (Project: {config.GOOGLE_CLOUD_PROJECT}, Region: {config.GOOGLE_CLOUD_REGION})")
    except Exception as e:
        logger.error(f"🔥 Failed to initialize Vertex AI: {e}")
        raise


def generate_text_with_retry(prompt: str, max_retries: int = 3, base_delay: float = 1.0, **kwargs) -> str:
    """Sends a prompt to the initialized Gemini model with retry logic for empty responses."""
    if not model:
        logger.error("🔥 Gemini model not initialized. Call initialize_gemini() first.")
        return "Error: The AI model is not available. Please contact the administrator."

    for attempt in range(max_retries):
        try:
            logger.info(f"➡️ Sending prompt to Vertex AI Gemini (attempt {attempt + 1}/{max_retries}): '{prompt[:80]}...'")
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
            logger.error(f"🔥 An error occurred while generating text with Vertex AI (attempt {attempt + 1}): {e}")
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
            logger.info(f"➡️ Sending writing prompt to Vertex AI Gemini Pro (attempt {attempt + 1}/{max_retries}): '{prompt[:80]}...'")
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
            logger.error(f"🔥 An error occurred while generating writing text with Vertex AI (attempt {attempt + 1}): {e}")
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
