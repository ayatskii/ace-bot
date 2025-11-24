# migrate_to_vertex.py
# Script to migrate gemini_api.py from Gemini API to Vertex AI

def migrate_gemini_api():
    # Read the original file
    with open('gemini_api.py', 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    
    new_lines = []
    skip_until = -1
    
    for i, line in enumerate(lines):
        if i < skip_until:
            continue
            
        # Replace imports at the top
        if 'import google.generativeai as genai' in line:
            new_lines.append('import vertexai\n')
            new_lines.append('from vertexai.generative_models import GenerativeModel, GenerationConfig\n')
            continue
        
        # Replace the initialize_gemini function
        if 'def initialize_gemini():' in line and i < 50:
            # Skip the old function and write new one
            skip_until = find_next_function_start(lines, i+1)
            new_lines.extend(get_new_init_function())
            continue
        
        # Update log messages
        modified_line = line
        modified_line = modified_line.replace('Sending prompt to Gemini (attempt', 'Sending prompt to Vertex AI Gemini (attempt')
        modified_line = modified_line.replace('Sending writing prompt to Gemini Pro (attempt', 'Sending writing prompt to Vertex AI Gemini (attempt')
        modified_line = modified_line.replace('generating text with Gemini (attempt', 'generating text with Vertex AI (attempt')
        modified_line = modified_line.replace('generating writing text with Gemini Pro (attempt', 'generating writing text with Vertex AI (attempt')
        
        new_lines.append(modified_line)
    
    # Write the new file
    with open('gemini_api.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print('Migration completed successfully!')

def find_next_function_start(lines, start_idx):
    """Find the next function definition"""
    for i in range(start_idx, len(lines)):
        if lines[i].startswith('def '):
            return i
    return len(lines)

def get_new_init_function():
    """Return the new Vertex AI initialization function"""
    return [
        'def initialize_gemini():\n',
        '    """Initializes the Gemini models via Vertex AI with the configured project and region."""\n',
        '    global model, writing_model\n',
        '    try:\n',
        '        # Initialize Vertex AI with project and region from config\n',
        '        vertexai.init(\n',
        '            project=config.GOOGLE_CLOUD_PROJECT,\n',
        '            location=config.GOOGLE_CLOUD_REGION\n',
        '        )\n',
        '        \n',
        '        # Configure generation settings for flash model (general use)\n',
        '        generation_config = GenerationConfig(\n',
        '            temperature=0.9,\n',
        '            top_p=0.95,\n',
        '            top_k=50\n',
        '        )\n',
        '        \n',
        '        # Initialize the general-purpose flash model\n',
        '        model = GenerativeModel(\n',
        "            model_name='gemini-2.0-flash-exp',\n",
        '            generation_config=generation_config,\n',
        '            system_instruction=SYSTEM_INSTRUCTION\n',
        '        )\n',
        '        \n',
        '        # Configure generation settings for pro model (writing evaluation)\n',
        '        writing_config = GenerationConfig(\n',
        '            temperature=0.7,\n',
        '            top_p=0.8,\n',
        '            top_k=40\n',
        '        )\n',
        '        \n',
        '        # Initialize the writing-specific pro model\n',
        '        writing_model = GenerativeModel(\n',
        "            model_name='gemini-2.0-flash-exp',\n",
        '            generation_config=writing_config,\n',
        '            system_instruction=SYSTEM_INSTRUCTION\n',
        '        )\n',
        '        \n',
        '        logger.info(f"Vertex AI Gemini models initialized (Project: {config.GOOGLE_CLOUD_PROJECT}, Region: {config.GOOGLE_CLOUD_REGION})")\n',
        '    except Exception as e:\n',
        '        logger.error(f"Failed to initialize Vertex AI: {e}")\n',
        '        raise\n',
        '\n',
        '\n',
    ]

if __name__ == '__main__':
    migrate_gemini_api()
