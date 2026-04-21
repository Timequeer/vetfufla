import requests
from flask import current_app

class ENoteClient:
    def __init__(self, base_url, login, password):
        self.base_url = base_url
        self.login = login
        self.password = password
        self.token = None

    def _auth(self):
        # TODO: реальная авторизация в Еноте (получение токена)
        self.token = "fake-token"
        return True

    def _request(self, method, endpoint, data=None):
        if not self.token:
            self._auth()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        # Заглушка – возвращаем тестовые данные
        return self._mock_response(endpoint)

    def _mock_response(self, endpoint):
        if "pets" in endpoint:
            return [
                {"guid": "pet1", "name": "Барсик", "species": "кот", "birth_date": "2020-01-01"},
                {"guid": "pet2", "name": "Шарик", "species": "собака", "birth_date": "2019-05-15"}
            ]
        if "appointments" in endpoint:
            return [
                {"id": 1, "pet_guid": "pet1", "doctor_guid": "doc1", "date": "2026-05-20T10:00:00", "status": "confirmed"},
                {"id": 2, "pet_guid": "pet2", "doctor_guid": "doc1", "date": "2026-05-21T14:00:00", "status": "pending"}
            ]
        if "lab_results" in endpoint:
            return [{"id": 1, "name": "Общий анализ крови", "date": "2026-04-10", "result": "норма"}]
        if "vaccinations" in endpoint:
            return [{"id": 1, "name": "Бешенство", "date": "2025-06-01", "next_due": "2026-06-01"}]
        return []

    def get_pets_by_owner_guid(self, owner_guid):
        return self._request("GET", f"/owners/{owner_guid}/pets")

    def get_pets_by_doctor_guid(self, doctor_guid):
        return self._request("GET", f"/doctors/{doctor_guid}/pets")

    def get_appointments(self, pet_guid=None, doctor_guid=None, from_date=None):
        if pet_guid:
            return self._request("GET", f"/pets/{pet_guid}/appointments")
        if doctor_guid:
            return self._request("GET", f"/doctors/{doctor_guid}/appointments")
        return []

    def get_lab_results(self, pet_guid):
        return self._request("GET", f"/pets/{pet_guid}/lab_results")

    def get_vaccinations(self, pet_guid):
        return self._request("GET", f"/pets/{pet_guid}/vaccinations")