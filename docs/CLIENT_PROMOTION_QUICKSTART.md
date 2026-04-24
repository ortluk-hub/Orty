# Client Promotion System - Quick Start

## Overview
Registered clients can now apply for admin status through a secure approval workflow.

## How It Works

### 1. Client Submits Request
```python
import hashlib
import requests

# Hash the admin secret (proves you know it without sending it)
admin_secret_hash = hashlib.sha256("OrtyIAmYourFather".encode()).hexdigest()

# Submit request
response = requests.post(
    "http://localhost:8080/v1/clients/me/promotion/request",
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    json={
        "reason": "I need admin access to manage bug reports",
        "admin_secret_hash": admin_secret_hash,
    }
)
```

### 2. Admin Reviews
```python
# List pending requests (admin only)
response = requests.get(
    "http://localhost:8080/v1/clients/promotion/requests?status=pending",
    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
)
pending = response.json()

# Approve a request
requests.post(
    "http://localhost:8080/v1/clients/promotion/approve",
    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    json={"request_id": pending['requests'][0]['request_id']}
)
```

### 3. Client Gets Admin Status
```python
# Check status
response = requests.get(
    "http://localhost:8080/v1/auth/me",
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}
)
print(f"Is admin: {response.json()['is_admin']}")
# Output: Is admin: True
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/clients/me/promotion/request` | POST | Bearer | Request admin |
| `/v1/clients/promotion/requests` | GET | Admin | List requests |
| `/v1/clients/promotion/approve` | POST | Admin | Approve |
| `/v1/clients/promotion/reject` | POST | Admin | Reject |
| `/v1/clients/admin/list` | GET | Admin | List admins |
| `/v1/auth/me` | GET | Bearer | Check status |

## Security

- **Hash verification**: Proves knowledge of secret without transmitting it
- **Approval required**: Existing admin must approve
- **Audit trail**: All requests recorded
- **Least privilege**: Default is no admin

## Files Changed

- `service/storage/clients_repo.py` - Promotion logic
- `service/storage/db.py` - Schema (is_admin column, promotion_requests table)
- `service/security.py` - hash_token() function
- `service/models/schemas.py` - Request/response schemas
- `service/api/routes/v1_clients.py` - API endpoints
- `service/api/deps.py` - Admin status in auth

## Documentation

- `docs/CLIENT_PROMOTION_SYSTEM.md` - Full documentation
- `EVOLUTION_CHANGELOG_PROMOTION.md` - Change log

## Test It

```bash
cd /home/ortluk/ortluk-hub/orty/Orty
source .venv/bin/activate
python -m uvicorn service.api:app --reload

# In another terminal, run the test script
./test_promotion.sh  # (create this based on EVOLUTION_CHANGELOG_PROMOTION.md)
```

## Why This Matters

Before: Only web UI (with admin secret) could admin
After: Any registered client can apply, admins approve

This enables:
- Multiple admin clients (mobile, desktop, API)
- Delegated administration
- Auditable access control
- Secure scaling
