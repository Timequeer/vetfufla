```python
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
    except Exception:
        return dt_str


PRIORITY_KEYS = ('name', 'diagnosisName', 'serviceName', 'description',
                 'title', 'text', 'value', 'label')


def _extract_text(val) -> str:
    """Рекурсивно витягує текст з будь-якої структури. Захист від [object Object]."""
    if not val and val != 0:
        return ''
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        for key in PRIORITY_KEYS:
            found = val.get(key)
            if found and isinstance(found, str):
                return found.strip()
        for v in val.values():
            if v and isinstance(v, str):
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
        except Exception as e:
            print(f"API Request Error ({endpoint}): {e}")
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

    # ─── Клієнт (ЗА ЛОГІКОЮ ДЕНИСА) ────────────────────────────
    def get_client_by_phone(self, phone: str) -> Optional[dict]:
        """
        КРОК 1: Шукаємо за номером (витягуємо короткі дані / id).
        КРОК 2: Робимо прямий запит по ID (отримуємо contactSubjects).
        """
        digits = ''.join(filter(str.isdigit, phone))
        formatted = f"+{digits}" if not phone.startswith('+') else phone
        
        # Крок 1: Запит за номером
        items, _ = self._api_get_page('clients', {'phone_number': formatted})
        
        # Фолбек: якщо не знайшло, шукаємо просто по цифрах
        if not items:
            items, _ = self._api_get_page('clients', {'phone_number': digits})
            
        if not items:
            return None

        # Витягуємо ID клієнта з результатів
        client_short = items[0]
        client_id = client_short.get('id')
        if not client_id:
            return None

        # Крок 2: РОБИМО ЗАПИТ ПО ID (саме те, що на скріншоті)
        full_items, _ = self._api_get_page(f'clients/{client_id}')
        if not full_items:
            return None
            
        client = full_items[0]

        # Збираємо всі можливі subject IDs (як на фото)
        subject_ids = set()
        subject_ids.add(client_id)
        
        main_subject_id = client.get('mainContactSubjectId')
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
        """
        Отримує всі ідентифікатори (contactSubjects) клієнта по його ID.
        """
        cache_key = f'subject_ids_{owner_guid}'
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._cache_ttl:
            return cached[1]

        items, _ = self._api_get_page(f'clients/{owner_guid}')
        if not items:
            return [owner_guid]

        client = items[0]
        subject_ids = set()
        subject_ids.add(owner_guid)

        main_subject_id = client.get('mainContactSubjectId')
        if main_subject_id:
            subject_ids.add(main_subject_id)
            
        for subj in client.get('contactSubjects', []):
            if subj.get('id'):
                subject_ids.add(subj['id'])

        result = list(subject_ids)
        self._cache[cache_key] = (time.time(), result)
        return result

    # ─── Тварини ───────────────────────────────────────────────
    def get_pets_by_owner(self, owner_guid: str) -> list:
        """
        ЖОРСТКА ФІЛЬТРАЦІЯ НА СТОРОНІ СЕРВЕРА
        Відсіюємо всіх тварин, чий ownerId не збігається з subject_ids клієнта.
        """
        # Запитуємо пацієнтів
        all_pets = self._api_get_all('patients', {'client_id': owner_guid})
        if not all_pets:
            return []

        # Отримуємо всі правильні ID цього клієнта (за логікою Дениса)
        subject_ids = set(self.get_client_subject_ids(owner_guid))

        # Фільтруємо - залишаємо ТІЛЬКИ тих тварин, які належать цьому клієнту
        filtered = [p for p in all_pets if p.get('ownerId') in subject_ids]

        # Повертаємо тільки перевірених
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
            return items[0]
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
            'Description': (
                _extract_text(v.get('diagnosisDescription')) or
                _extract_text(v.get('diagnosis')) or
                _extract_text(v.get('anamnesis')) or
                _extract_text(v.get('visitKindName')) or
                'Прийом'
            ),
            '_pet_name': v.get('_pet_name', ''),
            'id': v.get('id', ''),
        } for v in all_visits]
        return sorted(result, key=lambda x: x['Date'], reverse=True)

    # ─── Майбутні записи (Фільтрація CANCELLED) ─────────────────
    def get_appointments_by_owner(self, owner_guid: str) -> list:
        all_bookings = self._api_get_all('bookings')

        result = []
        now = datetime.now()

        for b in all_bookings:
            client = b.get("client") or {}
            client_id = client.get("clientId")

            if not client_id or client_id != owner_guid:
                continue

            raw_date = b.get('startTime') or b.get('eventDate')
            if not raw_date:
                continue

            try:
                dt = datetime.fromisoformat(raw_date[:19])
            except Exception:
                continue

            if dt < now:
                continue

            status = ''
            history = b.get("bookingStatusHistory")
            if history and isinstance(history, list):
                # Сортуємо історію за датою на випадок неправильного порядку
                history.sort(key=lambda x: x.get('changedAt', ''))
                status = history[-1].get("bookingStatus", '')

            # ПРОПУСКАЄМО СКАСОВАНІ ЗАПИСИ
            if status == 'CANCELLED':
                continue

            result.append({
                'ЗаписьНаДату': _format_datetime(raw_date),
                'Кличка': b.get('patient', {}).get('petName', ''),
                'Подтверждено': b.get('isConfirmed', False),
                'status': status,
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

    # ─── Графік (Фільтрація CANCELLED) ────────────────────────
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
        from_date = date.today().isoformat()
        to_date = (date.today() + timedelta(days=7)).isoformat()
        entity_id = self.get_entity_id()
        doctors = self.get_doctors_list()
        doctor_map = {
            d['id']: f"{d.get('firstName', '')} {d.get('surname', '')}".strip()
            for d in doctors
        }

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
                        history.sort(key=lambda x: x.get('changedAt', ''))
                        status = history[-1].get('bookingStatus', '')
                    
                    # ПРОПУСКАЄМО СКАСОВАНІ ВІЗИТИ В РОЗКЛАДІ
                    if status == 'CANCELLED':
                        continue
                        
                    client_info = slot.get('client', {}) or {}
                    patient_info = slot.get('patient', {}) or {}
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

```
