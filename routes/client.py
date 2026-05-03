import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EnotClient:
    """
    HTTP-клієнт для Enote API v2.
    Базовий URL: https://app.enote.vet/{clinic_id}/hs
    Endpoints:   /api/v2/...
    """

    def __init__(self, base_url: str, api_key: str):
        # base_url = "https://app.enote.vet/YOUR_CLINIC_ID/hs"
        # НЕ додавай /api/v2 сюди — він вже є в кожному endpoint
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        Виконати GET-запит. endpoint починається з /api/v2/...
        """
        url = f"{self.base_url}{endpoint}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error %s for %s: %s", resp.status_code, url, resp.text)
            raise
        except requests.exceptions.RequestException as e:
            logger.error("Request failed for %s: %s", url, e)
            raise

    def _post(self, endpoint: str, body: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.post(url, json=body, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error %s for %s: %s", resp.status_code, url, resp.text)
            raise

    def _patch(self, endpoint: str, body: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.patch(url, json=body, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error("HTTP error %s for %s: %s", resp.status_code, url, resp.text)
            raise

    # ─── Довідники ───────────────────────────────────────────────

    def get_employees(self, next_page_token: str = None, page_size: int = 100) -> dict:
        return self._get("/api/v2/employees", {
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    def get_clients(self, phone_number: str = None,
                    next_page_token: str = None, page_size: int = 100) -> dict:
        return self._get("/api/v2/clients", {
            "phone_number": phone_number,
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    def get_client(self, client_id: str) -> dict:
        return self._get(f"/api/v2/clients/{client_id}")

    def get_patients(self, phone_number: str = None,
                     next_page_token: str = None, page_size: int = 100) -> dict:
        return self._get("/api/v2/patients", {
            "phone_number": phone_number,
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    def get_patient(self, patient_id: str) -> dict:
        return self._get(f"/api/v2/patients/{patient_id}")

    def get_visit_kinds(self, next_page_token: str = None, page_size: int = 100) -> dict:
        return self._get("/api/v2/visit_kinds", {
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    # ─── Амбулаторні записи (візити) ─────────────────────────────

    def get_appointments(self, from_date: str = None, to_date: str = None,
                         employee_id: str = None,
                         next_page_token: str = None, page_size: int = 100) -> dict:
        """
        ВАЖЛИВО: API v2 НЕ підтримує фільтр по patient_id.
        Фільтрувати по пацієнту треба після отримання даних.
        """
        return self._get("/api/v2/appointments", {
            "from_date": from_date,
            "to_date": to_date,
            "employee_id": employee_id,
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    # ─── Діагностика (аналізи) ────────────────────────────────────

    def get_diagnostic(self, from_date: str = None, to_date: str = None,
                       employee_id: str = None,
                       next_page_token: str = None, page_size: int = 100) -> dict:
        """
        ВАЖЛИВО: API v2 НЕ підтримує фільтр по patient_id.
        Фільтрувати по пацієнту треба після отримання даних.
        """
        return self._get("/api/v2/diagnostic", {
            "from_date": from_date,
            "to_date": to_date,
            "employee_id": employee_id,
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    # ─── Попередній запис / графік лікарів ───────────────────────

    def get_bookings(self, from_date: str = None, to_date: str = None,
                     employee_id: str = None,
                     next_page_token: str = None, page_size: int = 100) -> dict:
        return self._get("/api/v2/bookings", {
            "from_date": from_date,
            "to_date": to_date,
            "employee_id": employee_id,
            "next_page_token": next_page_token,
            "page_size": page_size,
        })

    def get_available_days(self, from_date: str, to_date: str,
                           entity_id: str = None,
                           role_id: str = None,
                           employee_id: str = None) -> dict:
        """
        Отримати дні прийому лікаря.
        from_date, to_date — обов'язкові, формат YYYY-MM-DD.
        """
        return self._get("/api/v2/bookings/available_days", {
            "from": from_date,   # НЕ from_date — параметр називається "from"
            "to": to_date,       # НЕ to_date   — параметр називається "to"
            "entity_id": entity_id,
            "role_id": role_id,
            "employee_id": employee_id,
        })

    def get_visit_times(self, visit_kind_id: str, date: str,
                        entity_id: str = None,
                        role_id: str = None,
                        employee_id: str = None) -> dict:
        """
        Отримати вільні/зайняті слоти на конкретний день.
        visit_kind_id і date — обов'язкові.
        """
        return self._get("/api/v2/bookings/visit_times", {
            "visit_kind_id": visit_kind_id,
            "date": date,
            "entity_id": entity_id,
            "role_id": role_id,
            "employee_id": employee_id,
        })

    def create_booking(self, body: dict) -> dict:
        return self._post("/api/v2/bookings", body)

    def cancel_booking(self, booking_id: str) -> dict:
        url = f"{self.base_url}/api/v2/bookings/{booking_id}/cancel"
        resp = self.session.put(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
