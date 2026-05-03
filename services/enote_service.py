import requests
import os
import time
from urllib.parse import quote

class EnoteClient:
    def __init__(self):
        self.base_url = os.getenv('ENOTE_BASE_URL', 'https://app.enote.vet')
        self.clinic_guid = os.getenv('ENOTE_CLINIC_GUID')
        self.user = os.getenv('ENOTE_ODATA_USER')
        self.password = os.getenv('ENOTE_ODATA_PASSWORD')
        self.api_key = os.getenv('ENOTE_API_KEY')
        self.session = requests.Session()
        self.session.auth = (self.user, self.password)
        self.api_v2_base = f"{self.base_url}/{self.clinic_guid}/hs/api/v2"
        self._cache = {}
        self._cache_ttl = 600

    def _build_url(self, endpoint):
        encoded = quote(endpoint, safe='')
        return f"{self.base_url}/{self.clinic_guid}/odata/standard.odata/{encoded}"

    def _get(self, url, params):
        params.setdefault("$format", "json")
        try:
            r = self.session.get(url, params=params, timeout=30)
            if r.ok:
                return r.json().get('value', [])
        except Exception:
            return []
        return []

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

    def _api_get(self, endpoint, params=None):
        if not self.api_key:
            return []
        headers = {'apikey': self.api_key}
        url = f"{self.api_v2_base}/{endpoint}"
        try:
            r = self.session.get(url, headers=headers, params=params, timeout=30)
            if r.ok:
                resp = r.json()
                return resp.get('data', [])
        except Exception:
            pass
        return []

    # ---------- Тварини (OData) ----------
    def get_pets_by_owner(self, owner_guid):
        # Спочатку пробуємо новий API
        if self.api_key:
            try:
                data = self._api_get('patients', {'page_size': 500})
                if data:
                    result = []
                    for p in data:
                        if p.get('ownerId') == owner_guid:
                            result.append({
                                'Ref_Key': p['id'],
                                'Description': p.get('name', ''),
                                'ДатаРождения': p.get('birthDate', ''),
                                'Пол': 'Female' if p.get('gender') == 'FEMALE' else 'Male',
                                'Кастрировано': p.get('isCastrated', False),
                                'НомерЧипа': p.get('chipNumber', '')
                            })
                    if result:
                        return result
            except Exception:
                pass
        # Fallback OData
        url = self._build_url("Catalog_Карточки")
        def fetch():
            data = self._get(url, {"$filter": f"Хозяин_Key eq guid'{owner_guid}'"})
            if data:
                return data
            result, skip = [], 0
            while True:
                batch = self._get(url, {"$top": 100, "$skip": skip})
                if not batch:
                    break
                result += [p for p in batch if p.get('Хозяин_Key') == owner_guid]
                skip += 100
            return result
        return self._cached(f"pets:{owner_guid}", fetch)

    def get_contact_by_owner(self, owner_guid):
        url = self._build_url("Catalog_КонтактныеЛица")
        skip = 0
        while True:
            batch = self._get(url, {"$top": 100, "$skip": skip})
            if not batch:
                return None
            for c in batch:
                if c.get('ОбъектВладелец') == owner_guid:
                    return c
            skip += 100

    # ---------- Візити (API v2 + OData fallback) ----------
    def get_visits_by_owner(self, owner_guid):
        if self.api_key:
            try:
                pets = self.get_pets_by_owner(owner_guid)
                pet_ids = [p['Ref_Key'] for p in pets]
                appointments = self._api_get('appointments', {'page_size': 2000})
                if appointments:
                    result = []
                    for a in appointments:
                        if a.get('patientId') in pet_ids:
                            pet_name = next((p['Description'] for p in pets if p['Ref_Key'] == a.get('patientId')), '')
                            result.append({
                                'Date': a.get('eventDate', ''),
                                'Description': a.get('anamnesis', '') or 'Прийом',
                                '_pet_name': pet_name
                            })
                    if result:
                        return sorted(result, key=lambda x: x['Date'], reverse=True)
            except Exception:
                pass

        url = self._build_url("Document_Посещение")
        params = {"$orderby": "Date desc", "$top": 2000, "$format": "json"}
        try:
            r = self.session.get(url, params=params, timeout=30)
            if r.ok:
                all_visits = r.json().get('value', [])
                pets = {p['Ref_Key']: p.get('Description', '') for p in self.get_pets_by_owner(owner_guid)}
                filtered = []
                for v in all_visits:
                    if v.get('Карточка_Key') in pets:
                        v['_pet_name'] = pets[v['Карточка_Key']]
                        filtered.append(v)
                return filtered
        except Exception:
            pass
        return []

    # ---------- Записи на прийом ----------
    def get_appointments_by_owner(self, owner_guid):
        if self.api_key:
            try:
                pets = self.get_pets_by_owner(owner_guid)
                pet_ids = [p['Ref_Key'] for p in pets]
                bookings = self._api_get('bookings', {'page_size': 2000})
                if bookings:
                    result = []
                    for b in bookings:
                        if b.get('patient', {}).get('patientId') in pet_ids:
                            result.append({
                                'ЗаписьНаДату': b.get('appointmentStartTime', ''),
                                'Кличка': b.get('patient', {}).get('petName', ''),
                                'Подтверждено': b.get('isConfirmed', False),
                                'Executed': b.get('objectState') == 'ACCEPTED'
                            })
                    if result:
                        return sorted(result, key=lambda x: x['ЗаписьНаДату'], reverse=True)
            except Exception:
                pass

        url = self._build_url("Task_ПредварительнаяЗапись")
        params = {"$orderby": "ЗаписьНаДату desc", "$top": 2000, "$format": "json"}
        try:
            r = self.session.get(url, params=params, timeout=30)
            if r.ok:
                all_apps = r.json().get('value', [])
                filtered = [a for a in all_apps if a.get('Хозяин_Key') == owner_guid]
                for a in filtered:
                    a['_pet_name'] = ''
                return filtered
        except Exception:
            pass
        return []

    # ---------- Аналізи (API v2) ----------
    def get_analyses_by_owner(self, owner_guid):
        if self.api_key:
            try:
                pets = self.get_pets_by_owner(owner_guid)
                pet_ids = [p['Ref_Key'] for p in pets]
                diagnostics = self._api_get('diagnostic', {'page_size': 2000})
                if diagnostics:
                    result = []
                    for d in diagnostics:
                        if d.get('patientId') in pet_ids:
                            pet_name = next((p['Description'] for p in pets if p['Ref_Key'] == d.get('patientId')), '')
                            result.append({
                                'Description': d.get('descriptionStudy', 'Дослідження'),
                                'Date': d.get('eventDate', ''),
                                '_pet_name': pet_name
                            })
                    if result:
                        return sorted(result, key=lambda x: x['Date'], reverse=True)
            except Exception:
                pass
        return []

    # ---------- Графік (OData) ----------
    def get_schedule(self):
        url = self._build_url("InformationRegister_ГрафикРаботы")
        params = {"$orderby": "Period desc", "$top": 500, "$format": "json"}
        try:
            r = self.session.get(url, params=params, timeout=30)
            if r.ok:
                data = r.json().get('value', [])
                doctors = self._get_doctors_odata()
                shifts = self._get_shifts_odata()
                result = []
                for entry in data:
                    period = entry.get('Period')
                    if not period:
                        continue
                    doctor_key = entry.get('ФизЛицо_Key')
                    shift_key = entry.get('Смена_Key')
                    shift_info = shifts.get(shift_key, {})
                    result.append({
                        'doctor': doctors.get(doctor_key, doctor_key),
                        'date': period[:10],
                        'start': shift_info.get('start', ''),
                        'end': shift_info.get('end', ''),
                        'works': entry.get('Работает'),
                        'allow_online': entry.get('РазрешитьОнлайнЗапись')
                    })
                return result
        except Exception:
            pass
        return []

    def _get_doctors_odata(self):
        url = self._build_url("Catalog_ФизическиеЛица")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                doctors = {}
                for d in r.json().get('value', []):
                    doctors[d['Ref_Key']] = d.get('Description', '')
                return doctors
        except Exception:
            pass
        return {}

    def _get_shifts_odata(self):
        url = self._build_url("Catalog_Смены")
        try:
            r = self.session.get(url, params={"$top": 200, "$format": "json"}, timeout=25)
            if r.ok:
                shifts = {}
                for s in r.json().get('value', []):
                    shifts[s['Ref_Key']] = {
                        'name': s.get('Description', ''),
                        'start': s.get('Время1', ''),
                        'end': s.get('Время2', '')
                    }
                return shifts
        except Exception:
            pass
        return {}

    # ---------- Пошук клієнта ----------
    def get_client_by_phone(self, phone):
        if self.api_key:
            try:
                digits = ''.join(filter(str.isdigit, phone))
                if not digits.startswith('+'):
                    digits = '+' + digits
                data = self._api_get('clients', {'phone_number': digits})
                if data and len(data) > 0:
                    return data[0].get('id')
            except Exception:
                pass

        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('38'):
            digits = digits[2:]
        url = self._build_url("Catalog_Клиенты")
        data = self._get(url, {
            "$filter": f"substringof('{digits}',КонтактнаяИнформация)",
            "$top": 1
        })
        if data:
            return data[0]['Ref_Key']
        return None

enote = EnoteClient()
