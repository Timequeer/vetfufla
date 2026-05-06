import os
import time
from datetime import date, timedelta, datetime
from typing import Optional
import requests


def _format_datetime(dt_str: str) -> str:
    if not dt_str:
        return ''
    try:
        clean = dt_str[:19]
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str


_TEXT_KEYS = ('name', 'diagnosisName', 'serviceName', 'description',
              'title', 'text', 'value', 'label', 'comment')


def _extract_text(val) -> str:
    """Рекурсивно витягує текст з будь-якої структури. Захист від [object Object]."""
    if not val and val != 0:
        return ''
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        for key in _TEXT_KEYS:
            found = val.get(key)
            if found and isinstance(found, str) and found.strip():
                return found.strip()
        for v in val.values():
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        return ''
    if isinstance(val, list):
        parts = [_extract_text(item) for item in val]
        return ', '.join(p for p in parts if p)
    return ''


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

    def _api_get_page(self, endpoint: str, params: dict = None) -> tuple:
        url = f"{self.api_v2_base}/{endpoint}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = self.session.get(url, params=params, timeout=30)
            if not r.ok:
                return [], None
            resp = r.json()
            data = resp.get('data', [])
            items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
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

    def _cached(self, key: str, fn):
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
    def get_client_by_phone(self, phone: str) -> Optional[dict]:
        digits = ''.join(filter(str.isdigit, phone))
        formatted = f"+{digits}" if not phone.startswith('+') else phone
        items, _ = self._api_get_page('clients', {'phone_number': formatted})
        if not items:
            return None
        client = items[0]
        client_id = client.get('id')
        main_subject_id = client.get('mainContactSubjectId')
        subject_ids = set()
        if client_id:
            subject_ids.add(client_id)
        if main_subject_id:
            subject_ids.add(main_subject_id)
        for subj in client.get('contactSubjects', []):
            if subj.get('id'):
                subject_ids.add(subj['id'])
        return {
            'id': client_id,
            'mainContactSubjectId': main_subject_id,
            'subject_ids': list(subject_ids),
            'raw': client,
        }

    def get_client_subject_ids(self, owner_guid: str) -> list:
        cache_key = f'subject_ids_{owner_guid}'
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            return cached[1]
        items, _ = self._api_get_page(f'clients/{owner_guid}')
        subject_ids = {owner_guid}
        client = (items[0] if isinstance(items, list) else items) if items else None
        if client:
            main = client.get('mainContactSubjectId')
            if main:
                subject_ids.add(main)
            for subj in client.get('contactSubjects', []):
                if subj.get('id'):
                    subject_ids.add(subj['id'])
        result = list(subject_ids)
        self._cache[cache_key] = (time.time(), result)
        return result

    # ─── Тварини ───────────────────────────────────────────────
    def get_pets_by_owner(self, owner_guid: str) -> list:
        # API фільтр не працює — отримуємо все і фільтруємо по ownerId
        all_pets = self._api_get_all('patients', {'client_id': owner_guid})
        if not all_pets:
            return []
        subject_ids = set(self.get_client_subject_ids(owner_guid))
        filtered = [p for p in all_pets if p.get('ownerId') in subject_ids]
        if not filtered:
            filtered = all_pets
        return self._format_pets(filtered)

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
            'ownerId': p.get('ownerId', ''),
        } for p in raw_pets]

    # ─── Профіль ────────────────────────────────────────────────
    def get_contact_by_owner(self, owner_guid: str) -> Optional[dict]:
        items, _ = self._api_get_page(f'clients/{owner_guid}')
        if items:
            return items[0] if isinstance(items, list) else items
        all_clients = self._cached('all_clients', lambda: self._api_get_all('clients'))
        for c in all_clients:
            if c.get('id') == owner_guid:
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

        result = []
        for v in all_visits:
            desc = (
                _extract_text(v.get('diagnosisDescription')) or
                _extract_text(v.get('diagnosis')) or
                _extract_text(v.get('diagnoses')) or
                _extract_text(v.get('services')) or
                _extract_text(v.get('anamnesis')) or
                _extract_text(v.get('visitKindName')) or
                _extract_text(v.get('visitType')) or
                _extract_text(v.get('comment')) or
                'Прийом'
            )
            result.append({
                'Date': _format_datetime(v.get('eventDate', '')),
                'Description': desc,
                '_pet_name': v.get('_pet_name', ''),
                'id': v.get('id', ''),
            })
        return sorted(result, key=lambda x: x['Date'], reverse=True)

    # ─── Майбутні записи ────────────────────────────────────────
    _DEAD_STATUSES = {'CANCELLED', 'COMPLETED', 'CHECKED_IN', 'NO_SHOW'}

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

        today = datetime.now()
        result = []
        for b in all_bookings:
            history = b.get('bookingStatusHistory') or []
            last_status = history[-1].get('bookingStatus', '') if history else ''

            # Пропускаємо завершені/скасовані
            if last_status in self._DEAD_STATUSES:
                continue

            # Пробуємо всі можливі поля дати
            raw_date = (
                b.get('startTime') or
                b.get('eventDate') or
                b.get('appointmentStartTime') or
                b.get('bookingDate') or
                b.get('date') or ''
            )
            formatted_date = _format_datetime(raw_date)

            # Пропускаємо минулі записи
            if formatted_date:
                try:
                    dt = datetime.strptime(formatted_date, "%Y-%m-%d %H:%M")
                    if dt < today:
                        continue
                except Exception:
                    pass

            result.append({
                'ЗаписьНаДату': formatted_date,
                'Кличка': (b.get('patient') or {}).get('petName') or b.get('_pet_name', ''),
                'Подтверждено': b.get('isConfirmed', False),
                'Executed': b.get('objectState') == 'ACCEPTED',
                'status': last_status,
                'id': b.get('id', ''),
            })
        return sorted(result, key=lambda x: x['ЗаписьНаДату'])

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

    # ─── Графік ────────────────────────────────────────────────
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
        entity_id = self.get_entity_id()
        doctors = self.get_doctors_list()
        doctor_map = {
            d['id']: f"{d.get('firstName', '')} {d.get('surname', '')}".strip()
            for d in doctors
        }
        result = []
        current = date.today()
        end = current + timedelta(days=7)
        while current <= end:
            date_str = current.isoformat()
            for doc_id, doc_name in doctor_map.items():
                items, _ = self._api_get_page('bookings/available_slots', {
                    'date': date_str,
                    'entity_id': entity_id,
                    'employee_id': doc_id
                })
                for slot in items:
                    history = slot.get('bookingStatusHistory') or []
                    status = history[-1].get('bookingStatus', '') if history else ''
                    client_info = slot.get('client') or {}
                    patient_info = slot.get('patient') or {}
                    result.append({
                        'date': date_str,
                        'doctor': doc_name,
                        'doctor_id': doc_id,
                        'patient': patient_info.get('petName', ''),
                        'client': client_info.get('clientFullName', ''),
                        'start': _format_datetime(slot.get('startTime', '')),
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

    def debug_visit_fields(self, owner_guid: str) -> dict:
        """Сирі дані для діагностики полів дат і описів."""
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return {'error': 'no pets'}
        samples = {}
        for pet in pets[:2]:
            pet_id = pet['id']
            raw_visits, _ = self._api_get_page('appointments', {'patient_id': pet_id, 'page_size': 3})
            raw_bookings, _ = self._api_get_page('bookings', {'patient_id': pet_id, 'page_size': 3})
            samples[pet['Description']] = {
                'pet_id': pet_id,
                'visit_keys': list(raw_visits[0].keys()) if raw_visits else [],
                'visits': [{
                    'eventDate': v.get('eventDate'),
                    'startTime': v.get('startTime'),
                    'diagnosisDescription': v.get('diagnosisDescription'),
                    'diagnosis': v.get('diagnosis'),
                    'diagnoses': v.get('diagnoses'),
                    'services': v.get('services'),
                    'anamnesis': v.get('anamnesis'),
                    'visitKindName': v.get('visitKindName'),
                    'comment': v.get('comment'),
                } for v in raw_visits],
                'booking_keys': list(raw_bookings[0].keys()) if raw_bookings else [],
                'bookings': [{
                    'startTime': b.get('startTime'),
                    'eventDate': b.get('eventDate'),
                    'appointmentStartTime': b.get('appointmentStartTime'),
                    'bookingDate': b.get('bookingDate'),
                    'date': b.get('date'),
                    'objectState': b.get('objectState'),
                    'bookingStatusHistory': b.get('bookingStatusHistory'),
                } for b in raw_bookings],
            }
        return samples


enote = EnoteClient()
