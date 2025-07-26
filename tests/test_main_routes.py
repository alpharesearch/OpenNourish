import pytest
from flask import url_for, request
from models import db, Food, UnifiedPortion

def test_index_redirects_authenticated(auth_client_onboarded):
    """
    Tests that an authenticated and onboarded user is redirected from the index to the dashboard.
    """
    client = auth_client_onboarded
    response = client.get(url_for('main.index'), follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == url_for('dashboard.index')

def test_index_redirects_unauthenticated(client):
    """
    Tests that an unauthenticated user is redirected from the index to the login page.
    """
    response = client.get(url_for('main.index'), follow_redirects=True)
    assert response.status_code == 200
    assert response.request.path == url_for('auth.login', _external=False)

def test_favicon_route(client, monkeypatch):
    """
    Tests that the /favicon.ico route returns the favicon file.
    """
    # Mock send_from_directory to avoid file system dependency
    mock_send = monkeypatch.setattr('opennourish.main.routes.send_from_directory', lambda x, y, mimetype: "favicon content")

    response = client.get(url_for('main.favicon'))
    assert response.status_code == 200
    assert "favicon content" in response.data.decode()

def test_food_detail_not_found(client):
    """
    Tests that the food detail page returns a 404 for a non-existent FDC ID.
    """
    response = client.get(url_for('main.food_detail', fdc_id=9999999))
    assert response.status_code == 404

def test_food_detail_success(client, sample_usda_food):
    """
    Tests that the food detail page renders successfully for a valid FDC ID.
    """
    response = client.get(url_for('main.food_detail', fdc_id=sample_usda_food.fdc_id))
    assert response.status_code == 200
    assert sample_usda_food.description.encode() in response.data

def test_upc_search_not_found(client):
    """
    Tests that the UPC search returns a 404 JSON response for a non-existent barcode.
    """
    response = client.get(url_for('main.upc_search', barcode='000000000000'))
    assert response.status_code == 404
    assert response.json['status'] == 'not_found'

def test_upc_search_success(client, sample_usda_food):
    """
    Tests that the UPC search returns a successful JSON response for a valid barcode.
    """
    # Add a UPC to the sample food
    with client.application.app_context():
        food = db.session.get(Food, sample_usda_food.fdc_id)
        food.upc = "123456789012"
        db.session.commit()

    response = client.get(url_for('main.upc_search', barcode='123456789012'))
    assert response.status_code == 200
    json_data = response.json
    assert json_data['status'] == 'found'
    assert json_data['fdc_id'] == sample_usda_food.fdc_id
    assert json_data['description'] == sample_usda_food.description
