from flask import url_for
from models import db, User

def test_update_meals_per_day(client, auth_client):

    # Test setting meals_per_day to 6
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '180',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '6',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.meals_per_day == 6

    # Verify diary page shows all 6 meal types
    response = auth_client.get('/diary/')
    assert b"Breakfast" in response.data
    assert b"Snack (morning)" in response.data
    assert b"Lunch" in response.data
    assert b"Snack (afternoon)" in response.data
    assert b"Dinner" in response.data
    assert b"Snack (evening)" in response.data

    # Test setting meals_per_day to 3
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '180',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.meals_per_day == 3

    # Verify diary page shows only 3 meal types
    response = auth_client.get('/diary/')
    assert b"Breakfast" in response.data
    assert b"Snack (morning)" not in response.data
    assert b"Lunch" in response.data
    assert b"Snack (afternoon)" not in response.data
    assert b"Dinner" in response.data
    assert b"Snack (evening)" not in response.data

def test_update_age_and_gender(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '35',
        'gender': 'Female',
        'measurement_system': 'metric',
        'height_cm': '165',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.age == 35
        assert user.gender == 'Female'

def test_update_metric_height(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '175.5',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.measurement_system == 'metric'
        assert user.height_cm == 175.5

def test_update_us_height(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'us',
        'height_ft': '5',
        'height_in': '10',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.measurement_system == 'us'
        # 5 feet 10 inches = 70 inches = 177.8 cm
        assert user.height_cm == 177.8

def test_update_navbar_preference(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '180',
        'navbar_preference': 'bg-primary navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.navbar_preference == 'bg-primary navbar-dark'

def test_update_diary_default_view(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '180',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'yesterday',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.diary_default_view == 'yesterday'

def test_update_theme_preference(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '180',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'dark',
        'meals_per_day': '3',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.theme_preference == 'dark'

def test_change_password(client, auth_client):
    response = auth_client.post('/settings/', data={
        'password': 'new_password',
        'password2': 'new_password',
        'submit_password': 'Change Password'
    }, follow_redirects=True)
    assert b"Your password has been changed." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.check_password('new_password')
        assert not user.check_password('password') # Assuming initial password was 'password'