"""Coverage + regression tests for opennourish/undo/routes.py (DOX security items:
BuildError default endpoints and session-supplied user_id/PK spoofing).
"""

from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from models import db, DailyLog, MyFood, User


def _payload(client):
    with client.session_transaction() as sess:
        return sess.get("last_deleted")


def _set(client, value):
    with client.session_transaction() as sess:
        sess["last_deleted"] = value


def test_undo_without_session_entry(auth_client):
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    assert b"No action to undo." in response.data


def test_undo_reinsert_happy_path_restores_owner_row(auth_client, app_with_db):
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        log = DailyLog(user_id=user.id, log_date=date(2026, 1, 1), meal_name="Snack")
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        data = {
            "id": log_id,
            "user_id": user.id,
            "log_date": "2026-01-01",
            "meal_name": "Snack",
        }
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": data,
            "redirect_info": {"endpoint": "dashboard.index"},
        },
    )
    with app_with_db.app_context():
        db.session.delete(db.session.get(DailyLog, log_id))
        db.session.commit()
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    with app_with_db.app_context():
        restored = db.session.get(DailyLog, log_id)
        assert restored is not None
        assert restored.user_id == user.id


def test_undo_reinsert_rejects_foreign_user_id(auth_client, app_with_db):
    with app_with_db.app_context():
        victim = User(username="victim", email="victim@example.com")
        victim.set_password("password")
        db.session.add(victim)
        db.session.commit()
        victim_id = victim.id
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "id": 555555,
                "user_id": victim_id,
                "log_date": "2026-01-01",
                "meal_name": "Snack",
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data
    with app_with_db.app_context():
        assert db.session.get(DailyLog, 555555) is None


def test_undo_reinsert_refuses_existing_primary_key(auth_client_two_users, app_with_db):
    client, user_one, user_two = auth_client_two_users
    with app_with_db.app_context():
        row = DailyLog(
            user_id=user_two.id, log_date=date(2026, 1, 1), meal_name="Snack"
        )
        db.session.add(row)
        db.session.commit()
        taken_id = row.id
    _set(
        client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "id": taken_id,
                "user_id": user_one.id,
                "log_date": "2026-01-02",
                "meal_name": "Snack",
            },
        },
    )
    response = client.get("/undo", follow_redirects=True)
    assert b"already exists" in response.data
    with app_with_db.app_context():
        assert db.session.get(DailyLog, taken_id).user_id == user_two.id


def test_undo_reinsert_rejects_non_numeric_id(auth_client):
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "id": "1; DROP TABLE users",
                "user_id": 1,
                "log_date": "2026-01-01",
                "meal_name": "Snack",
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"id is invalid" in response.data


def test_undo_reassign_refused_for_other_users_owned_row(auth_client, app_with_db):
    with app_with_db.app_context():
        victim = User(username="victim", email="victim@example.com")
        victim.set_password("password")
        db.session.add(victim)
        db.session.commit()
        victim_id = victim.id
        food = MyFood(user_id=victim_id, description="Theirs", calories_per_100g=1)
        db.session.add(food)
        db.session.commit()
        food_id = food.id
    _set(
        auth_client,
        {
            "type": "my_food",
            "undo_method": "reassign_owner",
            "data": {"item_id": food_id, "original_user_id": victim_id},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data
    with app_with_db.app_context():
        assert db.session.get(MyFood, food_id).user_id == victim_id


def test_undo_reassign_restores_orphaned_row_to_caller(auth_client, app_with_db):
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        user_id = user.id
        food = MyFood(user_id=None, description="Orphan", calories_per_100g=1)
        db.session.add(food)
        db.session.commit()
        food_id = food.id
    _set(
        auth_client,
        {
            "type": "my_food",
            "undo_method": "reassign_owner",
            "data": {"item_id": food_id, "original_user_id": user_id},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    with app_with_db.app_context():
        assert db.session.get(MyFood, food_id).user_id == user_id


def test_undo_reassign_of_row_owned_by_someone_else_rejected(auth_client, app_with_db):
    # DailyLog is owner-addressable; claiming the victim's still-owned row via
    # a tampered reassign payload must be refused.
    with app_with_db.app_context():
        victim = User(username="victim", email="victim@example.com")
        victim.set_password("password")
        db.session.add(victim)
        db.session.commit()
        victim_id = victim.id
        log = DailyLog(user_id=victim_id, log_date=date(2026, 1, 1), meal_name="Snack")
        db.session.add(log)
        db.session.commit()
        log_id = log.id
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reassign_owner",
            "data": {"item_id": log_id, "original_user_id": victim_id},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data
    with app_with_db.app_context():
        assert db.session.get(DailyLog, log_id).user_id == victim_id


def test_undo_malformed_records_do_not_500(auth_client):
    # Session value that is not a dict at all.
    _set(auth_client, "not-a-dict")
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    assert b"malformed" in response.data

    # data is not a dict.
    _set(
        auth_client,
        {"type": "dailylog", "undo_method": "reinsert", "data": None},
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    assert b"malformed" in response.data


def test_undo_unknown_method_and_type_are_handled(auth_client):
    _set(
        auth_client,
        {"type": "dailylog", "undo_method": "teleport", "data": {"id": 1}},
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Unknown undo method" in response.data

    _set(
        auth_client,
        {"type": "not_a_model", "undo_method": "reinsert", "data": {"user_id": 1}},
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Unknown item type" in response.data


def test_undo_bad_redirect_endpoint_degrades_to_diary(auth_client, app_with_db):
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "id": 666666,
                "user_id": user.id,
                "log_date": "2026-01-01",
                "meal_name": "Snack",
            },
            "redirect_info": {"endpoint": "no.such.endpoint"},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert response.status_code == 200
    assert b"Could not build the original page URL." in response.data


def test_undo_reinsert_unknown_column_is_not_written(auth_client):
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "user_id": 1,
                "evil_column": "boom",
                "log_date": "2026-01-01",
                "meal_name": "Snack",
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Could not restore the item." in response.data


# --- ownership derivation from payload foreign keys -------------------------


def _uid(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().id


def test_owner_derivation_friendship_parties(auth_client, app_with_db):
    uid = _uid(app_with_db, "testuser")
    # A friendship naming the caller as a party passes the owner check.
    _set(
        auth_client,
        {
            "type": "friendship",
            "undo_method": "reinsert",
            "data": {
                "id": 424242,
                "requester_id": uid,
                "receiver_id": uid + 500,
                "status": "accepted",
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" not in response.data

    # Neither party is the caller -> rejected.
    _set(
        auth_client,
        {
            "type": "friendship",
            "undo_method": "reinsert",
            "data": {
                "id": 424243,
                "requester_id": uid + 500,
                "receiver_id": uid + 501,
                "status": "accepted",
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_owner_derivation_recipe_ingredient_parent(auth_client, app_with_db):
    from models import Recipe, RecipeIngredient

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        mine = Recipe(user_id=uid, name="Mine")
        db.session.add(mine)
        db.session.commit()
        my_recipe_id = mine.id
    _set(
        auth_client,
        {
            "type": "recipe_ingredient",
            "undo_method": "reinsert",
            "data": {"id": 3001, "recipe_id": my_recipe_id, "amount_grams": 5},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" not in response.data
    with app_with_db.app_context():
        assert db.session.get(RecipeIngredient, 3001) is not None

    # A parent recipe owned by nobody current -> rejected.
    _set(
        auth_client,
        {
            "type": "recipe_ingredient",
            "undo_method": "reinsert",
            "data": {"id": 3002, "recipe_id": 999999, "amount_grams": 5},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data

    # Non-int recipe_id cannot prove ownership.
    _set(
        auth_client,
        {
            "type": "recipe_ingredient",
            "undo_method": "reinsert",
            "data": {"id": 3003, "recipe_id": "abc", "amount_grams": 5},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_owner_derivation_meal_item_parent(auth_client, app_with_db):
    from models import MyMeal

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        meal = MyMeal(user_id=uid, name="Mine Meal")
        db.session.add(meal)
        db.session.commit()
        meal_id = meal.id
    _set(
        auth_client,
        {
            "type": "mymealitem",
            "undo_method": "reinsert",
            "data": {"id": 3101, "my_meal_id": meal_id, "amount_grams": 10},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" not in response.data

    _set(
        auth_client,
        {
            "type": "mymealitem",
            "undo_method": "reinsert",
            "data": {"id": 3102, "my_meal_id": 999999, "amount_grams": 10},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_owner_derivation_portion_parents(auth_client, app_with_db):
    from models import MyFood, UnifiedPortion

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        food = MyFood(user_id=uid, description="Sauce", calories_per_100g=1)
        db.session.add(food)
        db.session.commit()
        food_id = food.id
    _set(
        auth_client,
        {
            "type": "portion",
            "undo_method": "reinsert",
            "data": {
                "id": 4001,
                "my_food_id": food_id,
                "portion_description": "Spoon",
                "gram_weight": 15,
                "seq_num": 1,
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" not in response.data
    with app_with_db.app_context():
        assert db.session.get(UnifiedPortion, 4001) is not None

    # A portion without any resolvable parent is refused.
    _set(
        auth_client,
        {
            "type": "portion",
            "undo_method": "reinsert",
            "data": {"id": 4002, "portion_description": "Nobody's", "gram_weight": 1},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_fdc_portion_requires_key_user(client, app_with_db):
    # Non-key users may not reinsert shared USDA portions.
    with app_with_db.app_context():
        plain = User(username="plain", email="plain@example.com")
        plain.set_password("password")
        db.session.add(plain)
        db.session.commit()
        plain_id = plain.id
    with client.session_transaction() as sess:
        sess["_user_id"] = plain_id
        sess["_fresh"] = True
    _set(
        client,
        {
            "type": "portion",
            "undo_method": "reinsert",
            "data": {
                "id": 5001,
                "fdc_id": 12345,
                "description": "cup",
                "gram_weight": 120,
                "seq_num": 9,
            },  # noqa: E501
        },
    )
    response = client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_fdc_portion_reinsert_allowed_for_key_user(client, app_with_db):
    from models import UnifiedPortion

    with app_with_db.app_context():
        key = User(username="keyuser", email="key@example.com", is_key_user=True)
        key.set_password("password")
        db.session.add(key)
        db.session.commit()
        key_id = key.id
    with client.session_transaction() as sess:
        sess["_user_id"] = key_id
        sess["_fresh"] = True
    _set(
        client,
        {
            "type": "portion",
            "undo_method": "reinsert",
            "data": {
                "id": 5002,
                "fdc_id": 12345,
                "portion_description": "cup",
                "gram_weight": 120,
                "seq_num": 9,
            },
        },
    )
    response = client.get("/undo", follow_redirects=True)
    assert b"permission to restore" not in response.data
    with app_with_db.app_context():
        assert db.session.get(UnifiedPortion, 5002) is not None


# --- reassign helper error branches -----------------------------------------


def test_reassign_helper_error_branches(auth_client, app_with_db):
    # Unknown model type.
    _set(
        auth_client,
        {"type": "nope", "undo_method": "reassign_owner", "data": {"item_id": 1}},
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Unknown item type" in response.data

    # Bool ids are invalid.
    _set(
        auth_client,
        {
            "type": "my_food",
            "undo_method": "reassign_owner",
            "data": {"item_id": True, "original_user_id": 1},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"stored id is invalid" in response.data

    # Item does not exist.
    _set(
        auth_client,
        {
            "type": "my_food",
            "undo_method": "reassign_owner",
            "data": {"item_id": 999998, "original_user_id": 1},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Could not find the item to restore." in response.data

    # Models without a user_id column (UnifiedPortion) can never be reassigned.
    _set(
        auth_client,
        {
            "type": "portion",
            "undo_method": "reassign_owner",
            "data": {"item_id": 1, "original_user_id": 1},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_reinsert_numeric_string_id_is_converted(auth_client, app_with_db):
    uid = _uid(app_with_db, "testuser")
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "id": "987650",
                "user_id": uid,
                "log_date": "2026-01-01",
                "meal_name": "Snack",
            },
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Item restored." in response.data
    with app_with_db.app_context():
        assert db.session.get(DailyLog, 987650) is not None


def test_reassign_commit_failure_rolls_back(auth_client, app_with_db, monkeypatch):
    from sqlalchemy.orm.scoping import scoped_session

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        food = MyFood(user_id=None, description="Ghost", calories_per_100g=1)
        db.session.add(food)
        db.session.commit()
        food_id = food.id

    def boom(self, *args, **kwargs):
        raise SQLAlchemyError("simulated commit failure")

    monkeypatch.setattr(scoped_session, "commit", boom)
    _set(
        auth_client,
        {
            "type": "my_food",
            "undo_method": "reassign_owner",
            "data": {"item_id": food_id, "original_user_id": uid},
        },
    )
    # Read the flash straight from the session: following the redirect would
    # depend on which page (diary vs onboarding) finally renders it.
    response = auth_client.get("/undo", follow_redirects=False)
    monkeypatch.undo()
    assert response.status_code == 302
    with auth_client.session_transaction() as sess:
        assert "Could not restore the item." in str(sess.get("_flashes", ""))
    with app_with_db.app_context():
        assert db.session.get(MyFood, food_id).user_id is None


def test_redirect_info_non_string_endpoint_falls_back(auth_client, app_with_db):
    uid = _uid(app_with_db, "testuser")
    _set(
        auth_client,
        {
            "type": "dailylog",
            "undo_method": "reinsert",
            "data": {
                "id": "987651",
                "user_id": uid,
                "log_date": "2026-01-01",
                "meal_name": "Snack",
            },
            "redirect_info": {"endpoint": 42, "params": ["not", "a", "dict"]},
        },
    )
    response = auth_client.get("/undo", follow_redirects=False)
    assert response.status_code == 302
    assert "/diary" in response.headers["Location"]


def test_recipe_ingredient_reinsert_uses_parent_recipe_owner(auth_client, app_with_db):
    """Portionless recipe_ingredient payloads resolve ownership through the
    parent Recipe (lines around the recipe_ingredient owner branch)."""
    from models import Recipe, RecipeIngredient

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        recipe = Recipe(user_id=uid, name="Undo Parent")
        db.session.add(recipe)
        db.session.flush()
        ing = RecipeIngredient(recipe_id=recipe.id, amount_grams=50, seq_num=1)
        db.session.add(ing)
        db.session.commit()
        ing_id, recipe_id = ing.id, recipe.id
    _set(
        auth_client,
        {
            "type": "recipe_ingredient",
            "undo_method": "reinsert",
            "data": {
                "id": ing_id,
                "recipe_id": recipe_id,
                "amount_grams": 50,
                "seq_num": 1,
            },
        },
    )
    with app_with_db.app_context():
        db.session.delete(db.session.get(RecipeIngredient, ing_id))
        db.session.commit()
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Item restored." in response.data
    with app_with_db.app_context():
        assert db.session.get(RecipeIngredient, ing_id) is not None


def test_recipe_portion_reinsert_uses_parent_recipe_owner(auth_client, app_with_db):
    """A portion payload keyed by recipe_id proves ownership via the recipe."""
    from models import Recipe, UnifiedPortion

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        recipe = Recipe(user_id=uid, name="Portion Parent")
        db.session.add(recipe)
        db.session.flush()
        portion = UnifiedPortion(
            recipe_id=recipe.id,
            amount=1,
            measure_unit_description="g",
            portion_description="",
            modifier="",
            gram_weight=1.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()
        portion_id, recipe_id = portion.id, recipe.id
    _set(
        auth_client,
        {
            "type": "portion",
            "undo_method": "reinsert",
            "data": {
                "id": portion_id,
                "recipe_id": recipe_id,
                "amount": 1,
                "measure_unit_description": "g",
                "portion_description": "",
                "modifier": "",
                "gram_weight": 1.0,
                "seq_num": 1,
            },
        },
    )
    with app_with_db.app_context():
        db.session.delete(db.session.get(UnifiedPortion, portion_id))
        db.session.commit()
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Item restored." in response.data
    with app_with_db.app_context():
        assert db.session.get(UnifiedPortion, portion_id) is not None


def test_fasting_session_reinsert_converts_full_datetime(auth_client, app_with_db):
    """start_time is a DateTime column: a full ISO datetime string converts."""
    from models import FastingSession

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        session = FastingSession(
            user_id=uid,
            planned_duration_hours=16,
            status="completed",
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id
    _set(
        auth_client,
        {
            "type": "fasting_session",
            "undo_method": "reinsert",
            "data": {
                "id": session_id,
                "user_id": uid,
                "start_time": "2026-01-01T10:00:00",
                "planned_duration_hours": 16,
                "status": "completed",
            },
        },
    )
    with app_with_db.app_context():
        db.session.delete(db.session.get(FastingSession, session_id))
        db.session.commit()
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Item restored." in response.data
    with app_with_db.app_context():
        restored = db.session.get(FastingSession, session_id)
        assert restored is not None
        assert restored.start_time.year == 2026


def test_fasting_session_reinsert_falls_back_for_date_only_string(
    auth_client, app_with_db
):
    """A date-only string in a DateTime column hits the ValueError fallback."""
    from models import FastingSession

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        session = FastingSession(
            user_id=uid, planned_duration_hours=12, status="completed"
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id
    _set(
        auth_client,
        {
            "type": "fasting_session",
            "undo_method": "reinsert",
            "data": {
                "id": session_id,
                "user_id": uid,
                "start_time": "2026-02-02",
                "planned_duration_hours": 12,
                "status": "completed",
            },
        },
    )
    with app_with_db.app_context():
        db.session.delete(db.session.get(FastingSession, session_id))
        db.session.commit()
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Item restored." in response.data


def test_mymealitem_without_int_parent_id_cannot_prove_owner(auth_client, app_with_db):
    _set(
        auth_client,
        {
            "type": "mymealitem",
            "undo_method": "reinsert",
            "data": {"id": 987652, "my_meal_id": "x", "amount_grams": 1},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_portion_without_any_parent_id_cannot_prove_owner(auth_client, app_with_db):
    _set(
        auth_client,
        {
            "type": "portion",
            "undo_method": "reinsert",
            "data": {"id": 987653, "gram_weight": 1.0},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data


def test_unparseable_datetime_reports_restore_failure(auth_client, app_with_db):
    """Garbage in a DateTime column hits the ValueError fallback inside
    _apply_session_types, which then fails and rolls back cleanly."""
    from models import FastingSession

    with app_with_db.app_context():
        uid = _uid(app_with_db, "testuser")
        session = FastingSession(
            user_id=uid, planned_duration_hours=8, status="completed"
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id
    _set(
        auth_client,
        {
            "type": "fasting_session",
            "undo_method": "reinsert",
            "data": {
                "id": session_id,
                "user_id": uid,
                "start_time": "yesterday-ish",
                "planned_duration_hours": 8,
                "status": "completed",
            },
        },
    )
    with app_with_db.app_context():
        db.session.delete(db.session.get(FastingSession, session_id))
        db.session.commit()
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"Could not restore the item." in response.data
    with app_with_db.app_context():
        assert db.session.get(FastingSession, session_id) is None


def test_food_category_payload_cannot_prove_owner(auth_client, app_with_db):
    """FoodCategory rows have no owner column and no special branch; the
    ownership resolver must fall through to None and reject the restore."""
    _set(
        auth_client,
        {
            "type": "food_category",
            "undo_method": "reinsert",
            "data": {"id": 987654, "name": "Ghost Category"},
        },
    )
    response = auth_client.get("/undo", follow_redirects=True)
    assert b"permission to restore" in response.data
