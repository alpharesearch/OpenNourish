import os
import subprocess
import tempfile
import re
from flask import (
    send_file,
    current_app,
)
from datetime import datetime
from models import (
    db,
    Food,
    MyFood,
    Recipe,
    UnifiedPortion,
)
from opennourish.utils import (
    get_available_portions,
)

NO_CACHE_HEADERS = "no-cache, no-store, must-revalidate"
TYPST_NOT_FOUND_ERROR = "Typst executable not found. Please ensure Typst is installed and in your system's PATH."
TYPST_NOT_FOUND_SHORT_ERROR = "Typst executable not found."
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S"


def _get_nutrition_label_data(fdc_id):
    food = db.session.get(Food, fdc_id)
    if not food:
        return None, None, None

    # Map common nutrition label fields to USDA nutrient names and their units
    nutrient_info = {
        "Energy": {
            "names": [
                "Energy",
                "Energy (Atwater General Factors)",
                "Energy (Atwater Specific Factors)",
            ],
            "unit": "kcal",
            "format": ".0f",
        },
        "Total lipid (fat)": {
            "names": ["Total lipid (fat)", "Lipids"],
            "unit": "g",
            "format": ".1f",
        },
        "Fatty acids, total saturated": {
            "names": ["Fatty acids, total saturated"],
            "unit": "g",
            "format": ".1f",
        },
        "Fatty acids, total trans": {
            "names": ["Fatty acids, total trans"],
            "unit": "g",
            "format": ".1f",
        },
        "Cholesterol": {"names": ["Cholesterol"], "unit": "mg", "format": ".0f"},
        "Sodium": {"names": ["Sodium", "Sodium, Na"], "unit": "mg", "format": ".0f"},
        "Carbohydrate, by difference": {
            "names": ["Carbohydrate, by difference", "Carbohydrates"],
            "unit": "g",
            "format": ".1f",
        },
        "Fiber, total dietary": {
            "names": ["Fiber, total dietary", "Total dietary fiber (AOAC 2011.25)"],
            "unit": "g",
            "format": ".1f",
        },
        "Sugars, total including NLEA": {
            "names": ["Sugars, total including NLEA", "Sugars, total", "Total Sugars"],
            "unit": "g",
            "format": ".1f",
        },
        "Sugars, added": {"names": ["Sugars, added"], "unit": "g", "format": ".1f"},
        "Protein": {
            "names": ["Protein", "Adjusted Protein"],
            "unit": "g",
            "format": ".1f",
        },
        "Vitamin D": {
            "names": ["Vitamin D (D2 + D3)"],
            "unit": "mcg",
            "format": ".0f",
            "key": "vitamin_d",
        },
        "Calcium": {
            "names": ["Calcium", "Calcium, Ca", "Calcium, added", "Calcium, intrinsic"],
            "unit": "mg",
            "format": ".0f",
            "key": "calcium",
        },
        "Iron": {
            "names": [
                "Iron",
                "Iron, Fe",
                "Iron, heme",
                "Iron, non-heme",
                "Iron, added",
                "Iron, intrinsic",
            ],
            "unit": "mg",
            "format": ".1f",
            "key": "iron",
        },
        "Potassium": {
            "names": ["Potassium", "Potassium, K"],
            "unit": "mg",
            "format": ".0f",
            "key": "potassium",
        },
    }

    # Extract nutrient values
    nutrients_for_label = {}
    for label_field, info in nutrient_info.items():
        found_value = None  # Initialize to None to distinguish from 0.0
        for usda_name in info["names"]:
            # Iterate through the eager-loaded food.nutrients
            for fn in food.nutrients:
                if fn.nutrient.name == usda_name:
                    found_value = fn.amount
                    break  # Break as soon as a match is found
            # If a value was found for the current usda_name, stop searching other names for this label_field
            if found_value is not None:
                break
        nutrients_for_label[label_field] = (
            found_value if found_value is not None else 0.0
        )  # Assign 0.0 if not found
    return food, nutrient_info, nutrients_for_label


# this is for USDA foods
def _generate_typst_content(
    food, nutrient_info, nutrients_for_label, include_extra_info=False
):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping the '*' character."""
        if not isinstance(text, str):
            return text
        return text.replace("*", r"\*")

    # 1. Determine the default portion and scaling factor
    default_portion = (
        UnifiedPortion.query.filter(UnifiedPortion.fdc_id == food.fdc_id)
        .filter(UnifiedPortion.seq_num.isnot(None))
        .order_by(UnifiedPortion.seq_num)
        .first()
    )

    if default_portion and default_portion.gram_weight > 0:
        if default_portion.measure_unit_description == "g":
            serving_size_str = _sanitize_for_typst(
                default_portion.full_description_str_1
            )
        else:
            serving_size_str = _sanitize_for_typst(
                default_portion.full_description_str_1
                + f" ({round(default_portion.gram_weight)}g)"
            )

        scaling_factor = default_portion.gram_weight / 100.0
    else:
        # Fallback to 100g if no default portion is found
        serving_size_str = "100g"
        scaling_factor = 1.0

    # 2. Scale the nutrient values
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in nutrients_for_label.items()
    }

    ingredients_str = food.ingredients if food.ingredients else "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).all()
    if food_portions:
        portions_list = [
            f"{p.full_description_str_1} ({p.gram_weight}g)" for p in food_portions
        ]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"
    portions_str = _sanitize_for_typst(portions_str)

    # Sanitize food description
    sanitized_food_description = _sanitize_for_typst(food.description)

    # Prepare UPC for EAN-13. A 12-digit UPC-A needs a leading 0.
    # The ean13 function takes the first 12 digits and calculates the 13th.
    upc_str = "0"
    if food.upc and len(food.upc) == 12:
        upc_str = f"0{food.upc}"[:12]
    elif food.upc and len(food.upc) == 13:
        upc_str = food.upc[:12]
    elif food.upc:
        # Pad or truncate to 12 digits if it's some other length
        upc_str = food.upc.ljust(12, "0")[:12]

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1",
  serving_size: "{serving_size_str}",
  calories: "{scaled_nutrients['Energy']:{nutrient_info['Energy']['format']}}",
  total_fat: (value: {scaled_nutrients['Total lipid (fat)']:{nutrient_info['Total lipid (fat)']['format']}}, unit: "{nutrient_info['Total lipid (fat)']['unit']}"),
  saturated_fat: (value: {scaled_nutrients['Fatty acids, total saturated']:{nutrient_info['Fatty acids, total saturated']['format']}}, unit: "{nutrient_info['Fatty acids, total saturated'] ['unit']}"),
  trans_fat: (value: {scaled_nutrients['Fatty acids, total trans']:{nutrient_info['Fatty acids, total trans']['format']}}, unit: "{nutrient_info['Fatty acids, total trans']['unit']}"),
  cholesterol: (value: {scaled_nutrients['Cholesterol']:{nutrient_info['Cholesterol']['format']}}, unit: "{nutrient_info['Cholesterol']['unit']}"),
  sodium: (value: {scaled_nutrients['Sodium']:{nutrient_info['Sodium']['format']}}, unit: "{nutrient_info['Sodium']['unit']}"),
  carbohydrate: (value: {scaled_nutrients['Carbohydrate, by difference']:{nutrient_info['Carbohydrate, by difference']['format']}}, unit: "{nutrient_info['Carbohydrate, by difference']['unit']}"),
  fiber: (value: {scaled_nutrients['Fiber, total dietary']:{nutrient_info['Fiber, total dietary']['format']}}, unit: "{nutrient_info['Fiber, total dietary']['unit']}"),
  sugars: (value: {scaled_nutrients['Sugars, total including NLEA']:{nutrient_info['Sugars, total including NLEA']['format']}}, unit: "{nutrient_info['Sugars, total including NLEA']['unit']}"),
  added_sugars: (value: {scaled_nutrients['Sugars, added']:{nutrient_info['Sugars, added']['format']}}, unit: "{nutrient_info['Sugars, added']['unit']}"),
  protein: (value: {scaled_nutrients['Protein']:{nutrient_info['Protein']['format']}}, unit: "{nutrient_info['Protein']['unit']}"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {scaled_nutrients['Vitamin D']:{nutrient_info['Vitamin D']['format']}}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {scaled_nutrients['Calcium']:{nutrient_info['Calcium']['format']}}, unit: "mg"),
    (name: "Iron", key: "iron", value: {scaled_nutrients['Iron']:{nutrient_info['Iron']['format']}}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {scaled_nutrients['Potassium']:{nutrient_info['Potassium']['format']}}, unit: "mg"),
  ),
)
"""

    if include_extra_info:
        typst_content_data = (
            typst_content_data
            + f"""
#set page(paper: "a4", header: align(right + horizon)[OpenNourish Food fact sheet], columns: 2)
#set text(font: "Liberation Sans")
#place(
  top + center,
  float: true,
  scope: "parent",
  clearance: 2em,
)[
= {sanitized_food_description}
]
"""
        )

    if include_extra_info and food.upc:
        typst_content_data = (
            typst_content_data
            + f"""
== UPC:
#ean13(scale:(1.8, .5), \"{upc_str}\")
"""
        )

    if include_extra_info:
        typst_content = (
            typst_content_data
            + f"""
== Ingredients: 
{ingredients_str}

== Portion Sizes: 
{portions_str}

#colbreak()
#nutrition-label-nam(data)
Net Carbs: {_sanitize_for_typst(round(float(scaled_nutrients['Carbohydrate, by difference']) - float(scaled_nutrients['Fiber, total dietary']), 2))}g

"""
        )
    else:
        typst_content = (
            typst_content_data
            + """
#set page(width: 12cm, height: 18cm)
#show: nutrition-label-nam(data)
"""
        )

    return typst_content


def generate_nutrition_label_pdf(fdc_id):
    food, nutrient_info, nutrients_for_label = _get_nutrition_label_data(fdc_id)
    if not food:
        return "Food not found", 404

    typst_content = _generate_typst_content(
        food, nutrient_info, nutrients_for_label, include_extra_info=True
    )
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
        pdf_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    os.path.basename(typ_file_path),
                    os.path.basename(pdf_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            response = send_file(
                pdf_file_path,
                as_attachment=False,
                download_name=f"nutrition_label_{fdc_id}_{timestamp}.pdf",
                mimetype="application/pdf",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = NO_CACHE_HEADERS
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return (
                TYPST_NOT_FOUND_ERROR,
                500,
            )


def generate_nutrition_label_svg(fdc_id):
    food, nutrient_info, nutrients_for_label = _get_nutrition_label_data(fdc_id)
    if not food:
        return "Food not found", 404

    typst_content = _generate_typst_content(food, nutrient_info, nutrients_for_label)

    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
        svg_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.svg")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    "--format",
                    "svg",
                    os.path.basename(typ_file_path),
                    os.path.basename(svg_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            response = send_file(
                svg_file_path,
                as_attachment=False,
                download_name=f"nutrition_label_{fdc_id}.svg",
                mimetype="image/svg+xml",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = NO_CACHE_HEADERS
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return (
                TYPST_NOT_FOUND_ERROR,
                500,
            )


def _get_nutrition_label_data_myfood(my_food_id):
    """
    Fetches a MyFood item and its nutritional data, formatted for the Typst label generator.
    """
    my_food = db.session.get(MyFood, my_food_id)
    if not my_food:
        return None, None

    # The Typst template expects specific keys. We map the MyFood attributes to these keys.
    # All values are per 100g.
    nutrients_for_label = {
        "Energy": my_food.calories_per_100g or 0,
        "Total lipid (fat)": my_food.fat_per_100g or 0,
        "Fatty acids, total saturated": my_food.saturated_fat_per_100g or 0,
        "Fatty acids, total trans": my_food.trans_fat_per_100g or 0,
        "Cholesterol": my_food.cholesterol_mg_per_100g or 0,
        "Sodium": my_food.sodium_mg_per_100g or 0,
        "Carbohydrate, by difference": my_food.carbs_per_100g or 0,
        "Fiber, total dietary": my_food.fiber_per_100g or 0,
        "Sugars, total including NLEA": my_food.sugars_per_100g or 0,
        "Sugars, added": my_food.added_sugars_per_100g or 0,
        "Protein": my_food.protein_per_100g or 0,
        "Vitamin D": my_food.vitamin_d_mcg_per_100g or 0,
        "Calcium": my_food.calcium_mg_per_100g or 0,
        "Iron": my_food.iron_mg_per_100g or 0,
        "Potassium": my_food.potassium_mg_per_100g or 0,
    }
    return my_food, nutrients_for_label


def _generate_typst_content_myfood(my_food, nutrients_for_label, label_only=False):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping special characters."""
        if not isinstance(text, str):
            return text
        return text.replace("\\", r"\\").replace('"', r"\"").replace("*", r"\*")

    # 1. Determine the default portion and scaling factor
    default_portion = (
        UnifiedPortion.query.filter(UnifiedPortion.my_food_id == my_food.id)
        .filter(UnifiedPortion.seq_num.isnot(None))
        .order_by(UnifiedPortion.seq_num)
        .first()
    )

    if default_portion and default_portion.gram_weight > 0:
        if default_portion.measure_unit_description == "g":
            serving_size_str = _sanitize_for_typst(
                default_portion.full_description_str_1
            )
        else:
            serving_size_str = _sanitize_for_typst(
                default_portion.full_description_str_1
                + f" ({round(default_portion.gram_weight)}g)"
            )

        scaling_factor = default_portion.gram_weight / 100.0
    else:
        # Fallback to 100g if no default portion is found
        serving_size_str = "100g"
        scaling_factor = 1.0

    # 2. Scale the nutrient values
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in nutrients_for_label.items()
    }

    # Sanitize all user-provided strings
    sanitized_food_name = _sanitize_for_typst(my_food.description)

    ingredients_str = my_food.ingredients if my_food.ingredients else "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)

    # Prepare UPC for EAN-13. The typst ean13 function takes the first 12 digits.
    current_app.logger.debug(f"my_food.upc from DB: {my_food.upc}")
    upc_str = "0"  # Default

    # Check for our internal 13-digit UPCs (now stored with checksum)
    if my_food.upc and len(my_food.upc) == 13 and my_food.upc.startswith("200"):
        upc_str = my_food.upc[:12]  # Slice off the checksum for the label generator
        current_app.logger.debug(
            f"Internal EAN-13 detected. Passing first 12 digits to label: {upc_str}"
        )

    # Check for a standard 12-digit UPC-A, which needs a leading '0'
    elif my_food.upc and len(my_food.upc) == 12:
        upc_str = f"0{my_food.upc}"[:12]
        current_app.logger.debug(f"Standard UPC-A detected. Prepending 0: {upc_str}")

    # Handle existing full 13-digit EANs that are NOT our internal ones
    elif my_food.upc and len(my_food.upc) == 13:
        upc_str = my_food.upc[:12]
        current_app.logger.debug(
            f"Full EAN-13 detected. Using first 12 digits: {upc_str}"
        )

    # Fallback for other lengths
    elif my_food.upc:
        upc_str = my_food.upc.ljust(12, "0")[:12]
        current_app.logger.debug(f"Fallback sizing applied: {upc_str}")

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(my_food_id=my_food.id).all()
    if food_portions:
        portions_list = [
            f"{_sanitize_for_typst(p.full_description_str_1)} ({p.gram_weight}g)"
            for p in food_portions
        ]
        portions_str = "\ ".join(portions_list)
    else:
        portions_str = "N/A"

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1",
  serving_size: "{serving_size_str}",
  calories: "{scaled_nutrients['Energy']:.0f}",
  total_fat: (value: {scaled_nutrients['Total lipid (fat)']:.1f}, unit: "g"),
  saturated_fat: (value: {scaled_nutrients['Fatty acids, total saturated']:.1f}, unit: "g"),
  trans_fat: (value: {scaled_nutrients['Fatty acids, total trans']:.1f}, unit: "g"),
  cholesterol: (value: {scaled_nutrients['Cholesterol']:.0f}, unit: "mg"),
  sodium: (value: {scaled_nutrients['Sodium']:.0f}, unit: "mg"),
  carbohydrate: (value: {scaled_nutrients['Carbohydrate, by difference']:.1f}, unit: "g"),
  fiber: (value: {scaled_nutrients['Fiber, total dietary']:.1f}, unit: "g"),
  sugars: (value: {scaled_nutrients['Sugars, total including NLEA']:.1f}, unit: "g"),
  added_sugars: (value: {scaled_nutrients['Sugars, added']:.1f}, unit: "g"),
  protein: (value: {scaled_nutrients['Protein']:.1f}, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {scaled_nutrients['Vitamin D']:.0f}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {scaled_nutrients['Calcium']:.0f}, unit: "mg"),
    (name: "Iron", key: "iron", value: {scaled_nutrients['Iron']:.1f}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {scaled_nutrients['Potassium']:.0f}, unit: "mg"),
  ),
)
"""

    if label_only:
        typst_content = (
            typst_content_data
            + """
#set page(width: 2in, height: 1in)
#set page(margin: (x: 0.1cm, y: 0.1cm))
#set text(font: "Liberation Sans", size: 8pt)
"""
        )

    if label_only and my_food.upc:
        typst_content = (
            typst_content
            + f"""
#ean13(scale:(1.6, .5), "{upc_str}")
"""
        )

    if label_only:
        typst_content = (
            typst_content
            + f"""
{sanitized_food_name}
"""
        )
    else:
        typst_content = (
            typst_content_data
            + """
#set page(width: 6in, height: 4in, columns: 2)
#set page(margin: (x: 0.2in, y: 0.05in))
#set text(font: \"Liberation Sans\", size: 8pt)
"""
        )

    if not label_only and my_food.upc:
        typst_content = (
            typst_content
            + f"""
#ean13(scale:(2.0, .5), \"{upc_str}\")
"""
        )

    if not label_only:
        typst_content = (
            typst_content
            + f"""
#box(width: 3.25in, height: 3in, clip: true, 
[== My Food: 
{sanitized_food_name}
== Ingredients: 
{ingredients_str}
== Portion Sizes: 
{portions_str}])
#colbreak()
#set align(right)
#nutrition-label-nam(data, scale-percent: 73%, show-footnote: false,)
#linebreak()
Net Carbs: {_sanitize_for_typst(round(float(scaled_nutrients['Carbohydrate, by difference']) - float(scaled_nutrients['Fiber, total dietary']), 2))}g
"""
        )

    return typst_content


def generate_myfood_label_pdf(my_food_id, label_only=False):
    """
    Generates a PDF nutrition label for a MyFood item.
    Can generate a label-only PDF or a full-page PDF with additional details.
    """
    my_food, nutrients_for_label = _get_nutrition_label_data_myfood(my_food_id)
    if not my_food:
        return "Food not found", 404

    typst_content = _generate_typst_content_myfood(
        my_food, nutrients_for_label, label_only=label_only
    )
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(
            tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.typ"
        )
        pdf_file_path = os.path.join(
            tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.pdf"
        )

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    os.path.basename(typ_file_path),
                    "--pages",
                    "1",
                    os.path.basename(pdf_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            safe_description = (
                re.sub(r"[^\\w\\s-]", "", my_food.description).strip().replace(" ", "_")
            )
            download_name = f"{safe_description}_{file_suffix}_{timestamp}.pdf"
            response = send_file(
                pdf_file_path,
                as_attachment=False,
                download_name=download_name,
                mimetype="application/pdf",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = NO_CACHE_HEADERS
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            current_app.logger.error(
                f"Typst compilation failed for my_food_id {my_food_id}: {e.stderr}"
            )
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error(TYPST_NOT_FOUND_SHORT_ERROR)
            return (
                TYPST_NOT_FOUND_ERROR,
                500,
            )


def _generate_typst_content_recipe(
    recipe, nutrients_for_label, label_only=False, svg_only=False
):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping special characters."""
        if not isinstance(text, str):
            return text
        return text.replace("\\", r"\\").replace('"', r"\"").replace("*", r"\*")

    # 0. Determine how many servings the recipe has
    servings_str = _sanitize_for_typst(recipe.servings)

    # 1. Determine the default portion and scaling factor
    default_portion = (
        UnifiedPortion.query.filter(UnifiedPortion.recipe_id == recipe.id)
        .filter(UnifiedPortion.seq_num.isnot(None))
        .order_by(UnifiedPortion.seq_num)
        .first()
    )

    if default_portion and default_portion.gram_weight > 0:
        if default_portion.measure_unit_description == "g":
            serving_size_str = _sanitize_for_typst(
                default_portion.full_description_str_1
            )
        else:
            serving_size_str = _sanitize_for_typst(
                default_portion.full_description_str_1
                + f" ({round(default_portion.gram_weight)}g)"
            )

        scaling_factor = default_portion.gram_weight / 100.0
    else:
        # Fallback to 100g if no default portion is found
        serving_size_str = "100g"
        scaling_factor = 1.0

    # 2. Scale the nutrient values
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in nutrients_for_label.items()
    }

    # Sanitize all user-provided strings
    sanitized_recipe_name = _sanitize_for_typst(recipe.name)

    # Create a string of ingredients for the recipe
    # Manually fetch USDA food data
    from opennourish.utils import calculate_nutrition_for_items

    usda_food_ids = [ing.fdc_id for ing in recipe.ingredients if ing.fdc_id]
    if usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}
    ingredients_str = ""
    if recipe.ingredients:
        for ing in recipe.ingredients:
            if ing.fdc_id:
                ing.usda_food = usda_foods_map.get(ing.fdc_id)

            # Calculate nutrition for each individual ingredient
            ingredient_nutrition = calculate_nutrition_for_items([ing])
            ing.calories = ingredient_nutrition["calories"]
            ing.protein = ingredient_nutrition["protein"]
            ing.carbs = ingredient_nutrition["carbs"]
            ing.fat = ingredient_nutrition["fat"]

            # Calculate quantity and portion description
            food_object = None
            if hasattr(ing, "usda_food") and ing.usda_food:
                food_object = ing.usda_food
                ing.description = food_object.description
            elif ing.my_food:
                food_object = ing.my_food
                ing.description = food_object.description
            elif ing.linked_recipe:
                food_object = ing.linked_recipe
                ing.description = food_object.name

            ing.quantity = ing.amount_grams
            ing.portion_description = "g"
            selected_portion = None

            if ing.portion_id_fk:
                selected_portion = db.session.get(UnifiedPortion, ing.portion_id_fk)

            if food_object:
                available_portions = get_available_portions(food_object)
                available_portions.sort(key=lambda p: p.gram_weight, reverse=True)
                if selected_portion and selected_portion.gram_weight > 0:
                    ing.quantity = ing.amount_grams / selected_portion.gram_weight
                    ing.portion_description = selected_portion.full_description_str
            ingredient_line = ""
            if ing.portion_description.strip().lower() != "g":
                ingredient_line = " ({}g)".format(round(ing.amount_grams))

            ingredients_str = (
                ingredients_str
                + _sanitize_for_typst(
                    "{:.2f}".format(ing.quantity)
                    + " "
                    + ing.portion_description
                    + ingredient_line
                    + " "
                    + ing.description
                )
                + "\\ "
            )
    else:
        ingredients_str = "N/A"

    # Sanitize all user-provided strings
    sanitized_recipe_instructions = _sanitize_for_typst(recipe.instructions)

    # Prepare UPC for EAN-13. The typst ean13 function takes the first 12 digits.
    current_app.logger.debug(f"recipe.upc from DB: {recipe.upc}")
    upc_str = "0"  # Default

    # Check for our internal 13-digit UPCs (now stored with checksum)
    if recipe.upc and len(recipe.upc) == 13 and recipe.upc.startswith("201"):
        upc_str = recipe.upc[:12]  # Slice off the checksum for the label generator
        current_app.logger.debug(
            f"Internal EAN-13 detected. Passing first 12 digits to label: {upc_str}"
        )

    # Check for a standard 12-digit UPC-A, which needs a leading '0'
    elif recipe.upc and len(recipe.upc) == 12:
        upc_str = f"0{recipe.upc}"[:12]
        current_app.logger.debug(f"Standard UPC-A detected. Prepending 0: {upc_str}")

    # Handle existing full 13-digit EANs that are NOT our internal ones
    elif recipe.upc and len(recipe.upc) == 13:
        upc_str = recipe.upc[:12]
        current_app.logger.debug(
            f"Full EAN-13 detected. Using first 12 digits: {upc_str}"
        )

    # Fallback for other lengths
    elif recipe.upc:
        upc_str = recipe.upc.ljust(12, "0")[:12]
        current_app.logger.debug(f"Fallback sizing applied: {upc_str}")

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(recipe_id=recipe.id).all()
    if food_portions:
        portions_list = [
            f"{_sanitize_for_typst(p.full_description_str_1)} ({p.gram_weight}g)"
            for p in food_portions
        ]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "{servings_str}",
  serving_size: "{serving_size_str}",
  calories: "{scaled_nutrients['Energy']:.0f}",
  total_fat: (value: {scaled_nutrients['Total lipid (fat)']:.1f}, unit: "g"),
  saturated_fat: (value: {scaled_nutrients['Fatty acids, total saturated']:.1f}, unit: "g"),
  trans_fat: (value: {scaled_nutrients['Fatty acids, total trans']:.1f}, unit: "g"),
  cholesterol: (value: {scaled_nutrients['Cholesterol']:.0f}, unit: "mg"),
  sodium: (value: {scaled_nutrients['Sodium']:.0f}, unit: "mg"),
  carbohydrate: (value: {scaled_nutrients['Carbohydrate, by difference']:.1f}, unit: "g"),
  fiber: (value: {scaled_nutrients['Fiber, total dietary']:.1f}, unit: "g"),
  sugars: (value: {scaled_nutrients['Sugars, total including NLEA']:.1f}, unit: "g"),
  added_sugars: (value: {scaled_nutrients['Sugars, added']:.1f}, unit: "g"),
  protein: (value: {scaled_nutrients['Protein']:.1f}, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {scaled_nutrients['Vitamin D']:.0f}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {scaled_nutrients['Calcium']:.0f}, unit: "mg"),
    (name: "Iron", key: "iron", value: {scaled_nutrients['Iron']:.1f}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {scaled_nutrients['Potassium']:.0f}, unit: "mg"),
  ),
)
"""

    if svg_only:
        typst_content = (
            typst_content_data
            + """
#set page(width: 12cm, height: 18cm)
#nutrition-label-nam(data)
"""
        )
    elif label_only:
        typst_content = (
            typst_content_data
            + """
#set page(width: 6in, height: 4in, columns: 2)
#set page(margin: (x: 0.2in, y: 0.05in))
#set text(font: \"Liberation Sans\", size: 8pt)
"""
        )

        if recipe.upc:
            typst_content = (
                typst_content
                + f"""
#ean13(scale:(1.6, .5), \"{upc_str}\")
"""
            )

        typst_content = (
            typst_content
            + f"""
#box(width: 3.25in, height: 3in, clip: true, 
[== Recipe: 
{sanitized_recipe_name}
== Ingredients: 
{ingredients_str}
== Portion Sizes: 
{portions_str}])
#colbreak()
#set align(right)
#nutrition-label-nam(data, scale-percent: 73%, show-footnote: false,)
#linebreak()
Net Carbs: {_sanitize_for_typst(round(float(scaled_nutrients['Carbohydrate, by difference']) - float(scaled_nutrients['Fiber, total dietary']), 2))}g
"""
        )
    else:
        typst_content = (
            typst_content_data
            + f"""
#set page(paper: \"us-letter\", columns: 2)
#set page(margin: (x: 0.75in, y: 0.75in))
#set text(font: \"Liberation Sans\", size: 10pt)

#box(width: 4.25in, height: 8in, clip: true, 
[= {sanitized_recipe_name}
== Ingredients: 
{ingredients_str}
== Instructions: 
{sanitized_recipe_instructions}])
#colbreak()
#set align(right)
"""
        )

        if recipe.upc:
            typst_content = (
                typst_content
                + f"""
#ean13(scale:(2.0, .5), \"{upc_str}\")
"""
            )

        typst_content = (
            typst_content
            + f"""
== Portion Sizes: 
{portions_str}
== Label:
#nutrition-label-nam(data, scale-percent: 75%)
#linebreak()
Net Carbs: {_sanitize_for_typst(round(float(scaled_nutrients['Carbohydrate, by difference']) - float(scaled_nutrients['Fiber, total dietary']), 2))}g
"""
        )

    return typst_content


def _get_nutrition_label_data_recipe(recipe_id):
    """
    Fetches a Recipe item and its nutritional data, formatted for the Typst label generator.
    """
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        return None, None

    # The Typst template expects specific keys. We map the Recipe attributes to these keys.
    # All values are per 100g.
    nutrients_for_label = {
        "Energy": recipe.calories_per_100g or 0,
        "Total lipid (fat)": recipe.fat_per_100g or 0,
        "Fatty acids, total saturated": recipe.saturated_fat_per_100g or 0,
        "Fatty acids, total trans": recipe.trans_fat_per_100g or 0,
        "Cholesterol": recipe.cholesterol_mg_per_100g or 0,
        "Sodium": recipe.sodium_mg_per_100g or 0,
        "Carbohydrate, by difference": recipe.carbs_per_100g or 0,
        "Fiber, total dietary": recipe.fiber_per_100g or 0,
        "Sugars, total including NLEA": recipe.sugars_per_100g or 0,
        "Sugars, added": recipe.added_sugars_per_100g or 0,
        "Protein": recipe.protein_per_100g or 0,
        "Vitamin D": recipe.vitamin_d_mcg_per_100g or 0,
        "Calcium": recipe.calcium_mg_per_100g or 0,
        "Iron": recipe.iron_mg_per_100g or 0,
        "Potassium": recipe.potassium_mg_per_100g or 0,
    }
    return recipe, nutrients_for_label


def generate_recipe_label_pdf(recipe_id, label_only=False):
    """
    Generates a PDF nutrition label for a Recipe item.
    Can generate a label-only PDF or a full-page PDF with additional details.
    """
    recipe, nutrients_for_label = _get_nutrition_label_data_recipe(recipe_id)
    if not recipe:
        return "Recipe not found", 404

    typst_content = _generate_typst_content_recipe(
        recipe, nutrients_for_label, label_only=label_only
    )
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(
            tmpdir, f"recipe_label_{recipe.id}_{file_suffix}.typ"
        )
        pdf_file_path = os.path.join(
            tmpdir, f"recipe_label_{recipe.id}_{file_suffix}.pdf"
        )

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    os.path.basename(typ_file_path),
                    "--pages",
                    "1",
                    os.path.basename(pdf_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
            safe_recipe_name = (
                re.sub(r"[^\w\s-]", "", recipe.name).strip().replace(" ", "_")
            )
            download_name = f"{safe_recipe_name}_{file_suffix}_{timestamp}.pdf"
            response = send_file(
                pdf_file_path,
                as_attachment=False,
                download_name=download_name,
                mimetype="application/pdf",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = NO_CACHE_HEADERS
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            current_app.logger.error(
                f"Typst compilation failed for recipe_id {recipe_id}: {e.stderr}"
            )
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error(TYPST_NOT_FOUND_SHORT_ERROR)
            return (
                TYPST_NOT_FOUND_ERROR,
                500,
            )


def generate_recipe_label_svg(recipe_id):
    recipe, nutrients_for_label = _get_nutrition_label_data_recipe(recipe_id)
    if not recipe:
        return "Recipe not found", 404

    typst_content = _generate_typst_content_recipe(
        recipe, nutrients_for_label, svg_only=True
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"recipe_label_{recipe_id}.typ")
        svg_file_path = os.path.join(tmpdir, f"recipe_label_{recipe_id}.svg")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    "--format",
                    "svg",
                    os.path.basename(typ_file_path),
                    os.path.basename(svg_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            response = send_file(
                svg_file_path,
                as_attachment=False,
                download_name=f"recipe_label_{recipe_id}.svg",
                mimetype="image/svg+xml",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = NO_CACHE_HEADERS
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            current_app.logger.error(
                f"Typst compilation failed for recipe_id {recipe_id}: {e.stderr}"
            )
            return f"Error generating SVG: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error(TYPST_NOT_FOUND_SHORT_ERROR)
            return (
                TYPST_NOT_FOUND_ERROR,
                500,
            )
