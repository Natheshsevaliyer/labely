"""Unit tests for app/models/user.py (User model methods)."""
import pytest
from datetime import datetime, timedelta

from app.models.user import User, PasswordResetToken
from app.core.security import verify_password


class TestUserModel:
    def test_set_password_stores_hash(self, db):
        user = User(email="a@test.com", username="alice")
        user.set_password("mypassword")
        assert user.password != "mypassword"
        assert user.password is not None

    def test_verify_password_correct(self, db):
        user = User(email="b@test.com", username="bob")
        user.set_password("secret123")
        assert user.verify_password("secret123") is True

    def test_verify_password_wrong(self, db):
        user = User(email="c@test.com", username="carol")
        user.set_password("correct")
        assert user.verify_password("wrong") is False

    def test_user_persisted_to_db(self, db):
        user = User(email="d@test.com", username="dave")
        user.set_password("pw1234")
        db.add(user)
        db.commit()

        fetched = db.query(User).filter(User.email == "d@test.com").first()
        assert fetched is not None
        assert fetched.username == "dave"
        assert fetched.verify_password("pw1234")

    def test_unique_email_constraint(self, db, test_user):
        dup = User(email=test_user.email, username="newuser")
        dup.set_password("pw1234")
        db.add(dup)
        with pytest.raises(Exception):
            db.commit()

    def test_unique_username_constraint(self, db, test_user):
        dup = User(email="unique@example.com", username=test_user.username)
        dup.set_password("pw1234")
        db.add(dup)
        with pytest.raises(Exception):
            db.commit()


class TestPasswordResetToken:
    def test_reset_token_persisted(self, db, test_user):
        token = PasswordResetToken(
            user_id=test_user.id,
            token="reset-token-abc",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            used=False,
        )
        db.add(token)
        db.commit()

        fetched = db.query(PasswordResetToken).filter(
            PasswordResetToken.token == "reset-token-abc"
        ).first()
        assert fetched is not None
        assert fetched.user_id == test_user.id
        assert fetched.used is False
