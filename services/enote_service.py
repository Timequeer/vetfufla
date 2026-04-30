import requests
import os
import time

MAX_ITEMS = 200  # максимальна кількість записів, яку повертає один метод

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

    def _get_json(self, url, params=None, max_tries=3):
        """GET-запит із повторними спробами та логуванням помилок"""
        for attempt in range(max_tries):
            try:
                r = self.session.get(url, params=params, timeout=30)
                if r.ok:
                    return r.json().get('value', [])
                # Логуємо помилку (тільки в консоль, не клієнту)
                print(f"[ENOTE ERROR] {r.status_code}: {r.text[:200]}")
                if r.status_code >= 500:
                    time.sleep(1)
                    continue
                return []
            except requests.exceptions.RequestException as e:
                print(f"[ENOTE EXCEPTION] {e}")
                if attempt == max_tries - 1:
                    raise e
                time.sleep(2)
        return []

    def _cached_or_fetch(self, cache_key, fetcher):
        """Загальна логіка кешування"""
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]

        data = fetcher()
        # Обмежуємо розмір кеша
        if len(self._cache) > 100:
            self._cache.clear()
        self._cache[cache_key] = (now, data)
        return data

    def clear_cache(self):
        self._cache.clear()

    # ---------- Тварини ----------
    def _fetch_pets_by_owner(self, owner_guid):
        url = self._build_url("Catalog_Карточки")
        # Спроба 1: навігація з guid'...'
        batch = self._get_json(url, {
            "$format": "json",
            "$filter": f"Хозяин/Ref_Key eq guid'{owner_guid}'"
        })
        if batch:
            return batch[:MAX_ITEMS]

        # Спроба 2: навігація з рядковим GUID
        batch = self._get_json(url, {
            "$format": "json",
            "$filter": f"Хозяин/Ref_Key eq '{owner_guid}'"
        })
        if batch:
            return batch[:MAX_ITEMS]

        # Спроба 3: посторінкове сканування (обмежене)
        found = []
        top = 10
        skip = 0
        empty_pages = 0
        while len(found) < MAX_ITEMS:
            page = self._get_json(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not page:
                empty_pages += 1
                if empty_pages > 3:
                    break
            else:
                empty_pages = 0
                for pet in page:
                    if pet.get('Хозяин_Key') == owner_guid:
                        found.append(pet)
            skip += top
            if skip > 500:  # після 500 записів припиняємо
                break
        return found[:MAX_ITEMS]

    def get_pets_by_owner(self, owner_guid):
        return self._cached_or_fetch(f"pets_{owner_guid}", lambda: self._fetch_pets_by_owner(owner_guid))

    # ---------- Аналізи ----------
    def _fetch_analyses_by_pet(self, pet_guid):
        url = self._build_url("Document_Анализы")
        # Спроба 1: навігація
        batch = self._get_json(url, {
            "$format": "json",
            "$filter": f"Карточка/Ref_Key eq guid'{pet_guid}'"
        })
        if batch:
            return batch[:MAX_ITEMS]
        batch = self._get_json(url, {
            "$format": "json",
            "$filter": f"Карточка/Ref_Key eq '{pet_guid}'"
        })
        if batch:
            return batch[:MAX_ITEMS]

        # Спроба 2: посторінково
        found = []
        top = 10
        skip = 0
        empty_pages = 0
        while len(found) < MAX_ITEMS:
            page = self._get_json(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not page:
                empty_pages += 1
                if empty_pages > 3:
                    break
            else:
                empty_pages = 0
                for a in page:
                    if a.get('Карточка_Key') == pet_guid:
                        found.append(a)
            skip += top
            if skip > 300:
                break
        return found[:MAX_ITEMS]

    def get_analyses_by_pet(self, pet_guid):
        return self._cached_or_fetch(f"analyses_{pet_guid}", lambda: self._fetch_analyses_by_pet(pet_guid))

    # ---------- Візити ----------
    def _fetch_visits_by_pet(self, pet_guid):
        url = self._build_url("Document_Посещение")
        batch = self._get_json(url, {
            "$format": "json",
            "$filter": f"Карточка/Ref_Key eq guid'{pet_guid}'"
        })
        if batch:
            return batch[:MAX_ITEMS]
        batch = self._get_json(url, {
            "$format": "json",
            "$filter": f"Карточка/Ref_Key eq '{pet_guid}'"
        })
        if batch:
            return batch[:MAX_ITEMS]

        found = []
        top = 10
        skip = 0
        empty_pages = 0
        while len(found) < MAX_ITEMS:
            page = self._get_json(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not page:
                empty_pages += 1
                if empty_pages > 3:
                    break
            else:
                empty_pages = 0
                for v in page:
                    if v.get('Карточка_Key') == pet_guid:
                        found.append(v)
            skip += top
            if skip > 300:
                break
        return found[:MAX_ITEMS]

    def get_visits_by_pet(self, pet_guid):
        return self._cached_or_fetch(f"visits_{pet_guid}", lambda: self._fetch_visits_by_pet(pet_guid))

    # ---------- Контакт ----------
    def get_contact_by_owner(self, owner_guid):
        def fetcher():
            url = self._build_url("Catalog_КонтактныеЛица")
            top = 10
            skip = 0
            empty_pages = 0
            while True:
                page = self._get_json(url, {
                    "$format": "json",
                    "$top": top,
                    "$skip": skip
                })
                if not page:
                    empty_pages += 1
                    if empty_pages > 3:
                        break
                else:
                    empty_pages = 0
                    for c in page:
                        if c.get('ОбъектВладелец') == owner_guid:
                            return c
                skip += top
                if skip > 200:
                    break
            return None
        return self._cached_or_fetch(f"contact_{owner_guid}", fetcher)

enote = EnoteClient()
