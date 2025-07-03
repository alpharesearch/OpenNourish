from flask import Blueprint, render_template, request, redirect, url_for, send_file
from flask_login import current_user
from models import db, Food
import subprocess
import tempfile
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))

@main_bp.route('/food/<int:fdc_id>')
def food_detail(fdc_id):
    q = request.args.get('q')
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404
    return render_template('food_detail.html', food=food, search_term=q)

@main_bp.route('/upc/<barcode>')
def upc_search(barcode):
    q = request.args.get('q')
    food = db.session.execute(
        db.select(Food).filter_by(upc=barcode)
    ).first()
    if food:
        return redirect(url_for('main.food_detail', fdc_id=food[0].fdc_id, q=q))
    else:
        return "UPC not found", 404

@main_bp.route('/generate_nutrition_label/<int:fdc_id>')
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
        "Vitamin C, total ascorbic acid": {"names": ["Vitamin C, total ascorbic acid"], "unit": "mg", "format": ".0f", "key": "vitamin_c"}
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
            micronutrients_typst.append(                    f"(name: \"{label_field}\", key: \"{info['key']}\", value: {value}, unit: \"{info['unit']}\", dv: 0)"
            )

    # Join micronutrients for Typst array syntax
    micronutrients_typst_str = ",\n    ".join(micronutrients_typst)

    typst_content = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam

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

#show: nutrition-label-nam(data)

#align(center, text(20pt, "Nutrition Facts for {food.description}"))

"""
    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
        pdf_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            result = subprocess.run(
                ["typst", "compile", os.path.basename(typ_file_path), os.path.basename(pdf_file_path)],
                capture_output=True, text=True, check=True, cwd=tmpdir
            )

            return send_file(pdf_file_path, as_attachment=False, download_name=f"nutrition_label_{fdc_id}.pdf", mimetype='application/pdf')
        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500
