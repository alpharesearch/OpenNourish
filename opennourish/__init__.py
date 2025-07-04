from flask import Flask
import os
from models import db, User
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def create_app(config_class=Config):
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))
    if isinstance(config_class, dict):
        app.config.update(config_class)
    else:
        app.config.from_object(config_class)

    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)

    from opennourish.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from opennourish.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    from opennourish.search import search_bp
    app.register_blueprint(search_bp, url_prefix='/search')

    from opennourish.database import database_bp
    app.register_blueprint(database_bp, url_prefix='/database')

    from opennourish.diary import diary_bp
    app.register_blueprint(diary_bp, url_prefix='/')

    from opennourish.goals import bp as goals_bp
    app.register_blueprint(goals_bp, url_prefix='/goals')

    from opennourish.recipes.routes import recipes_bp
    app.register_blueprint(recipes_bp, url_prefix='/recipes')

    from opennourish.settings import settings_bp
    app.register_blueprint(settings_bp)

    from opennourish.tracking import tracking_bp
    app.register_blueprint(tracking_bp, url_prefix='/tracking')

    from opennourish.exercise import exercise_bp
    app.register_blueprint(exercise_bp, url_prefix='/exercise')

    from opennourish.main.routes import main_bp
    app.register_blueprint(main_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.template_filter('nl2br')
    def nl2br_filter(s):
        return s.replace("\n", "<br>")

    @app.cli.command("init-user-db")
    def init_user_db_command():
        """Clears existing user data and creates new tables."""
        with app.app_context():
            db.create_all()
            db.session.commit()
        print("Initialized the user database.")

    return app
