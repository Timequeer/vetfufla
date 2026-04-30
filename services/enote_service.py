import requests
import os

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.user = os.getenv('ENOTE_ODATA_USER')
        self.password = os.getenv('ENOTE_ODATA_PASSWORD')
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)

    def _build_url(self, endpoint):
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{endpoint}"

    def _format_guid(self, guid: str) -> str:
        if not guid:
            return guid
        if '-' in guid:
            return guid
        if len(guid) == 32:
            return f"{guid[:8]}-{guid[8:12]}-{guid[12:16]}-{guid[16:20]}-{guid[20:]}"
        return guid

    # ---------- Животные ----------
    def get_all_pets(self):
        """Получить вообще все карточки животных (без фильтра)"""
        url = self._build_url("Catalog_Карточки")
        params = {"$format": "json"}
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

    # ---------- Анализы ----------
    def get_all_analyses(self):
        """Получить все анализы (без фильтра)"""
        url = self._build_url("Document_Анализы")
        params = {"$format": "json", "$top": 500
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

    # ---------- Визиты (посещения) ----------
    def get_all_visits(self):
        """Получить все посещения (без фильтра)"""
        url = self._build_url("Document_Посещение")
        params = {"$format": "json", "$top": 500}
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

    # ---------- Контактные лица ----------
    def get_all_contacts(self):
        """Получить все контактные лица"""
        url = self._build_url("Catalog_КонтактныеЛица")
        params = {"$format": "json", "$top": 500}
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

enote = EnoteClient()
