import os
import sys

# Load environmental variables
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key or api_key == "your_gemini_api_key_here":
    print("Error: GEMINI_API_KEY is not set or is still the default placeholder in .env.", file=sys.stderr)
    sys.exit(1)

try:
    from google import genai
except ImportError:
    print("Error: google-genai SDK is not installed.", file=sys.stderr)
    sys.exit(1)

def list_models():
    print("=== AVAILABLE GEMINI MODELS ===")
    try:
        client = genai.Client(api_key=api_key)
        
        # Call models.list() to get the list of models
        models = list(client.models.list())
        
        # Sort models by name
        models.sort(key=lambda m: m.name)
        
        for model in models:
            model_name = model.name
            display_name = getattr(model, "display_name", "N/A")
            supported_actions = getattr(model, "supported_actions", [])
            input_token_limit = getattr(model, "input_token_limit", "N/A")
            output_token_limit = getattr(model, "output_token_limit", "N/A")
            
            # Check if generateContent is supported
            supports_generate = "generateContent" in supported_actions or "generate_content" in [a.lower() for a in supported_actions]
            supports_generate_str = "YES" if supports_generate else "NO"
            
            print(f"MODEL NAME: {model_name}")
            print(f"DISPLAY NAME: {display_name}")
            print(f"SUPPORTED ACTIONS: {supported_actions}")
            print(f"SUPPORTED GENERATE CONTENT: {supports_generate_str}")
            print(f"INPUT TOKEN LIMIT: {input_token_limit}")
            print(f"OUTPUT TOKEN LIMIT: {output_token_limit}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error listing models: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    list_models()
