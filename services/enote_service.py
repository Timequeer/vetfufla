import requests
import os
import time

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.api_key = os.getenv('ENOTE_API_KEY')
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': self.api_key,
            'Content-Type': 'application/json'
        })
        self._cache = {}
        self._cache_ttl = 600

    def _api(self, path):
        return f"{self.base_url}/{self.clinic_guid}/api/v2/{path}"

    def _get(self, path, params=None):
        try:
            r = self.session.get(self._api(path), params=params or {}, timeout=25)
            if r.ok:
                data = r.json()
                if data.get('result'):
                    return data.get('data', [])
        except Exception as e:
            print(f"[ENOTE] Error {path}: {e}")
        return []

    def _get_paginated(self, path, params=None, max_pages=5):
        results = []
        p = dict(params or {})
        p['page_size'] = 50
        for _ in range(max_pages):
            try:
                r = self.session.get(self._api(path), params=p, timeout=25)
                if not r.ok:
                    break
                body = r.json()
                if not body.get('result'):
                    break
                data = body.get('data', [])
                if isinstance(data, list):
                    results.extend(data)
                elif isinstance(data, dict):
                    results.append(data)
                pagination = body.get('pagination', {})
                if pagination.get('is_last_page', True):
                    break
                token = pagination.get('next_page_token')
                if not token:
                    break
                p['next_page_token'] = token
            except Exception as e:
                print(f"[ENOTE] Paginated error {path}: {e}")
                break
        return results

    def _cached(self, key, fn):
        now = time.time()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < self._cache_ttl:
            return hit[1]
        data = fn()
        self._cache[key] = (now, data)
        return data

    def clear_cache(self):
        self._cache.clear()

    # ---------- Пошук клієнта за телефоном ----------
    def get_client_by_phone(self, phone):
        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('38'):
            digits = digits[2:]
        search = digits[-9:] if len(digits) >= 9 else digits
        clients = self._get_paginated('clients', {'phone': search})
        if clients:
            return clients[0].get('id')
        return None

    # ---------- Тварини ----------
    def get_pets_by_owner(self, owner_guid):
        def fetch():
            return self._get_paginated('patients', {'clientId': owner_guid})
        return self._cached(f"pets:{owner_guid}", fetch)

    # ---------- Профіль клієнта ----------
    def get_client_profile(self, owner_guid):
        def fetch():
            data = self._get(f'clients/{owner_guid}')
            if isinstance(data, dict):
                return data
            return {}
        return self._cached(f"profile:{owner_guid}", fetch)

    # ---------- Візити ----------
    def get_visits_by_owner(self, owner_guid):
        def fetch():
            pets = self.get_pets_by_owner(owner_guid)
            pet_names = {p.get('id'): p.get('name', '') for p in pets}
            all_visits = self._get_paginated('visits', {'clientId': owner_guid})
            for v in all_visits:
                v['_pet_name'] = pet_names.get(v.get('patientId'), '')
            all_visits.sort(key=lambda x: x.get('eventDate', ''), reverse=True)
            return all_visits
        return self._cached(f"visits:{owner_guid}", fetch)

    # ---------- Аналізи ----------
    def get_analyses_by_owner(self, owner_guid):
        def fetch():
            pets = self.get_pets_by_owner(owner_guid)
            pet_names = {p.get('id'): p.get('name', '') for p in pets}
            all_analyses = self._get_paginated('diagnostic', {'clientId': owner_guid})
            for a in all_analyses:
                a['_pet_name'] = pet_names.get(a.get('patientId'), '')
            all_analyses.sort(key=lambda x: x.get('eventDate', ''), reverse=True)
            return all_analyses
        return self._cached(f"analyses:{owner_guid}", fetch)

    # ---------- Записи на прийом ----------
    def get_appointments_by_owner(self, owner_guid):
        def fetch():
            pets = self.get_pets_by_owner(owner_guid)
            pet_names = {p.get('id'): p.get('name', '') for p in pets}
            all_apps = self._get_paginated('appointments', {'clientId': owner_guid})
            for a in all_apps:
                a['_pet_name'] = pet_names.get(a.get('patientId'), '')
            return all_apps
        return self._cached(f"appointments:{owner_guid}", fetch)

    # ---------- Графік роботи ----------
    def get_schedule(self):
        def fetch():
            return self._get_paginated('schedule')
        return self._cached('schedule', fetch)

enote = EnoteClient()
