# serve.py

from waitress import serve
from opennourish import create_app

# Create the Flask app instance using your application factory
app = create_app()

if __name__ == '__main__':
    print("Starting production server with Waitress...")
    # The serve function runs the app.
    # It's configured to listen on all network interfaces on port 8080.
    serve(app, host='0.0.0.0', port=5010)