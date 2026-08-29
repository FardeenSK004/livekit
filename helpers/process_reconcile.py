"""Process and Stage ID reconciliation helper."""

import logging
from typing import Optional, Union, Tuple, List, Dict, Any

logger = logging.getLogger("mantra.helpers.process_reconcile")


def reconcile_process_and_stage_id(
    process_id: Optional[Union[int, str]],
    stage_id: Optional[Union[int, str]],
    process_stage_data: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """
    Ensures process_id and stage_id are correctly mapped to each other based on process_stage_data.
    If stage_id belongs to process P in process_stage_data, process_id will be updated/enforced to P.
    """
    pid_int = None
    if process_id is not None:
        try:
            pid_int = int(process_id)
        except (ValueError, TypeError):
            pass

    sid_int = None
    if stage_id is not None:
        try:
            sid_int = int(stage_id)
        except (ValueError, TypeError):
            pass

    if not process_stage_data or not isinstance(process_stage_data, list):
        return pid_int, sid_int

    stage_to_process_map = {}
    process_to_stages_map = {}

    for p in process_stage_data:
        if not isinstance(p, dict):
            continue
        pid_raw = p.get("id") or p.get("process_id")
        if pid_raw is None:
            continue
        try:
            pid = int(pid_raw)
        except (ValueError, TypeError):
            continue

        stages_list = p.get("stages") or p.get("stageDetails") or []
        if not isinstance(stages_list, list):
            continue

        process_to_stages_map[pid] = set()
        for stg in stages_list:
            if not isinstance(stg, dict):
                continue
            sid_raw = stg.get("stage_id") or stg.get("id")
            if sid_raw is None:
                continue
            try:
                sid = int(sid_raw)
                stage_to_process_map[sid] = pid
                process_to_stages_map[pid].add(sid)
            except (ValueError, TypeError):
                continue

    # Reconciliation logic
    if sid_int is not None:
        if sid_int in stage_to_process_map:
            mapped_pid = stage_to_process_map[sid_int]
            if pid_int != mapped_pid:
                logger.warning(
                    f"Reconciled process_id mismatch: stage_id {sid_int} belongs to process {mapped_pid}, "
                    f"overriding process_id {pid_int} -> {mapped_pid}"
                )
                pid_int = mapped_pid
    elif pid_int is not None:
        if pid_int in process_to_stages_map:
            stgs = process_to_stages_map[pid_int]
            if len(stgs) == 1:
                sid_int = list(stgs)[0]

    return pid_int, sid_int
