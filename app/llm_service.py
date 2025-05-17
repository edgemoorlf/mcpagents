from typing import Optional, AsyncGenerator, Dict, List
import os
from openai import AsyncOpenAI, OpenAI
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

class LLMService:
    def __init__(self):
        """Initialize the LLM service with configuration from environment variables."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-2024-11-20")
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "8000"))
        self.base_url = os.getenv("OPENAI_BASE_URL")
        
        # Prepare kwargs for OpenAI clients
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        # Initialize both sync and async clients
        self.client = OpenAI(**client_kwargs)
        self.async_client = AsyncOpenAI(**client_kwargs)

    def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion using the LLM API synchronously via HTTP POST.
        """
        url = self.base_url.rstrip('/') + "/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Error in LLM completion: {str(e)}")
            return None

    async def generate_completion_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a completion using the OpenAI API with streaming support.
        
        Args:
            system_prompt: The system message to set the context
            user_prompt: The user's input prompt
            temperature: Optional override for the default temperature
            max_tokens: Optional override for the default max_tokens
            
        Yields:
            Chunks of the generated text response
        """
        try:
            stream = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"Error in LLM streaming: {str(e)}")
            yield None

# Create a singleton instance
llm_service = LLMService() 