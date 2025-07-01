
from flask import Flask, render_template, request, redirect, url_for, send_file
import os
import subprocess
import tempfile
from sqlalchemy.exc import OperationalError
from models import db, Food, Portion, FoodNutrient, User, Recipe, RecipeIngredient, DailyLog

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
        return render_template('index.html', results=results, warning=warning, results_count=len(results))

    @app.route('/search_unfiltered', methods=['GET', 'POST'])
    def search_unfiltered():
        results = []
        warning = None
        if request.method == 'POST':
            search_term = request.form.get('search_unfiltered')
            if search_term:
                try:
                    results = db.session.execute(
                        db.select(Food).filter(
                            Food.description.ilike(f'%{search_term}%')
                        ).limit(250)
                    ).scalars().all()
                except OperationalError:
                    warning = "Database tables not found. Please run 'flask init-user-db' and 'python import_usda_data.py' to set up the databases."
        return render_template('index.html', results=results, warning=warning, results_count=len(results))

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

    @app.route('/generate_nutrition_label/<int:fdc_id>')
    def generate_nutrition_label(fdc_id):
        food = db.session.get(Food, fdc_id)
        if not food:
            return "Food not found", 404

        

        # Map common nutrition label fields to USDA nutrient names and their units
        nutrient_info = {
            "Energy": {"names": ["Energy", "Energy (Atwater General Factors)"], "unit": "kcal", "format": ".0f"},
            "Total lipid (fat)": {"names": ["Total lipid (fat)"], "unit": "g", "format": ".1f"},
            "Fatty acids, total saturated": {"names": ["Fatty acids, total saturated"], "unit": "g", "format": ".1f"},
            "Fatty acids, total trans": {"names": ["Fatty acids, total trans"], "unit": "g", "format": ".1f"},
            "Cholesterol": {"names": ["Cholesterol"], "unit": "mg", "format": ".0f"},
            "Sodium": {"names": ["Sodium"], "unit": "mg", "format": ".0f"},
            "Carbohydrate, by difference": {"names": ["Carbohydrate, by difference"], "unit": "g", "format": ".1f"},
            "Fiber, total dietary": {"names": ["Fiber, total dietary"], "unit": "g", "format": ".1f"},
            "Sugars, total including NLEA": {"names": ["Sugars, total including NLEA"], "unit": "g", "format": ".1f"},
            "Protein": {"names": ["Protein"], "unit": "g", "format": ".1f"},
            "Vitamin D (D2 + D3)": {"names": ["Vitamin D (D2 + D3)"], "unit": "mcg", "format": ".0f", "key": "vitamin_d"},
            "Calcium": {"names": ["Calcium"], "unit": "mg", "format": ".0f", "key": "calcium"},
            "Iron": {"names": ["Iron"], "unit": "mg", "format": ".1f", "key": "iron"},
            "Potassium": {"names": ["Potassium"], "unit": "mg", "format": ".0f", "key": "potassium"},
            "Vitamin A, RAE": {"names": ["Vitamin A, RAE"], "unit": "mcg", "format": ".0f", "key": "vitamin_a"},
            "Vitamin C, total ascorbic acid": {"names": ["Vitamin C, total ascorbic acid"], "unit": "mg", "format": ".0f", "key": "vitamin_c"},
        }

        # Extract nutrient values
        nutrients_for_label = {}
        for label_field, info in nutrient_info.items():
            found_value = 0.0
            for usda_name in info["names"]:
                for fn in food.nutrients:
                    if fn.nutrient.name == usda_name:
                        found_value = fn.amount
                        break
                if found_value > 0:
                    break
            nutrients_for_label[label_field] = found_value

        # Prepare data for Typst
        # Construct the micronutrients array for Typst
        micronutrients_typst = []
        for label_field, info in nutrient_info.items():
            if "key" in info: # These are micronutrients
                value = nutrients_for_label[label_field]
                micronutrients_typst.append(                    f"(name: \"{label_field}\", key: \"{info['key']}\", value: {value}, unit: \"{info['unit']}\")"
                )
        
        # Join micronutrients for Typst array syntax
        micronutrients_typst_str = ",\n    ".join(micronutrients_typst)

        typst_content = f"""
#import "@preview/nutrition-label:0.1.0": *

#set text(font: "IBM Plex Sans")

#let data = (
  servings: "1", // Assuming 1 serving for 100g
  serving_size: "100g",
  calories: "{nutrients_for_label['Energy']:{nutrient_info['Energy']['format']}}",
  total_fat: (value: {nutrients_for_label['Total lipid (fat)']:{nutrient_info['Total lipid (fat)']['format']}}, unit: "{nutrient_info['Total lipid (fat)']['unit']}"),
  saturated_fat: (value: {nutrients_for_label['Fatty acids, total saturated']:{nutrient_info['Fatty acids, total saturated']['format']}}, unit: "{nutrient_info['Fatty acids, total saturated']['unit']}"),
  trans_fat: (value: {nutrients_for_label['Fatty acids, total trans']:{nutrient_info['Fatty acids, total trans']['format']}}, unit: "{nutrient_info['Fatty acids, total trans']['unit']}"),
  cholesterol: (value: {nutrients_for_label['Cholesterol']:{nutrient_info['Cholesterol']['format']}}, unit: "{nutrient_info['Cholesterol']['unit']}"),
  sodium: (value: {nutrients_for_label['Sodium']:{nutrient_info['Sodium']['format']}}, unit: "{nutrient_info['Sodium']['unit']}"),
  carbohydrate: (value: {nutrients_for_label['Carbohydrate, by difference']:{nutrient_info['Carbohydrate, by difference']['format']}}, unit: "{nutrient_info['Carbohydrate, by difference']['unit']}"),
  fiber: (value: {nutrients_for_label['Fiber, total dietary']:{nutrient_info['Fiber, total dietary']['format']}}, unit: "{nutrient_info['Fiber, total dietary']['unit']}"),
  sugars: (value: {nutrients_for_label['Sugars, total including NLEA']:{nutrient_info['Sugars, total including NLEA']['format']}}, unit: "{nutrient_info['Sugars, total including NLEA']['unit']}"),
  added_sugars: (value: 0, unit: "g"), // Assuming no added sugars data for now
  protein: (value: {nutrients_for_label['Protein']:{nutrient_info['Protein']['format']}}, unit: "{nutrient_info['Protein']['unit']}"),
  micronutrients: (
    {micronutrients_typst_str}
  ),
)

#show: nutrition-label.with(data)

#align(center, text(20pt, "Nutrition Facts for {food.description}"))

"""

        with tempfile.TemporaryDirectory() as tmpdir:
            typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
            pdf_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.pdf")

            with open(typ_file_path, "w", encoding="utf-8") as f:
                f.write(typst_content)

            try:
                print(f"Attempting to compile Typst file: {typ_file_path}")
                print(f"Output PDF will be: {pdf_file_path}")
                if not os.path.exists(typ_file_path):
                    print(f"Error: Typst file does not exist at {typ_file_path}")
                    return "Error: Typst input file not found.", 500

                # Run Typst command
                result = subprocess.run(
                    ["typst", "compile", typ_file_path, pdf_file_path],
                    capture_output=True, text=True, check=True
                )
                print("Typst stdout:", result.stdout)
                print("Typst stderr:", result.stderr)

                return send_file(pdf_file_path, as_attachment=True, download_name=f"nutrition_label_{food.description}.pdf", mimetype='application/pdf')
            except subprocess.CalledProcessError as e:
                print(f"Typst compilation failed: {e}")
                print(f"Stdout: {e.stdout}")
                print(f"Stderr: {e.stderr}")
                return f"Error generating PDF: {e.stderr}", 500
            except FileNotFoundError:
                return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
