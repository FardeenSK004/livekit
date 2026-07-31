#!/usr/bin/env python3
"""
Toggle SIP dispatch rules between production and dev agent names for all providers (Plivo, Twilio, Zadarma, etc.).

USAGE:
    python tools/toggle-dev-dispatch.py status                         # Show all inbound dispatch rules and their status
    python tools/toggle-dev-dispatch.py on [--provider plivo|twilio|zadarma] [--trunk-id ST_xxx] [--all]
    python tools/toggle-dev-dispatch.py off [--provider plivo|twilio|zadarma] [--trunk-id ST_xxx] [--all]

Examples:
    python tools/toggle-dev-dispatch.py on --all                         # Toggle ALL rules to dev
    python tools/toggle-dev-dispatch.py on --provider zadarma            # Toggle only Zadarma rules to dev
    python tools/toggle-dev-dispatch.py on --provider plivo              # Toggle only Plivo rules to dev
    python tools/toggle-dev-dispatch.py on zadarma                       # Shortcut: positional provider works too

Requires LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in .env.local
"""
import json
import os
import sys
import json as pyjson

from dotenv import load_dotenv
load_dotenv(".env.local")

AGENT_NAME = os.getenv("AGENT_NAME", "mantra-agent")

from livekit import api


def get_lk_client():
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    lk_url = os.getenv("LIVEKIT_URL")
    if lk_url and lk_url.startswith("wss://"):
        api_url = lk_url.replace("wss://", "https://")
    elif lk_url and lk_url.startswith("ws://"):
        api_url = lk_url.replace("ws://", "http://")
    else:
        api_url = lk_url
    return api.LiveKitAPI(url=api_url, api_key=api_key, api_secret=api_secret)


async def get_all_inbound_info(lk_client):
    """Fetch all dispatch rules + inbound trunks and return merged info."""
    rules_resp = await lk_client.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())
    trunks_resp = await lk_client.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())
    trunk_map = {t.sip_trunk_id: t for t in trunks_resp.items}

    items = []
    for rule in rules_resp.items:
        trunk_ids = list(rule.trunk_ids)
        providers, trunk_names, numbers = [], [], []
        for tid in trunk_ids:
            trunk = trunk_map.get(tid)
            if trunk:
                trunk_names.append(trunk.name)
                numbers.extend(list(trunk.numbers))
                meta = trunk.metadata
                if meta:
                    try:
                        meta_dict = pyjson.loads(meta) if isinstance(meta, str) else meta
                        if isinstance(meta_dict, dict) and "provider" in meta_dict:
                            providers.append(meta_dict["provider"].lower())
                    except:
                        pass
                if not providers:
                    name_lower = trunk.name.lower()
                    if "plivo" in name_lower:
                        providers.append("plivo")
                    elif "twilio" in name_lower:
                        providers.append("twilio")
                    elif "zadarma" in name_lower:
                        providers.append("zadarma")

        current_agent = AGENT_NAME
        if rule.room_config and rule.room_config.agents:
            current_agent = rule.room_config.agents[0].agent_name

        room_prefix = "inbound_"
        if rule.rule and rule.rule.dispatch_rule_individual:
            room_prefix = rule.rule.dispatch_rule_individual.room_prefix

        items.append({
            "rule": rule,
            "rule_id": rule.sip_dispatch_rule_id,
            "name": rule.name,
            "trunk_ids": trunk_ids,
            "trunk_names": trunk_names,
            "numbers": numbers,
            "providers": list(set(providers)),
            "current_agent": current_agent,
            "room_prefix": room_prefix,
            "room_config": rule.room_config
        })
    return items


def parse_args():
    args = sys.argv[1:]
    cmd = args[0] if args else "status"
    provider = None
    trunk_id = None
    all_flag = False

    i = 1
    while i < len(args):
        arg = args[i]
        if arg in ("plivo", "twilio", "zadarma"):
            provider = arg.lower()
            i += 1
        elif arg == "--provider" and i + 1 < len(args):
            provider = args[i+1].lower()
            i += 2
        elif arg == "--trunk-id" and i + 1 < len(args):
            trunk_id = args[i+1]
            i += 2
        elif arg == "--all":
            all_flag = True
            i += 1
        else:
            i += 1
    return cmd, provider, trunk_id, all_flag


def _backup_path(trunk_ids, rule_id):
    """Return the canonical backup path: keyed by first trunk ID, falling back to rule ID."""
    key = trunk_ids[0] if trunk_ids else rule_id
    return f".dispatch-rule-backup-{key}.json"


def _find_backup_file(trunk_ids, rule_id):
    """Find existing backup file by scanning all backup files for matching trunk IDs."""
    expected = _backup_path(trunk_ids, rule_id)
    if os.path.exists(expected):
        return expected
    for fname in os.listdir("."):
        if not fname.startswith(".dispatch-rule-backup-") or not fname.endswith(".json"):
            continue
        try:
            with open(fname) as f:
                data = pyjson.loads(f.read())
            backup_tids = data.get("trunk_ids", [])
            if any(tid in backup_tids for tid in trunk_ids):
                return fname
        except:
            pass
    return None


async def cmd_status(lk_client):
    items = await get_all_inbound_info(lk_client)
    if not items:
        print("No inbound dispatch rules found.")
        return
    print(f"{'RULE ID':<18} | {'NAME':<25} | {'PROVIDER':<10} | {'AGENT':<18} | {'TRUNK(S)':<15} | {'NUMBERS'}")
    print("-" * 105)
    for item in items:
        prov = ", ".join(item["providers"]) or "unknown"
        trunks = ", ".join(item["trunk_ids"])
        nums = ", ".join(item["numbers"]) or "none"
        print(f"{item['rule_id']:<18} | {item['name']:<25} | {prov:<10} | {item['current_agent']:<18} | {trunks:<15} | {nums}")


async def cmd_on(lk_client, provider_filter, trunk_id_filter, all_flag):
    items = await get_all_inbound_info(lk_client)
    if not items:
        print("No inbound dispatch rules found.")
        return

    targets = []
    for item in items:
        if trunk_id_filter and trunk_id_filter not in item["trunk_ids"]:
            continue
        if provider_filter and provider_filter not in item["providers"]:
            continue
        targets.append(item)

    if not targets:
        print("No dispatch rules matched the specified filters.")
        return

    if len(targets) > 1 and not all_flag and not trunk_id_filter and not provider_filter:
        print(f"Found {len(targets)} inbound rules. Specify --all, --provider <name>, or --trunk-id <id> to target specific rules, or use status to inspect.")
        return

    for item in targets:
        rule_id = item["rule_id"]
        current_agent = item["current_agent"]
        if current_agent == AGENT_NAME:
            print(f"Rule {rule_id} ({item['name']}) already in DEV mode — skipping.")
            continue

        backup_file = _backup_path(item["trunk_ids"], rule_id)
        backup = {
            "sip_dispatch_rule_id": rule_id,
            "name": item["name"],
            "metadata": item["rule"].metadata,
            "room_prefix": item["room_prefix"],
            "trunk_ids": item["trunk_ids"],
            "agent_name": current_agent,
            "room_config": {
                "empty_timeout": item["room_config"].empty_timeout if item["room_config"] else 300,
                "departure_timeout": item["room_config"].departure_timeout if item["room_config"] else 60,
            }
        }
        with open(backup_file, "w") as f:
            f.write(pyjson.dumps(backup, indent=2))
        print(f"✓ Backed up {rule_id} → {backup_file}")

        metadata_dict = {}
        if item["rule"].metadata:
            try:
                metadata_dict = pyjson.loads(item["rule"].metadata)
            except:
                pass

        print(f"  Deleting old rule: {rule_id}")
        await lk_client.sip.delete_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        )

        req = api.CreateSIPDispatchRuleRequest(
            name=item["name"],
            metadata=pyjson.dumps(metadata_dict),
            rule=api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                    room_prefix=item["room_prefix"]
                )
            ),
            room_config=api.RoomConfiguration(
                empty_timeout=backup["room_config"]["empty_timeout"],
                departure_timeout=backup["room_config"]["departure_timeout"],
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=AGENT_NAME,
                        metadata=pyjson.dumps(metadata_dict)
                    )
                ]
            ),
            trunk_ids=item["trunk_ids"]
        )
        new_rule = await lk_client.sip.create_dispatch_rule(req)
        print(f"  ✓ Created DEV rule: {new_rule.sip_dispatch_rule_id} (agent: {AGENT_NAME})")


async def cmd_off(lk_client, provider_filter, trunk_id_filter, all_flag):
    items = await get_all_inbound_info(lk_client)
    if not items:
        print("No inbound dispatch rules found.")
        return

    targets = []
    for item in items:
        if trunk_id_filter and trunk_id_filter not in item["trunk_ids"]:
            continue
        if provider_filter and provider_filter not in item["providers"]:
            continue
        targets.append(item)

    if not targets:
        print("No dispatch rules matched the specified filters.")
        return

    for item in targets:
        rule_id = item["rule_id"]
        current_agent = item["current_agent"]

        # If already in production, skip
        if current_agent != AGENT_NAME:
            print(f"✓ Rule {rule_id} already in production ({current_agent}) — skipping.")
            continue

        backup_file = _find_backup_file(item["trunk_ids"], rule_id)
        if backup_file:
            with open(backup_file) as f:
                backup = pyjson.loads(f.read())
        else:
            # No backup found — create a synthetic one from current rule config
            print(f"  (No backup file found for {rule_id} — using current rule config with agent: {AGENT_NAME})")
            backup = {
                "name": item["name"],
                "metadata": item["rule"].metadata,
                "room_prefix": item["room_prefix"],
                "trunk_ids": item["trunk_ids"],
                "agent_name": AGENT_NAME,
                "room_config": {
                    "empty_timeout": item["room_config"].empty_timeout if item["room_config"] else 300,
                    "departure_timeout": item["room_config"].departure_timeout if item["room_config"] else 60,
                }
            }

        # Delete current DEV rule (if it exists — handle 404 gracefully)
        try:
            print(f"  Deleting DEV rule: {rule_id}")
            await lk_client.sip.delete_dispatch_rule(
                api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
            )
        except Exception as e:
            if "not_found" in str(e) or "404" in str(e) or "cannot be found" in str(e):
                print(f"  (DEV rule {rule_id} already gone — production rule exists, skipping recreate to avoid duplicates)")
                if backup_file and os.path.exists(backup_file):
                    os.remove(backup_file)
                continue
            else:
                print(f"  ⚠ Delete failed: {e} (continuing with restore)")

        metadata_dict = {}
        if backup.get("metadata"):
            try:
                metadata_dict = pyjson.loads(backup["metadata"])
            except:
                pass

        req = api.CreateSIPDispatchRuleRequest(
            name=backup["name"],
            metadata=pyjson.dumps(metadata_dict),
            rule=api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                    room_prefix=backup["room_prefix"]
                )
            ),
            room_config=api.RoomConfiguration(
                empty_timeout=backup["room_config"]["empty_timeout"],
                departure_timeout=backup["room_config"]["departure_timeout"],
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=backup["agent_name"],
                        metadata=pyjson.dumps(metadata_dict)
                    )
                ]
            ),
            trunk_ids=backup["trunk_ids"]
        )
        new_rule = await lk_client.sip.create_dispatch_rule(req)
        print(f"  ✓ Restored rule: {new_rule.sip_dispatch_rule_id} (agent: {backup['agent_name']})")
        if backup_file and os.path.exists(backup_file):
            os.remove(backup_file)


async def main():
    cmd, provider, trunk_id, all_flag = parse_args()
    if cmd not in ("on", "off", "status"):
        print(__doc__)
        return

    lk_client = get_lk_client()
    try:
        if cmd == "status":
            await cmd_status(lk_client)
        elif cmd == "on":
            await cmd_on(lk_client, provider, trunk_id, all_flag)
        elif cmd == "off":
            await cmd_off(lk_client, provider, trunk_id, all_flag)
    finally:
        await lk_client.aclose()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
