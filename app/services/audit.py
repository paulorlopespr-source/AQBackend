from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AuditLog


def write_audit(db:Session,event_type:str,entity_type:str="",entity_id:str="",message:str="",payload:dict[str,Any]|None=None)->None:
    db.add(AuditLog(event_type=event_type,entity_type=entity_type,entity_id=entity_id,message=message,payload_json=json.dumps(payload or {},ensure_ascii=False,default=str)))


def recommendation_payload(row)->dict[str,Any]:
    return {"fixture_id":row.fixture_id,"league":row.league,"market":row.market,"selection":row.selection,"probability":row.probability,"confidence":row.confidence,"risk":row.risk,"odd":row.offered_odd,"result":row.result,"model_version":getattr(row,"model_version","")}
