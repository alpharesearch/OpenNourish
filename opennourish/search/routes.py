from flask import render_template, request
from flask_login import login_required
from . import search_bp
from models import db, Food, Portion, FoodNutrient
from sqlalchemy.exc import OperationalError

@search_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    results = []
    warning = None
    if request.method == 'POST':
        search_term = request.form.get('search')
        if search_term:
            try:
                results = db.session.execute(
                    db.select(Food).filter(
                        Food.description.ilike(f'%{search_term}%')
                    ).outerjoin(Portion).outerjoin(FoodNutrient).group_by(Food.fdc_id).order_by(
                        db.func.count(Portion.id).desc(),
                        db.func.count(FoodNutrient.nutrient_id).desc(),
                        db.case(
                            (Food.description.ilike(search_term), 0),
                            (Food.description.ilike(f'{search_term}%'), 1),
                            else_=2
                        )
                    ).limit(250)
                ).scalars().all()
            except OperationalError:
                warning = "Database tables not found. Please run 'flask init-user-db' and 'python import_usda_data.py' to set up the databases."
    return render_template('search/index.html', results=results, warning=warning, results_count=len(results))