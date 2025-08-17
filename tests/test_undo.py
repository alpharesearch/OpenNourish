from models import db, DailyLog, User, MyFood, CheckIn
from datetime import date


def test_hard_delete_and_reinsert(client, auth_client):
    # 1. Create and delete a DailyLog entry
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        log = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name="Breakfast",
            amount_grams=100,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    auth_client.post(f"/diary/log/{log_id}/delete")

    # 2. Verify it's gone from the DB
    with auth_client.application.app_context():
        deleted_log = db.session.get(DailyLog, log_id)
        assert deleted_log is None

    # 3. Verify the session contains the correct data
    with auth_client.session_transaction() as session:
        assert "last_deleted" in session
        assert session["last_deleted"]["undo_method"] == "reinsert"
        assert session["last_deleted"]["data"]["id"] == log_id

    # 4. Call the undo route
    auth_client.get("/undo")

    # 5. Verify the DailyLog has been re-created
    with auth_client.application.app_context():
        restored_log = db.session.get(DailyLog, log_id)
        assert restored_log is not None
        assert restored_log.meal_name == "Breakfast"


def test_anonymize_and_reassign(client, auth_client):
    # 1. Create a MyFood entry
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(user_id=user.id, description="Test Food")
        db.session.add(my_food)
        db.session.commit()
        food_id = my_food.id
        original_user_id = user.id

    # 2. Call the delete_my_food endpoint
    auth_client.post(f"/my_foods/{food_id}/delete")

    # 3. Verify the entry still exists but its user_id is None
    with auth_client.application.app_context():
        anonymized_food = db.session.get(MyFood, food_id)
        assert anonymized_food is not None
        assert anonymized_food.user_id is None

    # 4. Verify the session contains the correct data
    with auth_client.session_transaction() as session:
        assert "last_deleted" in session
        assert session["last_deleted"]["undo_method"] == "reassign_owner"
        assert session["last_deleted"]["data"]["item_id"] == food_id
        assert session["last_deleted"]["data"]["original_user_id"] == original_user_id

    # 5. Call the undo route
    auth_client.get("/undo")

    # 6. Verify the user_id has been restored
    with auth_client.application.app_context():
        restored_food = db.session.get(MyFood, food_id)
        assert restored_food is not None
        assert restored_food.user_id == original_user_id


def test_undo_overwrite(client, auth_client):
    # 1. Create two test items
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        log = DailyLog(
            user_id=user.id, log_date=date.today(), meal_name="Lunch", amount_grams=200
        )
        check_in = CheckIn(user_id=user.id, checkin_date=date.today(), weight_kg=70)
        db.session.add_all([log, check_in])
        db.session.commit()
        log_id = log.id
        check_in_id = check_in.id

    # 2. Delete a DailyLog, then delete a CheckIn
    auth_client.post(f"/diary/log/{log_id}/delete")
    auth_client.post(f"/tracking/check-in/{check_in_id}/delete")

    # 3. Verify the session only contains the CheckIn data
    with auth_client.session_transaction() as session:
        assert "last_deleted" in session
        assert session["last_deleted"]["type"] == "check_in"
        assert session["last_deleted"]["data"]["id"] == check_in_id

    # 4. Call undo
    auth_client.get("/undo")

    # 5. Verify CheckIn is restored and DailyLog is not
    with auth_client.application.app_context():
        restored_check_in = db.session.get(CheckIn, check_in_id)
        assert restored_check_in is not None
        deleted_log = db.session.get(DailyLog, log_id)
        assert deleted_log is None


def test_invalid_undo(client, auth_client):
    # 1. Call the undo route with an empty session
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    assert b"No action to undo." in response.data
