from opennourish import create_app
from models import db

app = create_app()

@app.cli.command("init-user-db")
def init_user_db_command():
    """Clears existing user data and creates new tables."""
    with app.app_context():
        db.create_all()
        db.session.commit()
    print("Initialized the user database.")

if __name__ == '__main__':
    app.run(debug=True)
