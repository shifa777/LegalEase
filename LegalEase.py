import os
import time
import requests
from typing import Optional

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "legalease:latest")

SYSTEM_PROMPT = (
    "You are LegalEase, an AI legal assistant specialized in Indian laws. "
    "Always give clear, simple answers in plain text only — avoid Markdown or special symbols like (* # -). "
    "Whenever possible, include reliable source links or citations to Indian legal websites, government portals, or official court documents."
)



def ask_LegalEase(prompt: str, system_prompt: Optional[str] = None, max_retries: int = 3) -> str:
    url = f"{OLLAMA_HOST}/api/generate"

    # Send a plain prompt compatible with most Ollama models (no chat template tags)
    if system_prompt:
        formatted_prompt = f"{system_prompt}\n\n{prompt}"
    else:
        formatted_prompt = prompt

    payload = {
        "model": MODEL,
        "prompt": formatted_prompt,
        "stream": False,
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            # Use a session with keep-alive for better connection reuse
            resp = requests.post(url, json=payload, timeout=120)  # 2 minutes - enough time for model to load
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except requests.exceptions.Timeout:
            last_error = "Request timed out. The model may be loading for the first time or the query is too complex."
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"[OLLAMA] Timeout on attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
        except requests.exceptions.ConnectionError:
            last_error = "Cannot connect to Ollama. Please ensure Ollama is running with 'ollama serve' or 'ollama run legalease:latest'."
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[OLLAMA] Connection error on attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
        except requests.exceptions.HTTPError as e:
            # Handle 500 errors with retry
            if e.response.status_code >= 500:
                last_error = f"Ollama server error (HTTP {e.response.status_code}). The model may be overloaded or starting up."
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"[OLLAMA] Server error on attempt {attempt + 1}/{max_retries}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            last_error = str(e)
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[OLLAMA] Error on attempt {attempt + 1}/{max_retries}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
        
        # If we get here without returning, break out of retry loop
        break
    
    # All retries exhausted
    return f"Error contacting Ollama after {max_retries} attempts: {last_error}"
