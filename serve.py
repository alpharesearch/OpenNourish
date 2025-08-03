from waitress import serve
from opennourish import create_app

app = create_app()

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8081, clear_untrusted_proxy_headers=False)
