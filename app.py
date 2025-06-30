
from flask import Flask, render_template, request, redirect, url_for
from models import db, Food, Portion, User, Recipe, RecipeIngredient, DailyLog
import os
from sqlalchemy import or_

# Get the absolute path of the directory where the script is located
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# Configure the SQLAlchemy database URI for the user database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'opennourish.db')
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

@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    if request.method == 'POST':
        search_term = request.form.get('search')
        if search_term:
            # Search for foods by description or ingredients
            results = Food.query.filter(
                Food.description.ilike(f'{search_term}%')
            ).order_by(
                db.case(
                    (Food.description.ilike(search_term), 0), # Exact match
                    (Food.description.ilike(f'{search_term}%'), 1), # Starts with search term
                    else_=2 # Other matches (though with the filter, this will be less relevant)
                )
            ).limit(250).all()
    return render_template('index.html', results=results)

@app.route('/food/<int:fdc_id>')
def food_detail(fdc_id):
    food = Food.query.options(db.joinedload(Food.portions).joinedload(Portion.measure_unit)).get_or_404(fdc_id)
    return render_template('food_detail.html', food=food)

@app.route('/upc/<barcode>')
def upc_search(barcode):
    food = Food.query.filter_by(upc=barcode).first()
    if food:
        return redirect(url_for('food_detail', fdc_id=food.fdc_id))
    else:
        return "UPC not found", 404

if __name__ == '__main__':
    app.run(debug=True)
