import datetime as dt
import json


def log(db, user, entity, entity_id, action, detail=None):
    db.execute(
        "INSERT INTO audit_log(ts,user_id,username,entity,entity_id,action,detail) VALUES (?,?,?,?,?,?,?)",
        (dt.datetime.now().isoformat(timespec="seconds"), user["id"] if user else None,
         user["username"] if user else "system", entity, entity_id, action,
         json.dumps(detail, default=str) if detail is not None else None))
