"""Load and parse agents_data and Leave Tracker files."""
import pandas as pd
from datetime import datetime, timedelta


def _norm(s):
    """Normalize column name: lowercase, strip, collapse whitespace, replace / with space."""
    if not isinstance(s, str):
        return str(s).lower().strip()
    return ' '.join(s.lower().replace('/', ' ').split())


def load_roster(file_path):
    """
    Load agents_data roster from Excel.
    Returns list of dicts with:
        workday_id, pseudo_name, email, manager, role, shift_time, off_day
    """
    df = pd.read_excel(file_path, sheet_name=0)
    df.columns = [_norm(c) for c in df.columns]

    # Flexible column mapping
    id_col = next((c for c in df.columns if 'workday' in c and 'id' in c), 'workday id')
    name_col = next((c for c in df.columns if 'pseudo' in c or 'name' in c), 'pseudo name')
    email_col = next((c for c in df.columns if 'email' in c), 'email')
    mgr_col = next((c for c in df.columns if 'manager' in c), 'manager')
    role_col = next((c for c in df.columns if 'role' in c or 'jd' in c), 'role jd')
    shift_col = next((c for c in df.columns if 'shift' in c and 'time' in c), 'shift time')
    off_col = next((c for c in df.columns if 'off' in c and 'day' in c), 'off day')

    roster = []
    for _, row in df.iterrows():
        roster.append({
            'workday_id': str(row.get(id_col, '')).strip(),
            'pseudo_name': str(row.get(name_col, '')).strip(),
            'email': str(row.get(email_col, '')).strip(),
            'manager': str(row.get(mgr_col, '')).strip(),
            'role': str(row.get(role_col, '')).strip() if pd.notna(row.get(role_col)) else '—',
            'shift_time': str(row.get(shift_col, '09:00')).strip(),
            'off_day': str(row.get(off_col, '')).strip()
        })

    return roster


def load_leaves(file_path):
    """
    Load Leave Tracker from Excel (Workday Data sheet).
    Returns dict mapping workday_id -> list of leave dates (approved only).
    """
    try:
        df = pd.read_excel(file_path, sheet_name='Workday Data')
    except:
        # If no Workday Data sheet, return empty
        return {}

    df.columns = [_norm(c) for c in df.columns]

    id_col = next((c for c in df.columns if 'employee' in c and 'id' in c), None)
    date_col = next((c for c in df.columns if 'time off' in c and 'date' in c), None)
    status_col = next((c for c in df.columns if 'status' in c), None)

    if not all([id_col, date_col]):
        return {}

    # Filter to approved leaves
    if status_col:
        df = df[df[status_col].str.lower().str.contains('approve', na=False)]

    leaves = {}
    for _, row in df.iterrows():
        emp_id = str(row[id_col]).strip()
        date_val = row[date_col]

        if pd.notna(date_val):
            if isinstance(date_val, datetime):
                date_obj = date_val.date()
            else:
                try:
                    date_obj = pd.to_datetime(date_val).date()
                except:
                    continue

            leaves.setdefault(emp_id, []).append(date_obj)

    return leaves
