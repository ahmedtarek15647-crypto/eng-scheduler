"""
SQLite Database layer for Engineering Project Scheduler.
Supports automatic project code numbering (e.g. 26-0001), completion tracking,
cash receipt dates, monthly financial aggregation, and follow-up logging.
"""

import sqlite3
import json
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "projects.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_code TEXT UNIQUE,
        name TEXT NOT NULL,
        client_name TEXT NOT NULL,
        client_contact TEXT,
        discipline TEXT NOT NULL,
        start_date TEXT NOT NULL,
        scheduled_end_date TEXT NOT NULL,
        deadline TEXT,
        cost REAL NOT NULL,
        currency TEXT DEFAULT 'EGP',
        weekend_type TEXT DEFAULT 'Fri-Sat',
        scope_description TEXT,
        remarks TEXT DEFAULT '',
        is_finished INTEGER DEFAULT 0,
        actual_end_date TEXT,
        is_cash_received INTEGER DEFAULT 0,
        received_cash_date TEXT,
        received_amount REAL DEFAULT 0.0,
        status TEXT DEFAULT 'In Progress',
        tasks_json TEXT,
        milestones_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    # Automatic schema migration for existing databases
    existing_cols = [row[1] for row in cursor.execute("PRAGMA table_info(projects)").fetchall()]
    new_cols = {
        "project_code": "TEXT",
        "scheduled_end_date": "TEXT",
        "remarks": "TEXT DEFAULT ''",
        "is_finished": "INTEGER DEFAULT 0",
        "actual_end_date": "TEXT",
        "is_cash_received": "INTEGER DEFAULT 0",
        "received_cash_date": "TEXT",
        "received_amount": "REAL DEFAULT 0.0"
    }
    for col_name, col_def in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_def}")
    
    conn.commit()
    conn.close()

def get_next_project_code():
    """
    Generates sequential project code starting with current 2-digit year.
    Example: 26-0001, 26-0002, 26-0003...
    """
    conn = get_connection()
    cursor = conn.cursor()
    year_prefix = datetime.now().strftime("%y")  # '26' for 2026
    
    cursor.execute("SELECT project_code FROM projects WHERE project_code LIKE ? ORDER BY project_code DESC LIMIT 1", (f"{year_prefix}-%",))
    row = cursor.fetchone()
    conn.close()

    if not row or not row['project_code']:
        return f"{year_prefix}-0001"
    
    try:
        last_code = row['project_code']
        last_seq = int(last_code.split("-")[1])
        return f"{year_prefix}-{last_seq + 1:04d}"
    except (IndexError, ValueError):
        return f"{year_prefix}-0001"

def save_project(project_data):
    conn = get_connection()
    cursor = conn.cursor()

    code = project_data.get('project_code')
    if not code:
        code = get_next_project_code()

    scheduled_end = project_data.get('scheduled_end_date') or project_data.get('deadline')
    deadline = scheduled_end
    currency = project_data.get('currency') or 'EGP'

    tasks = project_data.get('tasks', [])
    milestones = project_data.get('milestones', [])

    is_fin = 1 if project_data.get('is_finished') else 0
    is_cash = 1 if project_data.get('is_cash_received') else 0

    if is_fin:
        for t in tasks:
            t['status'] = 'Completed'
            t['progress'] = 100

    if is_cash:
        for m in milestones:
            m['status'] = 'Paid'

    cursor.execute("""
    INSERT INTO projects (
        project_code, name, client_name, client_contact, discipline, 
        start_date, scheduled_end_date, deadline, cost, currency, weekend_type,
        scope_description, remarks, is_finished, actual_end_date,
        is_cash_received, received_cash_date, received_amount,
        status, tasks_json, milestones_json, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        code,
        project_data['name'],
        project_data['client_name'],
        project_data.get('client_contact', ''),
        project_data['discipline'],
        project_data['start_date'],
        scheduled_end,
        deadline,
        project_data['cost'],
        currency,
        project_data.get('weekend_type', 'Fri-Sat'),
        project_data.get('scope_description', ''),
        project_data.get('remarks', ''),
        is_fin,
        project_data.get('actual_end_date'),
        is_cash,
        project_data.get('received_cash_date'),
        project_data.get('received_amount', 0.0),
        'Completed' if is_fin else project_data.get('status', 'In Progress'),
        json.dumps(tasks),
        json.dumps(milestones),
        datetime.now().isoformat()
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def update_project(project_id, project_data):
    conn = get_connection()
    cursor = conn.cursor()
    scheduled_end = project_data.get('scheduled_end_date') or project_data.get('deadline')
    currency = project_data.get('currency') or 'EGP'
    
    is_fin = 1 if project_data.get('is_finished') else 0
    is_cash = 1 if project_data.get('is_cash_received') else 0
    
    tasks = project_data.get('tasks', [])
    milestones = project_data.get('milestones', [])

    if is_fin:
        for t in tasks:
            t['status'] = 'Completed'
            t['progress'] = 100
    
    if is_cash:
        for m in milestones:
            m['status'] = 'Paid'

    cursor.execute("""
    UPDATE projects SET
        project_code = ?,
        name = ?,
        client_name = ?,
        client_contact = ?,
        discipline = ?,
        start_date = ?,
        scheduled_end_date = ?,
        deadline = ?,
        cost = ?,
        currency = ?,
        weekend_type = ?,
        scope_description = ?,
        remarks = ?,
        is_finished = ?,
        actual_end_date = ?,
        is_cash_received = ?,
        received_cash_date = ?,
        received_amount = ?,
        status = ?,
        tasks_json = ?,
        milestones_json = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        project_data.get('project_code'),
        project_data['name'],
        project_data['client_name'],
        project_data.get('client_contact', ''),
        project_data['discipline'],
        project_data['start_date'],
        scheduled_end,
        scheduled_end,
        project_data['cost'],
        currency,
        project_data.get('weekend_type', 'Fri-Sat'),
        project_data.get('scope_description', ''),
        project_data.get('remarks', ''),
        is_fin,
        project_data.get('actual_end_date'),
        is_cash,
        project_data.get('received_cash_date'),
        project_data.get('received_amount', 0.0),
        'Completed' if is_fin else project_data.get('status', 'In Progress'),
        json.dumps(tasks),
        json.dumps(milestones),
        datetime.now().isoformat(),
        project_id
    ))
    conn.commit()
    conn.close()

def get_all_projects():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY id DESC")
    rows = cursor.fetchall()
    projects = []
    for r in rows:
        item = dict(r)
        item['tasks'] = json.loads(item['tasks_json']) if item['tasks_json'] else []
        item['milestones'] = json.loads(item['milestones_json']) if item['milestones_json'] else []
        if not item.get('scheduled_end_date'):
            item['scheduled_end_date'] = item.get('deadline', '')
        if not item.get('currency'):
            item['currency'] = 'EGP'
        projects.append(item)
    conn.close()
    return projects

def get_project_by_id(project_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item['tasks'] = json.loads(item['tasks_json']) if item['tasks_json'] else []
    item['milestones'] = json.loads(item['milestones_json']) if item['milestones_json'] else []
    if not item.get('scheduled_end_date'):
        item['scheduled_end_date'] = item.get('deadline', '')
    if not item.get('currency'):
        item['currency'] = 'EGP'
    return item

def delete_project(project_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def get_received_cash_records():
    """
    Returns all projects where cash has been received,
    ordered chronologically by received_cash_date.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, project_code, name, client_name, cost, currency, 
           received_amount, received_cash_date, actual_end_date, scheduled_end_date
    FROM projects 
    WHERE is_cash_received = 1 AND received_cash_date IS NOT NULL AND received_cash_date != ''
    ORDER BY received_cash_date DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        item = dict(r)
        if not item.get('currency'):
            item['currency'] = 'EGP'
        results.append(item)
    return results

def get_pending_payment_followups():
    """
    Identifies projects that are FINISHED (is_finished = 1)
    but CASH NOT YET RECEIVED (is_cash_received = 0).
    Calculates follow-up intervals (every 10 days since actual completion).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, project_code, name, client_name, client_contact, 
           cost, currency, actual_end_date, scheduled_end_date, remarks
    FROM projects 
    WHERE is_finished = 1 AND (is_cash_received = 0 OR is_cash_received IS NULL)
    ORDER BY actual_end_date ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    today = date.today()
    followups = []
    
    for r in rows:
        item = dict(r)
        if not item.get('currency'):
            item['currency'] = 'EGP'
            
        actual_str = item.get("actual_end_date")
        if actual_str:
            try:
                actual_date = datetime.strptime(actual_str, "%Y-%m-%d").date()
                days_elapsed = (today - actual_date).days
            except ValueError:
                days_elapsed = 0
        else:
            days_elapsed = 0
        
        item["days_since_finished"] = max(0, days_elapsed)
        cycle_number = (days_elapsed // 10) + 1
        days_to_next_cycle = 10 - (days_elapsed % 10) if days_elapsed > 0 else 10
        is_call_due_today = (days_elapsed >= 10 and days_elapsed % 10 == 0) or (days_elapsed > 10 and days_elapsed % 10 <= 2)

        item["cycle_number"] = cycle_number
        item["days_to_next_cycle"] = days_to_next_cycle
        item["is_call_due_now"] = is_call_due_today
        item["severity"] = "high" if days_elapsed >= 30 else ("medium" if days_elapsed >= 10 else "normal")
        followups.append(item)
        
    return followups
