"""
ai/generator.py — AI-powered birthday message generation using Groq.

Uses the groq SDK (OpenAI-compatible) with llama-3.3-70b-versatile.
Falls back to a warm hardcoded message if Groq fails or times out.

Model priority: llama-3.3-70b-versatile → llama3-70b-8192 → hardcoded fallback.
"""

from groq import Groq

from config import GROQ_API_KEY
from utils.logger import log_event

# Groq client — initialised once at module load
_client = Groq(api_key=GROQ_API_KEY)

# Model priority list — first working model wins
_MODELS = [
    "llama-3.3-70b-versatile",   # Best quality, Groq free tier
    "llama3-70b-8192",           # Fallback if above is unavailable
    "llama3-8b-8192",            # Lighter fallback
]

# ---------------------------------------------------------------------------
# Prompt template — edit this to change the AI's writing style
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """You are writing a warm, personalised birthday message on behalf of Accenture.

Employee name: {name}
Role / Title: {role}
Department: {department}
Fun facts and notes from their manager: {fun_facts}
Manager's personal message: {personal_message}

Write a birthday message (3-5 sentences) that:
- Feels warm, genuine and personal — not generic or corporate
- References at least one specific detail from the fun facts if provided
- Acknowledges their role and contribution to the team (use the role/title if provided, otherwise keep it general)
- Ends with warm wishes for the year ahead
- Is appropriate for a professional workplace
- Does not start with "Dear" or "Hi" — jump straight into the message
- Does NOT mention any specific technical field or domain unless the fun facts explicitly mention it

Return only the message paragraph, nothing else."""

# ---------------------------------------------------------------------------
# Fallback message — used when Groq is unavailable
# ---------------------------------------------------------------------------

_FALLBACK_TEMPLATE = (
    "Today is a very special day — it's {name}'s birthday! "
    "The whole team at Accenture is thinking of you and celebrating everything "
    "that makes you such an incredible colleague. "
    "Your dedication and the energy you bring to {department} every day are truly valued. "
    "Here's to an amazing year ahead filled with joy, growth, and all the things "
    "that make you smile. Happy Birthday, {name}! 🎉"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_birthday_message(
    name: str,
    department: str,
    fun_facts: str,
    personal_message: str,
    role: str = "",
) -> str:
    """
    Generate a personalised birthday message using Groq (Llama 3).

    If Groq fails (network error, rate limit, timeout, etc.), returns
    a warm hardcoded fallback message that still includes the employee's name.

    Args:
        name:             Employee's display name.
        department:       Employee's department or cost centre.
        fun_facts:        Manager-provided fun facts (free text).
        personal_message: Manager's personal message to the employee.
        role:             Employee's role/title as provided by their manager.

    Returns:
        A 3–5 sentence birthday message string.
    """
    prompt = PROMPT_TEMPLATE.format(
        name=name,
        role=role or "Team Member",
        department=department or "the team",
        fun_facts=fun_facts or "No specific facts provided.",
        personal_message=personal_message or "No personal message provided.",
    )

    last_exc = None
    message = None

    for model_name in _MODELS:
        try:
            response = _client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a warm, empathetic writer who crafts personalised birthday messages for Accenture employees.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=300,
            )
            message = response.choices[0].message.content.strip()
            if message:
                log_event(
                    "INFO",
                    "ai_message_generated",
                    detail=f"employee={name}, model={model_name}, chars={len(message)}, message={message}",
                )
                return message
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue  # Try next model

    # All models failed — use hardcoded fallback
    fallback_message = _FALLBACK_TEMPLATE.format(
        name=name,
        department=department or "the team",
    )
    log_event(
        "WARNING",
        "ai_message_fallback",
        detail=f"employee={name}, reason={last_exc}, message={fallback_message}",
    )
    return fallback_message
