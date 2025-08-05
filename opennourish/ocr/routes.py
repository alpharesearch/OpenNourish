import re
import pytesseract
from flask import request, jsonify, current_app
from PIL import Image
from . import ocr_bp


def extract_nutrition_data(text):
    """
    Extracts nutrition data from OCR text using refined regex and heuristics.
    """
    data = {}
    # This pattern looks for a number but stops at a space, g, or the end of the string,
    # which prevents it from grabbing the percentage values that sometimes follow.
    patterns = {
        "serving_size": r"Serving size\s+(.*)",
        "calories": r"Calories\D*\s*(\d+)",
        "total_fat": r"Total Fat\s+([\d.]+)(?=\s|g|$)",
        "saturated_fat": r"Saturated Fat\s+([\d.]+)(?=\s|g|$)",
        "trans_fat": r"Trans Fat\s+([\d.]+)(?=\s|g|$)",
        "cholesterol": r"Cholesterol\s+([0O\d.]+)(?=\s|m|$)",
        "sodium": r"Sodium\s+([0O\d.]+)(?=\s|m|$)",
        "total_carbohydrate": r"Total Carbohydrate\s+([\d.]+)(?=\s|g|$)",
        "dietary_fiber": r"Dietary Fiber\s+([\d.]+)(?=\s|g|$)",
        "total_sugars": r"Total Sugars\s+([\d.]+)(?=\s|g|$)",
        "protein": r"Protein\s+([\d.]+)(?=\s|g|$)",
    }

    # Fields that should end in 'g' and are prone to the '9' error
    g_unit_fields = {
        "total_fat",
        "saturated_fat",
        "trans_fat",
        "total_carbohydrate",
        "dietary_fiber",
        "total_sugars",
        "protein",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()

            # Apply the "ends with 9" heuristic for g-unit fields.
            if key in g_unit_fields and value.endswith("9"):
                value = value[:-1]

            # Normalize O to 0 for cholesterol and sodium
            if key in ["cholesterol", "sodium"]:
                value = value.replace("O", "0")

            data[key] = value

    # Extract gram weight from serving size
    if "serving_size" in data:
        # Look for the standard (XXg) format
        match = re.search(r"\((\d+(\.\d+)?)\s*g\)", data["serving_size"], re.IGNORECASE)
        if match:
            data["gram_weight"] = match.group(1)
        else:
            # Fallback for formats like "55g" or "55 g"
            match = re.search(r"(\d+(\.\d+)?)\s*g", data["serving_size"], re.IGNORECASE)
            if match:
                data["gram_weight"] = match.group(1)

    return data


@ocr_bp.route("/api/ocr-nutrition-label", methods=["POST"])
def ocr_nutrition_label():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if file:
        try:
            img = Image.open(file.stream)
            # Preprocessing
            gray_img = img.convert("L")

            # OCR with configuration for a single block of text
            config = "--psm 6"
            text = pytesseract.image_to_string(gray_img, config=config)
            current_app.logger.debug(f"OCR Text: {text}")

            # Extract structured data
            data = extract_nutrition_data(text)

            return jsonify(data)
        except Exception as e:
            current_app.logger.error(f"OCR Error: {e}")
            return jsonify({"error": "Error processing image"}), 500
