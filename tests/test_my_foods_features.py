import pytest
from models import db, User, MyFood, Food, FoodNutrient, Nutrient, UnifiedPortion

def test_create_my_food(auth_client):
    """
    Tests creating a new custom food based on a user-defined portion.
    The user provides nutrition for a serving, and it's scaled to 100g.
    """
    # User provides nutrition facts for a 50g serving
    food_data = {
        'description': 'Homemade Granola',
        # Nutrition for a 50g serving
        'calories_per_100g': 225.0,  # In the form, this field is now just 'Calories'
        'protein_per_100g': 5.0,     # 'Protein (g)'
        'carbs_per_100g': 30.0,      # 'Carbohydrates (g)'
        'fat_per_100g': 10.0,        # 'Fat (g)'
        # Portion form data
        'amount': 1,
        'measure_unit_description': 'cup',
        'portion_description': '',
        'modifier': '',
        'gram_weight': 50.0  # The gram weight of the '1 cup' serving
    }
    response = auth_client.post('/my_foods/new', data=food_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Custom food added successfully!' in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood.query.filter_by(user_id=user.id, description='Homemade Granola').first()
        assert my_food is not None
        # Verify that the values have been correctly scaled to 100g (doubled in this case)
        assert my_food.calories_per_100g == 450.0
        assert my_food.protein_per_100g == 10.0
        assert my_food.carbs_per_100g == 60.0
        assert my_food.fat_per_100g == 20.0

        # Verify the user-defined portion was created
        user_portion = UnifiedPortion.query.filter_by(my_food_id=my_food.id, gram_weight=50.0).first()
        assert user_portion is not None
        assert user_portion.measure_unit_description == 'cup'

        # Verify the automatic 1g portion was also created
        gram_portion = UnifiedPortion.query.filter_by(my_food_id=my_food.id, gram_weight=1.0).first()
        assert gram_portion is not None

def test_copy_usda_food(auth_client):
    """
    Tests copying a USDA food to My Foods.
    """
    with auth_client.application.app_context():
        # Create a sample USDA Food and Nutrients
        test_food = Food(fdc_id=12345, description='USDA Test Apple')
        db.session.add(test_food)

        # Nutrient IDs: calories=1008, protein=1003, carbs=1005, fat=1004
        db.session.add(Nutrient(id=1008, name='Energy', unit_name='kcal'))
        db.session.add(Nutrient(id=1003, name='Protein', unit_name='g'))
        db.session.add(Nutrient(id=1005, name='Carbohydrate, by difference', unit_name='g'))
        db.session.add(Nutrient(id=1004, name='Total lipid (fat)', unit_name='g'))

        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1008, amount=52.0))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1003, amount=0.3))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1005, amount=13.8))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1004, amount=0.2))
        
        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(fdc_id=12345, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        fdc_id = test_food.fdc_id
        gram_portion_id = gram_portion.id

    response = auth_client.post('/search/add_item', data={
        'food_id': fdc_id,
        'food_type': 'usda',
        'target': 'my_foods',
        'amount': 100, # Amount is required by the form
        'portion_id': gram_portion_id
    }, follow_redirects=True)
    assert response.status_code == 200
    
    # Using response.data to check for flash messages is more reliable in tests
    assert b'USDA Test Apple has been added to your foods.' in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood.query.filter_by(user_id=user.id, description='USDA Test Apple').first()
        assert my_food is not None
        assert my_food.calories_per_100g == 52.0
        assert my_food.protein_per_100g == 0.3
        assert my_food.carbs_per_100g == 13.8
        assert my_food.fat_per_100g == 0.2

def test_edit_my_food(auth_client):
    """
    Tests editing an existing custom food.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        initial_food = MyFood(
            user_id=user.id,
            description='Old Food',
            calories_per_100g=100.0,
            protein_per_100g=1.0,
            carbs_per_100g=10.0,
            fat_per_100g=5.0
        )
        db.session.add(initial_food)
        db.session.commit()
        food_id = initial_food.id

    updated_food_data = {
        'description': 'Updated Food',
        'calories_per_100g': 150.0,
        'protein_per_100g': 2.0,
        'carbs_per_100g': 15.0,
        'fat_per_100g': 7.0
    }
    response = auth_client.post(f'/my_foods/{food_id}/edit', data=updated_food_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Food updated successfully!' in response.data

    with auth_client.application.app_context():
        updated_food = db.session.get(MyFood, food_id)
        assert updated_food is not None
        assert updated_food.description == 'Updated Food'
        assert updated_food.calories_per_100g == 150.0

def test_delete_my_food(auth_client):
    """
    Tests deleting a custom food.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        food_to_delete = MyFood(
            user_id=user.id,
            description='Food to Delete',
            calories_per_100g=200.0,
            protein_per_100g=5.0,
            carbs_per_100g=20.0,
            fat_per_100g=10.0
        )
        db.session.add(food_to_delete)
        db.session.commit()
        food_id = food_to_delete.id

    response = auth_client.post(f'/my_foods/{food_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Food deleted successfully!' in response.data

    with auth_client.application.app_context():
        deleted_food = db.session.get(MyFood, food_id)
        assert deleted_food is None
