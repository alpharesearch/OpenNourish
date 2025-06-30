
from flask import Flask, render_template, request, redirect, url_for
from models import db, Food, Portion, User, Recipe, RecipeIngredient, DailyLog
import os
from sqlalchemy import or_

# Get the absolute path of the directory where the script is located
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# Configure the SQLAlchemy database URI for the user database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'user_data.db')
# Configure the bind for the USDA database
app.config['SQLALCHEMY_BINDS'] = {
    'usda': 'sqlite:///' + os.path.join(basedir, 'usda_data.db')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy with the app
db.init_app(app)

@app.cli.command("init-user-db")
def init_user_db_command():
    """Clears existing user data and creates new tables."""
    db.create_all()
    print("Initialized the user database.")

from sqlalchemy.exc import OperationalError

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    warning = None
    if request.method == 'POST':
        search_term = request.form.get('search')
        if search_term:
            try:
                # Use the 'usda' bind to search for foods
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
    # Use the 'usda' bind to get food details
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404
    return render_template('food_detail.html', food=food)

@app.route('/upc/<barcode>')
def upc_search(barcode):
    # Use the 'usda' bind to search by UPC
    food = db.session.execute(
        db.select(Food).filter_by(upc=barcode)
    ).scalar_one_or_none()
    if food:
        return redirect(url_for('food_detail', fdc_id=food.fdc_id))
    else:
        return "UPC not found", 404

if __name__ == '__main__':
    app.run(debug=True)
