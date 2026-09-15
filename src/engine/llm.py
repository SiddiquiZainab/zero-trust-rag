import os
import requests
from typing import Optional, Dict, Any

class OllamaLLM:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: str = "llama3",
        temperature: float = 0.2
    ):
        # Fallback to local host if environment variable isn't set
        self.base_url = base_url or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model_name = model_name
        self.temperature = temperature
        self.api_url = f"{self.base_url}/api/generate"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Sends prompt to the Ollama REST API and returns generated response."""
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(self.api_url, json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to communicate with Ollama server at {self.base_url}: {str(e)}")

if __name__ == "__main__":
    # --- Quick Unit Test ---
    print("Testing connection to Ollama container...")
    llm = OllamaLLM()
    try:
        res = llm.generate(prompt="Reply with the text 'Ollama connectivity check OK'")
        print(f"LLM Response: {res}")
    except Exception as e:
        print(f"Test Failed: {e}")