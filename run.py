from opennourish import create_app

# This function is automatically discovered by Flask's CLI
def create_app_cli():
    return create_app()

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)