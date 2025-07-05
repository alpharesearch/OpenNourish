from flask import Blueprint, current_app
import click
from models import db, ExerciseActivity

exercise_bp = Blueprint('exercise', __name__)

@exercise_bp.cli.command("seed-activities")
def seed_activities():
    """Seeds the ExerciseActivity table with common exercises."""
    with current_app.app_context():
        if ExerciseActivity.query.first():
            current_app.logger.debug("Exercise activities already exist.")
            return

        activities = [
            {'name': 'Running', 'met_value': 9.8},
            {'name': 'Walking', 'met_value': 3.5},
            {'name': 'Swimming', 'met_value': 7.0},
            {'name': 'Cycling', 'met_value': 7.5},
            {'name': 'Weightlifting', 'met_value': 5.0},
            {'name': 'Yoga', 'met_value': 2.5},
            {'name': 'Jumping Rope', 'met_value': 12.3},
            {'name': 'Hiking', 'met_value': 6.0},
            {'name': 'Rowing', 'met_value': 8.5},
            {'name': 'Basketball', 'met_value': 8.0},
            {'name': 'Soccer', 'met_value': 7.0},
            {'name': 'Tennis', 'met_value': 7.3},
            {'name': 'Dancing', 'met_value': 5.5},
            {'name': 'Gardening', 'met_value': 3.8},
            {'name': 'Elliptical Trainer', 'met_value': 5.0}
        ]

        for activity_data in activities:
            activity = ExerciseActivity(name=activity_data['name'], met_value=activity_data['met_value'])
            db.session.add(activity)

        db.session.commit()
        current_app.logger.debug("Exercise activities seeded successfully.")

from . import routes
