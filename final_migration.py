# final_migration.py
# Complete migration script from Gemini API to Vertex AI

def migrate():
    with open('gemini_api.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace import
    content = content.replace(
        'import google.generativeai as genai',
        'import vertexai\\nfrom vertexai.generative_models import GenerativeModel, GenerationConfig'
    )

    # Replace initialization
    content = content.replace(
        '''genai.configure(api_key=config.GEMINI_API_KEY)
        
        generation_config = genai.GenerationConfig(''',
        '''vertexai.init(project=config.GOOGLE_CLOUD_PROJECT, location=config.GOOGLE_CLOUD_REGION)
        
        generation_config = GenerationConfig('''
    )

    # Replace model classes
    content = content.replace('genai.GenerativeModel', 'GenerativeModel')
    content = content.replace('genai.GenerationConfig', 'GenerationConfig')

    # Update model initialization with system instruction
    content = content.replace(
        """model = GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config=generation_config
        )""",
        """model = GenerativeModel(
            model_name='gemini-2.0-flash-exp',
            generation_config=generation_config,
            system_instruction=SYSTEM_INSTRUCTION
        )"""
    )

    content = content.replace(
        """writing_model = GenerativeModel(
            model_name='gemini-2.5-pro',
            generation_config=writing_config
        )""",
        """writing_model = GenerativeModel(
            model_name='gemini-2.0-flash-exp',
            generation_config=writing_config,
            system_instruction=SYSTEM_INSTRUCTION
        )"""
    )

    # Update log messages - DO NOT reference config here, use string templates
    content = content.replace(
        '"Gemini API models initialized successfully."',
        'f"Vertex AI models initialized (Project: {config.GOOGLE_CLOUD_PROJECT}, Region: {config.GOOGLE_CLOUD_REGION})"'
    )

    content = content.replace('Failed to initialize Gemini API', 'Failed to initialize Vertex AI')
    content = content.replace('Sending prompt to Gemini (attempt', 'Sending prompt to Vertex AI Gemini (attempt')
    content = content.replace('Sending writing prompt to Gemini Pro (attempt', 'Sending writing prompt to Vertex AI (attempt')
    content = content.replace('generating text with Gemini (attempt', 'generating text with Vertex AI (attempt')
    content = content.replace('generating writing text with Gemini Pro (attempt', 'generating writing text with Vertex AI (attempt')

    with open('gemini_api.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print('Migration completed successfully!')

if __name__ == '__main__':
    migrate()
