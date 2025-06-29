def test_home_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200

def test_search_feature(client):
    response = client.post('/', data={'search': 'apple'})
    assert response.status_code == 200
    assert b'Apple' in response.data
