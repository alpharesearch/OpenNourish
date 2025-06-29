# tests/test_app.py

def test_home_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200

def test_search_feature(client):
    # This test now uses the 'Test Apple' we created in conftest.py
    response = client.post('/', data={'search': 'Test Apple'})
    assert response.status_code == 200
    # Check for the specific test data
    assert b'Test Apple' in response.data
    # Check that other test data is NOT in the response
    assert b'Test Butter' not in response.data