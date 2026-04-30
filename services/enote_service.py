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

    def _build_url(self, endpoint):
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{endpoint}"

    def _get_with_retry(self, url, params=None, max_tries=3):
        """Виконати GET-запит із повторними спробами при помилках з'єднання"""
        for attempt in range(max_tries):
            try:
                r = self.session.get(url, params=params, timeout=30)
                if r.ok:
                    return r.json().get('value', [])
                # Якщо помилка не тимчасова, не повторюємо
                if r.status_code >= 500:
                    time.sleep(1)
                    continue
                return []
            except requests.exceptions.RequestException as e:
                if attempt == max_tries - 1:
                    raise e
                time.sleep(2)
        return []

    # ---------- Тварини (ефективний пошук) ----------
    def get_pets_by_owner(self, owner_guid):
        """Знайти всіх тварин конкретного власника за допомогою маленьких сторінок"""
        url = self._build_url("Catalog_Карточки")
        top = 10  # дуже маленькі сторінки
        skip = 0
        found = []
        empty_pages = 0
        while True:
            batch = self._get_with_retry(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not batch:
                empty_pages += 1
                if empty_pages > 3:  # три порожні сторінки підряд → кінець
                    break
            else:
                empty_pages = 0
                for pet in batch:
                    if pet.get('Хозяин_Key') == owner_guid:
                        found.append(pet)
            skip += top
            # Якщо знайшли хоч одну тварину і пройшли багато сторінок, можна зупинитись
            if found and skip > 500:  # після 500 записів зупиняємось
                break
        return found

    # ---------- Аналізи (тільки для конкретної тварини) ----------
    def get_analyses_by_pet(self, pet_guid):
        url = self._build_url("Document_Анализы")
        top = 10
        skip = 0
        found = []
        empty_pages = 0
        while True:
            batch = self._get_with_retry(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not batch:
                empty_pages += 1
                if empty_pages > 3:
                    break
            else:
                empty_pages = 0
                for a in batch:
                    if a.get('Карточка_Key') == pet_guid:
                        found.append(a)
                # Якщо знайшли хоч один аналіз, можна припинити після певної кількості сторінок
                if found and skip > 200:
                    break
            skip += top
        return found

    # ---------- Візити (аналогічно) ----------
    def get_visits_by_pet(self, pet_guid):
        url = self._build_url("Document_Посещение")
        top = 10
        skip = 0
        found = []
        empty_pages = 0
        while True:
            batch = self._get_with_retry(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not batch:
                empty_pages += 1
                if empty_pages > 3:
                    break
            else:
                empty_pages = 0
                for v in batch:
                    if v.get('Карточка_Key') == pet_guid:
                        found.append(v)
                if found and skip > 200:
                    break
            skip += top
        return found

    # ---------- Контакт ----------
    def get_contact_by_owner(self, owner_guid):
        url = self._build_url("Catalog_КонтактныеЛица")
        top = 10
        skip = 0
        empty_pages = 0
        while True:
            batch = self._get_with_retry(url, {
                "$format": "json",
                "$top": top,
                "$skip": skip
            })
            if not batch:
                empty_pages += 1
                if empty_pages > 3:
                    break
            else:
                empty_pages = 0
                for c in batch:
                    if c.get('ОбъектВладелец') == owner_guid:
                        return c
            skip += top
        return None

enote = EnoteClient()
