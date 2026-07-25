from app.main import create_app


def test_critical_routes_registered():
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in paths
    assert "/api/v1/webhooks/telephony" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/dashboard/metrics" in paths
    assert "/api/v1/kb/ingest" in paths
    assert "/dispatch-test" in paths
