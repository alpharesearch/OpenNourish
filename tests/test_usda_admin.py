import pytest
from models import db, User, Food, UnifiedPortion
from flask import url_for

@pytest.fixture(scope='function')
def key_user_client(app_with_db):
    """A test client that is authenticated as a key user."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='keyuser', email='keyuser@example.com', is_key_user=True)
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client

@pytest.fixture(scope='function')
def admin_user_client(app_with_db):
    """A test client that is authenticated as an admin user."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='adminuser', email='adminuser@example.com', is_admin=True)
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client

def test_add_usda_portion_key_user(key_user_client):
    """Test that a key_user can add a portion to a USDA food."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=11111, description='USDA Food for Key User Test')
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = key_user_client.post(url_for('usda_admin.add_usda_portion'), data={
        'fdc_id': fdc_id,
        'amount': '1',
        'measure_unit_description': 'slice',
        'portion_description': '',
        'modifier': 'test modifier',
        'gram_weight': '28.0'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Portion added successfully.' in response.data
    
    with key_user_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(fdc_id=fdc_id, gram_weight=28.0).first()
        assert portion is not None
        assert portion.measure_unit_description == 'slice'
        assert portion.modifier == 'test modifier'

def test_add_usda_portion_admin_user(admin_user_client):
    """Test that an admin can add a portion to a USDA food."""
    with admin_user_client.application.app_context():
        food = Food(fdc_id=22222, description='USDA Food for Admin Test')
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = admin_user_client.post(url_for('usda_admin.add_usda_portion'), data={
        'fdc_id': fdc_id,
        'amount': '1',
        'measure_unit_description': 'serving',
        'portion_description': 'of greatness',
        'modifier': 'admin modifier',
        'gram_weight': '100.0'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Portion added successfully.' in response.data
    
    with admin_user_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(fdc_id=fdc_id, gram_weight=100.0).first()
        assert portion is not None
        assert portion.measure_unit_description == 'serving'
        assert portion.portion_description == 'of greatness'
        assert portion.modifier == 'admin modifier'

def test_add_usda_portion_unauthorized(auth_client):
    """Test that a regular user cannot add a portion."""
    with auth_client.application.app_context():
        food = Food(fdc_id=33333, description='USDA Food for Unauthorized Test')
        db.session.add(food)
        db.session.commit()
        fdc_id = food.fdc_id

    response = auth_client.post(url_for('usda_admin.add_usda_portion'), data={
        'fdc_id': fdc_id,
        'amount': '1',
        'measure_unit_description': 'forbidden slice',
        'portion_description': '',
        'gram_weight': '99.0'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'This action requires special privileges.' in response.data
    
    with auth_client.application.app_context():
        portion = UnifiedPortion.query.filter_by(gram_weight=99.0).first()
        assert portion is None

def test_edit_usda_portion_key_user(key_user_client):
    """Test that a key_user can edit a USDA portion."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=44444, description='USDA Food to Edit')
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description='cup',
            portion_description='',
            modifier='old modifier',
            gram_weight=150.0
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id

    response = key_user_client.post(url_for('usda_admin.edit_usda_portion', portion_id=portion_id), data={
        'amount': '1.5',
        'measure_unit_description': 'updated cup',
        'portion_description': 'fluffed',
        'modifier': 'new modifier',
        'gram_weight': '155.5'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Portion updated successfully.' in response.data

    with key_user_client.application.app_context():
        updated_portion = db.session.get(UnifiedPortion, portion_id)
        assert updated_portion.gram_weight == 155.5
        assert updated_portion.measure_unit_description == 'updated cup'
        assert updated_portion.portion_description == 'fluffed'
        assert updated_portion.amount == 1.5
        assert updated_portion.modifier == 'new modifier'

def test_edit_usda_portion_unauthorized(auth_client):
    """Test that a regular user cannot edit a USDA portion."""
    with auth_client.application.app_context():
        food = Food(fdc_id=55555, description='USDA Food Edit Unauthorized')
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description='cup',
            portion_description='',
            gram_weight=150.0
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id
        original_weight = portion.gram_weight

    response = auth_client.post(url_for('usda_admin.edit_usda_portion', portion_id=portion_id), data={
        'amount': '1',
        'measure_unit_description': 'forbidden update',
        'portion_description': '',
        'gram_weight': '999.0'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'This action requires special privileges.' in response.data
    
    with auth_client.application.app_context():
        portion_after = db.session.get(UnifiedPortion, portion_id)
        assert portion_after.gram_weight == original_weight

def test_delete_usda_portion_key_user(key_user_client):
    """Test that a key_user can delete a USDA portion."""
    with key_user_client.application.app_context():
        food = Food(fdc_id=66666, description='USDA Food to Delete Portion From')
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description='item',
            portion_description='to be deleted',
            gram_weight=10.0
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id

    response = key_user_client.post(url_for('usda_admin.delete_usda_portion', portion_id=portion_id), follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Portion deleted successfully.' in response.data
    
    with key_user_client.application.app_context():
        deleted_portion = db.session.get(UnifiedPortion, portion_id)
        assert deleted_portion is None

def test_delete_usda_portion_unauthorized(auth_client):
    """Test that a regular user cannot delete a USDA portion."""
    with auth_client.application.app_context():
        food = Food(fdc_id=77777, description='USDA Food Delete Unauthorized')
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            amount=1.0,
            measure_unit_description='item',
            portion_description='not to be deleted',
            gram_weight=20.0
        )
        db.session.add_all([food, portion])
        db.session.commit()
        portion_id = portion.id

    response = auth_client.post(url_for('usda_admin.delete_usda_portion', portion_id=portion_id), follow_redirects=True)
    
    assert response.status_code == 200
    assert b'This action requires special privileges.' in response.data
    
    with auth_client.application.app_context():
        not_deleted_portion = db.session.get(UnifiedPortion, portion_id)
        assert not_deleted_portion is not None