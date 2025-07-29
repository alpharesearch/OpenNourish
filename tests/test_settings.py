from flask import url_for
from models import db, User, MyFood, Recipe, UserGoal, CheckIn, DailyLog, ExerciseLog, MyMeal, Friendship
from datetime import date

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
        'week_start_day': 'Sunday',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.theme_preference == 'dark'

def test_update_week_start_day(client, auth_client):
    response = auth_client.post('/settings/', data={
        'age': '30',
        'gender': 'Male',
        'measurement_system': 'metric',
        'height_cm': '180',
        'navbar_preference': 'bg-dark navbar-dark',
        'diary_default_view': 'today',
        'theme_preference': 'light',
        'meals_per_day': '3',
        'week_start_day': 'Sunday',
        'submit_settings': 'Save Settings'
    }, follow_redirects=True)
    assert b"Your settings have been updated." in response.data
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        assert user.week_start_day == 'Sunday'

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

def test_set_timezone(auth_client_with_user):
    client, user = auth_client_with_user
    new_timezone = 'America/New_York'

    with client.application.test_request_context():
        response = client.post(
            url_for('settings.set_timezone', _external=False),
            json={'timezone': new_timezone}
        )
    assert response.status_code == 200
    assert response.json['status'] == 'success'
    assert response.json['message'] == 'Timezone updated.'

    with client.application.app_context():
        updated_user = db.session.get(User, user.id)
        assert updated_user.timezone == new_timezone

def test_set_timezone_no_timezone_provided(auth_client_with_user):
    client, user = auth_client_with_user

    with client.application.test_request_context():
        response = client.post(
            url_for('settings.set_timezone', _external=False),
            json={}
        )
    assert response.status_code == 400
    assert response.json['status'] == 'error'
    assert response.json['message'] == 'Timezone not provided.'

    with client.application.app_context():
        # Ensure timezone was not changed
        updated_user = db.session.get(User, user.id)
        assert updated_user.timezone == 'UTC' # Assuming initial timezone is UTC

def test_restart_onboarding(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        user.has_completed_onboarding = True
        db.session.commit()

    with client.application.test_request_context():
        response = client.post(url_for('settings.restart_onboarding', _external=False), follow_redirects=False)
    assert response.status_code == 302
    assert '/onboarding/step1' in response.headers['Location']

    with client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'info'
        assert flashes[0][1] == 'You have restarted the onboarding wizard.'

    with client.application.app_context():
        updated_user = db.session.get(User, user.id)
        assert updated_user.has_completed_onboarding is False

def test_delete_confirm_page(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.test_request_context():
        response = client.get(url_for('settings.delete_confirm', _external=False))
    assert response.status_code == 200
    assert b'Confirm Account Deletion' in response.data
    assert b'To confirm, please re-enter your current password.' in response.data

def test_delete_account_success(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        # Add some data associated with the user to verify deletion/anonymization
        my_food = MyFood(user_id=user.id, description='Test MyFood')
        recipe = Recipe(user_id=user.id, name='Test Recipe')
        user_goal = UserGoal(user_id=user.id, calories=2000)
        check_in = CheckIn(user_id=user.id, weight_kg=70)
        daily_log = DailyLog(user_id=user.id, log_date=date.today())
        exercise_log = ExerciseLog(user_id=user.id, manual_description='Running', duration_minutes=30, calories_burned=200)
        my_meal = MyMeal(user_id=user.id, name='Test Meal')
        # Create a friendship where user is requester and receiver
        friend_user_1 = User(username='friend1', email='friend1@example.com')
        friend_user_2 = User(username='friend2', email='friend2@example.com')
        db.session.add_all([friend_user_1, friend_user_2])
        db.session.commit()
        friendship_req = Friendship(requester_id=user.id, receiver_id=friend_user_1.id, status='accepted')
        friendship_rec = Friendship(requester_id=friend_user_2.id, receiver_id=user.id, status='accepted')

        db.session.add_all([my_food, recipe, user_goal, check_in, daily_log, exercise_log, my_meal, friendship_req, friendship_rec])
        db.session.commit()

        user_id = user.id # Store user_id before deletion
        my_food_id = my_food.id
        recipe_id = recipe.id
        user_goal_id = user_goal.id
        check_in_id = check_in.id
        daily_log_id = daily_log.id
        exercise_log_id = exercise_log.id
        my_meal_id = my_meal.id
        friendship_req_id = friendship_req.id
        friendship_rec_id = friendship_rec.id

    with client.application.test_request_context():
        response = client.post(
            url_for('settings.delete_account', _external=False),
            data={'password': 'password'},
            follow_redirects=False # Do not follow redirect to check session flashes
        )
    assert response.status_code == 302
    assert '/' in response.headers['Location']

    with client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'success'
        assert flashes[0][1] == 'Your account has been permanently deleted.'

    with client.application.app_context():
        # Verify user is deleted
        deleted_user = db.session.get(User, user_id)
        assert deleted_user is None

        # Verify associated data is handled
        assert db.session.get(MyFood, my_food_id).user_id is None
        assert db.session.get(Recipe, recipe_id).user_id is None
        assert db.session.get(UserGoal, user_goal_id) is None
        assert db.session.get(CheckIn, check_in_id) is None
        assert db.session.get(DailyLog, daily_log_id) is None
        assert db.session.get(ExerciseLog, exercise_log_id) is None
        assert db.session.get(MyMeal, my_meal_id) is None # MyMeal should be deleted due to cascade
        assert db.session.get(Friendship, friendship_req_id) is None
        assert db.session.get(Friendship, friendship_rec_id) is None

def test_delete_account_incorrect_password(auth_client_with_user):
    client, user = auth_client_with_user
    user_id = user.id # Store user_id before potential deletion

    with client.application.test_request_context():
        response = client.post(
            url_for('settings.delete_account', _external=False),
            data={'password': 'wrong_password'},
            follow_redirects=True
        )
    assert response.status_code == 200
    assert b'Incorrect password.' in response.data
    assert b'Confirm Account Deletion' in response.data # Should render the same page with error

    with client.application.app_context():
        # Verify user is NOT deleted
        existing_user = db.session.get(User, user_id)
        assert existing_user is not None
        assert existing_user.id == user_id

def test_delete_account_unauthenticated(client):
    with client.application.test_request_context():
        response = client.post(url_for('settings.delete_account', _external=False), data={'password': 'password'}, follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']