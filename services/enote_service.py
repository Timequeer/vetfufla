import requests
import os
import time
from datetime import date, timedelta
from urllib.parse import quote
 
 
class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.user = os.getenv('ENOTE_ODATA_USER')
        self.password = os.getenv('ENOTE_ODATA_PASSWORD')
        self.api_key = os.getenv('ENOTE_API_KEY')
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)  # для OData
 
        # База API v2 — без /api/v2 на кінці
        self.api_v2_base = f"{self.base_url}/{self.clinic_guid}/hs"
 
        self._cache = {}
        self._cache_ttl = 600
 
    # ──────────────────────────────────────────────────────────────
    # OData helpers
    # ──────────────────────────────────────────────────────────────
 
    def _build_url(self, endpoint):
        encoded = quote(endpoint, safe='')
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{encoded}"
 
    def _get_odata(self, url, params):
        params.setdefault("$format", "json")
        try:
            r = self.session.get(url, params=params, timeout=30)
            if r.ok:
                return r.json().get('value', [])
        except Exception:
            return []
        return []
 
    def _cached(self, key, fn):
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
    # API v2 core
    # ──────────────────────────────────────────────────────────────
 
    def _api_get_page(self, endpoint, params=None):
        """Один запит. Повертає (items, next_page_token | None)."""
        headers = {'apikey': self.api_key}
        url = f"{self.api_v2_base}/api/v2/{endpoint}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=30)
            if not r.ok:
                return [], None
            resp = r.json()
 
            data = resp.get('data', [])
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
 
            pagination = resp.get('pagination') or {}
            next_token = pagination.get('next_page_token') if isinstance(pagination, dict) else None
            return items, next_token
        except Exception:
            return [], None
 
    def _api_get_all(self, endpoint, params=None) -> list:
        """Обходить всі сторінки через next_page_token."""
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
 
    def _api_get(self, endpoint, params=None) -> list:
        """Сумісність зі старим кодом — без пагінації."""
        items, _ = self._api_get_page(endpoint, params)
        return items
 
    # ──────────────────────────────────────────────────────────────
    # Пошук клієнта
    # ──────────────────────────────────────────────────────────────
 
    def get_client_by_phone(self, phone: str):
        """
        Повертає mainContactSubjectId клієнта —
        саме він є ownerId у пацієнтів (тварин).
        """
        if self.api_key:
            try:
                digits = ''.join(filter(str.isdigit, phone))
                formatted = f"+{digits}" if not phone.startswith('+') else phone
                items, _ = self._api_get_page('clients', {'phone_number': formatted})
                if items:
                    client = items[0]
                    # mainContactSubjectId == ownerId у пацієнтів
                    return client.get('mainContactSubjectId') or client.get('id')
            except Exception:
                pass
 
        # OData fallback
        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('38'):
            digits = digits[2:]
        url = self._build_url("Catalog_Клиенты")
        data = self._get_odata(url, {
            "$filter": f"substringof('{digits}',КонтактнаяИнформация)",
            "$top": 1
        })
        return data[0]['Ref_Key'] if data else None
 
    # ──────────────────────────────────────────────────────────────
    # Тварини (пацієнти)
    # ──────────────────────────────────────────────────────────────
 
    def get_pets_by_owner(self, owner_guid: str) -> list:
        if self.api_key:
            try:
                all_patients = self._api_get_all('patients')
                # owner_guid == mainContactSubjectId == ownerId у пацієнта
                owner_pets = [p for p in all_patients if p.get('ownerId') == owner_guid]
 
                return [{
                    'Ref_Key': p['id'],
                    'id': p['id'],
                    'Description': p.get('name') or p.get('description', ''),
                    'ДатаРождения': p.get('birthDate', ''),
                    'Пол': 'Female' if p.get('gender') == 'FEMALE' else 'Male',
                    'Кастрировано': p.get('isCastrated', False),
                    'НомерЧипа': p.get('chipNumber', ''),
                    'photoUrl': p.get('photoUrl', ''),
                } for p in owner_pets]
 
            except Exception:
                pass
 
        # OData fallback
        url = self._build_url("Catalog_Карточки")
        def fetch():
            data = self._get_odata(url, {"$filter": f"Хозяин_Key eq guid'{owner_guid}'"})
            if data:
                return data
            result, skip = [], 0
            while True:
                batch = self._get_odata(url, {"$top": 100, "$skip": skip})
                if not batch:
                    break
                result += [p for p in batch if p.get('Хозяин_Key') == owner_guid]
                skip += 100
            return result
        return self._cached(f"pets:{owner_guid}", fetch)
 
    def get_contact_by_owner(self, owner_guid: str):
        if self.api_key:
            try:
                # owner_guid == mainContactSubjectId,
                # шукаємо клієнта де цей id
                items = self._api_get_all('clients')
                for c in items:
                    if c.get('mainContactSubjectId') == owner_guid:
                        return c
            except Exception:
                pass
 
        # OData fallback
        url = self._build_url("Catalog_КонтактныеЛица")
        skip = 0
        while True:
            batch = self._get_odata(url, {"$top": 100, "$skip": skip})
            if not batch:
                return None
            for c in batch:
                if c.get('ОбъектВладелец') == owner_guid:
                    return c
            skip += 100
 
    # ──────────────────────────────────────────────────────────────
    # Минулі візити
    # ──────────────────────────────────────────────────────────────
 
    def get_visits_by_owner(self, owner_guid: str) -> list:
        if self.api_key:
            try:
                pets = self.get_pets_by_owner(owner_guid)
                if not pets:
                    return []
                pet_map = {p['id']: p.get('Description', '') for p in pets}
                pet_ids = set(pet_map)
 
                from_date = (date.today() - timedelta(days=730)).isoformat()
                to_date = date.today().isoformat()
 
                all_visits = self._api_get_all('appointments', {
                    'from_date': from_date,
                    'to_date': to_date,
                })
                result = [
                    {
                        'Date': a.get('eventDate', ''),
                        'Description': a.get('anamnesis') or a.get('diagnosisDescription') or 'Прийом',
                        '_pet_name': pet_map.get(a.get('patientId', ''), ''),
                        'id': a.get('id', ''),
                    }
                    for a in all_visits if a.get('patientId') in pet_ids
                ]
                return sorted(result, key=lambda x: x['Date'], reverse=True)
            except Exception:
                pass
 
        # OData fallback
        url = self._build_url("Document_Посещение")
        try:
            r = self.session.get(url, params={"$orderby": "Date desc", "$top": 2000, "$format": "json"}, timeout=30)
            if r.ok:
                all_visits = r.json().get('value', [])
                pets = {p['Ref_Key']: p.get('Description', '') for p in self.get_pets_by_owner(owner_guid)}
                filtered = [v for v in all_visits if v.get('Карточка_Key') in pets]
                for v in filtered:
                    v['_pet_name'] = pets.get(v['Карточка_Key'], '')
                return filtered
        except Exception:
            pass
        return []
 
    # ──────────────────────────────────────────────────────────────
    # Майбутні записи (bookings)
    # ──────────────────────────────────────────────────────────────
 
    def get_appointments_by_owner(self, owner_guid: str) -> list:
        if self.api_key:
            try:
                pets = self.get_pets_by_owner(owner_guid)
                if not pets:
                    return []
                pet_map = {p['id']: p.get('Description', '') for p in pets}
                pet_ids = set(pet_map)
 
                today = date.today().isoformat()
                future = (date.today() + timedelta(days=180)).isoformat()
 
                bookings = self._api_get_all('bookings', {
                    'from_date': today,
                    'to_date': future,
                })
                result = [
                    {
                        'ЗаписьНаДату': b.get('appointmentStartTime', ''),
                        'Кличка': b.get('patient', {}).get('petName') or pet_map.get(b.get('patient', {}).get('patientId', ''), ''),
                        'Подтверждено': b.get('isConfirmed', False),
                        'Executed': b.get('objectState') == 'ACCEPTED',
                        'id': b.get('id', ''),
                    }
                    for b in bookings if b.get('patient', {}).get('patientId') in pet_ids
                ]
                return sorted(result, key=lambda x: x['ЗаписьНаДату'], reverse=True)
            except Exception:
                pass
 
        # OData fallback
        url = self._build_url("Task_ПредварительнаяЗапись")
        try:
            r = self.session.get(url, params={"$orderby": "ЗаписьНаДату desc", "$top": 2000, "$format": "json"}, timeout=30)
            if r.ok:
                all_apps = r.json().get('value', [])
                return [a for a in all_apps if a.get('Хозяин_Key') == owner_guid]
        except Exception:
            pass
        return []
 
    # ──────────────────────────────────────────────────────────────
    # Аналізи
    # ──────────────────────────────────────────────────────────────
 
    def get_analyses_by_owner(self, owner_guid: str) -> list:
        if not self.api_key:
            return []
 
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return []
 
        pet_map = {p['id']: p.get('Description', '') for p in pets}
        pet_ids = set(pet_map)
 
        from_date = (date.today() - timedelta(days=730)).isoformat()
        to_date = date.today().isoformat()
 
        all_diag = self._api_get_all('diagnostic', {
            'from_date': from_date,
            'to_date': to_date,
        })
        result = [
            {
                'Description': d.get('descriptionStudy') or 'Діагностика',
                'Date': d.get('eventDate', ''),
                '_pet_name': pet_map.get(d.get('patientId', ''), ''),
                'isCompleted': d.get('isCompleted', False),
                'id': d.get('id', ''),
            }
            for d in all_diag if d.get('patientId') in pet_ids
        ]
        return sorted(result, key=lambda x: x['Date'], reverse=True)
 
    # ──────────────────────────────────────────────────────────────
    # Графік лікарів
    # ──────────────────────────────────────────────────────────────
 
    def get_schedule(self) -> list:
        if not self.api_key:
            return self._get_schedule_odata()
 
        try:
            from_date = date.today().isoformat()
            to_date = (date.today() + timedelta(days=30)).isoformat()
 
            doctors = self._api_get_all('employees')
            doctor_map = {d['id']: d.get('description') or d.get('name', '') for d in doctors}
 
            # ВАЖЛИВО: параметри "from"/"to", а НЕ "from_date"/"to_date"
            headers = {'apikey': self.api_key}
            url = f"{self.api_v2_base}/api/v2/bookings/available_days"
            r = self.session.get(url, headers=headers, params={
                'from': from_date,
                'to': to_date,
            }, timeout=30)
 
            if not r.ok:
                return self._get_schedule_odata()
 
            data = r.json().get('data', {})
            result = []
 
            if isinstance(data, list):
                for item in data:
                    emp_id = item.get('employeeId') or item.get('id', '')
                    result.append({
                        'date': item.get('date', ''),
                        'doctor': doctor_map.get(emp_id, emp_id),
                        'doctor_id': emp_id,
                        'start': item.get('start', ''),
                        'end': item.get('end', ''),
                    })
            elif isinstance(data, dict):
                for day_date, day_info in data.items():
                    if isinstance(day_info, list):
                        for emp_id in day_info:
                            result.append({
                                'date': day_date,
                                'doctor': doctor_map.get(emp_id, emp_id),
                                'doctor_id': emp_id,
                            })
 
            return result
        except Exception:
            pass
 
        return self._get_schedule_odata()
 
    def _get_schedule_odata(self) -> list:
        url = self._build_url("InformationRegister_ГрафикРаботы")
        try:
            r = self.session.get(url, params={"$orderby": "Period desc", "$top": 500, "$format": "json"}, timeout=30)
            if r.ok:
                data = r.json().get('value', [])
                doctors = self._get_doctors_odata()
                shifts = self._get_shifts_odata()
                result = []
                for entry in data:
                    period = entry.get('Period')
                    if not period:
                        continue
                    shift_info = shifts.get(entry.get('Смена_Key'), {})
                    result.append({
                        'doctor': doctors.get(entry.get('ФизЛицо_Key'), ''),
                        'date': period[:10],
                        'start': shift_info.get('start', ''),
                        'end': shift_info.get('end', ''),
                        'works': entry.get('Работает'),
                        'allow_online': entry.get('РазрешитьОнлайнЗапись'),
                    })
                return result
        except Exception:
            pass
        return []
 
    def _get_doctors_odata(self) -> dict:
        url = self._build_url("Catalog_ФизическиеЛица")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                return {d['Ref_Key']: d.get('Description', '') for d in r.json().get('value', [])}
        except Exception:
            pass
        return {}
 
    def _get_shifts_odata(self) -> dict:
        url = self._build_url("Catalog_Смены")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                return {
                    s['Ref_Key']: {
                        'name': s.get('Description', ''),
                        'start': s.get('Время1', ''),
                        'end': s.get('Время2', ''),
                    }
                    for s in r.json().get('value', [])
                }
        except Exception:
            pass
        return {}
 
    # ──────────────────────────────────────────────────────────────
    # Debug
    # ──────────────────────────────────────────────────────────────
 
    def debug_raw(self, endpoint: str, params: dict = None) -> dict:
        headers = {'apikey': self.api_key}
        url = f"{self.api_v2_base}/api/v2/{endpoint}"
        try:
            r = self.session.get(url, headers=headers, params=params or {}, timeout=30)
            return {
                'status': r.status_code,
                'url': r.url,
                'body': r.json() if 'json' in r.headers.get('content-type', '') else r.text[:500],
            }
        except Exception as e:
            return {'error': str(e)}
 
 
enote = EnoteClient()
