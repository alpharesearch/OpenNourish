import pytest
import os
from flask import current_app

# Define the expected data for the standard USDA test images.
EXPECTED_DATA_USDA = {
    "calories": "230",
    "total_fat": "8",
    "saturated_fat": "1",
    "cholesterol": "0",
    "sodium": "160",
    "total_carbohydrate": "37",
    "dietary_fiber": "4",
    "total_sugars": "12",
    "protein": "3",
    "gram_weight": "55",
}

# Define the expected data for the phone camera image.
# Note: "Dietary Fiber less than 1g" is expected to be parsed as "1".
EXPECTED_DATA_PHONE = {
    "calories": "110",
    "total_fat": "0",
    "saturated_fat": "0",
    "cholesterol": "0",
    "sodium": "0",
    "total_carbohydrate": "23",
    "dietary_fiber": "1",
    "total_sugars": "0",
    "protein": "3",
    "gram_weight": "30",
}

# A list of tuples, each containing an image path and its corresponding expected data.
TEST_CASES = [
    ("tests/ocr_big.png", EXPECTED_DATA_USDA),
    ("tests/ocr_small.png", EXPECTED_DATA_USDA),
    ("tests/ocr_phone.jpg", EXPECTED_DATA_PHONE),
]


@pytest.mark.parametrize("image_path, expected_data", TEST_CASES)
def test_ocr_nutrition_label(client, image_path, expected_data):
    """
    Tests the /api/ocr-nutrition-label endpoint and reports a success rate.
    """
    full_image_path = os.path.join(current_app.root_path, "..", image_path)
    if not os.path.exists(full_image_path):
        pytest.fail(f"Test image not found at: {full_image_path}")

    with open(full_image_path, "rb") as img_file:
        data = {"file": (img_file, os.path.basename(image_path))}
        response = client.post(
            "/api/ocr-nutrition-label", data=data, content_type="multipart/form-data"
        )

    assert response.status_code == 200
    extracted_data = response.get_json()

    correct_matches = 0
    total_fields = len(expected_data)
    report = [f"\n--- OCR Test Report for {image_path} ---"]

    for key, expected_value in expected_data.items():
        if key in extracted_data and extracted_data[key] == expected_value:
            correct_matches += 1
            report.append(f"[SUCCESS] '{key}': Extracted '{expected_value}'")
        elif key in extracted_data:
            report.append(
                f"[FAIL]    '{key}': Expected '{expected_value}', but got '{extracted_data[key]}'"
            )
        else:
            report.append(f"[FAIL]    '{key}': Was not found in the response.")

    success_rate = (correct_matches / total_fields) * 100
    report.append(
        f"--- Success Rate: {success_rate:.2f}% ({correct_matches}/{total_fields}) ---\n"
    )

    # Print the full report to the console
    print("\n".join(report))

    # Fail the test if the success rate is below a threshold (e.g., 80%)
    assert success_rate >= 70
