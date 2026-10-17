from sqlalchemy.orm import Session
from api.app.core.models import AuditLog
from api.app.core.enums import AuditAction
from uuid import UUID
from datetime import datetime

def log_action(db: Session, org_id: UUID, user_id: UUID, entity: str, entity_id: UUID, action: AuditAction, changes: dict = None):
    log = AuditLog(
        org_id=org_id,
        user_id=user_id,
        entity=entity,
        entity_id=entity_id,
        action=action,
        changes=changes or {},
        at=datetime.utcnow()
    )
    db.add(log)
    db.commit()