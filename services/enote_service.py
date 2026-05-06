import os
import time
from datetime import date, timedelta, datetime
from typing import Optional
import requests

def _format_datetime(dt_str: str) -> str:
    """ISO8601 → 'YYYY-MM-DD HH:MM'"""
    if not dt_str:
        return ''
    try:
        clean = dt_str[:19]
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str

PRIORITY_KEYS = ('name', 'diagnosisName', 'serviceName', 'description',
                 'title', 'text', 'value', 'label')

def _extract_text(val) -> str:
    """Рекурсивно витягує текст з будь-якої структури. Захист від [object Object]."""
    if not val and val != 0:
        return ''
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, dict):
        for key in PRIORITY_KEYS:
            found = val.get(key)
            if found and isinstance(found, str):
                return found.strip()
        for v in val.values():
            if v and isinstance(v, str):
                return v.strip()
        return ''
    if isinstance(val, list):
        parts = [_extract_text(item) for item in val]
        return ', '.join(p for p in parts if p)
    return ''

class EnoteClient:
    def __init__(self):
        # Отримуємо налаштування з навколишнього середовища (env)
        self.base_url = os.environ.get("ENOTE_BASE_URL", "https://app.enote.vet")
        self.clinic_guid = os.environ.get("ENOTE_CLINIC_GUID", "38174e48-16f0-11ee-6d89-2ae983d8a0f0")
        self.api_key = os.environ.get("ENOTE_API_KEY", "")
        
        self.api_v2_base = f"{self.base_url}/{self.clinic_guid}/hs/api/v2"
        
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def clear_cache(self):
        pass # Якщо у вас є логіка кешування, вона залишається тут

    def _api_get_page(self, endpoint: str, params: dict = None) -> tuple[list, int]:
        """Базовий метод отримання однієї сторінки з API"""
        url = f"{self.api_v2_base}/{endpoint}"
        try:
            r = self.session.get(url, params=params or {}, timeout=20)
            data = r.json()
            if data.get('result'):
                # Повертаємо дані і загальну кількість (якщо є)
                return data.get('data', []), data.get('total', 0)
        except Exception as e:
            print(f"Enote API Error on {endpoint}: {e}")
        return [], 0

    def _api_get_all(self, endpoint: str, params: dict = None) -> list:
        """Універсальний метод отримання всіх сторінок з захистом від зациклення"""
        all_data = []
        page = 1
        page_size = 100
        
        while True:
            current_params = (params or {}).copy()
            current_params.update({'page': page, 'page_size': page_size})
            
            data, _ = self._api_get_page(endpoint, current_params)
            if not data:
                break
            
            all_data.extend(data)
            
            if len(data) < page_size:
                break
            
            page += 1
            if page > 50: # Захист від вічного циклу
                break
                
        return all_data

    # ─── Робота з клієнтами ──────────────────────────────────────────
    def get_client_by_phone(self, phone: str) -> Optional[dict]:
        """
        Шукає клієнта за номером. Фільтрує результати і робить запит по ID.
        """
        if not phone:
            return None
        
        clean_target = "".join(filter(str.isdigit, phone))
        raw_clients = self._api_get_all('clients', {'phone_number': clean_target})
        
        if not raw_clients:
            return None

        found_client = None
        for c in raw_clients:
            c_phone = str(c.get('phone', '') or c.get('contactInfo', ''))
            # Перевіряємо останні 9 цифр, щоб ігнорувати коди країн типу +380
            if "".join(filter(str.isdigit, c_phone)).endswith(clean_target[-9:]):
                found_client = c
                break
        
        if not found_client:
            found_client = raw_clients[0]

        client_id = found_client.get('id')
        if not client_id:
            return None

        # Робимо запит по конкретному ID
        url = f"{self.api_v2_base}/clients/{client_id}"
        try:
            r = self.session.get(url, timeout=20)
            res = r.json()
            if res.get('result') and res.get('data'):
                return res['data'][0]
        except Exception as e:
            print(f"Error fetching client by ID: {e}")
            
        return found_client

    def get_client_subject_ids(self, client_id: str) -> list:
        """Повертає список ID для пацієнтів (якщо є така логіка у вашому API)"""
        # Цей метод був у ваших сніпетах, залишаю базову реалізацію
        return []

    # ─── Робота з пацієнтами ─────────────────────────────────────────
    def get_pets_by_owner(self, owner_guid: str) -> list:
        """Отримує тварин і примусово відсіює чужих"""
        if not owner_guid:
            return []
        
        raw_pets = self._api_get_all('patients', {'client_id': owner_guid})
        
        # ПРИМУСОВА ФІЛЬТРАЦІЯ
        filtered_pets = [
            p for p in raw_pets 
            if str(p.get('ownerId', '')).lower() == str(owner_guid).lower()
        ]
        return filtered_pets

    # ─── Розклад та бронювання (Нове) ────────────────────────────────
    def get_available_slots(self, date_str: str, employee_id: str, department_id: str) -> list:
        """Отримує слоти і відсіює скасовані (CANCELLED) записи"""
        params = {
            'date': date_str, 
            'employee_id': employee_id, 
            'entity_id': department_id
        }
        bookings = self._api_get_all('bookings/available_slots', params)
        
        valid_slots = []
        for b in bookings:
            # Перевірка дати
            if not b.get('startTime', '').startswith(date_str):
                continue
                
            history = b.get('bookingStatusHistory', [])
            is_cancelled = False
            
            if history:
                # Сортуємо від найновішого до найстарішого
                history.sort(key=lambda x: x.get('changedAt', ''), reverse=True)
                latest_status = history[0].get('bookingStatus')
                if latest_status == 'CANCELLED':
                    is_cancelled = True
                    
            if not is_cancelled:
                valid_slots.append(b)
                
        return valid_slots

    # ─── Debug методи з вашого сніпету ───────────────────────────────
    def debug_raw(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.api_v2_base}/{endpoint}"
        try:
            r = self.session.get(url, params=params or {}, timeout=30)
            return {
                'status': r.status_code,
                'url': r.url,
                'body': r.json() if 'json' in r.headers.get('content-type', '') else r.text[:500],
            }
        except Exception as e:
            return {'error': str(e)}

    def debug_visit_fields(self, owner_guid: str) -> dict:
        """Показує сирі поля першого візиту і першого запису — для діагностики дат і описів."""
        pets = self.get_pets_by_owner(owner_guid)
        if not pets:
            return {'error': 'no pets'}
        pet_id = pets[0]['id']

        raw_visits, _ = self._api_get_page('appointments', {'patient_id': pet_id, 'page_size': 1})
        raw_bookings, _ = self._api_get_page('bookings', {'patient_id': pet_id, 'page_size': 1})

        return {
            'pet_id': pet_id,
            'visit_keys': list(raw_visits[0].keys()) if raw_visits else [],
            'visit_sample': raw_visits[0] if raw_visits else None,
            'booking_sample': raw_bookings[0] if raw_bookings else None
        }

# Ініціалізація глобального об'єкта
enote = EnoteClient()
