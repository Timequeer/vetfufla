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

    def get_clients(self, phone=None):
        url = self._build_url("Catalog_Клиенты")
        params = {"$format": "json"}
        if phone:
            params["$filter"] = f"Телефон eq '{phone}'"
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

    def get_client_by_phone(self, phone):
        """Знаходить GUID клієнта за номером телефону через регістр контактної інформації"""
        # Нормалізуємо телефон (тільки цифри, без +)
        digits = ''.join(filter(str.isdigit, phone))
        # Пробуємо різні формати
        for fmt_phone in [digits, f'+{digits}', f'38{digits}' if not digits.startswith('38') else digits]:
            url = self._build_url("InformationRegister_КонтактнаяИнформация")
            params = {
                "$format": "json",
                "$filter": f"Представление eq '{fmt_phone}' and Тип eq 'Телефон'"
            }
            r = self.session.get(url, params=params)
            if r.ok:
                data = r.json().get('value', [])
                if data:
                    obj_ref = data[0].get('Объект')  # це може бути рядок з GUID клієнта
                    if obj_ref:
                        # витягаємо GUID з рядка (формат "guid'xxxx-...'")
                        import re
                        match = re.search(r"guid'([a-f0-9\-]+)'", obj_ref)
                        if match:
                            return match.group(1)
            # якщо не спрацювало, спробуємо інший фільтр
            params["$filter"] = f"Поле1 eq '{fmt_phone}' and Тип eq 'Телефон'"
            r = self.session.get(url, params=params)
            if r.ok:
                data = r.json().get('value', [])
                if data:
                    obj_ref = data[0].get('Объект')
                    if obj_ref:
                        import re
                        match = re.search(r"guid'([a-f0-9\-]+)'", obj_ref)
                        if match:
                            return match.group(1)
        return None

       def get_pets(self, client_guid=None):
        url = self._build_url("Catalog_Карточки")
        params = {"$format": "json"}
        if client_guid:
            # Правильный формат: просто GUID в кавычках без 'guid'
            params["$filter"] = f"Хозяин_Key eq '{self._format_guid(client_guid)}'"
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

    def get_analyses(self, pet_guid=None):
        url = self._build_url("Document_Анализы")
        params = {"$format": "json"}
        if pet_guid:
            params["$filter"] = f"Карточка_Key eq guid'{self._format_guid(pet_guid)}'"
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

    def get_appointments(self, doctor_guid=None, date_from=None, date_to=None):
        url = self._build_url("Document_Приемы")
        params = {"$format": "json"}
        filters = []
        if doctor_guid:
            filters.append(f"Врач_Key eq guid'{self._format_guid(doctor_guid)}'")
        if date_from and date_to:
            filters.append(f"ДатаДата gt {date_from} and ДатаДата lt {date_to}")
        if filters:
            params["$filter"] = " and ".join(filters)
        r = self.session.get(url, params=params)
        if r.ok:
            return r.json().get('value', [])
        return []

enote = EnoteClient()
