#!/usr/bin/env python3
"""
Toggle the Zadarma SIP dispatch rule between production and dev agent names.

USAGE:
    python tools/toggle-dev-dispatch.py on     # Switch to mantra-agent-dev
    python tools/toggle-dev-dispatch.py off    # Restore to mantra-agent (prod)
    python tools/toggle-dev-dispatch.py status # Show current rule

Requires LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in .env.local
"""
import json
import os
import sys
import json as pyjson

from dotenv import load_dotenv
load_dotenv(".env.local")

from livekit import api

# The dispatch rule for the Zadarma inbound trunk
ZADARMA_TRUNK_ID = "ST_wCjxf77iMhPM"
BACKUP_FILE = ".dispatch-rule-backup.json"


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


async def find_zadarma_rule(lk_client):
    resp = await lk_client.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())
    for item in resp.items:
        trunk_ids = list(item.trunk_ids)
        if ZADARMA_TRUNK_ID in trunk_ids:
            return item
    return None


async def get_agent_name(rule_info):
    if rule_info.room_config and rule_info.room_config.agents:
        return rule_info.room_config.agents[0].agent_name
    return "mantra-agent"


async def cmd_on(lk_client):
    rule = await find_zadarma_rule(lk_client)
    if not rule:
        print("ERROR: No dispatch rule found for Zadarma trunk")
        return

    rule_id = rule.sip_dispatch_rule_id
    current_agent = await get_agent_name(rule)
    print(f"Current rule: {rule_id}, agent: {current_agent}")

    if current_agent == "mantra-agent-dev":
        print("Already in DEV mode — nothing to do")
        return

    # Determine room_prefix from rule
    room_prefix = "inbound_"
    if rule.rule and rule.rule.dispatch_rule_individual:
        room_prefix = rule.rule.dispatch_rule_individual.room_prefix

    # Save backup
    backup = {
        "sip_dispatch_rule_id": rule_id,
        "name": rule.name,
        "metadata": rule.metadata,
        "room_prefix": room_prefix,
        "trunk_ids": list(rule.trunk_ids),
        "agent_name": current_agent,
        "room_config": {
            "empty_timeout": rule.room_config.empty_timeout if rule.room_config else 300,
            "departure_timeout": rule.room_config.departure_timeout if rule.room_config else 60,
        }
    }
    with open(BACKUP_FILE, "w") as f:
        f.write(pyjson.dumps(backup, indent=2))
    print(f"Saved backup to {BACKUP_FILE}")

    # Parse existing metadata
    metadata_dict = {}
    if rule.metadata:
        try:
            metadata_dict = pyjson.loads(rule.metadata)
        except:
            pass

    # Delete old rule
    print(f"Deleting old rule: {rule_id}")
    await lk_client.sip.delete_dispatch_rule(
        api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
    )

    # Create new rule with dev agent
    trunk_ids = list(rule.trunk_ids)
    req = api.CreateSIPDispatchRuleRequest(
        name=rule.name,
        metadata=pyjson.dumps(metadata_dict),
        rule=api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                room_prefix=room_prefix
            )
        ),
        room_config=api.RoomConfiguration(
            empty_timeout=backup["room_config"]["empty_timeout"],
            departure_timeout=backup["room_config"]["departure_timeout"],
            agents=[
                api.RoomAgentDispatch(
                    agent_name="mantra-agent-dev",
                    metadata=pyjson.dumps(metadata_dict)
                )
            ]
        ),
        trunk_ids=trunk_ids
    )
    new_rule = await lk_client.sip.create_dispatch_rule(req)
    print(f"Created DEV rule: {new_rule.sip_dispatch_rule_id}  (agent: mantra-agent-dev)")
    print("Inbound calls now route to your local agent.")
    print(f"Run `lk sip dispatch list` to verify.")
    print(f"\nTo switch back: python tools/toggle-dev-dispatch.py off")


async def cmd_off(lk_client):
    if not os.path.exists(BACKUP_FILE):
        print("No backup file found. Creating a default prod backup and restoring...")
        backup = {
            "name": "Rule for Zadarma Inbound Trunk",
            "metadata": "{}",
            "room_prefix": "inbound_7iMhPM",
            "trunk_ids": [ZADARMA_TRUNK_ID],
            "agent_name": "mantra-agent",
            "room_config": {"empty_timeout": 300, "departure_timeout": 60}
        }
    else:
        with open(BACKUP_FILE) as f:
            backup = pyjson.loads(f.read())

    # Check if a rule for this trunk already exists
    existing = await find_zadarma_rule(lk_client)
    if existing:
        existing_agent = await get_agent_name(existing)
        if existing_agent == backup["agent_name"] and os.path.exists(BACKUP_FILE):
            print(f"Already restored to {backup['agent_name']} — nothing to do")
            return
        # Delete the current rule first
        print(f"Deleting current rule: {existing.sip_dispatch_rule_id}")
        await lk_client.sip.delete_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=existing.sip_dispatch_rule_id)
        )

    # Parse metadata
    metadata_dict = {}
    if backup.get("metadata"):
        try:
            metadata_dict = pyjson.loads(backup["metadata"])
        except:
            pass

    # Restore original rule
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
    print(f"Restored rule: {new_rule.sip_dispatch_rule_id}  (agent: {backup['agent_name']})")
    if os.path.exists(BACKUP_FILE):
        os.remove(BACKUP_FILE)
    print("Inbound calls now route to production agent.")


async def cmd_status(lk_client):
    rule = await find_zadarma_rule(lk_client)
    if not rule:
        print("No dispatch rule found for Zadarma trunk")
        return
    agent = await get_agent_name(rule)
    backup_exists = os.path.exists(BACKUP_FILE)
    print(f"Rule ID:    {rule.sip_dispatch_rule_id}")
    print(f"Name:       {rule.name}")
    print(f"Agent:      {agent}")
    print(f"Trunk IDs:  {list(rule.trunk_ids)}")
    print(f"Backup:     {'exists' if backup_exists else 'none'}")
    print(f"Mode:       {'DEV' if agent == 'mantra-agent-dev' else 'PRODUCTION'}")


async def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("on", "off", "status"):
        print(__doc__)
        return

    lk_client = get_lk_client()
    try:
        cmd = sys.argv[1]
        if cmd == "on":
            await cmd_on(lk_client)
        elif cmd == "off":
            await cmd_off(lk_client)
        elif cmd == "status":
            await cmd_status(lk_client)
    finally:
        await lk_client.aclose()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
