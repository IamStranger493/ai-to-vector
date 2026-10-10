import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from app.config import Settings


def test_allowed_origins_are_normalized():
    s = Settings(ALLOWED_ORIGINS=" https://app.vercel.app/ , http://localhost:5173 ,, ")
    assert s.allowed_origins_list == ["https://app.vercel.app", "http://localhost:5173"]
