import requests
import os
import time
from datetime import datetime, timedelta

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.user = os.getenv('ENOTE_ODATA_USER')
        self.password = os.getenv('ENOTE_ODATA_PASSWORD')
        self.api_key = os.getenv('ENOTE_API_KEY')
        self.session = requests.Session()
        # для старого OData (графік, довідники)
        self.session.auth = (self.user, self.password)
        # для нового API
        self.api_base_url = f"{self.base_url}/{self.clinic_guid}/hs/api/v2"
        self._cache = {}
        self._cache_ttl = 600

    # ------ Старий OData-метод для одного ендпоінту ------
    def _build_url(self, endpoint):
        from urllib.parse import quote
        encoded = quote(endpoint, safe='')
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{encoded}"

    def _get_odata(self, url, params):
        params.setdefault("$format", "json")
        try:
            r = self.session.get(url, params=params, timeout=25)
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

    # ------ Новий API v2 ------
    def _api_get(self, endpoint, params=None):
        headers = {'apikey': self.api_key}
        url = f"{self.api_base_url}/{endpoint}"
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=25)
            if r.ok:
                return r.json().get('data', [])
        except Exception:
            pass
        return []

    # ---------- Тварини (поки що через OData) ----------
    def get_pets_by_owner(self, owner_guid):
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

    # ---------- Контактна особа (залишаємо OData) ----------
    def get_contact_by_owner(self, owner_guid):
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

    # ---------- Візити (через новий API) ----------
    def get_visits_by_owner(self, owner_guid):
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return []
        pet_ids = [p['Ref_Key'] for p in pets]
        all_visits = []
        # Завантажуємо останні 2000 амбулаторних прийомів
        params = {
            'page_size': 2000,
            #'from_date': (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d')  # опціонально
        }
        appointments = self._api_get('appointments', params)
        for app in appointments:
            if app.get('patientId') in pet_ids:
                all_visits.append({
                    'Date': app.get('eventDate', ''),
                    'Description': app.get('anamnesis', '') or 'Прийом',
                    '_pet_name': self._get_pet_name_by_id(pets, app.get('patientId'))
                })
        all_visits.sort(key=lambda x: x['Date'], reverse=True)
        return all_visits

    # ---------- Записи на прийом (через новий API) ----------
    def get_appointments_by_owner(self, owner_guid):
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return []
        pet_ids = [p['Ref_Key'] for p in pets]
        bookings = self._api_get('bookings', {'page_size': 2000})
        filtered = []
        for b in bookings:
            if b.get('patient', {}).get('patientId') in pet_ids:
                filtered.append({
                    'ЗаписьНаДату': b.get('appointmentStartTime', ''),
                    'Кличка': b.get('patient', {}).get('petName', ''),
                    'Подтверждено': b.get('isConfirmed', False),
                    'Executed': b.get('objectState') == 'ACCEPTED'  # проведено = виконано
                })
        filtered.sort(key=lambda x: x['ЗаписьНаДату'], reverse=True)
        return filtered

    # ---------- Аналізи (через новий API) ----------
    def get_analyses_by_owner(self, owner_guid):
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return []
        pet_ids = [p['Ref_Key'] for p in pets]
        diagnostics = self._api_get('diagnostic', {'page_size': 2000})
        filtered = []
        for d in diagnostics:
            if d.get('patientId') in pet_ids:
                filtered.append({
                    'Description': d.get('descriptionStudy') or 'Дослідження',
                    'Date': d.get('eventDate', ''),
                    '_pet_name': self._get_pet_name_by_id(pets, d.get('patientId'))
                })
        filtered.sort(key=lambda x: x['Date'], reverse=True)
        return filtered

    def _get_pet_name_by_id(self, pets, pet_id):
        for p in pets:
            if p['Ref_Key'] == pet_id:
                return p.get('Description', '')
        return ''

    # ---------- Довідник лікарів (OData) ----------
    def get_doctors(self):
        url = self._build_url("Catalog_ФизическиеЛица")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                doctors = {}
                for d in r.json().get('value', []):
                    doctors[d['Ref_Key']] = d.get('Description', '')
                return doctors
        except Exception:
            pass
        return {}

    # ---------- Довідник змін (OData) ----------
    def get_shifts(self):
        url = self._build_url("Catalog_Смены")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                shifts = {}
                for s in r.json().get('value', []):
                    shifts[s['Ref_Key']] = {
                        'name': s.get('Description', ''),
                        'start': s.get('Время1', ''),
                        'end': s.get('Время2', '')
                    }
                return shifts
        except Exception:
            pass
        return {}

    # ---------- Графік роботи (OData) ----------
    def get_schedule(self):
        url = self._build_url("InformationRegister_ГрафикРаботы")
        params = {
            "$orderby": "Period desc",
            "$top": 500,
            "$format": "json"
        }
        try:
            r = self.session.get(url, params=params, timeout=25)
            if r.ok:
                data = r.json().get('value', [])
                doctors = self.get_doctors()
                shifts = self.get_shifts()
                result = []
                for entry in data:
                    period = entry.get('Period')
                    if not period:
                        continue
                    doctor_key = entry.get('ФизЛицо_Key')
                    shift_key = entry.get('Смена_Key')
                    shift_info = shifts.get(shift_key, {})
                    result.append({
                        'doctor': doctors.get(doctor_key, doctor_key),
                        'date': period[:10],
                        'start': shift_info.get('start', ''),
                        'end': shift_info.get('end', ''),
                        'works': entry.get('Работает'),
                        'allow_online': entry.get('РазрешитьОнлайнЗапись')
                    })
                return result
        except Exception:
            pass
        return []

    # ---------- Пошук клієнта за телефоном ----------
    def find_client_by_phone(self, phone):
        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('38'):
            digits = digits[2:]
        url = self._build_url("Catalog_Клиенты")
        data = self._get_odata(url, {
            "$filter": f"substringof('{digits}',КонтактнаяИнформация)",
            "$top": 1
        })
        if data:
            return data[0]
        return None

enote = EnoteClient()
