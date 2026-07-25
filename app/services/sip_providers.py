"""SIP provider forwarding helpers — Zadarma, Twilio, Plivo."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import aiohttp

from app.config import settings
from app.services.db import db_service
from app.services.livekit import livekit_service
from app.services.redis import redis_service

logger = logging.getLogger("app.services.sip_providers")


def normalize_phone_number(number: str) -> str:
    return str(number or "").replace(" ", "").replace("+", "")


def get_zadarma_credentials() -> tuple[str, str]:
    key = settings.ZADARMA_API_KEY or settings.ZADARMA_KEY
    secret = settings.ZADARMA_API_SECRET or settings.ZADARMA_SECRET
    return key or "", secret or ""


async def update_zadarma_sip_forwarding(phone_number: str, sip_uri: str) -> dict:
    zadarma_key, zadarma_secret = get_zadarma_credentials()
    if not zadarma_key or not zadarma_secret:
        raise ValueError("Zadarma API credentials not found in environment variables.")

    number_clean = phone_number.replace("+", "")
    sip_uri_clean = sip_uri.replace("sip:", "")

    params = {"number": number_clean, "sip_id": sip_uri_clean}
    sorted_params = {k: params[k] for k in sorted(params.keys())}
    query_string = urlencode(sorted_params)
    md5_hash = hashlib.md5(query_string.encode("utf-8")).hexdigest()
    api_method = "/v1/direct_numbers/set_sip_id/"
    string_to_sign = api_method + query_string + md5_hash
    mac_hex = hmac.new(
        zadarma_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()
    signature = base64.b64encode(mac_hex.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"{zadarma_key}:{signature}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    url = f"https://api.zadarma.com{api_method}"

    async with aiohttp.ClientSession() as session:
        async with session.put(url, data=sorted_params, headers=headers) as resp:
            text = await resp.text()
            if resp.status == 200:
                try:
                    return json.loads(text)
                except Exception:
                    return {"status": "success", "response": text}
            logger.error("Zadarma API error %s: %s", resp.status, text)
            raise RuntimeError(f"Zadarma API error: {text}")


async def update_twilio_sip_forwarding(phone_number: str, sip_uri: str) -> dict:
    twilio_account_sid = settings.TWILIO_ACCOUNT_SID
    twilio_auth_token = settings.TWILIO_AUTH_TOKEN
    if not twilio_account_sid or not twilio_auth_token:
        raise ValueError("Twilio API credentials not found in environment variables.")

    number_clean = phone_number if phone_number.startswith("+") else f"+{phone_number}"
    auth = base64.b64encode(f"{twilio_account_sid}:{twilio_auth_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with aiohttp.ClientSession() as session:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}/IncomingPhoneNumbers.json"
        async with session.get(url, headers=headers, params={"PhoneNumber": number_clean}) as resp:
            text = await resp.text()
            if resp.status != 200:
                logger.error("Twilio API error listing numbers %s: %s", resp.status, text)
                raise RuntimeError(f"Twilio API error: {text}")
            data = json.loads(text)
            numbers = data.get("incoming_phone_numbers", [])
            if not numbers:
                raise RuntimeError(f"Phone number {number_clean} not found in Twilio account")
            number_sid = numbers[0]["sid"]

        host = (
            settings.LIVEKIT_URL.replace("wss://", "")
            .replace("ws://", "")
            .replace("https://", "")
            .replace("http://", "")
        )
        voice_url = f"https://{host}/api/v1/sip/twilio-webhook"
        update_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/{twilio_account_sid}"
            f"/IncomingPhoneNumbers/{number_sid}.json"
        )
        async with session.post(
            update_url, headers=headers, data={"VoiceUrl": voice_url, "VoiceMethod": "POST"}
        ) as resp:
            text = await resp.text()
            if resp.status == 200:
                try:
                    return json.loads(text)
                except Exception:
                    return {"status": "success", "response": text}
            logger.error("Twilio API error updating number %s: %s", resp.status, text)
            raise RuntimeError(f"Twilio API error: {text}")


async def update_plivo_sip_forwarding(phone_number: str, sip_uri: str) -> dict:
    plivo_auth_id = settings.PLIVO_AUTH_ID
    plivo_auth_token = settings.PLIVO_AUTH_TOKEN
    if not plivo_auth_id or not plivo_auth_token:
        raise ValueError("Plivo API credentials not found in environment variables.")

    number_clean = phone_number.replace("+", "").replace(" ", "")
    auth = base64.b64encode(f"{plivo_auth_id}:{plivo_auth_token}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    sip_domain = livekit_service.get_sip_domain()
    origination_host = f"{sip_domain}:5061;transport=tls"
    base_url = f"https://api.plivo.com/v1/Account/{plivo_auth_id}"
    trunk_label = f"LiveKit ({sip_domain.split('.')[0]})"

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/Zentrunk/URI/", headers=headers) as resp:
            uri_list = json.loads(await resp.text()) if resp.status == 200 else {"objects": []}

        uri_uuid = None
        for uri_obj in uri_list.get("objects", []):
            if sip_domain in uri_obj.get("uri", "") and "transport=tls" in uri_obj.get("uri", ""):
                uri_uuid = uri_obj.get("uri_uuid")
                logger.info("Found existing Zentrunk origination URI %s", uri_uuid)
                break

        if not uri_uuid:
            async with session.post(
                f"{base_url}/Zentrunk/URI/", headers=headers, json={"uri": origination_host}
            ) as resp:
                result_text = await resp.text()
                result = json.loads(result_text) if result_text else {}
                if resp.status in (200, 201, 202):
                    uri_uuid = result.get("uri_uuid")
                    logger.info("Created Zentrunk origination URI %s", uri_uuid)
                else:
                    raise RuntimeError(f"Failed to create Zentrunk URI: {result}")

        async with session.get(f"{base_url}/Zentrunk/Trunk/", headers=headers) as resp:
            trunk_list = json.loads(await resp.text()) if resp.status == 200 else {"objects": []}

        trunk_id = None
        for trunk_obj in trunk_list.get("objects", []):
            if trunk_obj.get("primary_uri_uuid") == uri_uuid:
                trunk_id = trunk_obj.get("trunk_id")
                break

        if not trunk_id:
            trunk_data = {
                "name": f"Inbound via {trunk_label}",
                "trunk_direction": "inbound",
                "primary_uri_uuid": uri_uuid,
            }
            async with session.post(f"{base_url}/Zentrunk/Trunk/", headers=headers, json=trunk_data) as resp:
                result_text = await resp.text()
                result = json.loads(result_text) if result_text else {}
                if resp.status in (200, 201, 202):
                    trunk_id = result.get("trunk_id")
                else:
                    raise RuntimeError(f"Failed to create Zentrunk trunk: {result}")

        async with session.get(f"{base_url}/Number/{number_clean}/", headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Phone number +{number_clean} not found in Plivo account")

        async with session.post(
            f"{base_url}/Number/{number_clean}/", headers=headers, json={"app_id": trunk_id}
        ) as resp:
            text = await resp.text()
            if resp.status in (200, 202):
                try:
                    result = json.loads(text)
                except Exception:
                    result = {"status": "success", "response": text}
                result["zentrunk_trunk_id"] = trunk_id
                result["zentrunk_uri_uuid"] = uri_uuid
                result["zentrunk_sip_domain"] = sip_domain
                return result
            logger.error("Plivo API error linking number %s: %s", resp.status, text)
            raise RuntimeError(f"Plivo API error: {text}")


async def update_provider_sip_forwarding(provider: str, phone_number: str, sip_uri: str) -> dict:
    provider = provider.lower().strip()
    if provider == "zadarma":
        return await update_zadarma_sip_forwarding(phone_number, sip_uri)
    if provider == "twilio":
        return await update_twilio_sip_forwarding(phone_number, sip_uri)
    if provider == "plivo":
        return await update_plivo_sip_forwarding(phone_number, sip_uri)
    raise ValueError(f"Unsupported provider: {provider}. Supported: zadarma, twilio, plivo")


def build_plivo_xml(
    sip_trunk_id: str, sip_domain: str, action_url: str, phone_number: str = ""
) -> str:
    sip_username = escape(phone_number or sip_trunk_id)
    sip_domain = escape(sip_domain)
    action_url = escape(action_url)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial action="{action_url}" method="POST" timeout="20">
        <User>sip:{sip_username}@{sip_domain}</User>
    </Dial>
</Response>"""


def build_twilio_xml(sip_trunk_id: str, sip_domain: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>sip:{sip_trunk_id}@{sip_domain};transport=tcp</Sip>
    </Dial>
</Response>"""


async def resolve_plivo_sip_trunk_id(to_number: str) -> str | None:
    clean_to = normalize_phone_number(to_number)
    candidates = [to_number, clean_to]
    if to_number and not to_number.startswith("+") and clean_to:
        candidates.append(f"+{clean_to}")

    for candidate in candidates:
        try:
            trunk_id = await redis_service.get_provider_trunk_mapping("plivo", candidate)
            if trunk_id:
                logger.info("Resolved Plivo SIP trunk from Redis for %s: %s", to_number, trunk_id)
                return trunk_id
        except Exception as e:
            logger.warning("Redis lookup failed for Plivo SIP trunk %s: %s", candidate, e)

    try:
        row = await db_service.get_org_config_sip_trunk(to_number, clean_to)
        if row:
            trunk_id = row
            logger.info("Resolved Plivo SIP trunk from DB for %s: %s", to_number, trunk_id)
            await redis_service.set_provider_trunk_mapping("plivo", to_number, trunk_id)
            return trunk_id
    except Exception as e:
        logger.warning("DB lookup failed for Plivo SIP trunk: %s", e)

    try:
        response = await livekit_service.list_inbound_trunks()
        for item in getattr(response, "items", []) or []:
            numbers = [str(n).strip() for n in getattr(item, "numbers", []) or []]
            normalized_numbers = {normalize_phone_number(n) for n in numbers}
            if clean_to in normalized_numbers or normalize_phone_number(to_number) in normalized_numbers:
                trunk_id = getattr(item, "sip_trunk_id", None)
                if trunk_id:
                    await redis_service.set_provider_trunk_mapping("plivo", to_number, trunk_id)
                    return trunk_id
    except Exception as e:
        logger.warning("LiveKit inbound trunk lookup failed for Plivo: %s", e)
    return None


async def resolve_twilio_sip_trunk_id(to_number: str) -> str | None:
    clean_to = to_number.replace("+", "")
    for candidate in (to_number, clean_to):
        try:
            trunk_id = await redis_service.get_provider_trunk_mapping("twilio", candidate)
            if trunk_id:
                return trunk_id
        except Exception as e:
            logger.warning("Redis lookup failed for Twilio SIP trunk: %s", e)

    try:
        trunk_id = await db_service.get_org_config_sip_trunk(to_number, clean_to)
        if trunk_id:
            await redis_service.set_provider_trunk_mapping("twilio", to_number, trunk_id)
            return trunk_id
    except Exception as e:
        logger.warning("DB lookup failed for Twilio SIP trunk: %s", e)
    return None
