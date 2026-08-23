import os
import sys
import warnings
from dotenv import load_dotenv

# Suppress the SDK's automatic function calling warning
warnings.filterwarnings("ignore", message=".*automatic function calling.*")

# Ensure we load local .env variables
load_dotenv()

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("LLM_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.7-flash"
    
    if not api_key or api_key == "your_gemini_api_key_here":
        print("Error: GEMINI_API_KEY is not set or is still the default placeholder in .env.", file=sys.stderr)
        sys.exit(1)
        
    print("Initializing official google-genai Client...")
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("Error: google-genai SDK is not installed.", file=sys.stderr)
        sys.exit(1)
        
    try:
        # Never print the API key directly
        client = genai.Client(api_key=api_key)
        print(f"Sending test request using model: {model_name}...")
        
        response = client.models.generate_content(
            model=model_name,
            contents="Reply with exactly: ParcelPilot Gemini connection OK",
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
        )
        
        text = response.text
        if text is None and response.candidates:
            cand = response.candidates[0]
            if cand.content and cand.content.parts:
                parts = [p.text for p in cand.content.parts if p.text is not None]
                if parts:
                    text = "".join(parts)
        
        if text is not None:
            answer = text.strip()
            print("Gemini connection successful.")
            print(f"Model response: {answer}")
            sys.exit(0)
        else:
            print("Error: Received response with no text content.", file=sys.stderr)
            if response.candidates:
                candidate = response.candidates[0]
                print(f"Finish Reason: {candidate.finish_reason}", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        err_str = str(e)
        if "503" in err_str or "unavailable" in err_str.lower() or "overloaded" in err_str.lower() or "high demand" in err_str.lower():
            print("Gemini connection unavailable: model temporarily overloaded")
            print("HTTP status: 503")
            print(f"Model: {model_name}")
            sys.exit(0)
        else:
            print(f"Error during connection test: {err_str}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
