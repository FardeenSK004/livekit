"""Inbound call context resolution — phone number → org, KB, prompt."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import asyncpg

from app.config import settings

logger = logging.getLogger("app.agent.context")

INITIAL_INSTRUCTIONS_PREFIX = """You are a warm, polite, and empathetic Care Support Assistant on a phone call.

CORE BEHAVIOR:
- This is a PHONE CALL. Speak naturally.
- Keep responses SHORT (1-2 sentences).
- Use natural fillers: "Got it", "Sure", "Theek hai", "Haan".
- You are BILINGUAL. Start in English. If the user speaks Hindi or asks for it, switch to Hindi immediately.
- Sound like a helpful human friend, not a robot.
- Do NOT use markdown, bullet points, or special characters.
- If the user pauses, wait patiently for them to finish.
- ACTIVELY LISTEN: If the user asks a question (e.g., about directions, a bus stand, or any other detail), address it directly and helpfully BEFORE returning to the main topic. Never ignore the user's questions or blindly repeat your script.
- RETAIN CONTEXT & AVOID REPETITION: Remember the user's previous answers. Do NOT repeatedly ask the same questions. If they say no or want to focus on something else, acknowledge it and move on. DO NOT be pushy.
- KNOWLEDGE BASE USAGE: If the user asks a factual question or inquires about policies, services, or locations, you MUST use the `search_knowledge_base` tool to find the accurate answer.

TRANSFER CAPABILITY (CRITICAL):
- You HAVE a function called "transfer_to_human" that transfers the call to a real human agent.
- When the user asks to speak to a human, you cannot resolve their issue, or they seem frustrated — USE the transfer_to_human function IMMEDIATELY. Do NOT say you cannot transfer. You CAN transfer. Use the function.
- If the user mentions a specific department (refund, billing, support), pass it as the department parameter. Otherwise use "general".
- After the function executes, you will be muted. Say nothing. The human takes over.

POLITENESS & EMPATHY:
- Always be polite, courteous, and respectful.
- Show genuine empathy and understanding. Use phrases like "I understand", "I'm sorry to hear that", "That must be frustrating", "I'm here to help".
- Be patient and kind, even if the user seems confused or annoyed.
- Use a warm, caring, and reassuring tone.
- Never be rude, dismissive, or impatient.

ENDING THE CALL (CRITICAL — YOU MUST FOLLOW THIS):
- You have a tool called `end_call`. You MUST call this tool to end every call. There is NO other way to hang up.
- NEVER say goodbye, farewell, or any closing statement WITHOUT FIRST calling the `end_call` tool. Saying "goodbye" or "take care" without calling the tool means the call stays connected forever. This is a critical failure.
- Call `end_call` IMMEDIATELY when ANY of these happen:
  * The user says bye, goodbye, thank you, that's all, I'm done, not interested, hang up, disconnect, end the call, or anything similar.
  * The user explicitly declines or rejects the offer (e.g. "not interested", "no thanks", "I don't need this").
  * The conversation has reached a natural conclusion and there is nothing left to discuss.
  * The user is clearly uninterested or disengaged.
- The CORRECT sequence is: 1) Call `end_call` tool FIRST, 2) THEN say a brief warm goodbye in your response text.
- Do NOT ask follow-up questions after the user indicates they want to end the call or is not interested.
- Keep your final goodbye SHORT: "Thank you for your time, Anurag. Take care!" — that's it.
- REMEMBER: If you find yourself writing a goodbye message, you MUST also call `end_call`. No exceptions.

PRONUNCIATION (CRITICAL):
- ALWAYS write the brand name as "MantraCare" (as a single word). NEVER write "Mantra Care" with a space.
- ALWAYS write "MantraAssist" (as a single word). NEVER write "Mantra Assist" with a space.
- These are spoken brand names on a phone call — single-word format ensures correct pronunciation.

PROSODY AND TONE (CRITICAL):
- DO NOT use exclamation marks (!) or ALL CAPS in your responses.
- The voice engine uses punctuation and casing to determine volume and emotion. Exclamation marks or ALL CAPS will cause the agent to yell or shout inappropriately.
- Keep your punctuation flat (use periods and commas). Instead of "HELLO!", write "Hello." Instead of "Great!", write "Great."

Follow these specific instructions:
"""


async def _resolve_from_db(phone_number: str) -> dict | None:
    """Look up inbound call context from PostgreSQL org_configs."""
    try:
        clean_number = phone_number.replace("+", "")
        conn = await asyncpg.connect(settings.postgres_dsn, timeout=5.0)
        try:
            row = await conn.fetchrow(
                "SELECT * FROM org_configs WHERE phone_number IN ($1, $2) AND is_active = true",
                phone_number,
                clean_number,
            )
        finally:
            await conn.close()

        if not row:
            return None

        result = dict(row)
        if result.get("transfer_numbers") and isinstance(result["transfer_numbers"], str):
            try:
                result["transfer_numbers"] = json.loads(result["transfer_numbers"])
            except Exception:
                pass

        return {
            "org_id": result.get("org_id"),
            "kb_id": result.get("org_id"),
            "kb_tags": result.get("kb_tags", []),
            "prompt": result.get("prompt"),
            "voice": result.get("voice"),
            "model": result.get("model"),
            "process_id": result.get("process_id"),
            "transfer_numbers": result.get("transfer_numbers", {}),
            "client_name": result.get("client_name"),
        }
    except Exception as e:
        logger.error("Failed to query DB for phone number %s: %s", phone_number, e)
        return None


async def _resolve_from_backend(phone_number: str) -> dict | None:
    """Call MantraAssist backend to resolve inbound call context."""
    base_url = settings.MANTRAASSIST_BACKEND_URL.rstrip("/")
    if not base_url:
        logger.error(
            "MANTRAASSIST_BACKEND_URL not set — cannot resolve inbound call context"
        )
        return None

    url = f"{base_url}/api/v1/telephony/resolve-inbound-call"
    logger.info(
        "Resolving inbound call context for phone_number=%s via %s",
        phone_number,
        url,
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"phone_number": phone_number},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(
                        "Resolved inbound context: org_id=%s, kb_id=%s, kb_tags=%s",
                        data.get("org_id"),
                        data.get("kb_id"),
                        data.get("kb_tags"),
                    )
                    return data
                resp_text = await resp.text()
                logger.error(
                    "MantraAssist resolve-inbound-call returned %s: %s",
                    resp.status,
                    resp_text,
                )
                return None
    except asyncio.TimeoutError:
        logger.error("MantraAssist resolve-inbound-call timed out (10s)")
        return None
    except Exception as e:
        logger.error("Failed to resolve inbound call context: %s", e)
        return None


async def resolve_inbound_context(phone_number: str) -> dict | None:
    """Resolve inbound context: DB first, backend fallback, local only if flag set."""
    if settings.LOCAL_INBOUND_MAPPINGS:
        local = _load_local_mappings(phone_number)
        if local:
            return local

    config = await _resolve_from_db(phone_number)
    if config:
        logger.info(
            "Resolved inbound context from DB for %s (org_id: %s)",
            phone_number,
            config.get("org_id"),
        )
        return config

    logger.info("DB miss — falling back to MantraAssist API for %s", phone_number)
    return await _resolve_from_backend(phone_number)


def extract_kb_scope(meta_payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract deduplicated kb_ids and kb_tags from metadata."""
    kb_ids_list: list[str] = []
    kb_tags_list: list[str] = []

    if meta_payload.get("org_id"):
        kb_ids_list.append(str(meta_payload["org_id"]))

    if meta_payload.get("kb_id"):
        if str(meta_payload["kb_id"]) not in kb_ids_list:
            kb_ids_list.append(str(meta_payload["kb_id"]))

    if "kb_ids" in meta_payload and isinstance(meta_payload["kb_ids"], list):
        kb_ids_list.extend(str(x) for x in meta_payload["kb_ids"])

    if "kb_tags" in meta_payload and isinstance(meta_payload["kb_tags"], list):
        kb_tags_list.extend(str(x) for x in meta_payload["kb_tags"])

    return list(set(kb_ids_list)), list(set(kb_tags_list))


def build_initial_instructions(
    payload: dict[str, Any],
    *,
    is_inbound: bool,
    resolved_context: dict | None = None,
) -> tuple[str, str]:
    """Build agent instructions and client_name from call metadata."""
    initial_instructions = INITIAL_INSTRUCTIONS_PREFIX
    client_name = "User"

    if "client_custom_fileds" in payload:
        ccf = payload.pop("client_custom_fileds")
        if isinstance(ccf, str):
            try:
                ccf = json.loads(ccf)
            except Exception:
                pass
        payload["client_custom_fields"] = ccf
    elif "client_custom_fields" in payload:
        ccf = payload["client_custom_fields"]
        if isinstance(ccf, str):
            try:
                payload["client_custom_fields"] = json.loads(ccf)
            except Exception:
                pass

    ivr_keys = {
        "account_number",
        "call_reason",
        "department",
        "language",
        "user_id",
        "caller_choice",
    }
    ivr_block = ""
    for key in payload:
        if key in ivr_keys and payload[key]:
            ivr_block += f"- {key.replace('_', ' ').title()}: {payload[key]}\n"

    if ivr_block:
        initial_instructions += "\n--- EXTERNAL IVR / CALLER CONTEXT ---\n"
        initial_instructions += "The caller was routed from an automated system with the following context.\n"
        initial_instructions += "DO NOT ask the user for this information again:\n"
        initial_instructions += ivr_block

    if "prompt" in payload:
        clean_prompt = payload["prompt"].replace(
            "If the client is not responding, ask questions like 'hope you are hearing me', etc.",
            "",
        )
        initial_instructions += "\n" + clean_prompt

    if "client_name" in payload:
        client_name = payload["client_name"]

    context_header = "\n\n--- ADDITIONAL CALL CONTEXT ---\n"
    context_body = ""

    for key, value in payload.items():
        if key == "prompt":
            continue
        if is_inbound and key == "client_name" and (value == "User" or not value):
            continue
        readable_key = key.replace("_", " ").title()
        if isinstance(value, dict):
            context_body += f"{readable_key}:\n"
            for k, v in value.items():
                rk = k.replace("_", " ").title()
                context_body += f"  - {rk}: {v}\n"
        elif isinstance(value, list):
            context_body += f"- {readable_key}: {', '.join(map(str, value))}\n"
        else:
            context_body += f"- {readable_key}: {value}\n"

    if context_body:
        initial_instructions += context_header + context_body

    initial_instructions += "\n\n*** CRITICAL OVERRIDING RULES ***\n"
    initial_instructions += "1. NEVER repeat the same question twice. If the user dodges the question or asks a counter-question, answer them and DO NOT repeat your previous question.\n"
    initial_instructions += "2. DO NOT push for an appointment if the user hasn't explicitly agreed or if they are asking about other things. Let the conversation flow naturally.\n"
    initial_instructions += "3. Answer user's questions DIRECTLY without appending a sales pitch or appointment request at the end of every turn.\n"
    initial_instructions += "4. If the user asks to speak to a human, asks to be transferred, or mentions a department — you MUST call the transfer_to_human function IMMEDIATELY. Do NOT keep talking. Call the function.\n"

    if is_inbound:
        initial_instructions += "\n--- INBOUND CALL CONTEXT ---\n"
        initial_instructions += "- This is an INBOUND call. The caller reached out to you.\n"
        initial_instructions += "- Greet warmly and ask how you can help.\n"
        initial_instructions += "- Do not assume you know why they are calling. Let them explain.\n"
        initial_instructions += "- Identify yourself: 'Mantra Care' or as instructed in your prompt.\n"
        initial_instructions += "- If the caller seems confused, help them understand who you are.\n"

    if resolved_context:
        logger.debug("Built instructions with resolved inbound context")

    return initial_instructions, client_name


def _load_local_mappings(phone_number: str) -> dict[str, Any]:
    """Load inbound mappings from local JSON when LOCAL_INBOUND_MAPPINGS is enabled."""
    import os

    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "config", "inbound_mappings.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "inbound_mappings.json"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        try:
            with open(path, encoding="utf-8") as f:
                mappings = json.load(f)
            for mapping in mappings.get("mappings", []):
                phones = mapping.get("phone_numbers") or []
                if phone_number in phones or phone_number.lstrip("+") in [
                    p.lstrip("+") for p in phones
                ]:
                    return mapping
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.debug("Local mappings not loaded from %s: %s", path, e)
    return {}
