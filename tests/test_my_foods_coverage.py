"""Coverage and regression tests for ``opennourish/my_foods``.

Ownership is always asserted in both directions: the owner's request succeeds
and changes the row, the stranger's request is refused and the row is
unchanged. Locked regressions:

* portion routes must not dereference ``portion.my_food.user_id`` for USDA or
  recipe portions (``my_food`` is ``None`` there, which used to be a 500).
* ``delete_category`` may only clear the category on the owner's own foods.
"""

from io import BytesIO
from unittest.mock import patch

import pytest

from models import (
    db,
    Food,
    FoodCategory,
    FoodNutrient,
    MyFood,
    Nutrient,
    UnifiedPortion,
    User,
)


def make_food(user_id, description="Sample Food", calories=100.0, portions=()):
    """Create a ``MyFood`` with the given ``(gram_weight, seq)`` portions."""
    food = MyFood(
        user_id=user_id,
        description=description,
        calories_per_100g=calories,
        protein_per_100g=5.0,
        carbs_per_100g=10.0,
        fat_per_100g=2.0,
    )
    db.session.add(food)
    db.session.flush()
    portion_ids = []
    for gram_weight, seq in portions:
        portion = UnifiedPortion(
            my_food_id=food.id,
            gram_weight=gram_weight,
            amount=1.0,
            measure_unit_description="g",
            seq_num=seq,
        )
        db.session.add(portion)
        db.session.flush()
        portion_ids.append(portion.id)
    db.session.commit()
    return food.id, portion_ids


def make_usda_food(fdc_id=12345, description="USDA Apple"):
    """Create a USDA food with mapped + unmapped nutrients and one portion."""
    db.session.add(Food(fdc_id=fdc_id, description=description, ingredients="apples"))
    db.session.add_all(
        [
            Nutrient(id=1008, name="Energy", unit_name="kcal"),
            Nutrient(id=1003, name="Protein", unit_name="g"),
            Nutrient(id=1093, name="Sodium, Na", unit_name="mg"),
            Nutrient(id=9999, name="Something Obscure", unit_name="g"),
        ]
    )
    db.session.add_all(
        [
            FoodNutrient(fdc_id=fdc_id, nutrient_id=1008, amount=52.0),
            FoodNutrient(fdc_id=fdc_id, nutrient_id=1003, amount=0.3),
            FoodNutrient(fdc_id=fdc_id, nutrient_id=1093, amount=1.0),
            FoodNutrient(fdc_id=fdc_id, nutrient_id=9999, amount=7.0),
        ]
    )
    usda_portion = UnifiedPortion(
        fdc_id=fdc_id,
        gram_weight=100.0,
        amount=1.0,
        measure_unit_description="apple",
        portion_description="medium",
        seq_num=1,
    )
    db.session.add(usda_portion)
    db.session.commit()
    return fdc_id, usda_portion.id


def username_of(client, user_id):
    return db.session.get(User, user_id).username


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_my_foods_list_user_view_and_pagination(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        for i in range(12):
            db.session.add(MyFood(user_id=user_id, description=f"Paged Food {i:02d}"))
        db.session.commit()

    first = auth_client.get("/my_foods/")
    second = auth_client.get("/my_foods/?page=2")
    beyond = auth_client.get("/my_foods/?page=99")
    junk = auth_client.get("/my_foods/?page=abc")

    assert first.status_code == second.status_code == 200
    assert b"Paged Food 00" in first.data
    assert b"Paged Food 11" in second.data
    assert b"Paged Food 00" not in second.data
    assert beyond.status_code == junk.status_code == 200


def test_my_foods_list_friends_view_without_friends(auth_client_with_user):
    client, user = auth_client_with_user

    with client.application.app_context():
        db.session.add(MyFood(user_id=user.id, description="Private Property"))
        db.session.commit()

    page = client.get("/my_foods/?view=friends")

    assert page.status_code == 200
    assert b"No custom foods found from your friends." in page.data
    assert b"Private Property" not in page.data


def test_my_foods_list_friends_view_with_friend_foods(auth_client_with_friendship):
    client, me, friend = auth_client_with_friendship

    with client.application.app_context():
        db.session.add(MyFood(user_id=friend.id, description="Friend Yogurt"))
        db.session.commit()

    page = client.get("/my_foods/?view=friends")

    assert page.status_code == 200
    assert b"Friend Yogurt" in page.data
    assert friend.username.encode() in page.data


# ---------------------------------------------------------------------------
# new_my_food
# ---------------------------------------------------------------------------


def test_new_my_food_get_offers_user_and_global_categories(auth_client):
    with auth_client.application.app_context():
        db.session.add(FoodCategory(description="My Home Meals", user_id=1))
        db.session.add(FoodCategory(description="Dairy And Eggs", user_id=None))
        db.session.commit()

    page = auth_client.get("/my_foods/new")

    assert page.status_code == 200
    assert b"My Home Meals" in page.data
    assert b"Dairy And Eggs" in page.data


def test_new_my_food_requires_a_usable_gram_weight(auth_client):
    """A zero/missing portion weight is refused and nothing is stored."""
    for gram_weight in ("0", ""):
        response = auth_client.post(
            "/my_foods/new",
            data={
                "description": "Zero Weight Food",
                "calories_per_100g": 10,
                "amount": 1,
                "measure_unit_description": "slice",
                "gram_weight": gram_weight,
            },
            follow_redirects=True,
        )
        assert b"Custom food added successfully!" not in response.data
        with auth_client.application.app_context():
            assert (
                MyFood.query.filter_by(description="Zero Weight Food").first() is None
            )


def test_new_my_food_creates_user_category_but_skips_same_as_description(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id

    response = auth_client.post(
        "/my_foods/new",
        data={
            "description": "Granola Crunch",
            "food_category": "granola crunch",  # same text as the description
            "calories_per_100g": 40,
            "amount": 1,
            "measure_unit_description": "bowl",
            "gram_weight": 40,
        },
        follow_redirects=True,
    )
    assert b"Custom food added successfully!" in response.data
    with auth_client.application.app_context():
        food = MyFood.query.filter_by(description="Granola Crunch").first()
        assert food.food_category_id is None

    response = auth_client.post(
        "/my_foods/new",
        data={
            "description": "Protein Bar",
            "food_category": "Bars",
            "calories_per_100g": 50,
            "amount": 1,
            "measure_unit_description": "bar",
            "gram_weight": 50,
        },
        follow_redirects=True,
    )
    assert b"Custom food added successfully!" in response.data
    with auth_client.application.app_context():
        food = MyFood.query.filter_by(description="Protein Bar").first()
        category = db.session.get(FoodCategory, food.food_category_id)
        assert category.description == "Bars"
        assert category.user_id == user_id
        assert food.calories_per_100g == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# edit_my_food
# ---------------------------------------------------------------------------


def test_edit_my_food_get_prefills_category_and_portion_selection(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        category = FoodCategory(description="Leftovers", user_id=user_id)
        db.session.add(category)
        db.session.flush()
        food_id, portion_ids = make_food(
            user_id, "Edit Target", 400.0, [(1.0, 1), (50.0, 2)]
        )
        food = db.session.get(MyFood, food_id)
        food.food_category_id = category.id
        db.session.commit()

    page = auth_client.get(f"/my_foods/{food_id}/edit")
    assert page.status_code == 200
    assert b"Leftovers" in page.data

    # A portion of this food is honoured.
    page = auth_client.get(f"/my_foods/{food_id}/edit?portion_id={portion_ids[1]}")
    assert page.status_code == 200

    # Somebody else's (or a nonsense) portion id falls back to the first one.
    page = auth_client.get(f"/my_foods/{food_id}/edit?portion_id=987654")
    assert page.status_code == 200


def test_edit_my_food_rejects_other_users_food(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        food_id, _ = make_food(user_two.id, "User Two Yogurt", 90.0, [(1.0, 1)])

    response = client.get(f"/my_foods/{food_id}/edit", follow_redirects=True)

    assert b"You are not authorized to edit this food." in response.data
    with client.application.app_context():
        assert db.session.get(MyFood, food_id).description == "User Two Yogurt"

    response = client.post(
        f"/my_foods/{food_id}/edit",
        data={"description": "Hijacked", "selected_portion_id": 1},
        follow_redirects=True,
    )
    assert b"You are not authorized to edit this food." in response.data
    with client.application.app_context():
        assert db.session.get(MyFood, food_id).description == "User Two Yogurt"


def test_edit_my_food_rescales_all_nutrient_fields(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        food_id, portion_ids = make_food(user_id, "Scaled Food", 10.0, [(50.0, 1)])
        # 50 g portion: the submitted values are for 50 g and must double.
        portion_id = portion_ids[0]

    response = auth_client.post(
        f"/my_foods/{food_id}/edit",
        data={
            "description": "Rescaled Food",
            "ingredients": "water, salt",
            "upc": "1234567890",
            "fdc_id": "12345",
            "selected_portion_id": portion_id,
            "calories_per_100g": 100,
            "protein_per_100g": 10,
            "carbs_per_100g": 20,
            "fat_per_100g": 5,
            "saturated_fat_per_100g": 1,
            "trans_fat_per_100g": 0.5,
            "cholesterol_mg_per_100g": 30,
            "sodium_mg_per_100g": 200,
            "fiber_per_100g": 3,
            "sugars_per_100g": 4,
            "added_sugars_per_100g": 2,
            "vitamin_d_mcg_per_100g": 1.5,
            "calcium_mg_per_100g": 60,
            "iron_mg_per_100g": 2,
            "potassium_mg_per_100g": 300,
        },
    )

    assert response.status_code == 302
    assert f"/my_foods/{food_id}/edit" in response.headers["Location"]
    assert b"portion_id=" in response.headers["Location"].encode()

    with auth_client.application.app_context():
        food = db.session.get(MyFood, food_id)
        assert food.description == "Rescaled Food"
        assert food.ingredients == "water, salt"
        assert food.upc == "1234567890"
        assert food.calories_per_100g == pytest.approx(200.0)
        assert food.protein_per_100g == pytest.approx(20.0)
        assert food.added_sugars_per_100g == pytest.approx(4.0)
        assert food.cholesterol_mg_per_100g == pytest.approx(60.0)
        assert food.sodium_mg_per_100g == pytest.approx(400.0)
        assert food.vitamin_d_mcg_per_100g == pytest.approx(3.0)
        assert food.potassium_mg_per_100g == pytest.approx(600.0)


def test_edit_my_food_rejects_foreign_portion_id(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine_id, my_portions = make_food(user_one.id, "Mine", 10.0, [(50.0, 1)])
        theirs_id, their_portions = make_food(user_two.id, "Theirs", 10.0, [(50.0, 1)])

    response = client.post(
        f"/my_foods/{mine_id}/edit",
        data={
            "description": "Sneaky",
            "calories_per_100g": 5,
            "selected_portion_id": their_portions[0],
        },
    )

    assert response.status_code == 302
    assert (
        b"Invalid portion selected for nutrient input." in client.get("/my_foods/").data
    )
    with client.application.app_context():
        food = db.session.get(MyFood, mine_id)
        assert food.description == "Mine"
        assert food.calories_per_100g == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# delete (undo-backed) + ownership
# ---------------------------------------------------------------------------


def test_delete_my_food_is_undo_backed_and_owner_gated(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine_id, _ = make_food(user_one.id, "Delete Me", 10.0)
        theirs_id, _ = make_food(user_two.id, "Not Yours", 10.0)

    # Stranger: 404 and the row keeps its owner.
    response = client.post(f"/my_foods/{theirs_id}/delete")
    assert response.status_code == 404
    with client.application.app_context():
        assert db.session.get(MyFood, theirs_id).user_id == user_two.id

    # Owner: anonymised and stashed for the undo blueprint.
    response = client.post(f"/my_foods/{mine_id}/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/my_foods/")
    with client.application.app_context():
        food = db.session.get(MyFood, mine_id)
        assert food.user_id is None
    with client.session_transaction() as sess:
        stash = sess["last_deleted"]
        assert stash["type"] == "my_food"
        assert stash["undo_method"] == "reassign_owner"
        assert stash["redirect_info"] == {"endpoint": "my_foods.my_foods"}
        assert stash["data"] == {"item_id": mine_id, "original_user_id": user_one.id}


# ---------------------------------------------------------------------------
# Portions
# ---------------------------------------------------------------------------


def test_add_portion_sets_next_sequence_number(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        food_id, _ = make_food(user_id, "Portioned", 10.0, [(1.0, 1)])

    response = auth_client.post(
        f"/my_foods/{food_id}/add_portion",
        data={
            "amount": 2,
            "measure_unit_description": "cup",
            "portion_description": "large",
            "modifier": "raw",
            "gram_weight": 240,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/my_foods/%d/edit#portions-table" % food_id
    )
    with auth_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(
            my_food_id=food_id, gram_weight=240.0
        ).first()
        assert portion is not None
        assert portion.seq_num == 2
        assert portion.modifier == "raw"
    assert (
        b"Portion added successfully!"
        in auth_client.get(f"/my_foods/{food_id}/edit").data
    )


def test_add_portion_reports_validation_errors(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        food_id, _ = make_food(user_id, "Bad Portion Food", 10.0, [(1.0, 1)])

    response = auth_client.post(
        f"/my_foods/{food_id}/add_portion",
        data={"amount": 1, "measure_unit_description": "cup", "gram_weight": ""},
        follow_redirects=True,
    )

    assert b"Error adding portion." in response.data
    with auth_client.application.app_context():
        assert UnifiedPortion.query.filter_by(my_food_id=food_id).count() == 1


def test_add_portion_rejects_other_users_food(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        theirs_id, _ = make_food(user_two.id, "Their Food", 10.0, [(1.0, 1)])

    response = client.post(
        f"/my_foods/{theirs_id}/add_portion",
        data={"amount": 1, "gram_weight": 120, "measure_unit_description": "cup"},
    )

    assert response.status_code == 404
    with client.application.app_context():
        assert UnifiedPortion.query.filter_by(my_food_id=theirs_id).count() == 1


def test_update_portion_owner_and_rejections(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine_id, my_portions = make_food(
            user_one.id, "Portion Owner", 10.0, [(50.0, 1)]
        )
        theirs_id, their_portions = make_food(
            user_two.id, "Portion Stranger", 10.0, [(50.0, 1)]
        )
        usda_fdc_id, usda_portion_id = make_usda_food(54321, "USDA Portion Host")

    # Owner updates every field.
    response = client.post(
        f"/my_foods/portion/{my_portions[0]}/update",
        data={
            "amount": 3,
            "measure_unit_description": "handful",
            "portion_description": "generous",
            "modifier": "cooked",
            "gram_weight": 80,
        },
    )
    assert response.status_code == 302
    assert f"/my_foods/{mine_id}/edit#portions-table" in response.headers["Location"]
    with client.application.app_context():
        portion = db.session.get(UnifiedPortion, my_portions[0])
        assert portion.gram_weight == pytest.approx(80.0)
        assert portion.measure_unit_description == "handful"

    # Validation error leaves the row alone.
    response = client.post(
        f"/my_foods/portion/{my_portions[0]}/update",
        data={"amount": 1, "gram_weight": "abc"},
        follow_redirects=True,
    )
    assert b"Error updating portion." in response.data
    with client.application.app_context():
        assert db.session.get(
            UnifiedPortion, my_portions[0]
        ).gram_weight == pytest.approx(80.0)

    # Somebody else's portion.
    response = client.post(
        f"/my_foods/portion/{their_portions[0]}/update",
        data={"amount": 1, "gram_weight": 999},
        follow_redirects=True,
    )
    assert (
        b"Portion not found or you do not have permission to edit it." in response.data
    )
    with client.application.app_context():
        assert db.session.get(
            UnifiedPortion, their_portions[0]
        ).gram_weight == pytest.approx(50.0)

    # A USDA portion has no MyFood parent: that used to raise AttributeError.
    response = client.post(
        f"/my_foods/portion/{usda_portion_id}/update",
        data={"amount": 1, "gram_weight": 999},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert (
        b"Portion not found or you do not have permission to edit it." in response.data
    )
    with client.application.app_context():
        assert db.session.get(
            UnifiedPortion, usda_portion_id
        ).gram_weight == pytest.approx(100.0)

    # A portion id that does not exist at all.
    response = client.post(
        "/my_foods/portion/987654/update",
        data={"amount": 1, "gram_weight": 5},
        follow_redirects=True,
    )
    assert (
        b"Portion not found or you do not have permission to edit it." in response.data
    )


def test_delete_portion_owner_and_rejections(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine_id, my_portions = make_food(
            user_one.id, "Delete Portion", 10.0, [(50.0, 1), (1.0, 2)]
        )
        theirs_id, their_portions = make_food(
            user_two.id, "Their Portion", 10.0, [(50.0, 1)]
        )
        _fdc, usda_portion_id = make_usda_food(54322, "USDA Keep")

    for portion_id in (their_portions[0], usda_portion_id, 987654):
        response = client.post(
            f"/my_foods/portion/{portion_id}/delete", follow_redirects=True
        )
        assert (
            b"Portion not found or you do not have permission to delete it."
            in response.data
        )

    with client.application.app_context():
        assert db.session.get(UnifiedPortion, their_portions[0]) is not None
        assert db.session.get(UnifiedPortion, usda_portion_id) is not None

    response = client.post(f"/my_foods/portion/{my_portions[0]}/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/my_foods/{mine_id}/edit#portions-table"
    )
    with client.application.app_context():
        assert db.session.get(UnifiedPortion, my_portions[0]) is None
    with client.session_transaction() as sess:
        stash = sess["last_deleted"]
        assert stash["type"] == "portion"
        assert stash["undo_method"] == "reinsert"
        assert stash["redirect_info"]["params"] == {"food_id": mine_id}


def test_move_portions_swaps_and_reports_edges(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        food_id, portion_ids = make_food(
            user_id, "Movable", 10.0, [(10.0, 1), (20.0, 2), (30.0, 3)]
        )

    # Move the middle portion to the top, then back down.
    response = auth_client.post(f"/my_foods/portion/{portion_ids[1]}/move_up")
    assert f"/my_foods/{food_id}/edit#portions-table" in response.headers["Location"]
    with auth_client.application.app_context():
        seqs = {
            p.id: p.seq_num
            for p in UnifiedPortion.query.filter_by(my_food_id=food_id).all()
        }
        assert seqs[portion_ids[1]] == 1
        assert seqs[portion_ids[0]] == 2
    assert b"Portion moved up." in auth_client.get(f"/my_foods/{food_id}/edit").data

    auth_client.post(f"/my_foods/portion/{portion_ids[1]}/move_up")
    assert (
        b"Portion is already at the top."
        in auth_client.get(f"/my_foods/{food_id}/edit").data
    )

    auth_client.post(f"/my_foods/portion/{portion_ids[2]}/move_down")
    assert (
        b"Portion is already at the bottom."
        in auth_client.get(f"/my_foods/{food_id}/edit").data
    )

    response = auth_client.post(f"/my_foods/portion/{portion_ids[2]}/move_down")
    assert response.status_code == 302
    with auth_client.application.app_context():
        seqs = {
            p.id: p.seq_num
            for p in UnifiedPortion.query.filter_by(my_food_id=food_id).all()
        }
        assert seqs[portion_ids[2]] == 3


def test_move_portions_reject_non_owners_and_usda_rows(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        _theirs, their_portions = make_food(
            user_two.id, "Their Mover", 10.0, [(10.0, 1)]
        )
        _fdc, usda_portion_id = make_usda_food(54323, "USDA Mover")

    for verb in ("move_up", "move_down"):
        for portion_id in (their_portions[0], usda_portion_id, 987654):
            response = client.post(f"/my_foods/portion/{portion_id}/{verb}")
            assert response.status_code == 302
            assert response.headers["Location"].endswith("/my_foods/")
        page = client.get("/my_foods/", follow_redirects=True)
        assert b"Portion not found or unauthorized." in page.data

    with client.application.app_context():
        assert db.session.get(UnifiedPortion, their_portions[0]).seq_num == 1
        assert db.session.get(UnifiedPortion, usda_portion_id).seq_num == 1


# ---------------------------------------------------------------------------
# copy_usda_food / copy_my_food
# ---------------------------------------------------------------------------


def test_copy_usda_food_without_id_and_with_unknown_id(auth_client):
    response = auth_client.post("/my_foods/copy_usda", data={}, follow_redirects=True)
    assert b"No USDA Food ID provided for copying." in response.data

    response = auth_client.post("/my_foods/copy_usda", data={"fdc_id": 999999})
    assert response.status_code == 404


def test_copy_usda_food_snapshots_nutrients_and_portions(auth_client):
    with auth_client.application.app_context():
        fdc_id, usda_portion_id = make_usda_food(12345, "USDA Apple")

    response = auth_client.post("/my_foods/copy_usda", data={"fdc_id": fdc_id})

    assert response.status_code == 302
    with auth_client.application.app_context():
        copy = MyFood.query.filter_by(description="USDA Apple").first()
        assert copy is not None
        assert copy.fdc_id == fdc_id
        assert copy.ingredients == "apples"
        assert copy.calories_per_100g == pytest.approx(52.0)
        assert copy.protein_per_100g == pytest.approx(0.3)
        assert copy.sodium_mg_per_100g == pytest.approx(1.0)
        copied_portions = UnifiedPortion.query.filter_by(my_food_id=copy.id).all()
        assert len(copied_portions) == 1
        assert copied_portions[0].gram_weight == pytest.approx(100.0)
        assert copied_portions[0].seq_num == 1
        # The USDA portion itself is untouched.
        assert db.session.get(UnifiedPortion, usda_portion_id).my_food_id is None
        assert db.session.get(UnifiedPortion, usda_portion_id).fdc_id == fdc_id

    assert f"/my_foods/{copy.id}/edit" in response.headers["Location"]


def test_copy_my_food_matrix(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine_id, _ = make_food(user_one.id, "Own Food", 120.0, [(1.0, 1), (40.0, 2)])
        theirs_id, _ = make_food(user_two.id, "Stranger Food", 80.0, [(1.0, 1)])

    # Stranger refused.
    response = client.post(f"/my_foods/{theirs_id}/copy", follow_redirects=True)
    assert (
        b"You can only copy foods from your friends or your own foods." in response.data
    )
    with client.application.app_context():
        assert MyFood.query.filter_by(user_id=user_one.id).count() == 1

    # Own food copied with nutrients and portions renumbered.
    response = client.post(f"/my_foods/{mine_id}/copy", follow_redirects=True)
    assert b"to your foods." in response.data
    with client.application.app_context():
        clone = MyFood.query.filter_by(description="Own Food (Copy)").first()
        assert clone is not None
        assert clone.user_id == user_one.id
        assert clone.calories_per_100g == pytest.approx(120.0)
        assert clone.protein_per_100g == pytest.approx(5.0)
        portions = UnifiedPortion.query.filter_by(my_food_id=clone.id).all()
        assert sorted(p.seq_num for p in portions) == [1, 2]
        assert {p.gram_weight for p in portions} == {1.0, 40.0}


def test_copy_friend_food_is_allowed(auth_client_with_friendship):
    client, me, friend = auth_client_with_friendship

    with client.application.app_context():
        friend_food_id, _ = make_food(friend.id, "Friend Dressing", 300.0, [(15.0, 1)])

    response = client.post(f"/my_foods/{friend_food_id}/copy", follow_redirects=True)

    assert b"to your foods." in response.data
    with client.application.app_context():
        clone = MyFood.query.filter_by(user_id=me.id).first()
        assert clone is not None
        assert clone.description == "Friend Dressing (Copy)"


# ---------------------------------------------------------------------------
# Nutrition-label routes
# ---------------------------------------------------------------------------


def test_pdf_label_routes_are_owner_gated(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine_id, _ = make_food(user_one.id, "Labelled Food", 10.0)
        theirs_id, _ = make_food(user_two.id, "Other Food", 10.0)

    for route in ("generate_pdf_label", "generate_pdf_details"):
        response = client.get(f"/my_foods/{theirs_id}/{route}")
        assert response.status_code == 404

    for route, label_only in (
        ("generate_pdf_label", True),
        ("generate_pdf_details", False),
    ):
        with patch("opennourish.my_foods.routes.generate_myfood_label_pdf") as make_pdf:
            make_pdf.return_value = "pdf-body"
            response = client.get(f"/my_foods/{mine_id}/{route}")
        assert response.status_code == 200
        make_pdf.assert_called_once_with(mine_id, label_only=label_only)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def test_manage_categories_add_and_duplicate(auth_client):
    page = auth_client.get("/my_foods/categories/manage")
    assert page.status_code == 200

    response = auth_client.post(
        "/my_foods/categories/manage",
        data={"description": "Smoothies"},
        follow_redirects=True,
    )
    assert b"Category added successfully." in response.data

    response = auth_client.post(
        "/my_foods/categories/manage",
        data={"description": "smoothies"},
        follow_redirects=True,
    )
    assert b"A category with this name already exists." in response.data

    with auth_client.application.app_context():
        assert FoodCategory.query.filter_by(description="Smoothies").count() == 1


def test_edit_category_branches(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine = FoodCategory(description="Soups", user_id=user_one.id)
        theirs = FoodCategory(description="Their Category", user_id=user_two.id)
        other = FoodCategory(description="Bowls", user_id=user_one.id)
        db.session.add_all([mine, theirs, other])
        db.session.commit()
        mine_id, theirs_id, other_id = mine.id, theirs.id, other.id

    # Rename works.
    response = client.post(
        f"/my_foods/categories/{mine_id}/edit",
        data={"description": "Noodle Soups"},
        follow_redirects=True,
    )
    assert b"Category updated successfully." in response.data
    with client.application.app_context():
        assert db.session.get(FoodCategory, mine_id).description == "Noodle Soups"

    # Empty name.
    response = client.post(
        f"/my_foods/categories/{mine_id}/edit", data={}, follow_redirects=True
    )
    assert b"Category name cannot be empty." in response.data

    # Duplicate name.
    response = client.post(
        f"/my_foods/categories/{mine_id}/edit",
        data={"description": "bowls"},
        follow_redirects=True,
    )
    assert b"Another category with this name already exists." in response.data
    with client.application.app_context():
        assert db.session.get(FoodCategory, mine_id).description == "Noodle Soups"
        assert db.session.get(FoodCategory, other_id).description == "Bowls"

    # Somebody else's category.
    response = client.post(
        f"/my_foods/categories/{theirs_id}/edit",
        data={"description": "Hijacked"},
        follow_redirects=True,
    )
    assert b"You are not authorized to edit this category." in response.data
    with client.application.app_context():
        assert db.session.get(FoodCategory, theirs_id).description == "Their Category"


def test_delete_category_is_scoped_to_the_owner(auth_client_two_users):
    """Regression: deleting a category must not touch another account's foods."""
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        my_category = FoodCategory(description="Freezer", user_id=user_one.id)
        their_category = FoodCategory(description="Freezer", user_id=user_two.id)
        db.session.add_all([my_category, their_category])
        db.session.flush()

        my_food = MyFood(
            user_id=user_one.id,
            description="My Frozen Peas",
            calories_per_100g=80.0,
            food_category_id=my_category.id,
        )
        # Another account's row happens to point at this category id.
        their_food = MyFood(
            user_id=user_two.id,
            description="Their Frozen Peas",
            calories_per_100g=80.0,
            food_category_id=my_category.id,
        )
        db.session.add_all([my_food, their_food])
        db.session.commit()
        my_category_id = my_category.id
        my_food_id = my_food.id
        their_food_id = their_food.id

    # The other account's category cannot be deleted through this one.
    with client.application.app_context():
        their_category_id = (
            FoodCategory.query.filter_by(user_id=user_two.id, description="Freezer")
            .first()
            .id
        )
    response = client.post(
        f"/my_foods/categories/{their_category_id}/delete", follow_redirects=True
    )
    assert b"You are not authorized to delete this category." in response.data
    with client.application.app_context():
        assert db.session.get(FoodCategory, their_category_id).user_id == user_two.id

    # Owner deletes it: own food is un-categorised, the other account's is not.
    response = client.post(
        f"/my_foods/categories/{my_category_id}/delete", follow_redirects=True
    )
    assert b"Category deleted successfully!" in response.data
    with client.application.app_context():
        assert db.session.get(FoodCategory, my_category_id) is None
        assert db.session.get(MyFood, my_food_id).food_category_id is None
        assert db.session.get(MyFood, their_food_id).food_category_id == my_category_id
    with client.session_transaction() as sess:
        stash = sess["last_deleted"]
        assert stash["type"] == "food_category"
        assert stash["undo_method"] == "reinsert"
        assert stash["data"]["id"] == my_category_id
        assert stash["redirect_info"] == {"endpoint": "my_foods.manage_categories"}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def test_import_rejects_missing_upload_and_wrong_file_type(auth_client):
    response = auth_client.post("/my_foods/import", data={}, follow_redirects=True)
    assert b"No file selected or text provided." in response.data

    response = auth_client.post(
        "/my_foods/import",
        data={"file": (BytesIO(b"- description: nope"), "foods.txt")},
        follow_redirects=True,
    )
    assert b"Invalid file type. Please upload a .yaml or .yml file." in response.data

    response = auth_client.post(
        "/my_foods/import",
        data={"yaml_text": "   "},
        follow_redirects=True,
    )
    assert b"No file selected or text provided." in response.data


def test_import_rejects_non_list_yaml(auth_client):
    response = auth_client.post(
        "/my_foods/import",
        data={"yaml_text": "description: Not A List\n"},
        follow_redirects=True,
    )

    assert b"YAML file must contain a list of food items." in response.data
    with auth_client.application.app_context():
        assert MyFood.query.count() == 0


def test_import_skips_unnamed_and_weightless_items(auth_client):
    payload = """
- nutrition_facts:
    calories: 10
  portions:
  - gram_weight: 10
- description: Zero Weight Treat
  nutrition_facts:
    calories: 50
    protein_grams: 0
    carbohydrates_grams: 0
    fat_grams: 0
  portions:
  - gram_weight: 0
- description: Good Import
  nutrition_facts:
    calories: 60
  portions:
  - gram_weight: 30
    measure_unit_description: serving
"""
    response = auth_client.post(
        "/my_foods/import", data={"yaml_text": payload}, follow_redirects=True
    )

    assert b"Import complete. Successfully added 1 new foods." in response.data
    assert b"2 items were skipped." in response.data
    assert (
        b"Zero Weight Treat (Foods with calories must have a gram weight"
        in response.data
    )
    assert b"Unnamed Item (Missing description)" in response.data
    with auth_client.application.app_context():
        food = MyFood.query.filter_by(description="Good Import").first()
        assert food.calories_per_100g == pytest.approx(200.0)
        assert UnifiedPortion.query.filter_by(my_food_id=food.id).count() == 1


def test_export_round_trips_into_import(auth_client):
    with auth_client.application.app_context():
        user_id = User.query.filter_by(username="testuser").first().id
        make_food(user_id, "Exported Food", 250.0, [(50.0, 1), (1.0, 2)])

    export = auth_client.get("/my_foods/export")
    assert export.status_code == 200
    assert b"Exported Food" in export.data

    with auth_client.application.app_context():
        for food in MyFood.query.all():
            db.session.delete(food)
        db.session.commit()

    response = auth_client.post(
        "/my_foods/import",
        data={"file": (BytesIO(export.data), "export.yaml")},
        follow_redirects=True,
    )
    assert b"Successfully added 1 new foods" in response.data
    with auth_client.application.app_context():
        food = MyFood.query.filter_by(description="Exported Food").first()
        assert food is not None
        assert food.calories_per_100g == pytest.approx(250.0, rel=1e-2)
