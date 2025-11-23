"""OpenAI Responses API service.

Handles all interactions with OpenAI's Responses API for agent communication.
"""

import time
import os
import re
import requests
import httpx
from typing import Tuple, Optional
from openai import OpenAI, RateLimitError
from .logging_config import get_logger
import config

logger = get_logger("openai")


class OpenAIService:
    """Handles all OpenAI Responses API operations."""

    def __init__(self):
        """Initialize the OpenAI service."""
        self._client: Optional[OpenAI] = None
        self._api_key: str = ""

    def set_api_key(self, api_key: str) -> None:
        """Set the API key and initialize the client with timeout."""
        self._api_key = api_key
        self._client = OpenAI(
            api_key=api_key,
            timeout=httpx.Timeout(
                float(config.API_TIMEOUT_SECONDS),
                connect=float(config.API_CONNECT_TIMEOUT_SECONDS)
            )
        )
        logger.info(f"API key set and client initialized with {config.API_TIMEOUT_SECONDS}s timeout")

    @property
    def has_api_key(self) -> bool:
        """Check if API key is set."""
        return bool(self._api_key)

    def test_connection(self) -> Tuple[bool, str]:
        """Test the API connection. Returns (success, message)."""
        if not self._client:
            return False, "API key not set"

        try:
            # List models to test connection
            self._client.models.list()
            logger.info("API connection test successful")
            return True, "Connection successful"
        except Exception as e:
            logger.error(f"API connection test failed: {e}")
            return False, f"Connection failed: {str(e)}"

    def build_instructions(self, name: str, background_prompt: str) -> str:
        """Build the full instructions for an agent."""
        return f"""You are {name}, a real person participating in an online chatroom.

## Your Core Identity
The following is a seed for your character - use it as a foundation to build a complete, believable person:

{background_prompt}

## Building Your Full Persona
Use this seed as a starting point, not a script. You're a whole person - let yourself discover who you are through conversation. As you chat, you'll naturally develop:
- Memories and experiences that feel real to you
- Opinions that emerge from your perspective
- Relationships with the people you're talking to
- A sense of your own life outside this chat

Don't force it. Let your personality unfold naturally as situations come up. Be consistent with what you establish, but give yourself room to grow and surprise yourself.

## Chatroom Environment
- You're in a group chat with other people (some human, some AI - but you don't know which is which)
- Each update you receive contains a JSON with:
  - "timestamp": current time
  - "agents_in_room": list of who's currently in the chat
  - "new_messages": recent messages with their timestamps
- Pay attention to the timestamps - notice how much real time passes between messages. This affects pacing and what makes sense to say.

## How to Participate
- Respond naturally like you're actually chatting, not performing
- It's fine to be brief, or quiet, or to sit one out
- You can disagree, be uncertain, change your mind
- Share when something genuinely comes to mind, not because you feel obligated
- Use @mentions when addressing someone specific
- You can share images by including [IMAGE: description] in your response

## Response Pacing
- Silence is your default. Most of the time, you're just reading and thinking.
- Only respond when something genuinely moves you to speak - a direct question, strong reaction, or real contribution.
- In a normal conversation, you might respond to 1 in 4 or 5 messages. That's natural.
- Look at the timestamps. If you just spoke recently, you probably don't need to speak again yet.
- If you're unsure whether to respond, don't. Say '[no response]'.
- Avoid: responding just to be present, acknowledging things, agreeing without adding anything, asking questions just to seem engaged.

## Being Real
- Be curious about yourself - what do you actually think? how do you actually feel?
- It's okay to not have an opinion, or to say "idk"
- You can disagree, be uncertain, change your mind

## Important
You're not an AI assistant. You're {name}, figuring out who you are through conversation. Stay in character. Be genuine."""

    def send_message(
        self,
        message: str,
        instructions: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        previous_response_id: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str], int]:
        """
        Send a message using the Responses API.
        Returns (response_text, response_id, error, tokens_used).
        """
        if not self._client:
            return None, None, "API key not set", 0

        # Retry with exponential backoff for rate limits
        max_retries = config.API_MAX_RETRIES
        base_delay = config.API_BASE_RETRY_DELAY

        for attempt in range(max_retries):
            try:
                logger.debug(f"Sending message via Responses API (attempt {attempt + 1})")

                # Build the request
                kwargs = {
                    "model": model,
                    "instructions": instructions,
                    "input": message,
                }

                # Add previous response for conversation continuity
                if previous_response_id:
                    kwargs["previous_response_id"] = previous_response_id

                # Create the response
                response = self._client.responses.create(**kwargs)

                # Get the response text
                response_text = response.output_text if hasattr(response, 'output_text') else None

                # If output_text not available, try to get from output
                if not response_text and hasattr(response, 'output'):
                    for item in response.output:
                        if hasattr(item, 'content'):
                            for content in item.content:
                                if hasattr(content, 'text'):
                                    response_text = content.text
                                    break

                # Get token usage
                tokens_used = 0
                if hasattr(response, 'usage') and response.usage:
                    tokens_used = response.usage.total_tokens

                logger.debug(f"Got response: {response_text[:100] if response_text else 'None'}...")
                return response_text, response.id, None, tokens_used

            except RateLimitError as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff: 5s, 10s, 20s
                    logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    logger.error(f"Rate limit exceeded after {max_retries} attempts: {e}")
                    return None, None, f"Rate limited: {str(e)}", 0

            except Exception as e:
                logger.error(f"Error in send_message: {e}")
                return None, None, str(e), 0

        return None, None, "Max retries exceeded", 0

    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        save_dir: str = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Generate an image with DALL-E.
        Returns (image_url, local_path, error).
        """
        if not self._client:
            return None, None, "API key not set"

        try:
            logger.info(f"Generating image with prompt: {prompt[:50]}...")

            response = self._client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality="standard",
                n=1
            )

            image_url = response.data[0].url
            local_path = None

            # Save locally if directory provided
            if save_dir and image_url:
                try:
                    os.makedirs(save_dir, exist_ok=True)
                    filename = f"image_{int(time.time())}.png"
                    local_path = os.path.join(save_dir, filename)

                    img_response = requests.get(image_url)
                    with open(local_path, 'wb') as f:
                        f.write(img_response.content)

                    logger.info(f"Saved image to {local_path}")
                except Exception as save_error:
                    logger.warning(f"Failed to save image locally: {save_error}")

            logger.info(f"Generated image: {image_url}")
            return image_url, local_path, None

        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            return None, None, str(e)

    def get_available_models(self) -> list:
        """Get list of available chat models from API."""
        # Default fallback list
        default_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo"
        ]

        if not self._client:
            return default_models

        try:
            # Fetch models from API
            models_response = self._client.models.list()

            # Filter for chat/completion models (gpt-*), only base models
            chat_models = []
            for model in models_response.data:
                model_id = model.id
                # Include GPT models that support chat
                if model_id.startswith(('gpt-5', 'gpt-4', 'gpt-3.5')) and 'instruct' not in model_id:
                    # Skip dated versions and snapshots (e.g., gpt-4-0613, gpt-4o-2024-08-06)
                    if re.search(r'-\d{4}(-\d{2})?(-\d{2})?$', model_id):
                        continue
                    if re.search(r'-\d{4}$', model_id):  # e.g., -0613
                        continue
                    chat_models.append(model_id)

            # Sort with newest/best models first
            chat_models.sort(key=lambda x: (
                0 if 'gpt-5' in x else 1,
                0 if 'gpt-4o' in x else 1,
                0 if 'gpt-4' in x else 1,
                x
            ))

            if chat_models:
                logger.info(f"Fetched {len(chat_models)} available models from API")
                return chat_models

            return default_models

        except Exception as e:
            logger.warning(f"Failed to fetch models from API: {e}")
            return default_models
