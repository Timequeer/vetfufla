from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, render_template, session, redirect, jsonify, request
from models import User
from services.enote_service import enote

analytics_bp = Blueprint('analytics', __name__)


def doctor_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect("/login")
        user = User.query.get(user_id)
        if not user or not user.is_doctor:
            return redirect("/dashboard")
        return f(*args, **kwargs)
    return decorated


@analytics_bp.route('/analytics')
@doctor_required
def analytics_page():
    return render_template("analytics.html")


@analytics_bp.route('/api/analytics/summary')
@doctor_required
def analytics_summary():
    """
    Зведена аналітика для дашборду лікаря.
    Повертає JSON з візитами за останні 30 днів.
    """
    doctors = enote.get_doctors_list()
    doctor_map = {d['id']: f"{d.get('firstName','')} {d.get('surname','')}".strip() for d in doctors}

    today = datetime.today()
    from_date = today - timedelta(days=30)

    visit_counts_by_doctor = defaultdict(int)
    visit_counts_by_day = defaultdict(int)
    status_counts = defaultdict(int)

    try:
        entity_id = enote.get_entity_id()
    except Exception:
        entity_id = None

    if entity_id:
        current = from_date.date()
        end = today.date()
        while current <= end:
            date_str = current.isoformat()
            for doc_id, doc_name in doctor_map.items():
                slots, _ = enote._api_get_page('bookings/available_slots', {
                    'date': date_str,
                    'entity_id': entity_id,
                    'employee_id': doc_id,
                })
                for slot in slots:
                    history = slot.get('bookingStatusHistory') or []
                    last_status = history[-1].get('bookingStatus', 'UNKNOWN') if history else 'UNKNOWN'
                    status_counts[last_status] += 1
                    if last_status in ('COMPLETED', 'CHECKED_IN'):
                        visit_counts_by_doctor[doc_name] += 1
                        visit_counts_by_day[date_str] += 1
            current += timedelta(days=1)

    sorted_days = sorted(visit_counts_by_day.keys())

    return jsonify({
        "period": {
            "from": from_date.strftime('%Y-%m-%d'),
            "to": today.strftime('%Y-%m-%d'),
        },
        "by_doctor": {
            "labels": list(visit_counts_by_doctor.keys()),
            "values": list(visit_counts_by_doctor.values()),
        },
        "by_day": {
            "labels": sorted_days,
            "values": [visit_counts_by_day[d] for d in sorted_days],
        },
        "by_status": {
            "labels": list(status_counts.keys()),
            "values": list(status_counts.values()),
        },
        "totals": {
            "completed_visits": sum(v for k, v in status_counts.items() if k in ('COMPLETED', 'CHECKED_IN')),
            "scheduled": status_counts.get('SCHEDULED', 0),
            "cancelled": status_counts.get('CANCELLED', 0),
            "doctors_count": len(doctor_map),
        }
    })
