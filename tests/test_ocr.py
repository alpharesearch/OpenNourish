import pytest
import os
from flask import current_app

# Define the expected data based on the nutrition label images
# This data is what we expect the OCR to extract.
EXPECTED_DATA = {
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

# List of test images to parameterize the test
TEST_IMAGES = ["tests/ocr_big.png", "tests/ocr_small.png"]


@pytest.mark.parametrize("image_path", TEST_IMAGES)
def test_ocr_nutrition_label(client, image_path):
    """
    Tests the /api/ocr-nutrition-label endpoint with different image resolutions.
    """
    # Construct the full path to the image file
    full_image_path = os.path.join(current_app.root_path, "..", image_path)

    # Check if the image file exists before proceeding
    if not os.path.exists(full_image_path):
        pytest.fail(f"Test image not found at: {full_image_path}")

    with open(full_image_path, "rb") as img_file:
        data = {"file": (img_file, os.path.basename(image_path))}

        # Make the POST request to the API endpoint
        response = client.post(
            "/api/ocr-nutrition-label", data=data, content_type="multipart/form-data"
        )

    # Assert that the request was successful
    assert response.status_code == 200

    # Parse the JSON response
    extracted_data = response.get_json()

    # Assert that the extracted data matches the expected data
    # We check each key individually to provide better feedback on failure
    for key, expected_value in EXPECTED_DATA.items():
        assert (
            key in extracted_data
        ), f"Key '{key}' was not found in the OCR response for image {image_path}."
        assert (
            extracted_data[key] == expected_value
        ), f"For image '{image_path}', key '{key}' expected value '{expected_value}', but got '{extracted_data[key]}'."
