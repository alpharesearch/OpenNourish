# tests/test_app.py

from models import db, Food

def test_home_page_loads(client):
    response = client.get('/')
    assert response.status_code == 302 # Expect redirect for non-logged-in user

