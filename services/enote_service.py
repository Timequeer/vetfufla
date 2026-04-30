import requests
import os
import time
from urllib.parse import quote

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
        def fetch():
            return self._get(url, {
                "$filter": f"Карточка_Key eq guid'{pet_guid}'",
                "$orderby": "Date desc",
                "$top": 10
            })
        return self._cached(f"visits_pet:{pet_guid}", fetch)

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

    # ---------- Аналізи (поки порожньо) ----------
    def get_analyses_by_owner(self, owner_guid):
        return []

    # ---------- Записи на прийом (через Карточка_Key) ----------
    def get_appointments_by_owner(self, owner_guid):
        pets = self.get_pets_by_owner(owner_guid)
        all_appointments = []
        for pet in pets:
            pet_key = pet.get('Ref_Key')
            if not pet_key:
                continue
            url = self._build_url("Task_ПредварительнаяЗапись")
            params = {
                "$filter": f"Карточка_Key eq guid'{pet_key}'",
                "$orderby": "ЗаписьНаДату desc",
                "$top": 20,
                "$format": "json"
            }
            try:
                r = self.session.get(url, params=params, timeout=25)
                if r.ok:
                    data = r.json().get('value', [])
                    for a in data:
                        a['_pet_name'] = pet.get('Description', '')
                        all_appointments.append(a)
            except Exception:
                pass
        all_appointments.sort(key=lambda x: x.get('ЗаписьНаДату', ''), reverse=True)
        self._cache[f"appointments:{owner_guid}"] = (time.time(), all_appointments)
        return all_appointments

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
