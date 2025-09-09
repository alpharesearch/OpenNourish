from models import (
    db,
    FoodCategory,
    UnifiedPortion,
    ExerciseActivity,
    Food,
    MyFood,
    Recipe,
    User,
)
import pytest


def test_seed_exercise_activities_command(app_with_db):
    """
    Tests the 'flask seed-exercise-activities' CLI command.
    """
    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        assert ExerciseActivity.query.count() == 0

    # Run the seeder for the first time
    result = runner.invoke(args=["seed-exercise-activities"])
    assert "Default exercise activities added." in result.output

    with app_with_db.app_context():
        assert ExerciseActivity.query.count() > 0
        activity = ExerciseActivity.query.filter_by(name="Walking").first()
        assert activity is not None
        assert activity.met_value == pytest.approx(3.5)

    # Run the seeder again to test idempotency
    result = runner.invoke(args=["seed-exercise-activities"])
    assert "Exercise activities already exist. Skipping." in result.output


def test_seed_usda_categories_command(app_with_db, tmp_path, monkeypatch):
    """
    Tests the 'flask seed-usda-categories' CLI command.
    """
    # The command looks for <root_path>/../persistent/usda_data
    # We create a temporary directory structure and point the app's root_path to it
    # so that the relative path resolves correctly.
    opennourish_dir = tmp_path / "opennourish"
    opennourish_dir.mkdir()

    usda_data_dir = tmp_path / "persistent" / "usda_data"
    usda_data_dir.mkdir(parents=True)

    # Create a dummy CSV file
    (usda_data_dir / "food_category.csv").write_text(
        'id,code,description\n1,1100,"Vegetables and Vegetable Products"\n'
    )

    # Monkeypatch the app's root_path to make the command find our temp file
    monkeypatch.setattr(app_with_db, "root_path", str(opennourish_dir))

    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        assert FoodCategory.query.count() == 0

    # Run the seeder
    result = runner.invoke(args=["seed-usda-categories"])
    assert "Successfully seeded 1 food categories." in result.output

    with app_with_db.app_context():
        assert FoodCategory.query.count() == 1
        category = FoodCategory.query.first()
        assert category.id == 1
        assert category.code == 1100
        assert category.description == "Vegetables and Vegetable Products"

    # Run again to test idempotency
    result = runner.invoke(args=["seed-usda-categories"])
    assert "Food categories already exist. Skipping." in result.output


def test_seed_usda_portions_command(app_with_db, tmp_path, monkeypatch):
    """
    Tests the 'flask seed-usda-portions' CLI command, including its
    idempotency, its ability to skip manually curated portions, and its
    ability to deduplicate portions that only differ by seq_num.
    """
    opennourish_dir = tmp_path / "opennourish"
    opennourish_dir.mkdir()

    usda_data_dir = tmp_path / "persistent" / "usda_data"
    usda_data_dir.mkdir(parents=True)

    # Create dummy CSV files with two different foods, one of which has
    # a duplicate portion that only differs by seq_num.
    (usda_data_dir / "measure_unit.csv").write_text("id,name\n9999,g\n1000,cup\n")
    (usda_data_dir / "food_portion.csv").write_text(
        "id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight\n"
        "1,123456,1,1.0,9999,slice,,25.0\n"  # Unique portion
        "2,123456,2,1.0,9999,slice,,25.0\n"  # Duplicate portion with different seq_num
        "3,789012,1,1.0,1000,scoop,,50.0\n"  # Another unique portion
    )

    monkeypatch.setattr(app_with_db, "root_path", str(opennourish_dir))

    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        assert UnifiedPortion.query.count() == 0

    # 1. Initial run of the seeder
    result = runner.invoke(args=["seed-usda-portions"])
    # The command should identify the duplicate and only seed 2 portions
    assert "Successfully seeded 2 new USDA portions" in result.output

    with app_with_db.app_context():
        # Verify that only 2 portions were created
        assert UnifiedPortion.query.count() == 2
        # Verify that only one portion for fdc_id 123456 exists
        assert UnifiedPortion.query.filter_by(fdc_id=123456).count() == 1
        portion1 = UnifiedPortion.query.filter_by(fdc_id=123456).first()
        portion2 = UnifiedPortion.query.filter_by(fdc_id=789012).first()
        assert portion1 is not None
        assert portion2 is not None
        assert portion1.was_imported is True
        assert portion2.was_imported is True

    # 2. Manually curate one of the portions
    with app_with_db.app_context():
        portion_to_curate = UnifiedPortion.query.filter_by(fdc_id=123456).first()
        portion_to_curate.was_imported = False
        portion_to_curate.portion_description = "A manually edited slice"
        db.session.commit()

    # 3. Re-run the seeder to test smart update logic
    result = runner.invoke(args=["seed-usda-portions"])

    # Assert that the command identified the curated food and skipped it
    assert (
        "Found 1 manually curated foods. Their portions will be skipped during re-import."
        in result.output
    )
    # Assert that it deleted the non-curated portion
    assert "Deleted 1 existing imported USDA portions" in result.output
    # Assert that it re-seeded the non-curated portion
    assert "Successfully seeded 1 new USDA portions" in result.output

    # 4. Verify the final state of the database
    with app_with_db.app_context():
        # The total count should still be 2
        assert UnifiedPortion.query.count() == 2

        # The curated portion should be untouched
        curated_portion = UnifiedPortion.query.filter_by(fdc_id=123456).first()
        assert curated_portion is not None
        assert curated_portion.was_imported is False
        assert curated_portion.portion_description == "A manually edited slice"

        # The other portion should have been re-seeded (and thus was_imported is True)
        reseeded_portion = UnifiedPortion.query.filter_by(fdc_id=789012).first()
        assert reseeded_portion is not None
        assert reseeded_portion.was_imported is True
        assert reseeded_portion.portion_description == "scoop"


def test_exercise_seed_activities_command(app_with_db):
    """
    Tests the 'flask exercise seed-activities' CLI command from the exercise blueprint.
    """
    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        # Clear any activities that might have been seeded by other tests/fixtures
        ExerciseActivity.query.delete()
        db.session.commit()
        assert ExerciseActivity.query.count() == 0

    # Run the seeder for the first time
    result = runner.invoke(args=["exercise", "seed-activities"])
    assert result.exit_code == 0

    with app_with_db.app_context():
        assert ExerciseActivity.query.count() > 0
        activity = ExerciseActivity.query.filter_by(name="Running").first()
        assert activity is not None
        assert abs(activity.met_value - 9.8) < 1e-6
        initial_count = ExerciseActivity.query.count()

    # Run the seeder again to test idempotency
    result = runner.invoke(args=["exercise", "seed-activities"])
    assert result.exit_code == 0

    with app_with_db.app_context():
        # The count should not have changed
        assert ExerciseActivity.query.count() == initial_count


def test_deduplicate_portions_command(app_with_db):
    """
    Tests the 'flask deduplicate-portions' CLI command.
    """
    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        # Setup: Create user, foods, and portions with duplicates
        user = User(id=1, username="testuser", email="test@test.com")
        db.session.add(user)

        # Food 1 (USDA): No duplicates
        food1 = Food(fdc_id=1, description="Apple")
        db.session.add(food1)
        portion1_1 = UnifiedPortion(
            fdc_id=1, portion_description="slice", gram_weight=25.0, seq_num=1
        )
        portion1_2 = UnifiedPortion(
            fdc_id=1, portion_description="whole", gram_weight=150.0, seq_num=2
        )
        db.session.add_all([portion1_1, portion1_2])

        # Food 2 (USDA): With duplicates that have different seq_num
        food2 = Food(fdc_id=2, description="Banana")
        db.session.add(food2)
        portion2_1 = UnifiedPortion(
            fdc_id=2, portion_description="slice", gram_weight=15.0, seq_num=1
        )
        portion2_2 = UnifiedPortion(
            fdc_id=2, portion_description="slice", gram_weight=15.0, seq_num=2
        )  # duplicate
        portion2_3 = UnifiedPortion(
            fdc_id=2, portion_description="whole", gram_weight=120.0, seq_num=3
        )
        portion2_4 = UnifiedPortion(
            fdc_id=2, portion_description="whole", gram_weight=120.0, seq_num=4
        )  # duplicate
        portion2_5 = UnifiedPortion(
            fdc_id=2, portion_description="whole", gram_weight=120.0, seq_num=5
        )  # triplicate
        db.session.add_all([portion2_1, portion2_2, portion2_3, portion2_4, portion2_5])

        # MyFood: With duplicates
        my_food = MyFood(id=1, user_id=1, description="My Test Food")
        db.session.add(my_food)
        my_food_portion1 = UnifiedPortion(
            my_food_id=1, portion_description="serving", gram_weight=100.0
        )
        my_food_portion2 = UnifiedPortion(
            my_food_id=1, portion_description="serving", gram_weight=100.0
        )  # duplicate
        my_food_portion3 = UnifiedPortion(
            my_food_id=1, portion_description="scoop", gram_weight=50.0
        )
        db.session.add_all([my_food_portion1, my_food_portion2, my_food_portion3])

        # Recipe: With duplicates
        recipe = Recipe(id=1, user_id=1, name="My Test Recipe")
        db.session.add(recipe)
        recipe_portion1 = UnifiedPortion(
            recipe_id=1, portion_description="bowl", gram_weight=250.0
        )
        recipe_portion2 = UnifiedPortion(
            recipe_id=1, portion_description="bowl", gram_weight=250.0
        )  # duplicate
        db.session.add_all([recipe_portion1, recipe_portion2])

        db.session.commit()

        # Initial state check
        assert UnifiedPortion.query.filter_by(fdc_id=1).count() == 2
        assert UnifiedPortion.query.filter_by(fdc_id=2).count() == 5
        assert UnifiedPortion.query.filter_by(my_food_id=1).count() == 3
        assert UnifiedPortion.query.filter_by(recipe_id=1).count() == 2
        assert UnifiedPortion.query.count() == 12

    # Run the command
    result = runner.invoke(args=["deduplicate-portions"])
    # 3 duplicates for food2, 1 for my_food, 1 for recipe = 5 total
    assert "Removed 5 duplicate portions." in result.output

    # Final state check
    with app_with_db.app_context():
        # Food 1 should be unchanged
        assert UnifiedPortion.query.filter_by(fdc_id=1).count() == 2

        # Food 2 should have duplicates removed
        assert UnifiedPortion.query.filter_by(fdc_id=2).count() == 2

        # MyFood should have duplicates removed
        assert UnifiedPortion.query.filter_by(my_food_id=1).count() == 2

        # Recipe should have duplicates removed
        assert UnifiedPortion.query.filter_by(recipe_id=1).count() == 1

        # Total count should be correct
        assert UnifiedPortion.query.count() == 2 + 2 + 2 + 1

        # Verify the correct portions remain (the ones with the lowest IDs)
        remaining_food2_portions = UnifiedPortion.query.filter_by(fdc_id=2).all()
        descriptions = {p.portion_description for p in remaining_food2_portions}
        assert descriptions == {"slice", "whole"}

        remaining_my_food_portions = UnifiedPortion.query.filter_by(my_food_id=1).all()
        descriptions = {p.portion_description for p in remaining_my_food_portions}
        assert descriptions == {"serving", "scoop"}

        remaining_recipe_portions = UnifiedPortion.query.filter_by(recipe_id=1).all()
        assert len(remaining_recipe_portions) == 1
        assert remaining_recipe_portions[0].portion_description == "bowl"
