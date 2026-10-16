"""
Hybrid Database layer for Engineering Project Scheduler.
Supports:
1. Permanent Cloud Storage via Supabase (PostgreSQL REST API)
2. Local SQLite fallback (projects.db)
3. 1-Tap JSON Backup & Restore for mobile and desktop
"""

import sqlite3
import json
import os
import requests
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / "projects.db"

# ---------------- CLOUD DB CONFIGURATION (SUPABASE) ----------------
def get_cloud_credentials():
    """Retrieves Supabase credentials from Streamlit secrets or environment variables."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets and "SUPABASE_KEY" in st.secrets:
            return st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    except Exception:
        pass

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return url, key
    return None, None

def is_cloud_enabled():
    url, key = get_cloud_credentials()
    return bool(url and key)

def get_supabase_headers():
    url, key = get_cloud_credentials()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

# ---------------- LOCAL SQLITE INITIALIZATION ----------------
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # Always ensure local sqlite is ready as fallback
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

# ---------------- PROJECT CODE GENERATOR ----------------
def get_next_project_code():
    year_prefix = datetime.now().strftime("%y")  # '26' for 2026

    if is_cloud_enabled():
        url, _ = get_cloud_credentials()
        try:
            res = requests.get(
                f"{url}/rest/v1/projects?project_code=like.{year_prefix}-*&order=project_code.desc&limit=1",
                headers=get_supabase_headers(),
                timeout=5
            )
            if res.status_code == 200 and res.json():
                last_code = res.json()[0]['project_code']
                last_seq = int(last_code.split("-")[1])
                return f"{year_prefix}-{last_seq + 1:04d}"
            return f"{year_prefix}-0001"
        except Exception:
            pass

    conn = get_connection()
    cursor = conn.cursor()
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

# ---------------- CRUD OPERATIONS ----------------
def save_project(project_data):
    code = project_data.get('project_code') or get_next_project_code()
    scheduled_end = project_data.get('scheduled_end_date') or project_data.get('deadline')
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

    # 1. Save to Supabase Cloud if enabled
    if is_cloud_enabled():
        url, _ = get_cloud_credentials()
        payload = {
            "project_code": code,
            "name": project_data['name'],
            "client_name": project_data['client_name'],
            "client_contact": project_data.get('client_contact', ''),
            "discipline": project_data['discipline'],
            "start_date": project_data['start_date'],
            "scheduled_end_date": scheduled_end,
            "deadline": scheduled_end,
            "cost": float(project_data['cost']),
            "currency": currency,
            "weekend_type": project_data.get('weekend_type', 'Fri-Sat'),
            "scope_description": project_data.get('scope_description', ''),
            "remarks": project_data.get('remarks', ''),
            "is_finished": is_fin,
            "actual_end_date": project_data.get('actual_end_date'),
            "is_cash_received": is_cash,
            "received_cash_date": project_data.get('received_cash_date'),
            "received_amount": float(project_data.get('received_amount', 0.0)),
            "status": 'Completed' if is_fin else project_data.get('status', 'In Progress'),
            "tasks_json": json.dumps(tasks),
            "milestones_json": json.dumps(milestones),
            "updated_at": datetime.now().isoformat()
        }
        try:
            r = requests.post(f"{url}/rest/v1/projects", headers=get_supabase_headers(), json=payload, timeout=8)
            if r.status_code in (200, 201) and r.json():
                new_id = r.json()[0]['id']
                return new_id
        except Exception as e:
            print(f"Supabase save failed, falling back to local: {e}")

    # 2. Local SQLite save
    conn = get_connection()
    cursor = conn.cursor()
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

    # Cloud update
    if is_cloud_enabled():
        url, _ = get_cloud_credentials()
        payload = {
            "project_code": project_data.get('project_code'),
            "name": project_data['name'],
            "client_name": project_data['client_name'],
            "client_contact": project_data.get('client_contact', ''),
            "discipline": project_data['discipline'],
            "start_date": project_data['start_date'],
            "scheduled_end_date": scheduled_end,
            "deadline": scheduled_end,
            "cost": float(project_data['cost']),
            "currency": currency,
            "weekend_type": project_data.get('weekend_type', 'Fri-Sat'),
            "scope_description": project_data.get('scope_description', ''),
            "remarks": project_data.get('remarks', ''),
            "is_finished": is_fin,
            "actual_end_date": project_data.get('actual_end_date'),
            "is_cash_received": is_cash,
            "received_cash_date": project_data.get('received_cash_date'),
            "received_amount": float(project_data.get('received_amount', 0.0)),
            "status": 'Completed' if is_fin else project_data.get('status', 'In Progress'),
            "tasks_json": json.dumps(tasks),
            "milestones_json": json.dumps(milestones),
            "updated_at": datetime.now().isoformat()
        }
        try:
            r = requests.patch(
                f"{url}/rest/v1/projects?id=eq.{project_id}",
                headers=get_supabase_headers(),
                json=payload,
                timeout=8
            )
            if r.status_code in (200, 204):
                return
        except Exception as e:
            print(f"Supabase update failed, falling back to local: {e}")

    # Local update
    conn = get_connection()
    cursor = conn.cursor()
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
    if is_cloud_enabled():
        url, _ = get_cloud_credentials()
        try:
            r = requests.get(f"{url}/rest/v1/projects?select=*&order=id.desc", headers=get_supabase_headers(), timeout=8)
            if r.status_code == 200:
                projects = []
                for item in r.json():
                    item['tasks'] = json.loads(item['tasks_json']) if item.get('tasks_json') else []
                    item['milestones'] = json.loads(item['milestones_json']) if item.get('milestones_json') else []
                    if not item.get('scheduled_end_date'):
                        item['scheduled_end_date'] = item.get('deadline', '')
                    if not item.get('currency'):
                        item['currency'] = 'EGP'
                    projects.append(item)
                return projects
        except Exception as e:
            print(f"Supabase read failed, falling back to local: {e}")

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
    if is_cloud_enabled():
        url, _ = get_cloud_credentials()
        try:
            r = requests.get(f"{url}/rest/v1/projects?id=eq.{project_id}&select=*&limit=1", headers=get_supabase_headers(), timeout=8)
            if r.status_code == 200 and r.json():
                item = r.json()[0]
                item['tasks'] = json.loads(item['tasks_json']) if item.get('tasks_json') else []
                item['milestones'] = json.loads(item['milestones_json']) if item.get('milestones_json') else []
                if not item.get('scheduled_end_date'):
                    item['scheduled_end_date'] = item.get('deadline', '')
                if not item.get('currency'):
                    item['currency'] = 'EGP'
                return item
        except Exception:
            pass

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
    if is_cloud_enabled():
        url, _ = get_cloud_credentials()
        try:
            requests.delete(f"{url}/rest/v1/projects?id=eq.{project_id}", headers=get_supabase_headers(), timeout=8)
        except Exception:
            pass

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def get_received_cash_records():
    all_projs = get_all_projects()
    records = [
        p for p in all_projs 
        if p.get('is_cash_received') and p.get('received_cash_date')
    ]
    records.sort(key=lambda x: x.get('received_cash_date', ''), reverse=True)
    return records

def get_pending_payment_followups():
    all_projs = get_all_projects()
    today = date.today()
    followups = []
    
    pending = [p for p in all_projs if p.get('is_finished') and not p.get('is_cash_received')]
    pending.sort(key=lambda x: x.get('actual_end_date') or '', reverse=False)

    for item in pending:
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

# ---------------- 1-TAP BACKUP & RESTORE UTILITIES ----------------
def export_database_json():
    """Serializes all project records into a clean portable JSON backup string."""
    projs = get_all_projects()
    return json.dumps(projs, indent=2, ensure_ascii=False)

def import_database_json(json_content):
    """Restores projects from a JSON backup into the active database."""
    try:
        data = json.loads(json_content)
        if not isinstance(data, list):
            return False, "Invalid format: Expected a list of projects."
        
        count = 0
        for item in data:
            # Check if project code already exists
            existing = [p for p in get_all_projects() if p.get('project_code') == item.get('project_code')]
            if existing:
                update_project(existing[0]['id'], item)
            else:
                save_project(item)
            count += 1
        return True, f"Successfully imported/synchronized {count} projects!"
    except Exception as e:
        return False, f"Import error: {str(e)}"
