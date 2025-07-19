from models import db, User

def test_user_model(client):
    with client.application.app_context():
        user = User(username='testuser', password_hash='test_hash', email='testuser@example.com')
        db.session.add(user)
        db.session.commit()
        assert User.query.count() == 1
