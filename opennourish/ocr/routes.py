import re
from paddleocr import PaddleOCR
from flask import request, jsonify, current_app
from PIL import Image, ImageOps
import numpy as np
import cv2
from . import ocr_bp


def extract_nutrition_data(text):
    """
    Extracts nutrition data from OCR text using refined regex and heuristics.
    """
    data = {}
    text = text.replace("O", "0")  # Replace 'O' with '0' globally before processing

    # A more robust pattern for calories, looking for a number near "Calories"
    calorie_pattern = r"(Calories|Amount per serving)\s*(\d+)|(\d+)\s*\n\s*Calories"
    calorie_match = re.search(calorie_pattern, text, re.IGNORECASE | re.DOTALL)
    if calorie_match:
        # Find the first non-empty group from the calorie match
        calories_value = next(
            (g for g in calorie_match.groups() if g is not None and g.isdigit()), None
        )
        if calories_value:
            data["calories"] = calories_value.strip()

    # Patterns for other nutrients, designed to be more flexible
    patterns = {
        "serving_size": r"Serving size\s+(.*?)(?:\n|$)",
        "total_fat": r"Total Fat\s+.*?([\d.]+)\s*g",
        "saturated_fat": r"Saturated Fat\s+.*?([\d.]+)\s*g",
        "trans_fat": r"Trans Fat\s+.*?([\d.]+)\s*g",
        "cholesterol": r"Cholesterol\s+.*?([\d.]+)\s*mg",
        "sodium": r"Sodium\s+.*?([\d.]+)\s*mg",
        "total_carbohydrate": r"Total Carbohydrate.*?([\d.]+)\s*g",
        "dietary_fiber": r"Dietary Fiber\s+.*?([\d.]+)\s*g|Dietary Fiber less than 1g",
        "total_sugars": r"Total Sugars\s+.*?([\d.]+)\s*g",
        "protein": r"Protein\s+.*?([\d.]+)\s*g",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            # Handle the special case for dietary fiber less than 1g
            if key == "dietary_fiber" and "less than 1g" in match.group(0):
                value = "1"
            else:
                value = match.group(1).strip()
            # Normalize O to 0 for all numerical values
            value = value.replace("O", "0")
            data[key] = value

    # Extract gram weight from serving size
    if "serving_size" in data:
        # Look for gram weight in various formats
        gram_weight_pattern = r"(?:\(|\s)(\d+(?:\.\d+)?)\s*g(?:\)|\s|$)"
        match = re.search(gram_weight_pattern, data["serving_size"], re.IGNORECASE)
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

            # Add a white border to the image to prevent text cutoff
            border_size = 50
            img_with_border = ImageOps.expand(img, border=border_size, fill="white")

            # Convert to grayscale
            gray_img = img_with_border.convert("L")

            # Adaptive Preprocessing: Apply resizing and thresholding only to large images
            # This helps normalize high-resolution photos without degrading smaller, cleaner images.
            max_width = 1200
            # A simple heuristic: if the image is large, it's likely a photo needing more processing.
            if gray_img.width > max_width:
                # Resize to a more manageable width
                scale = max_width / gray_img.width
                new_height = int(gray_img.height * scale)
                resized_img = gray_img.resize(
                    (max_width, new_height), Image.Resampling.LANCZOS
                )
                # Convert PIL Image to OpenCV format
                opencv_img = np.array(resized_img)
                # Apply Otsu's thresholding
                _, processed_img_cv = cv2.threshold(
                    opencv_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                # Convert back to PIL Image
                processed_img = Image.fromarray(processed_img_cv)
            else:
                # For smaller images (like the USDA test cases), skip resizing and thresholding
                processed_img = gray_img

            img_array = np.array(processed_img)

            # Initialize PaddleOCR
            # The first run will download the model, which can be slow.
            ocr = PaddleOCR(
                use_angle_cls=True, lang="en", det_limit_side_len=960, det_db_thresh=0.1
            )

            # Perform OCR
            result = ocr.ocr(img_array, cls=True)

            # Extract text from the result
            text_lines = []
            if result and result[0] is not None:
                for line in result[0]:
                    text_lines.append(line[1][0])

            text = "\n".join(text_lines)
            current_app.logger.debug(f"OCR Text: {text}")

            # Extract structured data
            data = extract_nutrition_data(text)

            return jsonify(data)
        except Exception as e:
            current_app.logger.error(f"OCR Error: {e}")
            return jsonify({"error": "Error processing image"}), 500
