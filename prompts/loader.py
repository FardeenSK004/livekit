"""Prompt loading and dynamic variable interpolation."""

import datetime
import os
from typing import Optional, List, Dict, Any

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_prompt_template(filename: str) -> str:
    """Load raw markdown prompt template from prompts directory."""
    path = os.path.join(_PROMPTS_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def build_system_prompt(
    is_inbound: bool = False,
    custom_prompt: Optional[str] = None,
    client_name: str = "User",
    appointment_data: Optional[Dict[str, Any]] = None,
    stage_details: Optional[List[Dict[str, Any]]] = None,
    process_stage_data: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Assemble complete system prompt instructions with live calendar dates and context."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    current_year = now_utc.year
    current_date_str = now_utc.strftime("%A, %B %d, %Y")
    current_time_str = now_utc.strftime("%I:%M %p UTC")

    template_file = "system_inbound.md" if is_inbound else "system_outbound.md"
    base_instructions = load_prompt_template(template_file)

    # Dynamic date/time injection
    time_context = f"""
LIVE DATE & TIME (CURRENT CALENDAR YEAR: {current_year}):
- Current Date: {current_date_str}
- Current Time: {current_time_str}
- When calculating relative dates (today, tomorrow, next week), calculate strictly from the CURRENT DATE ({current_date_str}).
"""

    prompt = f"{base_instructions}\n\n{time_context}\n\nFollow these specific instructions:\n"

    if custom_prompt:
        prompt += f"\n{custom_prompt}\n"

    if not is_inbound and client_name and client_name.lower() != "user":
        prompt += f"\n- The user's name is {client_name}. Greet them by name.\n"

    if appointment_data:
        prompt += f"\nAPPOINTMENT DETAILS:\n{appointment_data}\n"

    if stage_details:
        prompt += f"\nAVAILABLE CRM STAGES:\n{stage_details}\n"

    return prompt
