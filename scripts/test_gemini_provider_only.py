import os
import sys
import time
import warnings
from dotenv import load_dotenv

# Suppress the SDK's automatic function calling warning
warnings.filterwarnings("ignore", message=".*automatic function calling.*")

# Load environmental variables
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("LLM_MODEL") or "gemini-3.7-flash"

if not api_key or api_key == "your_gemini_api_key_here":
    print("Error: GEMINI_API_KEY is not set or is still the default placeholder in .env.", file=sys.stderr)
    sys.exit(1)

try:
    from google import genai
    from google.genai import types
    sdk_version = getattr(genai, "__version__", "unknown")
except ImportError:
    print("Error: google-genai SDK is not installed.", file=sys.stderr)
    sys.exit(1)

def run_smoke_test():
    print("=== GEMINI PROVIDER SMOKE TEST ===")
    print(f"SDK VERSION: {sdk_version}")
    print(f"MODEL: {model_name}")
    
    # Check if Vertex or API key Developer API mode
    api_mode = "Vertex AI" if "cloud.google.com" in os.getenv("GEMINI_API_ENDPOINT", "") else "Gemini Developer API"
    print(f"API MODE: {api_mode}")

    start_time = time.time()
    request_status = "SUCCESS"
    response_text = ""
    input_tokens = "N/A"
    output_tokens = "N/A"
    total_tokens = "N/A"
    latency = "0.0"
    error_type = "None"
    error_message = "None"

    try:
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model=model_name,
            contents="Reply with exactly: GEMINI_SMOKE_TEST_OK",
            config=types.GenerateContentConfig(
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
        )
        
        latency = f"{round(time.time() - start_time, 4)}s"
        
        # Extract text response safely
        response_text = response.text
        if response_text is None and response.candidates:
            cand = response.candidates[0]
            if cand.content and cand.content.parts:
                parts = [p.text for p in cand.content.parts if p.text is not None]
                if parts:
                    response_text = "".join(parts)
        
        response_text = response_text.strip() if response_text else ""
        
        # Token usage metadata
        usage = getattr(response, "usage_metadata", None)
        if usage:
            input_tokens = str(usage.prompt_token_count)
            output_tokens = str(usage.candidates_token_count)
            total_tokens = str(usage.total_token_count)

    except Exception as e:
        request_status = "FAILED"
        latency = f"{round(time.time() - start_time, 4)}s"
        error_type = type(e).__name__
        error_message = str(e)

    print(f"REQUEST STATUS: {request_status}")
    print(f"RESPONSE: {response_text}")
    print(f"INPUT TOKENS: {input_tokens}")
    print(f"OUTPUT TOKENS: {output_tokens}")
    print(f"TOTAL TOKENS: {total_tokens}")
    print(f"LATENCY: {latency}")
    print(f"ERROR TYPE: {error_type}")
    print(f"ERROR MESSAGE: {error_message}")
    print("=" * 34)

if __name__ == "__main__":
    run_smoke_test()
