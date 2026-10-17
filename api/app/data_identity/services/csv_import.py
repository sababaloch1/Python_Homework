import pandas as pd
from sqlalchemy.orm import Session
from fastapi import UploadFile
from api.app.core.models import ActivityRecord, ImportBatch, User
from api.app.core.enums import BatchStatus, AuditAction, ActivityCategory, Unit
from . import audit_service

def process_csv(file: UploadFile, db: Session, current_user: User):
    batch = ImportBatch(
        org_id=current_user.org_id,
        file_name=file.filename,
        uploaded_by=current_user.id,
        status=BatchStatus.pending
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        # sep=None auto-detects commas or semicolons. utf-8-sig removes Mac hidden characters.
        df = pd.read_csv(file.file, encoding='utf-8-sig', sep=None, engine='python')
        
        # Strip whitespace from column headers
        df.columns = df.columns.str.strip()
        
        # NFR-1.07: Check if the file has the required columns
        required_columns = {'category', 'amount', 'unit', 'period_start', 'period_end'}
        if not required_columns.issubset(df.columns):
            missing = required_columns - set(df.columns)
            batch.status = BatchStatus.failed
            batch.errors = [{"row": 1, "error": f"Missing columns: {', '.join(missing)}. Found: {list(df.columns)}"}]
            db.commit()
            return batch

    except Exception as e:
        batch.status = BatchStatus.failed
        batch.errors = [{"row": 0, "error": f"Invalid CSV format: {str(e)}"}]
        db.commit()
        return batch

    errors = []
    valid_records = []

    for index, row in df.iterrows():
        row_num = index + 2 
        try:
            # Convert to string and strip spaces just in case
            category_str = str(row['category']).strip()
            category = ActivityCategory(category_str)
            
            amount = float(row['amount'])
            if amount < 0:
                raise ValueError("Amount must be >= 0")
                
            unit_str = str(row['unit']).strip()
            unit = Unit(unit_str)
            
            period_start = pd.to_datetime(row['period_start']).date()
            period_end = pd.to_datetime(row['period_end']).date()
            
            valid_records.append({
                "org_id": current_user.org_id,
                "created_by": current_user.id,
                "import_batch_id": batch.id,
                "category": category,
                "amount": amount,
                "unit": unit,
                "period_start": period_start,
                "period_end": period_end,
                "note": str(row.get('note', ''))
            })
        except Exception as e:
            errors.append({"row": row_num, "error": str(e)})

    batch.row_count = len(df)
    batch.error_count = len(errors)
    
    if errors:
        batch.status = BatchStatus.failed
        batch.errors = errors
        db.commit()
        return batch

    for record_data in valid_records:
        record = ActivityRecord(**record_data)
        db.add(record)
    
    batch.status = BatchStatus.completed
    db.commit()

    audit_service.log_action(db, current_user.org_id, current_user.id, "ImportBatch", batch.id, AuditAction.create)
    
    return batch