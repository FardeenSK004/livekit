"""Organisation configurations controller."""

import json
import logging
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from dependencies.database import get_db_connection

logger = logging.getLogger("controllers.org_configs")


class OrgConfigsController:
    """CRUD controller for organisation phone configs."""

    @staticmethod
    async def list_org_configs(org_id: Optional[str] = None):
        try:
            conn = await get_db_connection()
            if org_id:
                rows = await conn.fetch("SELECT * FROM org_configs WHERE org_id = $1 ORDER BY created_at DESC", org_id)
            else:
                rows = await conn.fetch("SELECT * FROM org_configs ORDER BY created_at DESC")
            await conn.close()

            results = [dict(row) for row in rows]
            for r in results:
                if r.get('created_at'): r['created_at'] = r['created_at'].isoformat()
                if r.get('updated_at'): r['updated_at'] = r['updated_at'].isoformat()
                if r.get('id'): r['id'] = str(r['id'])
                if r.get('transfer_numbers') and isinstance(r['transfer_numbers'], str):
                    try: r['transfer_numbers'] = json.loads(r['transfer_numbers'])
                    except Exception: pass

            return {"status": "success", "count": len(results), "org_configs": results}
        except Exception as e:
            logger.error(f"Failed to list org configs: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def get_org_config(phone_number: str):
        try:
            clean_number = phone_number.replace("+", "")
            conn = await get_db_connection()
            row = await conn.fetchrow(
                "SELECT * FROM org_configs WHERE phone_number IN ($1, $2)",
                phone_number, clean_number
            )
            await conn.close()

            if not row:
                return JSONResponse({"status_code": 404, "status": "error", "error": "Not found"}, status_code=404)

            result = dict(row)
            if result.get('created_at'): result['created_at'] = result['created_at'].isoformat()
            if result.get('updated_at'): result['updated_at'] = result['updated_at'].isoformat()
            if result.get('id'): result['id'] = str(result['id'])
            if result.get('transfer_numbers') and isinstance(result['transfer_numbers'], str):
                try: result['transfer_numbers'] = json.loads(result['transfer_numbers'])
                except Exception: pass

            return {"status": "success", "org_config": result}
        except Exception as e:
            logger.error(f"Failed to get org config: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def update_org_config(phone_number: str, payload: dict):
        if not payload:
            return JSONResponse({"error": "No payload provided"}, status_code=400)

        try:
            clean_number = phone_number.replace("+", "")
            conn = await get_db_connection()

            row = await conn.fetchrow(
                "SELECT id FROM org_configs WHERE phone_number IN ($1, $2)",
                phone_number, clean_number
            )
            if not row:
                await conn.close()
                return JSONResponse({"status_code": 404, "status": "error", "error": "Not found"}, status_code=404)

            update_fields = []
            values = [row['id']]
            idx = 2

            allowed_fields = [
                "name", "prompt", "voice", "model", "kb_tags",
                "transfer_numbers", "client_name", "process_id", "is_active"
            ]

            for field in allowed_fields:
                if field in payload:
                    val = payload[field]
                    if field == "transfer_numbers" and isinstance(val, dict):
                        val = json.dumps(val)

                    update_fields.append(f"{field} = ${idx}")
                    values.append(val)
                    idx += 1

            if not update_fields:
                await conn.close()
                return {"status": "success", "message": "No valid fields to update"}

            update_fields.append("updated_at = NOW()")

            query = f"UPDATE org_configs SET {', '.join(update_fields)} WHERE id = $1 RETURNING *"
            updated_row = await conn.fetchrow(query, *values)
            await conn.close()

            result = dict(updated_row)
            if result.get('created_at'): result['created_at'] = result['created_at'].isoformat()
            if result.get('updated_at'): result['updated_at'] = result['updated_at'].isoformat()
            if result.get('id'): result['id'] = str(result['id'])
            if result.get('transfer_numbers') and isinstance(result['transfer_numbers'], str):
                try: result['transfer_numbers'] = json.loads(result['transfer_numbers'])
                except Exception: pass

            return {"status": "success", "org_config": result}
        except Exception as e:
            logger.error(f"Failed to update org config: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def delete_org_config(phone_number: str):
        try:
            clean_number = phone_number.replace("+", "")
            conn = await get_db_connection()
            row = await conn.fetchrow(
                "UPDATE org_configs SET is_active = false, updated_at = NOW() WHERE phone_number IN ($1, $2) RETURNING id",
                phone_number, clean_number
            )
            await conn.close()

            if not row:
                return JSONResponse({"status_code": 404, "status": "error", "error": "Not found"}, status_code=404)

            return {"status": "success", "message": f"Org config for {phone_number} deactivated"}
        except Exception as e:
            logger.error(f"Failed to delete org config: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)


org_configs_controller = OrgConfigsController()
