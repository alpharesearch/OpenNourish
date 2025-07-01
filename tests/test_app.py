# tests/test_app.py

from models import db, Food

def test_home_page_loads(client):
    response = client.get('/')
    assert response.status_code == 302 # Expect redirect for non-logged-in user

def test_search_feature(auth_client):
    with auth_client.application.app_context():
        # Add test data directly within the test function
        test_food_1 = Food(fdc_id=1, description='Test Apple')
        test_food_2 = Food(fdc_id=2, description='Test Butter')
        db.session.add(test_food_1)
        db.session.add(test_food_2)
        db.session.commit()

    response = auth_client.get('/database/search?q=Test+Apple') # Use GET and correct endpoint
    assert response.status_code == 200
    # Check for the specific test data
    assert b'Test Apple' in response.data
    # Check that other test data is NOT in the response
    assert b'Test Butter' not in response.data