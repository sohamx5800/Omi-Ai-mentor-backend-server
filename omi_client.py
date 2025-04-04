import requests
from config import OMI_API_KEY, OMI_APP_ID

class OmiClient:
    BASE_URL = "https://api.omi.me/v2/integrations"

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {OMI_API_KEY}",
            "X-App-ID": OMI_APP_ID,
            "Content-Type": "application/json"
        }

    def read_memories(self, user_id):
        try:
            response = requests.get(f"{self.BASE_URL}/{OMI_APP_ID}/user/memories?uid={user_id}", headers=self.headers)
            return response.json() if response.status_code == 200 else []
        except requests.RequestException:
            return []  # Fallback to empty list on failure

    def write_memory(self, user_id, memory_data):
        try:
            data = {"uid": user_id, "title": memory_data["title"], "summary": memory_data["summary"]}
            response = requests.post(f"{self.BASE_URL}/{OMI_APP_ID}/user/memories", json=data, headers=self.headers)
            return response.json() if response.status_code == 201 else None
        except requests.RequestException:
            return None

    def delete_memory(self, user_id, memory_id):
        try:
            response = requests.delete(f"{self.BASE_URL}/{OMI_APP_ID}/user/memories/{memory_id}?uid={user_id}", headers=self.headers)
            return response.status_code == 204
        except requests.RequestException:
            return False

    def read_conversations(self, user_id):
        try:
            response = requests.get(f"{self.BASE_URL}/{OMI_APP_ID}/conversations?uid={user_id}", headers=self.headers)
            return response.json() if response.status_code == 200 else []
        except requests.RequestException:
            return []