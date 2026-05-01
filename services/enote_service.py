import requests
import os
import time
from urllib.parse import quote
from datetime import datetime

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.user = os.getenv('ENOTE_ODATA_USER')
        self.password = os.getenv('ENOTE_ODATA_PASSWORD')
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        self._cache = {}
        self._cache_ttl = 600

    def _build_url(self, endpoint):
        encoded = quote(endpoint, safe='')
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{encoded}"

    def _get(self, url, params):
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

    # ---------- Тварини ----------
    def get_pets_by_owner(self, owner_guid):
        url = self._build_url("Catalog_Карточки")
        def fetch():
            data = self._get(url, {"$filter": f"Хозяин_Key eq guid'{owner_guid}'"})
            if data:
                return data
            result, skip = [], 0
            while True:
                batch = self._get(url, {"$top": 100, "$skip": skip})
                if not batch:
                    break
                result += [p for p in batch if p.get('Хозяин_Key') == owner_guid]
                skip += 100
            return result
        return self._cached(f"pets:{owner_guid}", fetch)

    # ---------- Візити ----------
    def get_visits_by_pet(self, pet_guid):
        url = self._build_url("Document_Посещение")
        params = {
            "$orderby": "Date desc",
            "$top": 500,
            "$format": "json"
        }
        try:
            r = self.session.get(url, params=params, timeout=25)
            if r.ok:
                all_data = r.json().get('value', [])
                return [v for v in all_data if v.get('Карточка_Key') == pet_guid]
        except Exception:
            pass
        return []

    # ---------- Контакти ----------
    def get_contact_by_owner(self, owner_guid):
        url = self._build_url("Catalog_КонтактныеЛица")
        skip = 0
        while True:
            batch = self._get(url, {"$top": 100, "$skip": skip})
            if not batch:
                return None
            for c in batch:
                if c.get('ОбъектВладелец') == owner_guid:
                    return c
            skip += 100

    # ---------- Аналізи ----------
    def get_analyses_by_owner(self, owner_guid):
        return []

    # ---------- Записи на прийом ----------
    def get_appointments_by_owner(self, owner_guid):
        url = self._build_url("Task_ПредварительнаяЗапись")
        params = {
            "$orderby": "ЗаписьНаДату desc",
            "$top": 500,
            "$format": "json"
        }
        try:
            r = self.session.get(url, params=params, timeout=25)
            if r.ok:
                all_data = r.json().get('value', [])
                filtered = [a for a in all_data if a.get('Хозяин_Key') == owner_guid]
                pets = {p['Ref_Key']: p.get('Description', '') for p in self.get_pets_by_owner(owner_guid)}
                for a in filtered:
                    a['_pet_name'] = pets.get(a.get('Карточка_Key'), '')
                self._cache[f"appointments:{owner_guid}"] = (time.time(), filtered)
                return filtered
        except Exception:
            pass
        return []

    # ---------- Довідник лікарів (з простим кешуванням) ----------
    def get_doctors(self):
        if 'doctors' in self._cache:
            return self._cache['doctors']
        url = self._build_url("Catalog_ФизическиеЛица")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                doctors = {}
                for d in r.json().get('value', []):
                    doctors[d['Ref_Key']] = d.get('Description', '')
                self._cache['doctors'] = doctors
                return doctors
        except Exception:
            pass
        return {}

    # ---------- Довідник змін (з простим кешуванням) ----------
    def get_shifts(self):
        if 'shifts' in self._cache:
            return self._cache['shifts']
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
                self._cache['shifts'] = shifts
                return shifts
        except Exception:
            pass
        return {}

    # ---------- Графік роботи (збалансований) ----------
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
        data = self._get(url, {
            "$filter": f"substringof('{digits}',КонтактнаяИнформация)",
            "$top": 1
        })
        if data:
            return data[0]
        return None

enote = EnoteClient()
