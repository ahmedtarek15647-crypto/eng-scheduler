"""
EngScheduler Pro - Engineering Project Intake & Cash Flow Management Web App.
Features:
1. Client Name (Input)
2. Automatic Project Code (e.g. 26-0001, 26-0002...)
3. Project Start Date (Input)
4. Project Scheduled End Date (Input)
5. Project Cash (100% Value) with EGP & multi-currency support
6. Remarks Tab for each project (Editable)
7. Project Finished Checkbox + Actual End Date (Auto-syncs tasks to Completed via callback)
8. Cash Received Checkbox + Received Cash Date (Auto-syncs milestones to Paid via callback)
9. Received Cash Financial Panel (Chronological ledger + Monthly Inflow Breakdown)
10. 10-Day Follow-Up Reminder Engine (Active until cash received)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta

from database import (
    init_db, save_project, update_project, get_all_projects, 
    get_project_by_id, delete_project, get_next_project_code,
    get_received_cash_records, get_pending_payment_followups,
    export_database_json, import_database_json, is_cloud_enabled
)
from scheduler_engine import generate_schedule, DISCIPLINE_TEMPLATES
from export_utils import generate_excel_schedule, format_whatsapp_proposal

# Page setup for mobile and desktop
st.set_page_config(
    page_title="EngScheduler Pro",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize database
init_db()

# Styling - Fully compatible with both Dark Theme and Light Theme
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .alert-call-due {
        background-color: rgba(220, 38, 38, 0.15);
        border: 1px solid #ef4444;
        border-left: 6px solid #dc2626;
        padding: 14px 18px;
        border-radius: 8px;
        margin-bottom: 16px;
        color: #f87171;
    }
    .alert-call-notice {
        background-color: rgba(217, 119, 6, 0.15);
        border: 1px solid #f59e0b;
        border-left: 6px solid #d97706;
        padding: 14px 18px;
        border-radius: 8px;
        margin-bottom: 16px;
        color: #fbbf24;
    }
    .status-badge-fin {
        background-color: rgba(16, 185, 129, 0.2);
        color: #34d399;
        border: 1px solid #10b981;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .status-badge-pending {
        background-color: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid #f59e0b;
        padding: 4px 12px;
        border-radius: 12px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# Callbacks for instant, reliable checkbox toggling
def on_finish_toggle(proj_id):
    p = get_project_by_id(proj_id)
    if not p:
        return
    is_fin = st.session_state.get(f"chk_fin_{proj_id}", False)
    p["is_finished"] = 1 if is_fin else 0
    p["actual_end_date"] = date.today().strftime("%Y-%m-%d") if is_fin else None
    p["status"] = "Completed" if is_fin else "In Progress"
    if is_fin:
        for t in p.get("tasks", []):
            t["status"] = "Completed"
            t["progress"] = 100
    update_project(proj_id, p)

def on_cash_toggle(proj_id):
    p = get_project_by_id(proj_id)
    if not p:
        return
    is_cash = st.session_state.get(f"chk_cash_{proj_id}", False)
    p["is_cash_received"] = 1 if is_cash else 0
    p["received_cash_date"] = date.today().strftime("%Y-%m-%d") if is_cash else None
    p["received_amount"] = p["cost"] if is_cash else 0.0
    if is_cash:
        for m in p.get("milestones", []):
            m["status"] = "Paid"
    else:
        for m in p.get("milestones", []):
            m["status"] = "Pending"
    update_project(proj_id, p)

def mark_cash_received_callback(proj_id):
    full_p = get_project_by_id(proj_id)
    if not full_p:
        return
    full_p["is_cash_received"] = 1
    full_p["received_cash_date"] = date.today().strftime("%Y-%m-%d")
    full_p["received_amount"] = full_p["cost"]
    for m in full_p.get("milestones", []):
        m["status"] = "Paid"
    update_project(proj_id, full_p)
    
    # Callback executes before widget instantiation, so modifying session_state is 100% legal
    st.session_state[f"chk_cash_{proj_id}"] = True
    st.session_state[f"rcv_date_{proj_id}"] = date.today()
    st.session_state[f"rcv_amt_{proj_id}"] = float(full_p["cost"])


# ---------------- TOP ALERT: 10-DAY CALL FOLLOW-UP REMINDER ----------------
followups = get_pending_payment_followups()
calls_due_now = [f for f in followups if f["is_call_due_now"] or f["days_since_finished"] >= 10]

if calls_due_now:
    st.markdown(f"""
    <div class="alert-call-due">
        <strong>⚠️ PAYMENT COLLECTION REMINDER:</strong> You have <strong>{len(calls_due_now)} finished project(s)</strong> awaiting payment where a 10-day client call cycle is active!
        <br><em>Check the '📞 Payment Call Follow-Ups' tab to review client contacts and log received cash.</em>
    </div>
    """, unsafe_allow_html=True)

# Header
st.title("🏗️ EngScheduler Pro")
st.caption("Engineering Project Intake • Critical Path Scheduling • Cash Flow Tracking • Payment Collection System")

# Navigation Tabs
tab_new, tab_manage, tab_cash_panel, tab_followups, tab_export = st.tabs([
    "➕ 1. New Project Intake",
    "📊 2. Project Tracking & WBS",
    "💰 3. Received Cash Panel (Monthly)",
    f"📞 4. Payment Call Follow-Ups ({len(followups)})",
    "📤 5. Export & Client Share"
])

# ---------------- TAB 1: NEW PROJECT INTAKE ----------------
with tab_new:
    next_code = get_next_project_code()
    st.subheader("New Project Registration")
    st.write("Fill in client details and dates to automatically allocate project code and WBS schedule.")

    with st.form("new_project_form"):
        r1_col1, r1_col2 = st.columns([1, 2])
        with r1_col1:
            st.text_input("Project Number (Automatic)", value=next_code, disabled=True, help="Automatically numbered based on current year (e.g. 26-0001)")
        with r1_col2:
            project_name = st.text_input("Project Title / Site Name*", placeholder="e.g. Residential Villa (G+1) Structural Package")

        r2_col1, r2_col2 = st.columns(2)
        with r2_col1:
            client_name = st.text_input("Client Name*", placeholder="e.g. Eng. Khalid Al-Mansoor / Al-Futtaim Properties")
            client_contact = st.text_input("Client Phone / WhatsApp (Optional)", placeholder="e.g. +20 10 1234 5678")
            discipline = st.selectbox("Engineering Discipline", list(DISCIPLINE_TEMPLATES.keys()))

        with r2_col2:
            today = date.today()
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                start_date = st.date_input("Project Start Date*", value=today)
            with col_d2:
                scheduled_end_date = st.date_input("Scheduled End Date (Deadline)*", value=today + timedelta(days=30))

            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                project_cash = st.number_input("Project Cash (100% Value)*", min_value=0.0, value=50000.0, step=1000.0)
            with col_c2:
                currency = st.selectbox("Currency", ["EGP", "USD", "SAR", "AED", "EUR", "QAR", "KWD"], index=0)

        weekend_type = st.selectbox(
            "Non-Working Days (Weekend)",
            ["Fri-Sat (Middle East Standard)", "Sat-Sun (International)", "Fri-Only (6-day week)", "Sun-Only (6-day week)"]
        )

        remarks_input = st.text_area(
            "Project Remarks / Notes (Scope, constraints, deliverables)",
            placeholder="Add any specific scope notes, agreed milestone stages, client requirements, or site specifications..."
        )

        create_btn = st.form_submit_button("🚀 Create Project & Generate Schedule", use_container_width=True)

    if create_btn:
        if not project_name.strip() or not client_name.strip():
            st.error("Please fill in both Project Title and Client Name.")
        elif scheduled_end_date <= start_date:
            st.error("Scheduled End Date must be after the Start Date.")
        else:
            weekend_code = "Fri-Sat" if "Fri-Sat" in weekend_type else ("Sat-Sun" if "Sat-Sun" in weekend_type else ("Fri-Only" if "Fri-Only" in weekend_type else "Sun-Only"))
            
            with st.spinner("Calculating Critical Path & Invoicing Milestones..."):
                schedule_res = generate_schedule(
                    start_str=start_date.strftime("%Y-%m-%d"),
                    deadline_str=scheduled_end_date.strftime("%Y-%m-%d"),
                    discipline=discipline,
                    total_cost=project_cash,
                    currency=currency,
                    weekend_type=weekend_code
                )

                project_record = {
                    "project_code": next_code,
                    "name": project_name,
                    "client_name": client_name,
                    "client_contact": client_contact,
                    "discipline": discipline,
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "scheduled_end_date": scheduled_end_date.strftime("%Y-%m-%d"),
                    "cost": project_cash,
                    "currency": currency,
                    "weekend_type": weekend_code,
                    "scope_description": remarks_input,
                    "remarks": remarks_input,
                    "is_finished": 0,
                    "actual_end_date": None,
                    "is_cash_received": 0,
                    "received_cash_date": None,
                    "received_amount": 0.0,
                    "status": "In Progress",
                    "tasks": schedule_res["tasks"],
                    "milestones": schedule_res["milestones"]
                }

                new_id = save_project(project_record)
                st.session_state["active_proj_id"] = new_id
                st.success(f"✅ Project **{next_code}** created successfully with currency **{currency}**! Switched to Tracking tab.")
                st.rerun()

# ---------------- TAB 2: PROJECT TRACKING & WBS ----------------
with tab_manage:
    all_projects = get_all_projects()

    if not all_projects:
        st.info("No projects yet. Use the 'New Project Intake' tab to create your first project.")
    else:
        project_dict = {p['id']: f"{p.get('project_code', 'N/A')} | {p['name']} ({p['client_name']})" for p in all_projects}
        active_id = st.session_state.get("active_proj_id", all_projects[0]["id"])
        
        default_index = 0
        if active_id in project_dict:
            default_index = list(project_dict.keys()).index(active_id)

        col_sel, col_stat = st.columns([3, 1])
        with col_sel:
            selected_id = st.selectbox(
                "Select Project",
                options=list(project_dict.keys()),
                format_func=lambda x: project_dict[x],
                index=default_index
            )
            st.session_state["active_proj_id"] = selected_id

        curr = get_project_by_id(selected_id)

        if curr:
            proj_currency = curr.get("currency") or "EGP"
            
            # Synchronize session state keys from database before widgets instantiate
            fin_key = f"chk_fin_{curr['id']}"
            cash_key = f"chk_cash_{curr['id']}"
            
            db_fin = bool(curr.get("is_finished", 0))
            db_cash = bool(curr.get("is_cash_received", 0))

            if fin_key not in st.session_state or st.session_state.get(f"_synced_fin_{curr['id']}") != db_fin:
                st.session_state[fin_key] = db_fin
                st.session_state[f"_synced_fin_{curr['id']}"] = db_fin

            if cash_key not in st.session_state or st.session_state.get(f"_synced_cash_{curr['id']}") != db_cash:
                st.session_state[cash_key] = db_cash
                st.session_state[f"_synced_cash_{curr['id']}"] = db_cash

            # Quick Action Status Checkboxes Container (Theme-aware border container)
            st.markdown("### ⚡ Project Status & Execution Checkboxes")
            
            with st.container(border=True):
                chk_col1, chk_col2 = st.columns(2)
                
                # Checkbox 1: Finish Project + Actual End Date
                with chk_col1:
                    is_fin_check = st.checkbox(
                        "🏁 Project Finished / Completed", 
                        key=fin_key,
                        on_change=on_finish_toggle,
                        args=(curr['id'],)
                    )
                    
                    actual_end_val = None
                    if is_fin_check:
                        default_actual = (
                            datetime.strptime(curr["actual_end_date"], "%Y-%m-%d").date()
                            if curr.get("actual_end_date")
                            else date.today()
                        )
                        actual_end_val = st.date_input(
                            "Actual End Date",
                            value=default_actual,
                            key=f"act_end_{curr['id']}"
                        )
                    else:
                        st.caption("Project is currently in progress.")

                # Checkbox 2: Receive Cash + Received Cash Date
                with chk_col2:
                    is_cash_check = st.checkbox(
                        "💰 Cash Received (100% Paid)", 
                        key=cash_key,
                        on_change=on_cash_toggle,
                        args=(curr['id'],)
                    )
                    
                    received_date_val = None
                    received_amt_val = curr.get("received_amount", curr["cost"])
                    if is_cash_check:
                        default_cash_date = (
                            datetime.strptime(curr["received_cash_date"], "%Y-%m-%d").date()
                            if curr.get("received_cash_date")
                            else date.today()
                        )
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            received_date_val = st.date_input(
                                "Cash Received Date",
                                value=default_cash_date,
                                key=f"rcv_date_{curr['id']}"
                            )
                        with col_c2:
                            received_amt_val = st.number_input(
                                f"Amount ({proj_currency})",
                                value=float(curr.get("received_amount") or curr["cost"]),
                                step=500.0,
                                key=f"rcv_amt_{curr['id']}"
                            )
                    else:
                        st.caption("Payment pending collection.")

            # Remarks Tab / Section
            st.markdown("### 📝 Project Remarks & Scope Notes")
            updated_remarks = st.text_area(
                "Remarks & Revision Log",
                value=curr.get("remarks", ""),
                height=110,
                key=f"remarks_{curr['id']}",
                placeholder="Log client revision requests, phone call notes, municipal submission dates..."
            )

            # Explicit Save Button for custom dates, amounts, and remarks
            if st.button("💾 Save Project Status & Remarks", type="primary", use_container_width=True):
                curr["is_finished"] = 1 if st.session_state.get(fin_key) else 0
                curr["actual_end_date"] = actual_end_val.strftime("%Y-%m-%d") if is_fin_check and actual_end_val else None
                curr["is_cash_received"] = 1 if st.session_state.get(cash_key) else 0
                curr["received_cash_date"] = received_date_val.strftime("%Y-%m-%d") if is_cash_check and received_date_val else None
                curr["received_amount"] = received_amt_val if is_cash_check else 0.0
                curr["remarks"] = updated_remarks
                curr["status"] = "Completed" if curr["is_finished"] else "In Progress"
                
                if curr["is_finished"]:
                    for t in curr.get("tasks", []):
                        t["status"] = "Completed"
                        t["progress"] = 100
                if curr["is_cash_received"]:
                    for m in curr.get("milestones", []):
                        m["status"] = "Paid"

                update_project(curr["id"], curr)
                st.success("✅ Changes saved! Status and Milestones are synchronized.")
                st.rerun()

            st.write("---")

            # Project Schedule Overview & Gantt
            st.markdown(f"### 📅 Schedule & Deliverables: {curr.get('project_code', '')} - {curr['name']}")
            
            # Metrics
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Project Cash (100%)", f"{curr['cost']:,.2f} {proj_currency}")
            m_col2.metric("Start Date", curr["start_date"])
            m_col3.metric("Scheduled End Date", curr.get("scheduled_end_date", curr.get("deadline", "")))
            
            with m_col4:
                st.write("**Execution / Cash**")
                fin_label = '<span class="status-badge-fin">Finished</span>' if curr.get("is_finished") else '<span class="status-badge-pending">In Progress</span>'
                cash_label = '<span class="status-badge-fin">Cash Received</span>' if curr.get("is_cash_received") else '<span class="status-badge-pending">Payment Due</span>'
                st.markdown(f"{fin_label} &nbsp; {cash_label}", unsafe_allow_html=True)

            # Interactive Plotly Gantt Chart
            tasks = curr.get("tasks", [])
            if tasks:
                df_gantt = pd.DataFrame(tasks)
                df_gantt["Start"] = pd.to_datetime(df_gantt["start"])
                df_gantt["Finish"] = pd.to_datetime(df_gantt["end"])
                df_gantt["Task_Label"] = df_gantt["phase"]

                fig = px.timeline(
                    df_gantt,
                    x_start="Start",
                    x_end="Finish",
                    y="Task_Label",
                    color="phase",
                    hover_data=["deliverable", "working_days", "budget"],
                    title="Phase Timeline & Critical Deliverables"
                )
                fig.update_yaxes(autorange="reversed")
                fig.update_layout(
                    height=320,
                    margin=dict(l=10, r=10, t=35, b=10),
                    showlegend=False,
                    xaxis_title="",
                    yaxis_title=""
                )
                st.plotly_chart(fig, use_container_width=True)

# ---------------- TAB 3: RECEIVED CASH FINANCIAL PANEL ----------------
with tab_cash_panel:
    st.subheader("💰 Received Cash Ledger & Monthly Inflow Analytics")
    st.write("Track all collected project payments and view monthly financial aggregates.")

    received_records = get_received_cash_records()
    all_projs = get_all_projects()

    # Determine default/primary currency from projects or fallback to EGP
    active_currencies = list({p.get("currency") or "EGP" for p in all_projs}) if all_projs else ["EGP"]
    primary_curr = active_currencies[0] if len(active_currencies) == 1 else "EGP"

    # Financial totals
    if len(active_currencies) <= 1:
        total_billed = sum(p["cost"] for p in all_projs)
        total_received = sum(r["received_amount"] for r in received_records)
        total_uncollected = total_billed - total_received

        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Total Collected Cash", f"{total_received:,.2f} {primary_curr}")
        c_m2.metric("Total Uncollected (Outstanding)", f"{total_uncollected:,.2f} {primary_curr}")
        c_m3.metric("Paid Projects Count", f"{len(received_records)} Projects")
    else:
        # Multi-currency breakdown
        st.write("#### Multi-Currency Financial Summary:")
        cols_cur = st.columns(len(active_currencies))
        for idx, cur in enumerate(active_currencies):
            cur_projs = [p for p in all_projs if (p.get("currency") or "EGP") == cur]
            cur_rcv = [r for r in received_records if (r.get("currency") or "EGP") == cur]
            cur_billed = sum(p["cost"] for p in cur_projs)
            cur_paid = sum(r["received_amount"] for r in cur_rcv)
            cur_out = cur_billed - cur_paid
            with cols_cur[idx]:
                st.metric(f"Collected ({cur})", f"{cur_paid:,.2f} {cur}")
                st.caption(f"Outstanding: {cur_out:,.2f} {cur} ({len(cur_rcv)}/{len(cur_projs)} projects paid)")

    st.write("---")

    if not received_records:
        st.info("No cash received yet. Mark projects as 'Cash Received' in Tab 2 or Tab 4 to populate this ledger.")
    else:
        df_rcv = pd.DataFrame(received_records)
        df_rcv["received_date"] = pd.to_datetime(df_rcv["received_cash_date"])
        df_rcv["month_year"] = df_rcv["received_date"].dt.strftime("%Y-%m (%B)")

        col_ledger, col_monthly = st.columns([3, 2])

        # Left Column: Chronological Ledger
        with col_ledger:
            st.markdown("#### 📜 Chronological Cash Receipts")
            st.write("Sorted by date of receipt (latest first):")
            
            display_df = df_rcv[[
                "received_cash_date", "project_code", "client_name", "received_amount", "currency"
            ]].copy()
            display_df.columns = ["Receipt Date", "Project Code", "Client", "Received Amount", "Currency"]
            display_df["Received Amount"] = display_df["Received Amount"].apply(lambda x: f"{x:,.2f}")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Right Column: Monthly Aggregation & Chart
        with col_monthly:
            st.markdown("#### 📅 Monthly Cash Breakdown")
            monthly_summary = df_rcv.groupby(["month_year", "currency"])["received_amount"].sum().reset_index()
            monthly_summary.columns = ["Month", "Currency", "Total Cash Inflow"]
            
            fig_bar = px.bar(
                monthly_summary,
                x="Month",
                y="Total Cash Inflow",
                color="Currency",
                text="Total Cash Inflow",
                title="Cash Inflow by Month",
                color_discrete_sequence=["#10b981", "#3b82f6", "#f59e0b"]
            )
            fig_bar.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_bar.update_layout(height=280, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)

            formatted_monthly = monthly_summary.copy()
            formatted_monthly["Total Cash Inflow"] = formatted_monthly["Total Cash Inflow"].apply(lambda x: f"{x:,.2f}")
            st.table(formatted_monthly)

# ---------------- TAB 4: 10-DAY CALL FOLLOW-UP REMINDERS ----------------
with tab_followups:
    st.subheader("📞 Client Payment Call Reminders (Every 10 Days)")
    st.write(
        "This automated engine tracks all **finished projects** where **cash has not yet been collected**. "
        "It notifies you to call the client every 10 days until you check 'Cash Received'."
    )

    pending_calls = get_pending_payment_followups()

    if not pending_calls:
        st.success("🎉 Great job! No pending follow-ups. All completed projects have their cash received!")
    else:
        for item in pending_calls:
            days = item["days_since_finished"]
            cycle = item["cycle_number"]
            code = item.get("project_code", "N/A")
            client = item.get("client_name", "N/A")
            phone = item.get("client_contact") or "No phone recorded"
            cur = item.get("currency") or "EGP"
            amt = f"{item.get('cost', 0):,.2f} {cur}"
            actual_end = item.get("actual_end_date") or "Unknown"

            alert_class = "alert-call-due" if (days >= 10 and days % 10 <= 2) or days >= 30 else "alert-call-notice"

            st.markdown(f"""
            <div class="{alert_class}">
                <h4 style="margin:0 0 6px 0;">🔔 Project {code} — {item.get('name')}</h4>
                <strong>Client:</strong> {client} &nbsp;|&nbsp; <strong>Phone:</strong> {phone} &nbsp;|&nbsp; <strong>Unpaid Fee:</strong> {amt}<br>
                <strong>Completed On:</strong> {actual_end} ({days} days ago) &nbsp;|&nbsp; <strong>Follow-up Stage:</strong> Call Cycle #{cycle}
            </div>
            """, unsafe_allow_html=True)

            btn_col1, btn_col2 = st.columns([3, 1])
            with btn_col1:
                st.caption(f"Remarks: {item.get('remarks') or 'No notes logged.'}")
            with btn_col2:
                st.button(
                    "✅ Mark Cash Received",
                    key=f"quick_rcv_{item['id']}",
                    on_click=mark_cash_received_callback,
                    args=(item['id'],)
                )

            st.write("---")

# ---------------- TAB 5: EXPORT & CLIENT SHARE ----------------
with tab_export:
    # 1. ALWAYS VISIBLE: Cloud Database Status & 1-Tap Mobile Backup/Restore
    st.subheader("💾 Database Backup & Cloud Sync")
    
    with st.container(border=True):
        st.markdown("#### ☁️ Cloud Database Status")
        if is_cloud_enabled():
            st.success("🟢 **Connected to Supabase Cloud Database!** Your data is permanently synchronized 24/7 in the cloud.")
        else:
            st.info("🟡 **Running on Local Database.** To enable permanent 24/7 cloud sync across all devices, configure your Supabase keys in Streamlit Secrets.")

    col_bk1, col_bk2 = st.columns(2)

    with col_bk1:
        st.markdown("#### 📥 1-Tap Mobile Backup")
        st.write("Download a complete backup of all your projects directly to your phone or computer:")
        backup_json = export_database_json()
        st.download_button(
            label="⬇️ Download All Projects Backup (.json)",
            data=backup_json,
            file_name=f"eng_scheduler_backup_{date.today().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True
        )

    with col_bk2:
        st.markdown("#### 📤 Restore / Import Backup")
        st.write("Restore projects from a backup file anytime:")
        uploaded_backup = st.file_uploader("Upload Backup JSON", type=["json"], key="backup_upload")
        if uploaded_backup is not None:
            if st.button("🔄 Restore Database from File", use_container_width=True):
                content = uploaded_backup.read().decode("utf-8")
                ok, msg = import_database_json(content)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.write("---")

    # 2. Individual Project Export (Excel & WhatsApp)
    st.subheader("📋 Project Proposal & Excel Export")
    all_projects = get_all_projects()

    if not all_projects:
        st.info("No projects created yet. Go to '➕ 1. New Project Intake' to create your first project schedule.")
    else:
        active_id = st.session_state.get("active_proj_id", all_projects[0]["id"])
        selected_project = get_project_by_id(active_id)

        if selected_project:
            cur = selected_project.get("currency") or "EGP"
            st.markdown(f"### Exporting: **{selected_project.get('project_code', '')}** — {selected_project['name']}")

            # Live Status Summary Box using Streamlit native theme-aware container (Dark & Light mode compatible)
            is_fin = bool(selected_project.get("is_finished", 0))
            is_cash = bool(selected_project.get("is_cash_received", 0))
            
            with st.container(border=True):
                st.markdown(f"#### 📋 Project Live State: `{selected_project.get('project_code', '')}`")
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("Currency", cur)
                sc2.metric("Execution Status", "✅ Finished" if is_fin else "⏳ In Progress")
                sc3.metric("Cash Status", "💰 Paid in Full" if is_cash else "⏳ Payment Pending")
                if is_cash:
                    st.caption(f"Payment received on: **{selected_project.get('received_cash_date', date.today())}** — All Excel milestones will be exported as **PAID**.")
                else:
                    st.caption("Payment pending — Milestones will be exported according to schedule.")

            exp_col1, exp_col2 = st.columns(2)

            with exp_col1:
                st.markdown("### 📊 Excel Schedule (.xlsx)")
                st.write("Complete workbook with Project Code, Executive Summary, Invoicing Milestones, and WBS Schedule.")
                excel_bytes = generate_excel_schedule(selected_project)
                safe_name = f"{selected_project.get('project_code', 'proj')}_{selected_project['name'].replace(' ', '_').lower()}"
                st.download_button(
                    label=f"⬇️ Download Excel File ({cur})",
                    data=excel_bytes,
                    file_name=f"{safe_name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with exp_col2:
                st.markdown("### 📱 Instant WhatsApp / Text Proposal")
                st.write("Copy and send via WhatsApp directly from your mobile phone:")
                wa_msg = format_whatsapp_proposal(selected_project)
                st.text_area("Client Text Message", value=wa_msg, height=220)

            st.write("---")
            if st.button("🗑️ Delete This Project", type="secondary"):
                delete_project(selected_project["id"])
                st.warning(f"Project '{selected_project['name']}' deleted.")
                st.rerun()
