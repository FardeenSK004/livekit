from app.services.auth import AuthService


def test_verify_login_rejects_when_hashes_empty(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ADMIN_USERNAME_HASH", "")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD_HASH", "")
    svc = AuthService()
    assert svc.verify_login("admin", "password") is False
