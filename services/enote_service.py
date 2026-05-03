import requests
import os
import time
import json

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.api_key = os.getenv('ENOTE_API_KEY')
        self.session = requests.Session()
        self.session.headers.update({'apikey': self.api_key})
        self._cache = {}
        self._cache_ttl = 600

    def _api(self, path):
        return f"{self.base_url}/{self.clinic_guid}/api/v2/{path}"

    def _parse(self, r):
        try:
            return json.loads(r.content.decode('utf-8-sig'))
        except Exception:
            return {}

    def _get(self, path, params=None):
        try:
            r = self.session.get(self._api(path), params=params or {}, timeout=25)
            if r.ok:
                body = self._parse(r)
                if body.get('result'):
                    return body.get('data', [])
        except Exception as e:
            print(f"[ENOTE v2] {path}: {e}")
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
                body = self._parse(r)
                if not body.get('result'):
                    break
                chunk = body.get('data', [])
                if isinstance(chunk, list):
                    results.extend(chunk)
                pagination = body.get('pagination', {})
                if pagination.get('is_last_page', True):
                    break
                token = pagination.get('next_page_token')
                if not token:
                    break
                p['next_page_token'] = token
            except Exception as e:
                print(f"[ENOTE v2 paginated] {path}: {e}")
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

    def get_client_by_phone(self, phone):
        digits = ''.join(filter(str.isdigit, phone))
        if not digits.startswith('380'):
            digits = '380' + digits.lstrip('0')
        formatted = '+' + digits
        clients = self._get_paginated('clients', {'phone_number': formatted})
        if clients:
            return clients[0].get('id')
        return None

    def get_client_profile(self, client_id):
        def fetch():
            data = self._get(f'clients/{client_id}')
            if isinstance(data, dict):
                return data
            return {}
        return self._cached(f"profile:{client_id}", fetch)

    def get_pets_by_owner(self, owner_guid):
        def fetch():
            all_pets = self._get_paginated('patients')
            return [p for p in all_pets if p.get('ownerId') == owner_guid]
        return self._cached(f"pets:{owner_guid}", fetch)

    def get_visits_by_owner(self, owner_guid):
        def fetch():
            pets = self.get_pets_by_owner(owner_guid)
            pet_ids = {p.get('id') for p in pets}
            pet_names = {p.get('id'): p.get('name', '') for p in pets}
            all_visits = self._get_paginated('appointments')
            filtered = []
            for v in all_visits:
                if v.get('patientId') in pet_ids:
                    v['_pet_name'] = pet_names.get(v.get('patientId'), '')
                    filtered.append(v)
            filtered.sort(key=lambda x: x.get('eventDate', ''), reverse=True)
            return filtered
        return self._cached(f"visits:{owner_guid}", fetch)

    def get_analyses_by_owner(self, owner_guid):
        def fetch():
            pets = self.get_pets_by_owner(owner_guid)
            pet_ids = {p.get('id') for p in pets}
            pet_names = {p.get('id'): p.get('name', '') for p in pets}
            all_diag = self._get_paginated('diagnostic')
            filtered = []
            for d in all_diag:
                if d.get('patientId') in pet_ids:
                    d['_pet_name'] = pet_names.get(d.get('patientId'), '')
                    filtered.append(d)
            filtered.sort(key=lambda x: x.get('eventDate', ''), reverse=True)
            return filtered
        return self._cached(f"analyses:{owner_guid}", fetch)

    def get_appointments_by_owner(self, owner_guid):
        return self.get_visits_by_owner(owner_guid)

    def get_analyses_by_pet(self, pet_guid):
        all_diag = self._get_paginated('diagnostic')
        return [d for d in all_diag if d.get('patientId') == pet_guid]

    def get_schedule(self):
        return self._cached('schedule', lambda: self._get_paginated('employees'))

enote = EnoteClient()
