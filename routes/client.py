import requests
from datetime import date, timedelta
from flask import Blueprint, render_template, session, redirect, jsonify, request
from models import User, db
from services.enote_service import enote

client_bp = Blueprint(‘client’, **name**)

# ─── Утиліта: автооновлення enote_guid ─────────────────────────

def _sync_enote_guid(user: User) -> None:
“””
Якщо у користувача є телефон — шукає клієнта в Enote і оновлює enote_guid.
Викликати після логіну або вручну через /api/sync-guid.
“””
if not user.phone:
return
client_data = enote.get_client_by_phone(user.phone)
if client_data and client_data.get(‘id’):
new_guid = client_data[‘id’]
if user.enote_guid != new_guid:
user.enote_guid = new_guid
db.session.commit()
enote.clear_cache()

# ─── Сторінки ───────────────────────────────────────────────────

@client_bp.route(’/dashboard’)
def dashboard():
if “user_id” not in session:
return redirect(”/login”)
user = User.query.get(session[“user_id”])
if not user:
return redirect(”/login”)
if user.is_doctor:
return redirect(”/doctor”)
# Автосинхронізація GUID при відкритті кабінету
_sync_enote_guid(user)
return render_template(“dashboard.html”, user=user)

@client_bp.route(’/online-appointment’)
def online_appointment():
if “user_id” not in session:
return redirect(”/login”)
return render_template(“schedule.html”, user=User.query.get(session[“user_id”]))

@client_bp.route(’/settings’)
def settings():
if “user_id” not in session:
return redirect(”/login”)
return render_template(“settings.html”)

# ─── API: дані клієнта ──────────────────────────────────────────

@client_bp.route(’/api/my-pets’)
def my_pets():
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Не авторизовано”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify([])
return jsonify(enote.get_pets_by_owner(user.enote_guid))

@client_bp.route(’/api/my-analyses’)
def my_analyses():
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Не авторизовано”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify([])
return jsonify(enote.get_analyses_by_owner(user.enote_guid))

@client_bp.route(’/api/my-visits’)
def my_visits():
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Не авторизовано”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify([])
return jsonify(enote.get_visits_by_owner(user.enote_guid))

@client_bp.route(’/api/my-appointments’)
def my_appointments():
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Не авторизовано”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify([])
return jsonify(enote.get_appointments_by_owner(user.enote_guid) or [])

@client_bp.route(’/api/my-profile’)
def my_profile():
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Не авторизовано”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify({“phone”: user.phone if user else “”, “email”: user.email if user else “”})
contact = enote.get_contact_by_owner(user.enote_guid)
if contact:
surname = contact.get(‘surname’) or contact.get(‘Фамилия’, ‘’)
first_name = contact.get(‘firstName’) or contact.get(‘Имя’, ‘’)
return jsonify({
“full_name”: f”{surname} {first_name}”.strip(),
“phone”: user.phone,
“email”: user.email
})
return jsonify({“phone”: user.phone, “email”: user.email})

# ─── API: утиліти ───────────────────────────────────────────────

@client_bp.route(’/api/clear-cache’)
def clear_cache():
enote.clear_cache()
return jsonify({“message”: “Кеш очищено”})

@client_bp.route(’/api/sync-guid’)
def sync_guid():
“”“Оновлює enote_guid поточного користувача з Enote за номером телефону.”””
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Unauthorized”}), 401
user = User.query.get(user_id)
if not user:
return jsonify({“error”: “User not found”}), 404

```
client_data = enote.get_client_by_phone(user.phone)
if not client_data:
    return jsonify({"error": "Клієнта не знайдено в Enote за цим номером телефону", "phone": user.phone}), 404

old_guid = user.enote_guid
new_guid = client_data['id']
user.enote_guid = new_guid
db.session.commit()
enote.clear_cache()

return jsonify({
    "status": "ok",
    "phone": user.phone,
    "old_guid": old_guid,
    "new_guid": new_guid,
    "mainContactSubjectId": client_data.get('mainContactSubjectId'),
    "subject_ids": client_data.get('subject_ids'),
})
```

@client_bp.route(’/api/schedule’)
def api_schedule():
return jsonify(enote.get_schedule())

# ─── Debug ──────────────────────────────────────────────────────

@client_bp.route(’/debug-owner’)
def debug_owner():
“””
Детальна діагностика: показує client_id, subject_ids, усіх тварин з API
і яких з них пропускає фільтр.
“””
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Unauthorized”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify({“error”: “No enote_guid”})

```
owner_guid = user.enote_guid

# Усі тварини що повертає API для цього client_id
raw_pets = enote._api_get_all('patients', {'client_id': owner_guid})

# Subject IDs клієнта
subject_ids = set(enote.get_client_subject_ids(owner_guid))

# Фільтровані
filtered = [p for p in raw_pets if p.get('ownerId') in subject_ids]

return jsonify({
    "owner_guid": owner_guid,
    "subject_ids": list(subject_ids),
    "total_from_api": len(raw_pets),
    "after_filter": len(filtered),
    "raw_pets": [{
        "id": p.get("id"),
        "name": p.get("name"),
        "ownerId": p.get("ownerId"),
        "in_filter": p.get("ownerId") in subject_ids,
    } for p in raw_pets],
})
```

@client_bp.route(’/debug-visits’)
def debug_visits():
“”“Показує сирі поля першого візиту і запису — для діагностики Invalid Date і [object Object].”””
user_id = session.get(“user_id”)
if not user_id:
return jsonify({“error”: “Unauthorized”}), 401
user = User.query.get(user_id)
if not user or not user.enote_guid:
return jsonify({“error”: “No enote_guid”})
return jsonify(enote.debug_visit_fields(user.enote_guid))

@client_bp.route(’/debug-schedule’)
def debug_schedule():
date_str = request.args.get(‘date’, date.today().isoformat())
entity_id = enote.get_entity_id()
doctors = enote.get_doctors_list()
if not doctors:
return jsonify({‘error’: ‘no doctors’})
emp_id = doctors[0][‘id’]
raw = enote.debug_raw(‘bookings/available_slots’, {
‘date’: date_str,
‘entity_id’: entity_id,
‘employee_id’: emp_id
})
return jsonify(raw)

@client_bp.route(’/test-api’)
def test_api():
if not enote.api_key:
return jsonify({“error”: “No API Key”})

```
client_data = enote.get_client_by_phone('+380685442567')
client_id = client_data['id'] if client_data else None

raw_pets = []
subject_ids = []
if client_id:
    raw_pets = enote._api_get_all('patients', {'client_id': client_id})
    subject_ids = enote.get_client_subject_ids(client_id)

return jsonify({
    "client_data": client_data,
    "client_id": client_id,
    "subject_ids": subject_ids,
    "pets_from_api": len(raw_pets),
    "owner_ids_in_pets": list(set(p.get('ownerId') for p in raw_pets if p.get('ownerId'))),
    "pets_sample": [{
        "id": p.get("id"),
        "name": p.get("name"),
        "ownerId": p.get("ownerId"),
    } for p in raw_pets[:10]],
})
```

@client_bp.route(’/test-api-url’)
def test_api_url():
if not enote.api_key:
return jsonify({“error”: “ENOTE_API_KEY not set”})

```
endpoints_to_try = [
    f"{enote.base_url}/enote9991/hs/api/v2",
    f"{enote.base_url}/{enote.clinic_guid}/hs/api/v2",
    f"{enote.base_url}/api/v2",
]

results = {}
headers = {'apikey': enote.api_key}
for url in endpoints_to_try:
    try:
        r = requests.get(f"{url}/clients?phone_number=%2B380685442567", headers=headers, timeout=15)
        results[url] = {
            "status": r.status_code,
            "preview": r.text[:200]
        }
    except Exception as e:
        results[url] = {"error": str(e)}

return jsonify(results)
```