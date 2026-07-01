# Labely – Unit & Integration Test Suite

## 195 tests across 8 test files, all passing ✅

### Files
| File | What it tests |
|------|--------------|
| `conftest.py` | Shared fixtures: in-memory SQLite DB, TestClient, auth tokens |
| `test_security.py` | JWT token creation/verification, password hashing |
| `test_exceptions.py` | All custom exception classes and HTTP status codes |
| `test_carrier.py` | Country-code resolution and carrier detection (GLS / Colissimo) |
| `test_date_utils.py` | `parse_date`, `format_date`, `get_date_range`, `get_month_range` |
| `test_file_utils.py` | `ensure_dir`, `safe_filename`, `get_file_size`, `cleanup_old_files` |
| `test_pagination.py` | `build_page_response` edge-cases |
| `test_schemas.py` | Auth, order, and response Pydantic schemas + validators |
| `test_models.py` | User / PasswordResetToken ORM model methods & DB constraints |
| `test_config.py` | Settings properties (DATABASE_URL, REDIS_URL, etc.) |
| `test_auth_endpoints.py` | /api/v1/auth/* endpoints (register, login, me, forgot/reset password…) |
| `test_api_endpoints.py` | /api/v1/orders/*, /api/v1/tracking/*, /api/v1/shipment/* |
| `test_health.py` | GET / and GET /health |

## Running the tests

### 1 – Install dependencies (once)
```bash
pip install -r requirements.txt
pip install "httpx==0.25.2"   # pin to starlette-compatible version
```

### 2 – Run all tests
```bash
pytest tests/ -v
```

### 3 – Run with coverage
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

### 4 – Run a single file
```bash
pytest tests/test_security.py -v
```

## Notes
- **No real database or Redis needed** – tests use SQLite in-memory and mock Redis.
- **No `.env` file needed** – `conftest.py` injects all required env vars before import.
- Only `httpx==0.25.2` differs from `requirements.txt`; the rest can be installed as-is.
