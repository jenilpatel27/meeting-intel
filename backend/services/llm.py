# backend/services/llm.py
import os
import json
import re
import time
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()


def get_llm():
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.2,
        max_output_tokens=8192,    # Allow long responses
        max_retries=2,             # LangChain built-in retry
    )


def run_prompt(system: str, user: str) -> str:
    """
    Run a simple prompt and return the AI's text response.
    Uses SystemMessage and HumanMessage directly to avoid
    LangChain's curly brace conflict with JSON in prompts.
    Retries automatically if rate limited.
    """
    llm = get_llm()

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user),
    ]

    for attempt in range(3):
        try:
            result = llm.invoke(messages)
            return result.content

        except Exception as e:
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Try to extract the wait time Gemini tells us
                wait_match = re.search(r'retryDelay.*?(\d+)s', error_str)
                wait = int(wait_match.group(1)) + 5 if wait_match else 65

                print(f"⏳ Rate limited. Waiting {wait} seconds (attempt {attempt + 1}/3)...")
                time.sleep(wait)

                if attempt == 2:
                    raise Exception(
                        f"Gemini API rate limit hit 3 times in a row. "
                        f"Please wait a few minutes and try again.\n"
                        f"Original error: {error_str[:300]}"
                    )
            else:
                # Not a rate limit error — raise immediately
                raise


def run_json_prompt(system: str, user: str) -> dict:
    """
    Run a prompt that MUST return JSON.
    - Uses messages directly (no ChatPromptTemplate) to avoid curly brace issues
    - Strips markdown fences if AI adds them
    - Retries on rate limit with the exact wait time Gemini specifies
    - Reads the FULL input — no trimming
    """
    llm = get_llm()

    full_system = (
        system
        + "\n\nCRITICAL INSTRUCTION: Return ONLY valid JSON. "
        + "No markdown. No code fences. No explanation before or after. "
        + "Just the raw JSON object or array."
    )

    messages = [
        SystemMessage(content=full_system),
        HumanMessage(content=user),
    ]

    for attempt in range(3):
        try:
            result = llm.invoke(messages)
            text = result.content.strip()

            # Strip markdown code fences if AI added them anyway
            text = re.sub(r'^```json\s*\n?', '', text)
            text = re.sub(r'^```\s*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
            text = text.strip()

            return json.loads(text)

        except json.JSONDecodeError as e:
            raise ValueError(
                f"AI returned invalid JSON.\n"
                f"Parse error: {e}\n"
                f"Raw response was:\n{text[:500]}"
            )

        except Exception as e:
            error_str = str(e)

            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Extract exact wait time from Gemini's error message
                wait_match = re.search(r'retryDelay.*?(\d+)s', error_str)
                wait = int(wait_match.group(1)) + 5 if wait_match else 65

                print(f"⏳ Rate limited. Waiting {wait} seconds (attempt {attempt + 1}/3)...")
                time.sleep(wait)

                if attempt == 2:
                    raise Exception(
                        f"Gemini API rate limit hit 3 times in a row. "
                        f"Please wait a few minutes and try again.\n"
                        f"Original error: {error_str[:300]}"
                    )
            else:
                raise