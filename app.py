
from flask import Flask, render_template, request, redirect, url_for
from models import db, Food, Portion, User, Recipe, RecipeIngredient, DailyLog
import os
from sqlalchemy.exc import OperationalError

def create_app(test_config=None):
    app = Flask(__name__)
    basedir = os.path.abspath(os.path.dirname(__file__))

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_mapping(
            SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(basedir, 'user_data.db'),
            SQLALCHEMY_BINDS={'usda': 'sqlite:///' + os.path.join(basedir, 'usda_data.db')},
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    db.init_app(app)

    @app.cli.command("init-user-db")
    def init_user_db_command():
        """Clears existing user data and creates new tables."""
        db.create_all()
        print("Initialized the user database.")

    @app.route('/', methods=['GET', 'POST'])
    def index():
        results = []
        warning = None
        if request.method == 'POST':
            search_term = request.form.get('search')
            if search_term:
                try:
                    results = db.session.execute(
                        db.select(Food).filter(
                            Food.description.ilike(f'{search_term}%')
                        ).order_by(
                            db.case(
                                (Food.description.ilike(search_term), 0),
                                (Food.description.ilike(f'{search_term}%'), 1),
                                else_=2
                            )
                        ).limit(250)
                    ).scalars().all()
                except OperationalError:
                    warning = "Database tables not found. Please run 'flask init-user-db' and 'python import_usda_data.py' to set up the databases."
        return render_template('index.html', results=results, warning=warning)

    @app.route('/food/<int:fdc_id>')
    def food_detail(fdc_id):
        food = db.session.get(Food, fdc_id)
        if not food:
            return "Food not found", 404
        return render_template('food_detail.html', food=food)

    @app.route('/upc/<barcode>')
    def upc_search(barcode):
        food = db.session.execute(
            db.select(Food).filter_by(upc=barcode)
        ).first()
        if food:
            return redirect(url_for('food_detail', fdc_id=food[0].fdc_id))
        else:
            return "UPC not found", 404

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
