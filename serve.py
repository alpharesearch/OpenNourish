from waitress import serve
from opennourish import create_app

app = create_app()

if __name__ == "__main__":
    # With TRUSTED_PROXY_HOPS=0 nothing here may rewrite the request's host or scheme, so
    # waitress has to clear X-Forwarded-* itself — leaving them in place would hand the value to
    # whatever reads the environ next. With hops above 0 the opposite is true: waitress must not
    # strip the headers ProxyFix was just registered to read. One setting, both sides.
    serve(
        app,
        host="0.0.0.0",
        port=8081,
        clear_untrusted_proxy_headers=not app.config.get("TRUSTED_PROXY_HOPS", 1),
    )
