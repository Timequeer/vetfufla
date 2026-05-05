import os
import time
from datetime import date, timedelta, datetime
from typing import Optional
import requests


def _format_datetime(dt_str: str) -> str:
    """ISO8601 → 'YYYY-MM-DD HH:MM'"""
    if not dt_str:
        return ''
    try:
        clean = dt_str[:19]
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M")
    except:
        return dt_str


class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID', '38174e48-16f0-11ee-6d89-2ae983d8a0f0')
        self.api_key = os.getenv('ENOTE_API_KEY', 'e1d15077-3bcc-491b-839b-8ef83b5f9eb8')
        self.api_v2_base = f"{self.base_url}/{self.clinic_guid}/hs/api/v2"

        self.session = requests.Session()
        self.session.headers.update({'apikey': self.api_key})

        self._cache = {}
        self._cache_ttl = 600

    # ─── Базові методи ─────────────────────────────────────────
    def _api_get_page(self, endpoint: str, params: dict = None) -> tuple:
        url = f"{self.api_v2_base}/{endpoint}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = self.session.get(url, params=params, timeout=30)
            if not r.ok:
                return [], None
            resp = r.json()
            data = resp.get('data', [])
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
            pagination = resp.get('pagination') or {}
            next_token = pagination.get('next_page_token') if isinstance(pagination, dict) else None
            return items, next_token
        except Exception:
            return [], None

    def _api_get_all(self, endpoint: str, params: dict = None) -> list:
        all_items = []
        params = dict(params or {})
        params.setdefault('page_size', 100)
        next_token = None
        while True:
            if next_token:
                params['next_page_token'] = next_token
            items, next_token = self._api_get_page(endpoint, params)
            all_items.extend(items)
            if not next_token:
                break
        return all_items

    def _cached(self, key: str, fn: callable):
        now = time.time()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < self._cache_ttl:
            return hit[1]
        data = fn()
        self._cache[key] = (now, data)
        return data

    def clear_cache(self):
        self._cache.clear()

    # ─── Клієнт ────────────────────────────────────────────────
    def get_client_by_phone(self, phone: str) -> Optional[str]:
        """Повертає id клієнта (звичайний GUID)."""
        digits = ''.join(filter(str.isdigit, phone))
        formatted = f"+{digits}" if not phone.startswith('+') else phone
        items, _ = self._api_get_page('clients', {'phone_number': formatted})
        if items:
            return items[0].get('id')
        return None

    # ─── Тварини ───────────────────────────────────────────────
    def get_pets_by_owner(self, owner_guid: str) -> list:
        """owner_guid = id клієнта. Використовує прямий фільтр client_id."""
        pets, _ = self._api_get_page('patients', {'client_id': owner_guid})
        if pets:
            return self._format_pets(pets)
        return []

    def _format_pets(self, raw_pets: list) -> list:
        return [{
            'Ref_Key': p['id'],
            'id': p['id'],
            'Description': p.get('name') or '',
            'ДатаРождения': p.get('birthDate', ''),
            'Пол': 'Female' if p.get('gender') == 'FEMALE' else 'Male',
            'Кастрировано': p.get('isCastrated', False),
            'НомерЧипа': p.get('chipNumber', ''),
            'photoUrl': p.get('photoUrl', ''),
        } for p in raw_pets]

    # ─── Профіль ────────────────────────────────────────────────
    def get_contact_by_owner(self, owner_guid: str) -> Optional[dict]:
        all_clients = self._cached('all_clients', lambda: self._api_get_all('clients'))
        for c in all_clients:
            if c['id'] == owner_guid:
                return c
        return None

    # ─── Візити ─────────────────────────────────────────────────
    def get_visits_by_owner(self, owner_guid: str) -> list:
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return []
        all_visits = []
        for pet in pets:
            pet_visits = self._api_get_all('appointments', {'patient_id': pet['id']})
            for v in pet_visits:
                v['_pet_name'] = pet['Description']
            all_visits.extend(pet_visits)
        result = [{
            'Date': _format_datetime(v.get('eventDate', '')),
            'Description': v.get('diagnosisDescription') or v.get('anamnesis', '') or 'Прийом',
            '_pet_name': v.get('_pet_name', ''),
            'id': v.get('id', ''),
        } for v in all_visits]
        return sorted(result, key=lambda x: x['Date'], reverse=True)

    # ─── Майбутні записи ────────────────────────────────────────
    def get_appointments_by_owner(self, owner_guid: str) -> list:
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return []
        all_bookings = []
        for pet in pets:
            pet_bookings = self._api_get_all('bookings', {'patient_id': pet['id']})
            for b in pet_bookings:
                b['_pet_name'] = pet['Description']
            all_bookings.extend(pet_bookings)
        result = [{
            'ЗаписьНаДату': _format_datetime(b.get('appointmentStartTime', '')),
            'Кличка': b.get('patient', {}).get('petName') or b.get('_pet_name', ''),
            'Подтверждено': b.get('isConfirmed', False),
            'Executed': b.get('objectState') == 'ACCEPTED',
            'id': b.get('id', ''),
        } for b in all_bookings]
        return sorted(result, key=lambda x: x['ЗаписьНаДату'], reverse=True)

    # ─── Аналізи ────────────────────────────────────────────────
    def get_analyses_by_owner(self, owner_guid: str) -> list:
        diagnostics = self._api_get_all('diagnostic', {'client_id': owner_guid})
        pets = self.get_pets_by_owner(owner_guid)
        pet_map = {p['id']: p['Description'] for p in pets}
        result = [{
            'Description': d.get('descriptionStudy') or 'Діагностика',
            'Date': _format_datetime(d.get('eventDate', '')),
            '_pet_name': pet_map.get(d.get('patientId', ''), ''),
            'isCompleted': d.get('isCompleted', False),
            'id': d.get('id', ''),
        } for d in diagnostics]
        return sorted(result, key=lambda x: x['Date'], reverse=True)

    # ─── Графік (через available_slots) ────────────────────────
    def get_entity_id(self) -> str:
        def fetch_dep():
            deps = self._api_get_all('departments')
            return deps[0]['id'] if deps else None
        dep_id = self._cached('first_department_id', fetch_dep)
        if dep_id and os.getenv('ENOTE_USE_DEPARTMENTS', 'false').lower() == 'true':
            return dep_id
        def fetch_org():
            orgs = self._api_get_all('organizations')
            return orgs[0]['id'] if orgs else None
        org_id = self._cached('first_organization_id', fetch_org)
        if org_id:
            return org_id
        raise Exception("Не вдалося отримати entity_id")

    def get_doctors_list(self) -> list:
        return self._cached('doctors_list', lambda: self._api_get_all('employees'))

    def get_schedule(self) -> list:
        """Графік на 7 днів: список записів на прийом."""
        from_date = date.today().isoformat()
        to_date = (date.today() + timedelta(days=7)).isoformat()
        entity_id = self.get_entity_id()
        doctors = self.get_doctors_list()
        doctor_map = {d['id']: f"{d.get('firstName', '')} {d.get('surname', '')}".strip() for d in doctors}

        result = []
        current = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        while current <= end:
            date_str = current.isoformat()
            for doc_id, doc_name in doctor_map.items():
                items, _ = self._api_get_page('bookings/available_slots', {
                    'date': date_str,
                    'entity_id': entity_id,
                    'employee_id': doc_id
                })
                for slot in items:
                    start = slot.get('startTime', '')
                    status = ''
                    history = slot.get('bookingStatusHistory')
                    if history and isinstance(history, list):
                        status = history[-1].get('bookingStatus', '')
                    client_info = slot.get('client', {})
                    patient_info = slot.get('patient', {})
                    result.append({
                        'date': date_str,
                        'doctor': doc_name,
                        'doctor_id': doc_id,
                        'patient': patient_info.get('petName', ''),
                        'client': client_info.get('clientFullName', ''),
                        'start': _format_datetime(start),
                        'duration': slot.get('duration', 0),
                        'status': status,
                        'comment': slot.get('comment', '')
                    })
            current += timedelta(days=1)
        return result

    # ─── Debug ───────────────────────────────────────────────────
    def debug_raw(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.api_v2_base}/{endpoint}"
        try:
            r = self.session.get(url, params=params or {}, timeout=30)
            return {
                'status': r.status_code,
                'url': r.url,
                'body': r.json() if 'json' in r.headers.get('content-type', '') else r.text[:500],
            }
        except Exception as e:
            return {'error': str(e)}


enote = EnoteClient()
