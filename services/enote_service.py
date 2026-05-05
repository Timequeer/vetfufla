import os
import time
from datetime import date, timedelta, datetime
from typing import List, Optional, Dict, Any
import requests


# ── допоміжна функція форматування ати ──────────────────────────
def _format_datetime(dt_str: str) -> str:
    """Перетворює ISO8601 рядок у звичний формат 'YYYY-MM-DD HH:MM'"""
    if not dt_str:
        return ''
    try:
        clean = dt_str[:19]  # '2023-03-10T09:10:00'
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M")
    except:
        return dt_str


class EnoteClient:
    def __init__(self):
        # Основні параметри підключення
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID', '38174e48-16f0-11ee-6d89-2ae983d8a0f0')
        self.api_key = os.getenv('ENOTE_API_KEY', 'e1d15077-3bcc-491b-839b-8ef83b5f9eb8')

        # Повна базова адреса API v2 (як у прикладах підтримки)
        self.api_v2_base = f"{self.base_url}/{self.clinic_guid}/hs/api/v2"

        # HTTP‑сесія тільки для API v2 (з apikey у заголовку)
        self.session = requests.Session()
        self.session.headers.update({'apikey': self.api_key})

        # Простий кеш у пам'яті
        self._cache = {}
        self._cache_ttl = 600  # 10 хвилин

    # ──────────────────────────────────────────────────────────────
    # Базові методи для роботи з API v2
    # ──────────────────────────────────────────────────────────────

    def _api_get_page(self, endpoint: str, params: dict = None) -> tuple:
        """Один запит. Повертає (список об'єктів, next_page_token або None)."""
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
                # Іноді data — один об'єкт, обгортаємо в список
                items = [data]

            pagination = resp.get('pagination') or {}
            next_token = pagination.get('next_page_token') if isinstance(pagination, dict) else None
            return items, next_token
        except Exception:
            return [], None

    def _api_get_all(self, endpoint: str, params: dict = None) -> list:
        """Обходить усі сторінки через next_page_token."""
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
        """Просте кешування результатів функції."""
        now = time.time()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < self._cache_ttl:
            return hit[1]
        data = fn()
        self._cache[key] = (now, data)
        return data

    def clear_cache(self):
        self._cache.clear()

    # ──────────────────────────────────────────────────────────────
    # Пошук клієнта (за номером телефону)
    # ──────────────────────────────────────────────────────────────

    def get_client_by_phone(self, phone: str) -> Optional[str]:
        """
        Повертає mainContactSubjectId клієнта — саме він використовується
        як ownerId у пацієнтів (тварин).
        """
        # Нормалізуємо номер
        digits = ''.join(filter(str.isdigit, phone))
        formatted = f"+{digits}" if not phone.startswith('+') else phone

        items, _ = self._api_get_page('clients', {'phone_number': formatted})
        if items:
            client = items[0]
            return client.get('mainContactSubjectId') or client.get('id')
        return None

    def get_client_id_by_phone(self, phone: str) -> Optional[str]:
        """Повертає id клієнта (не контактної особи)."""
        digits = ''.join(filter(str.isdigit, phone))
        formatted = f"+{digits}" if not phone.startswith('+') else phone
        items, _ = self._api_get_page('clients', {'phone_number': formatted})
        return items[0]['id'] if items else None

    # ──────────────────────────────────────────────────────────────
    # Універсальний ідентифікатор власника
    # ──────────────────────────────────────────────────────────────

    def _resolve_owner_id(self, owner_guid: str) -> str:
        """
        Повертає mainContactSubjectId для даного owner_guid.
        Якщо owner_guid вже є mainContactSubjectId, поверне його без змін.
        Інакше знайде справжній mainContactSubjectId за id клієнта.
        """
        clients = self._cached('all_clients', lambda: self._api_get_all('clients'))
        # Спочатку перевіряємо, чи є owner_guid серед mainContactSubjectId
        for c in clients:
            if c.get('mainContactSubjectId') == owner_guid:
                return owner_guid
        # Якщо ні – можливо owner_guid це id клієнта
        for c in clients:
            if c['id'] == owner_guid:
                return c.get('mainContactSubjectId') or c['id']
        # Нічого не знайдено – повертаємо як є
        return owner_guid

    # ──────────────────────────────────────────────────────────────
    # Тварини (пацієнти) власника
    # ──────────────────────────────────────────────────────────────

    def get_pets_by_owner(self, owner_guid: str) -> list:
        """
        Повертає список тварин для власника.
        owner_guid може бути як mainContactSubjectId, так і звичайним id клієнта.
        """
        resolved = self._resolve_owner_id(owner_guid)

        # Пробуємо прямий фільтр, якщо API підтримує client_id
        try:
            pets, _ = self._api_get_page('patients', {'client_id': resolved})
            if pets:
                return self._format_pets(pets)
        except Exception:
            pass

        # Fallback: завантажуємо всіх пацієнтів і фільтруємо за ownerId
        all_patients = self._api_get_all('patients')
        owner_pets = [p for p in all_patients if p.get('ownerId') == resolved]
        return self._format_pets(owner_pets)

    def _format_pets(self, raw_pets: list) -> list:
        """Приводить дані до звичного формату."""
        return [{
            'Ref_Key': p['id'],
            'id': p['id'],
            'Description': p.get('name') or p.get('description', ''),
            'ДатаРождения': p.get('birthDate', ''),
            'Пол': 'Female' if p.get('gender') == 'FEMALE' else 'Male',
            'Кастрировано': p.get('isCastrated', False),
            'НомерЧипа': p.get('chipNumber', ''),
            'photoUrl': p.get('photoUrl', ''),
        } for p in raw_pets]

    # ──────────────────────────────────────────────────────────────
    # Профіль клієнта (контактна особа)
    # ──────────────────────────────────────────────────────────────

    def get_contact_by_owner(self, owner_guid: str) -> Optional[dict]:
        """
        Знаходить клієнта за його mainContactSubjectId.
        Повертає дані клієнта (ім'я, телефон тощо).
        """
        resolved = self._resolve_owner_id(owner_guid)
        all_clients = self._cached('all_clients', lambda: self._api_get_all('clients'))
        for c in all_clients:
            if c.get('mainContactSubjectId') == resolved:
                return c
        return None

    # ──────────────────────────────────────────────────────────────
    # Візити (амбулаторні записи) для власника
    # ──────────────────────────────────────────────────────────────

    def get_visits_by_owner(self, owner_guid: str) -> list:
        """
        Повертає всі минулі візити для ВСІХ тварин власника.
        Використовує для кожної тварини прямий запит ?patient_id=...
        """
        resolved = self._resolve_owner_id(owner_guid)
        pets = self.get_pets_by_owner(resolved)
        if not pets:
            return []

        all_visits = []
        for pet in pets:
            pet_visits = self._api_get_all('appointments', {'patient_id': pet['id']})
            for v in pet_visits:
                v['_pet_name'] = pet['Description']
            all_visits.extend(pet_visits)

        # Форматуємо для фронтенду
        result = [{
            'Date': _format_datetime(v.get('eventDate', '')),
            'Description': v.get('diagnosisDescription') or v.get('anamnesis', '') or 'Прийом',
            '_pet_name': v.get('_pet_name', ''),
            'id': v.get('id', ''),
        } for v in all_visits]

        return sorted(result, key=lambda x: x['Date'], reverse=True)

    # ──────────────────────────────────────────────────────────────
    # Майбутні записи (bookings) для власника
    # ──────────────────────────────────────────────────────────────

    def get_appointments_by_owner(self, owner_guid: str) -> list:
        """
        Повертає майбутні (та всі) записи на прийом для всіх тварин власника.
        Використовує ?patient_id=...
        """
        resolved = self._resolve_owner_id(owner_guid)
        pets = self.get_pets_by_owner(resolved)
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

    # ──────────────────────────────────────────────────────────────
    # Аналізи (діагностичні дослідження) для клієнта
    # ──────────────────────────────────────────────────────────────

    def get_analyses_by_owner(self, owner_guid: str) -> list:
        """
        Отримує всі діагностики для клієнта через ?client_id=...
        Потребує id самого клієнта, а не mainContactSubjectId.
        """
        resolved = self._resolve_owner_id(owner_guid)
        # Знаходимо id клієнта за mainContactSubjectId
        all_clients = self._cached('all_clients', lambda: self._api_get_all('clients'))
        client = next((c for c in all_clients if c.get('mainContactSubjectId') == resolved), None)
        if not client:
            return []

        client_id = client['id']
        diagnostics = self._api_get_all('diagnostic', {'client_id': client_id})

        # Додаємо кличку тварини (можна взяти з patientId, але у відповіді її немає)
        pets = self.get_pets_by_owner(resolved)
        pet_map = {p['id']: p['Description'] for p in pets}

        result = [{
            'Description': d.get('descriptionStudy') or 'Діагностика',
            'Date': _format_datetime(d.get('eventDate', '')),
            '_pet_name': pet_map.get(d.get('patientId', ''), ''),
            'isCompleted': d.get('isCompleted', False),
            'id': d.get('id', ''),
        } for d in diagnostics]

        return sorted(result, key=lambda x: x['Date'], reverse=True)

    # ──────────────────────────────────────────────────────────────
    # Графік роботи лікаря (новий універсальний метод)
    # ──────────────────────────────────────────────────────────────

    def get_schedule_for_doctor(self, date_str: str, entity_id: str, employee_id: str) -> dict:
        """
        Отримує графік конкретного лікаря на конкретну дату.
        Використовує новий endpoint /schedules.
        """
        items, _ = self._api_get_page('schedules', {
            'date': date_str,
            'entity_id': entity_id,
            'employee_id': employee_id
        })
        return items[0] if items else {}

    def get_doctors_list(self) -> list:
        """Список усіх співробітників (лікарів)."""
        return self._cached('doctors_list', lambda: self._api_get_all('employees'))

    def get_entity_id(self) -> str:
        """
        Повертає entity_id (організацію або підрозділ), необхідний для графіка.
        Спочатку пробує підрозділи, потім організації.
        """
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
        raise Exception("Не вдалося отримати entity_id (організацію/підрозділ)")

    def get_schedule(self) -> list:
        """
        Повертає графік роботи лікарів на найближчі 7 днів.
        Формат, подібний до старого OData.
        """
        from_date = date.today().isoformat()
        to_date = (date.today() + timedelta(days=7)).isoformat()

        entity_id = self.get_entity_id()
        doctors = self.get_doctors_list()
        result = []

        current = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        while current <= end:
            date_str = current.isoformat()
            for doc in doctors:
                if not doc.get('id'):
                    continue
                try:
                    sched = self.get_schedule_for_doctor(date_str, entity_id, doc['id'])
                    if sched:
                        result.append({
                            'date': date_str,
                            'doctor': f"{doc.get('firstName', '')} {doc.get('surname', '')}".strip(),
                            'doctor_id': doc['id'],
                            # Поля нижче залежать від реальної відповіді API /schedules
                            # Якщо там інші назви – замініть після діагностики
                            'start': sched.get('shiftStart', ''),
                            'end': sched.get('shiftEnd', ''),
                            'works': sched.get('works', True),
                            'allow_online': sched.get('allowOnline', False)
                        })
                except Exception:
                    continue
            current += timedelta(days=1)
        return result

    # ──────────────────────────────────────────────────────────────
    # Debug
    # ──────────────────────────────────────────────────────────────

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


# Екземпляр для використання у застосунку
enote = EnoteClient()
