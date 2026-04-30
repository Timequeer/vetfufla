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
        # Кеш на 10 хвилин
        self._cache = {}
        self._cache_ttl = 600

    def _build_url(self, endpoint):
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{endpoint}"

    def _cached_get(self, cache_key, url, params=None):
        """Повертає дані з кешу або завантажує і кешує"""
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]

        if params is None:
            params = {}
        params.setdefault("$format", "json")
        r = self.session.get(url, params=params)
        if r.ok:
            data = r.json().get('value', [])
            self._cache[cache_key] = (now, data)
            return data
        return []

    def clear_cache(self):
        self._cache.clear()

    # ---------- Тварини (через навігацію або посторінково) ----------
    def get_pets_by_owner(self, owner_guid):
        """Отримати тварин конкретного власника"""
        url = self._build_url("Catalog_Карточки")
        # Спроба 1: навігаційний фільтр
        r = self.session.get(url, params={
            "$format": "json",
            "$filter": f"Хозяин/Ref_Key eq guid'{owner_guid}'"
        })
        if r.ok:
            data = r.json().get('value', [])
            if data:
                return data
        # Спроба 2: посторінкове завантаження з фільтрацією на клієнті
        all_pets = []
        top = 100
        skip = 0
        while True:
            r = self.session.get(url, params={
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not r.ok:
                break
            batch = r.json().get('value', [])
            if not batch:
                break
            # Фільтруємо на льоту
            for pet in batch:
                if pet.get('Хозяин_Key') == owner_guid:
                    all_pets.append(pet)
            skip += top
        return all_pets

    # ---------- Аналізи (теж через навігацію, інакше посторінково) ----------
    def get_analyses_by_pet(self, pet_guid):
        url = self._build_url("Document_Анализы")
        r = self.session.get(url, params={
            "$format": "json",
            "$filter": f"Карточка/Ref_Key eq guid'{pet_guid}'"
        })
        if r.ok:
            data = r.json().get('value', [])
            if data:
                return data
        # fallback: посторінково
        all_analyses = []
        top = 100
        skip = 0
        while True:
            r = self.session.get(url, params={
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not r.ok:
                break
            batch = r.json().get('value', [])
            if not batch:
                break
            for a in batch:
                if a.get('Карточка_Key') == pet_guid:
                    all_analyses.append(a)
            skip += top
        return all_analyses

    # ---------- Візити ----------
    def get_visits_by_pet(self, pet_guid):
        url = self._build_url("Document_Посещение")
        r = self.session.get(url, params={
            "$format": "json",
            "$filter": f"Карточка/Ref_Key eq guid'{pet_guid}'"
        })
        if r.ok:
            data = r.json().get('value', [])
            if data:
                return data
        all_visits = []
        top = 100
        skip = 0
        while True:
            r = self.session.get(url, params={
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not r.ok:
                break
            batch = r.json().get('value', [])
            if not batch:
                break
            for v in batch:
                if v.get('Карточка_Key') == pet_guid:
                    all_visits.append(v)
            skip += top
        return all_visits

    # ---------- Контакти (посторінково, бо навігація може не працювати) ----------
    def get_contact_by_owner(self, owner_guid):
        url = self._build_url("Catalog_КонтактныеЛица")
        top = 100
        skip = 0
        while True:
            r = self.session.get(url, params={
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not r.ok:
                break
            batch = r.json().get('value', [])
            if not batch:
                break
            for c in batch:
                if c.get('ОбъектВладелец') == owner_guid:
                    return c
            skip += top
        return None

enote = EnoteClient()
