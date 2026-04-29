import requests
import os
from flask import current_app

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.user = os.getenv('ENOTE_ODATA_USER')
        self.password = os.getenv('ENOTE_ODATA_PASSWORD')
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)

    def _build_url(self, endpoint):
        """Будує повний URL до OData endpoint"""
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{endpoint}"

    def get_clients(self, phone=None):
        """Отримати список клінік або конкретного за номером телефону"""
        url = self._build_url("Catalog_Клиенты")
        params = {"$format": "json"}
        if phone:
            params["$filter"] = f"Телефон eq '{phone}'"
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return None

    def get_pets(self, client_guid=None):
        """Отримати тварин клієнта за його GUID"""
        url = self._build_url("Catalog_Питомцы")
        params = {"$format": "json"}
        if client_guid:
            params["$filter"] = f"Владелец_Key eq guid'{client_guid}'"
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return None

    def get_analyses(self, pet_guid=None):
        """Отримати аналізи тварини"""
        url = self._build_url("Document_Анализы")
        params = {"$format": "json"}
        if pet_guid:
            params["$filter"] = f"Питомец_Key eq guid'{pet_guid}'"
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return None

    def get_appointments(self, doctor_guid=None, date_from=None, date_to=None):
        """Отримати записи на прийом"""
        url = self._build_url("Document_Приемы")
        params = {"$format": "json"}
        filters = []
        if doctor_guid:
            filters.append(f"Врач_Key eq guid'{doctor_guid}'")
        if date_from and date_to:
            filters.append(f"ДатаДата gt {date_from} and ДатаДата lt {date_to}")
        if filters:
            params["$filter"] = " and ".join(filters)
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return None

# Екземпляр для використання в інших модулях
enote = EnoteClient()
