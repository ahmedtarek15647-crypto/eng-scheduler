"""
Engineering Project Scheduling & Critical Path Engine.
Calculates realistic working days, allocates engineering WBS phases,
checks schedule feasibility, and generates payment milestone schedules.
"""

from datetime import datetime, timedelta
import math

DISCIPLINE_TEMPLATES = {
    "Structural Engineering": [
        {
            "phase": "1. Inception & Structural Criteria",
            "name": "Design Criteria & Architecture Review",
            "weight": 0.12,
            "deliverable": "Design Criteria Report & Grid Verification",
            "cost_weight": 0.10
        },
        {
            "phase": "2. Structural Analysis & Modeling",
            "name": "3D Analysis Model & Gravity/Lateral Loads",
            "weight": 0.28,
            "deliverable": "Analysis Model & Preliminary Sizing Calculations",
            "cost_weight": 0.30
        },
        {
            "phase": "3. Substructure & Foundation Design",
            "name": "Foundation Design & Geotechnical Checks",
            "weight": 0.18,
            "deliverable": "Foundation Layout & Soil Bearing Verification",
            "cost_weight": 0.15
        },
        {
            "phase": "4. Detailed Drafting & Reinforcement",
            "name": "Superstructure Framing & Rebar Details",
            "weight": 0.24,
            "deliverable": "CAD/Revit Structural Drawing Set",
            "cost_weight": 0.25
        },
        {
            "phase": "5. BOQ & Final Submittal",
            "name": "Material Takeoff (Concrete/Steel) & Sign-off",
            "weight": 0.18,
            "deliverable": "Final BOQ, Calculation Sheet & Signed Drawings",
            "cost_weight": 0.20
        }
    ],
    "Architectural Design": [
        {
            "phase": "1. Programming & Brief",
            "name": "Client Requirements & Space Planning",
            "weight": 0.12,
            "deliverable": "Space Program & Concept Diagrams",
            "cost_weight": 0.10
        },
        {
            "phase": "2. Schematic Design",
            "name": "Floor Plans, Circulation & Zoning",
            "weight": 0.28,
            "deliverable": "Schematic Floor Plans & Site Plan",
            "cost_weight": 0.30
        },
        {
            "phase": "3. 3D Massing & Elevations",
            "name": "Exterior Facades, Sections & 3D Views",
            "weight": 0.22,
            "deliverable": "3D Renders & Building Elevations",
            "cost_weight": 0.20
        },
        {
            "phase": "4. Permit & Construction Drawings",
            "name": "Detailed Architectural Working Drawings",
            "weight": 0.24,
            "deliverable": "Full Architectural Working Set",
            "cost_weight": 0.25
        },
        {
            "phase": "5. Schedules & BOQ Handover",
            "name": "Door/Window Schedules, Finishes & BOQ",
            "weight": 0.14,
            "deliverable": "Finishes Schedule, BOQ & Client Package",
            "cost_weight": 0.15
        }
    ],
    "MEP Engineering": [
        {
            "phase": "1. Calculations & Sizing",
            "name": "HVAC Heat Load, Water Demand & Power Sizing",
            "weight": 0.15,
            "deliverable": "MEP Design Basis & Sizing Calculations",
            "cost_weight": 0.15
        },
        {
            "phase": "2. Schematics & Single Line Diagrams",
            "name": "Electrical SLD & Piping/Duct Risers",
            "weight": 0.25,
            "deliverable": "Single Line Diagrams & Schematic Risers",
            "cost_weight": 0.25
        },
        {
            "phase": "3. Engineering Layouts & Routing",
            "name": "Lighting, Power, HVAC & Plumbing Layouts",
            "weight": 0.30,
            "deliverable": "Draft MEP Layout Drawings",
            "cost_weight": 0.30
        },
        {
            "phase": "4. Clash Detection & Coordination",
            "name": "Spatial Coordination with Structure & Architecture",
            "weight": 0.15,
            "deliverable": "Coordinated Combined Services Drawings",
            "cost_weight": 0.15
        },
        {
            "phase": "5. Equipment Schedules & BOQ",
            "name": "Equipment Schedules, BOQ & Specs",
            "weight": 0.15,
            "deliverable": "MEP BOQ & Equipment Specifications",
            "cost_weight": 0.15
        }
    ],
    "Interior Fitout": [
        {
            "phase": "1. Concept & Moodboard",
            "name": "Design Direction, Theme & Material Board",
            "weight": 0.15,
            "deliverable": "Approved Moodboard & Material Palette",
            "cost_weight": 0.15
        },
        {
            "phase": "2. Space Planning & Layout",
            "name": "Furniture Layout & Partition Plans",
            "weight": 0.25,
            "deliverable": "Dimensioned Furniture & Spatial Plans",
            "cost_weight": 0.25
        },
        {
            "phase": "3. Detailed Joinery & Millwork",
            "name": "Custom Cabinetry, Wall Cladding & Details",
            "weight": 0.30,
            "deliverable": "Shop Details for Millwork & Metalwork",
            "cost_weight": 0.30
        },
        {
            "phase": "4. Reflected Ceiling & Lighting",
            "name": "RCP, Lighting Fixtures & Power Drops",
            "weight": 0.15,
            "deliverable": "RCP Plans & Lighting Specifications",
            "cost_weight": 0.15
        },
        {
            "phase": "5. BOQ & Procurement Schedule",
            "name": "Loose Furniture & Finishes BOQ Handover",
            "weight": 0.15,
            "deliverable": "Full FF&E Schedule & Tender BOQ",
            "cost_weight": 0.15
        }
    ],
    "General Construction & Civil": [
        {
            "phase": "1. Site Survey & Mobilization",
            "name": "Topographic Survey & Site Logistics Plan",
            "weight": 0.12,
            "deliverable": "Site Setup & Survey Baseline Report",
            "cost_weight": 0.10
        },
        {
            "phase": "2. Earthworks & Utilities",
            "name": "Grading, Excavation & Subsurface Drainage",
            "weight": 0.25,
            "deliverable": "Earthworks Volume Calculations & Grading Plans",
            "cost_weight": 0.25
        },
        {
            "phase": "3. Infrastructure & Main Works",
            "name": "Primary Roads, Pavements & Structural Works",
            "weight": 0.33,
            "deliverable": "Infrastructure Layout & Construction Drawings",
            "cost_weight": 0.35
        },
        {
            "phase": "4. QA Inspections & Compliance",
            "name": "Field Quality Tests & Municipal Filings",
            "weight": 0.15,
            "deliverable": "Inspection Records & Approval Documentation",
            "cost_weight": 0.15
        },
        {
            "phase": "5. BOQ Reconciliation & Handover",
            "name": "As-Built Records & Final Quantity Settlement",
            "weight": 0.15,
            "deliverable": "Final As-Built BOQ & Project Closeout Dossier",
            "cost_weight": 0.15
        }
    ]
}

def is_working_day(date_obj, weekend_type="Fri-Sat"):
    """
    Checks if a given date is a working day based on weekend configuration.
    weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    """
    wd = date_obj.weekday()
    if weekend_type == "Fri-Sat":
        return wd not in (4, 5)  # Friday (4) and Saturday (5) off
    elif weekend_type == "Sat-Sun":
        return wd not in (5, 6)  # Saturday (5) and Sunday (6) off
    elif weekend_type == "Fri-Only":
        return wd != 4
    elif weekend_type == "Sun-Only":
        return wd != 6
    return True

def count_working_days(start_date, end_date, weekend_type="Fri-Sat"):
    """Counts total working days between start_date and end_date inclusive."""
    current = start_date
    working_days = 0
    while current <= end_date:
        if is_working_day(current, weekend_type):
            working_days += 1
        current += timedelta(days=1)
    return working_days

def add_working_days(start_date, num_days, weekend_type="Fri-Sat"):
    """Adds a specific number of working days to a start date."""
    if num_days <= 1:
        current = start_date
        while not is_working_day(current, weekend_type):
            current += timedelta(days=1)
        return current

    current = start_date
    days_counted = 1 if is_working_day(current, weekend_type) else 0
    
    while days_counted < num_days:
        current += timedelta(days=1)
        if is_working_day(current, weekend_type):
            days_counted += 1
            
    return current

def generate_schedule(start_str, deadline_str, discipline, total_cost, currency="USD", weekend_type="Fri-Sat"):
    """
    Main scheduling engine.
    Takes inputs, computes working days, allocates task durations,
    and returns a structured schedule with tasks, feasibility status, and payment milestones.
    """
    start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
    
    if deadline < start_date:
        raise ValueError("Deadline cannot be earlier than start date.")

    total_calendar_days = (deadline - start_date).days + 1
    total_working_days = count_working_days(start_date, deadline, weekend_type)

    if total_working_days < 5:
        feasibility_status = "CRITICAL: Under 5 working days available. Extreme overtime required."
        feasibility_level = "critical"
    elif total_working_days < 12:
        feasibility_status = "TIGHT: Compressed schedule. Parallel drafting tracks recommended."
        feasibility_level = "warning"
    else:
        feasibility_status = "HEALTHY: Adequate duration for standard engineering reviews."
        feasibility_level = "healthy"

    template = DISCIPLINE_TEMPLATES.get(discipline, DISCIPLINE_TEMPLATES["Structural Engineering"])

    tasks = []
    current_task_start = start_date
    # Ensure starting on a working day
    while not is_working_day(current_task_start, weekend_type):
        current_task_start += timedelta(days=1)

    allocated_days = 0
    total_tasks = len(template)

    for i, item in enumerate(template):
        is_last = (i == total_tasks - 1)
        if is_last:
            task_working_days = max(1, total_working_days - allocated_days)
        else:
            task_working_days = max(1, math.floor(total_working_days * item["weight"]))
            allocated_days += task_working_days

        task_end = add_working_days(current_task_start, task_working_days, weekend_type)
        if task_end > deadline:
            task_end = deadline

        phase_budget = round(total_cost * item["cost_weight"], 2)

        tasks.append({
            "id": i + 1,
            "phase": item["phase"],
            "name": item["name"],
            "start": current_task_start.strftime("%Y-%m-%d"),
            "end": task_end.strftime("%Y-%m-%d"),
            "working_days": task_working_days,
            "deliverable": item["deliverable"],
            "budget": phase_budget,
            "currency": currency,
            "progress": 0,
            "status": "Not Started"
        })

        # Next task starts next working day
        next_day = task_end + timedelta(days=1)
        while next_day <= deadline and not is_working_day(next_day, weekend_type):
            next_day += timedelta(days=1)
        current_task_start = next_day

    # Milestone payments (Standard 4-milestone engineering schedule)
    milestones = [
        {
            "milestone": "1. Mobilization & Advance",
            "trigger": "Contract Signing & Kickoff",
            "percentage": 20,
            "amount": round(total_cost * 0.20, 2),
            "due_date": start_date.strftime("%Y-%m-%d"),
            "status": "Pending"
        },
        {
            "milestone": "2. Preliminary Concept Approval",
            "trigger": f"Submittal of {tasks[1]['deliverable']}",
            "percentage": 30,
            "amount": round(total_cost * 0.30, 2),
            "due_date": tasks[1]['end'],
            "status": "Pending"
        },
        {
            "milestone": "3. Detailed Drawings & Draft BOQ",
            "trigger": f"Submittal of {tasks[3]['deliverable']}",
            "percentage": 35,
            "amount": round(total_cost * 0.35, 2),
            "due_date": tasks[3]['end'],
            "status": "Pending"
        },
        {
            "milestone": "4. Final Handover & Sign-off",
            "trigger": f"Delivery of {tasks[-1]['deliverable']}",
            "percentage": 15,
            "amount": round(total_cost * 0.15, 2),
            "due_date": deadline.strftime("%Y-%m-%d"),
            "status": "Pending"
        }
    ]

    return {
        "calendar_days": total_calendar_days,
        "working_days": total_working_days,
        "feasibility_status": feasibility_status,
        "feasibility_level": feasibility_level,
        "tasks": tasks,
        "milestones": milestones
    }
