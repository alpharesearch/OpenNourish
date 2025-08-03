from models import db, FoodCategory, UnifiedPortion, ExerciseActivity


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
        assert activity.met_value == 3.5

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
    Tests the 'flask seed-usda-portions' CLI command.
    """
    opennourish_dir = tmp_path / "opennourish"
    opennourish_dir.mkdir()

    usda_data_dir = tmp_path / "persistent" / "usda_data"
    usda_data_dir.mkdir(parents=True)

    # Create dummy CSV files
    (usda_data_dir / "measure_unit.csv").write_text("id,name\n9999,g\n")
    (usda_data_dir / "food_portion.csv").write_text(
        "id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight\n1,123456,1,1.0,9999,slice,,25.0\n"
    )

    monkeypatch.setattr(app_with_db, "root_path", str(opennourish_dir))

    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        assert UnifiedPortion.query.count() == 0

    # Run the seeder
    result = runner.invoke(args=["seed-usda-portions"])
    assert "Successfully seeded 1 total USDA portions" in result.output

    with app_with_db.app_context():
        assert UnifiedPortion.query.count() == 1
        portion = UnifiedPortion.query.first()
        assert portion.fdc_id == 123456
        assert portion.gram_weight == 25.0
        assert portion.portion_description == "slice"
        assert portion.modifier is None
        assert portion.was_imported is True

    # Test idempotency (deletes old portions and re-seeds)
    result = runner.invoke(args=["seed-usda-portions"])
    assert "Deleted 1 existing imported USDA portions" in result.output
    assert "Successfully seeded 1 total USDA portions" in result.output

    with app_with_db.app_context():
        assert UnifiedPortion.query.count() == 1


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
        assert activity.met_value == 9.8
        initial_count = ExerciseActivity.query.count()

    # Run the seeder again to test idempotency
    result = runner.invoke(args=["exercise", "seed-activities"])
    assert result.exit_code == 0

    with app_with_db.app_context():
        # The count should not have changed
        assert ExerciseActivity.query.count() == initial_count
