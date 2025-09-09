import pytest
import re
from models import db, User, Food, UnifiedPortion
from flask import url_for


@pytest.fixture(scope="function")
def key_user_client(app_with_db):
    """A test client that is authenticated as a key user."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(
                username="keyuser", email="keyuser@example.com", is_key_user=True
            )
            user.set_password("password")
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess["_user_id"] = user_id
            sess["_fresh"] = True
        yield client


@pytest.fixture(scope="function")
def admin_user_client(app_with_db):
    """A test client that is authenticated as an admin user."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(
                username="adminuser", email="adminuser@example.com", is_admin=True
            )
            user.set_password("password")
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess["_user_id"] = user_id
            sess["_fresh"] = True
        yield client


def test_add_usda_portion_key_user(key_user_client):
    """Test that a key_user can add a portion to a USDA food."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=11111, description="USDA Food for Key User Test")
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = key_user_client.post(
        url_for("usda_admin.add_usda_portion"),
        data={
            "fdc_id": fdc_id,
            "amount": "1",
            "measure_unit_description": "slice",
            "portion_description": "",
            "modifier": "test modifier",
            "gram_weight": "28.0",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Portion added successfully." in response.data

    with key_user_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(
            fdc_id=fdc_id, gram_weight=28.0
        ).first()
        assert portion is not None
        assert portion.measure_unit_description == "slice"
        assert portion.modifier == "test modifier"


def test_add_usda_portion_admin_user(admin_user_client):
    """Test that an admin can add a portion to a USDA food."""
    with admin_user_client.application.app_context():
        food = Food(fdc_id=22222, description="USDA Food for Admin Test")
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = admin_user_client.post(
        url_for("usda_admin.add_usda_portion"),
        data={
            "fdc_id": fdc_id,
            "amount": "1",
            "measure_unit_description": "serving",
            "portion_description": "of greatness",
            "modifier": "admin modifier",
            "gram_weight": "100.0",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Portion added successfully." in response.data

    with admin_user_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(
            fdc_id=fdc_id, gram_weight=100.0
        ).first()
        assert portion is not None
        assert portion.measure_unit_description == "serving"
        assert portion.portion_description == "of greatness"
        assert portion.modifier == "admin modifier"


def test_add_usda_portion_unauthorized(auth_client):
    """Test that a regular user cannot add a portion."""
    with auth_client.application.app_context():
        food = Food(fdc_id=33333, description="USDA Food for Unauthorized Test")
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = auth_client.post(
        url_for("usda_admin.add_usda_portion"),
        data={
            "fdc_id": fdc_id,
            "amount": "1",
            "measure_unit_description": "forbidden slice",
            "portion_description": "",
            "gram_weight": "99.0",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"This action requires special privileges." in response.data

    with auth_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(gram_weight=99.0).first()
        assert portion is None


def test_edit_usda_portion_key_user(key_user_client):
    """Test that a key_user can edit a USDA portion."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=44444, description="USDA Food to Edit")
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="",
            modifier="old modifier",
            gram_weight=150.0,
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id

    response = key_user_client.post(
        url_for("usda_admin.edit_usda_portion", portion_id=portion_id),
        data={
            "amount": "1.5",
            "measure_unit_description": "updated cup",
            "portion_description": "fluffed",
            "modifier": "new modifier",
            "gram_weight": "155.5",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Portion updated successfully." in response.data

    with key_user_client.application.app_context():
        updated_portion = db.session.get(UnifiedPortion, portion_id)
        assert updated_portion.gram_weight == pytest.approx(155.5)
        assert updated_portion.measure_unit_description == "updated cup"
        assert updated_portion.portion_description == "fluffed"
        assert updated_portion.amount == pytest.approx(1.5)
        assert updated_portion.modifier == "new modifier"


def test_edit_usda_portion_unauthorized(auth_client):
    """Test that a regular user cannot edit a USDA portion."""
    with auth_client.application.app_context():
        food = Food(fdc_id=55555, description="USDA Food Edit Unauthorized")
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="",
            gram_weight=150.0,
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id
        original_weight = portion.gram_weight

    response = auth_client.post(
        url_for("usda_admin.edit_usda_portion", portion_id=portion_id),
        data={
            "amount": "1",
            "measure_unit_description": "forbidden update",
            "portion_description": "",
            "gram_weight": "999.0",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"This action requires special privileges." in response.data

    with auth_client.application.app_context():
        portion_after = db.session.get(UnifiedPortion, portion_id)
        assert portion_after.gram_weight == original_weight


def test_delete_usda_portion_key_user(key_user_client):
    """Test that a key_user can delete a USDA portion and undo the deletion."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=66666, description="USDA Food to Delete Portion From")
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description="item",
            portion_description="to be deleted",
            gram_weight=10.0,
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id
        assert db.session.get(UnifiedPortion, portion_id) is not None

    # Delete the portion
    response = key_user_client.post(
        url_for("usda_admin.delete_usda_portion", portion_id=portion_id),
        follow_redirects=False,  # Do not follow redirect to check session
    )

    assert response.status_code == 302  # Should redirect after POST
    with key_user_client.application.app_context():
        deleted_portion = db.session.get(UnifiedPortion, portion_id)
        assert deleted_portion is None

    # Check for the flash message and get the undo link
    with key_user_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "success"
        assert "Portion deleted." in flashes[0][1]
        # Extract undo URL from the flash message's Markup
        undo_url_match = re.search(r"href='([^']+)'", flashes[0][1])
        assert undo_url_match is not None
        undo_url = undo_url_match.group(1)

    # Follow the undo link
    response = key_user_client.get(undo_url, follow_redirects=True)
    assert response.status_code == 200
    assert b"Item restored." in response.data

    # Verify the portion is back in the database
    with key_user_client.application.app_context():
        restored_portion = db.session.get(UnifiedPortion, portion_id)
        assert restored_portion is not None
        assert restored_portion.gram_weight == pytest.approx(10.0)


def test_delete_usda_portion_unauthorized(auth_client):
    """Test that a regular user cannot delete a USDA portion."""
    with auth_client.application.app_context():
        food = Food(fdc_id=88888, description="USDA Food Delete Unauthorized")
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="not to be deleted",
            gram_weight=100.0,
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id

    response = auth_client.post(
        url_for("usda_admin.delete_usda_portion", portion_id=portion_id),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard/" in response.headers["Location"]

    with auth_client.application.app_context():
        not_deleted_portion = db.session.get(UnifiedPortion, portion_id)
        assert not_deleted_portion is not None


def test_move_usda_portion_up(key_user_client):
    """Test moving a USDA portion up in the sequence."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=99999, description="USDA Food for Reordering")
        db.session.add(food)
        p1 = UnifiedPortion(
            fdc_id=food.fdc_id, portion_description="A", gram_weight=10.0, seq_num=1
        )
        p2 = UnifiedPortion(
            fdc_id=food.fdc_id, portion_description="B", gram_weight=20.0, seq_num=2
        )
        db.session.add_all([p1, p2])
        db.session.commit()
        p1_id, p2_id = p1.id, p2.id

    # Move p2 up
    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_up", portion_id=p2_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion moved up." in response.data

    with key_user_client.application.app_context():
        p1_new = db.session.get(UnifiedPortion, p1_id)
        p2_new = db.session.get(UnifiedPortion, p2_id)
        assert p1_new.seq_num == 2
        assert p2_new.seq_num == 1


def test_move_usda_portion_down(key_user_client):
    """Test moving a USDA portion down in the sequence."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=101010, description="USDA Food for Reordering Down")
        db.session.add(food)
        p1 = UnifiedPortion(
            fdc_id=food.fdc_id, portion_description="A", gram_weight=10.0, seq_num=1
        )
        p2 = UnifiedPortion(
            fdc_id=food.fdc_id, portion_description="B", gram_weight=20.0, seq_num=2
        )
        db.session.add_all([p1, p2])
        db.session.commit()
        p1_id, p2_id = p1.id, p2.id

    # Move p1 down
    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_down", portion_id=p1_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion moved down." in response.data

    with key_user_client.application.app_context():
        p1_new = db.session.get(UnifiedPortion, p1_id)
        p2_new = db.session.get(UnifiedPortion, p2_id)
        assert p1_new.seq_num == 2
        assert p2_new.seq_num == 1


def test_reorder_usda_portions_unauthorized(auth_client):
    """Test that a regular user cannot reorder USDA portions."""
    with auth_client.application.app_context():
        food = Food(fdc_id=111111, description="USDA Food Reorder Unauthorized")
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            portion_description="A",
            gram_weight=10.0,
            seq_num=1,
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id

    response = auth_client.post(
        url_for("usda_admin.move_usda_portion_up", portion_id=portion_id),
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard/" in response.headers["Location"]

    with auth_client.application.app_context():
        portion_after = db.session.get(UnifiedPortion, portion_id)
        assert portion_after.seq_num == 1


def test_add_usda_portion_no_gram_weight(key_user_client):
    """Test adding a portion with no gram weight fails."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=121212, description="Test Food")
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = key_user_client.post(
        url_for("usda_admin.add_usda_portion"),
        data={"fdc_id": fdc_id, "gram_weight": ""},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Gram weight is a required field." in response.data


def test_add_usda_portion_invalid_fdc_id(key_user_client):
    """Test adding a portion with an invalid fdc_id."""
    response = key_user_client.post(
        url_for("usda_admin.add_usda_portion"),
        data={"fdc_id": 999999, "gram_weight": "100"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"USDA Food not found." in response.data


def test_edit_usda_portion_invalid_portion_id(key_user_client):
    """Test editing a portion with an invalid portion_id."""
    response = key_user_client.post(
        url_for("usda_admin.edit_usda_portion", portion_id=999999),
        data={"gram_weight": "100"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"USDA portion not found." in response.data


def test_edit_usda_portion_no_gram_weight(key_user_client):
    """Test editing a portion to have no gram weight fails."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=131313, description="Test Food")
        portion = UnifiedPortion(fdc_id=food.fdc_id, gram_weight=100)
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id
        fdc_id = food.fdc_id

    response = key_user_client.post(
        url_for("usda_admin.edit_usda_portion", portion_id=portion_id),
        data={"gram_weight": ""},
        follow_redirects=False,  # Don't follow the redirect
    )

    assert response.status_code == 302  # Check for redirect
    assert f"/food/{fdc_id}" in response.location

    # Now, check the flash message in the session
    with key_user_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "danger"
        assert flashes[0][1] == "Gram weight is a required field."


def test_delete_usda_portion_invalid_portion_id(key_user_client):
    """Test deleting a portion with an invalid portion_id."""
    response = key_user_client.post(
        url_for("usda_admin.delete_usda_portion", portion_id=999999),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"USDA portion not found." in response.data


def test_move_usda_portion_up_invalid_portion_id(key_user_client):
    """Test moving a portion up with an invalid portion_id."""
    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_up", portion_id=999999),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"USDA portion not found." in response.data


def test_move_usda_portion_up_assigns_seq_num(key_user_client):
    """Test that move_up assigns sequence numbers if they are missing."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=141414, description="Test Food")
        p1 = UnifiedPortion(fdc_id=food.fdc_id, gram_weight=10, seq_num=None)
        p2 = UnifiedPortion(fdc_id=food.fdc_id, gram_weight=20, seq_num=None)
        db.session.add_all([food, p1, p2])
        db.session.commit()
        p1_id, p2_id = p1.id, p2.id

    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_up", portion_id=p2_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert (
        b"Assigned sequence numbers to all portions. Please try again." in response.data
    )

    with key_user_client.application.app_context():
        p1_new = db.session.get(UnifiedPortion, p1_id)
        p2_new = db.session.get(UnifiedPortion, p2_id)
        assert p1_new.seq_num == 1
        assert p2_new.seq_num == 2


def test_move_usda_portion_up_already_at_top(key_user_client):
    """Test moving the top portion up."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=151515, description="Test Food")
        p1 = UnifiedPortion(fdc_id=food.fdc_id, gram_weight=10, seq_num=1)
        db.session.add_all([food, p1])
        db.session.commit()
        p1_id = p1.id

    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_up", portion_id=p1_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion is already at the top." in response.data


def test_move_usda_portion_down_invalid_portion_id(key_user_client):
    """Test moving a portion down with an invalid portion_id."""
    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_down", portion_id=999999),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"USDA portion not found." in response.data


def test_move_usda_portion_down_already_at_bottom(key_user_client):
    """Test moving the bottom portion down."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=161616, description="Test Food")
        p1 = UnifiedPortion(fdc_id=food.fdc_id, gram_weight=10, seq_num=1)
        db.session.add_all([food, p1])
        db.session.commit()
        p1_id = p1.id

    response = key_user_client.post(
        url_for("usda_admin.move_usda_portion_down", portion_id=p1_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion is already at the bottom." in response.data
