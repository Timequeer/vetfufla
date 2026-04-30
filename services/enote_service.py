import requests
import os
import time

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
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{endpoint}"

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
    def get_analyses_by_owner(self, owner_guid):
        """Завантажує аналізи з ENOTE та фільтрує локально (fallback)"""
        def fetch():
            # Отримуємо контактну особу власника
            contact = self.get_contact_by_owner(owner_guid)
            if not contact:
                return []
            contact_guid = contact['Ref_Key']
            
            url = self._build_url("Document_Анализы")
            all_analyses = []
            skip = 0
            limit = 2000  # максимальна кількість записів для завантаження
            
            while len(all_analyses) < limit:
                batch = self._get(url, {"$top": 100, "$skip": skip})
                if not batch:
                    break
                for a in batch:
                    if a.get('КонтактноеЛицо_Key') == contact_guid:
                        all_analyses.append(a)
                skip += 100
            
            # Додаємо клички тварин
            pets = self.get_pets_by_owner(owner_guid)
            pet_names = {p['Ref_Key']: p.get('Description', '') for p in pets}
            for a in all_analyses:
                a['_pet_name'] = pet_names.get(a.get('Карточка_Key'), '')
            
            all_analyses.sort(key=lambda x: x.get('Date', ''), reverse=True)
            return all_analyses[:50]  # повертаємо максимум 50 останніх
        
        return self._cached(f"analyses_owner_fallback:{owner_guid}", fetch)

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

    # ---------- Аналізи ----------
    def get_analyses_by_owner(self, owner_guid):
        contact = self.get_contact_by_owner(owner_guid)
        if not contact:
            return []
        contact_guid = contact['Ref_Key']
        url = self._build_url("Document_Анализы")
        def fetch():
            return self._get(url, {
                "$filter": f"КонтактноеЛицо_Key eq guid'{contact_guid}'",
                "$orderby": "Date desc",
                "$top": 50
            })
        return self._cached(f"analyses_owner:{owner_guid}", fetch)

    def get_analyses_by_owner_via_pets(self, owner_guid):
        # більше не використовується, але щоб уникнути помилок – повертаємо порожній список
        return []
    # ---------- Записи на прийом ----------
    def get_appointments_by_owner(self, owner_guid):
        url = self._build_url("Task_ПредварительнаяЗапись")
        def fetch():
            return self._get(url, {
                "$filter": f"Хозяин_Key eq guid'{owner_guid}'",
                "$orderby": "ЗаписьНаДату desc",
                "$top": 20
            })
        return self._cached(f"appointments:{owner_guid}", fetch)

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
