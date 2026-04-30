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
        # Кэш: ключ -> (время сохранения, данные)
        self._cache = {}
        self._cache_ttl = 600  # 10 минут

    def _build_url(self, endpoint):
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{endpoint}"

    def _cached_get(self, cache_key, url, params=None):
        """Вернуть данные из кэша или загрузить и закэшировать"""
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
        # если ошибка — вернуть пустой список, но кэш не обновлять
        return []

    def clear_cache(self):
        self._cache.clear()

    # ---------- Животные ----------
    def get_all_pets(self):
        url = self._build_url("Catalog_Карточки")
        return self._cached_get("pets", url)

    # ---------- Анализы ----------
    def get_all_analyses(self):
        url = self._build_url("Document_Анализы")
        return self._cached_get("analyses", url)

    # ---------- Визиты ----------
    def get_all_visits(self):
        url = self._build_url("Document_Посещение")
        return self._cached_get("visits", url)

    # ---------- Контактные лица ----------
    def get_all_contacts(self):
        url = self._build_url("Catalog_КонтактныеЛица")
        return self._cached_get("contacts", url)

enote = EnoteClient()
