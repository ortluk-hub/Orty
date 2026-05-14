# Client Promotion System

## Overview

Orty now supports a client promotion system where registered clients can apply for admin status through a secure approval workflow. This allows multiple admin clients while maintaining security through the admin secret verification process.

## Architecture

```
┌──────────────────┐
│  Regular Client  │
│  (limited perms) │
└────────┬─────────┘
         │
         │ 1. Submit promotion request
         │    - Provide reason
         │    - Hash admin secret (proves knowledge)
         ▼
┌──────────────────┐
│  Promotion Queue │
│  (pending state) │
└────────┬─────────┘
         │
         │ 2. Admin reviews
         │    - View pending requests
         │    - Approve or reject
         ▼
┌──────────────────┐
│   Admin Client   │
│  (full perms)    │
└──────────────────┘
```

## Security Model

### Admin Secret Verification
- Clients must provide a **hash** of the admin secret (not the secret itself)
- This proves they have access to the secret (e.g., from documentation)
- The secret itself is never transmitted or stored in the request
- Hash algorithm: SHA-256

### Approval Requirements
- Only existing admin clients can approve/reject requests
- The primary root client (created with admin secret) is automatically admin
- Admin status is stored in the database (`is_admin` flag)
- All promotion actions are auditable

## API Endpoints

### 1. Request Promotion

**POST** `/v1/clients/me/promotion/request`

Submit a promotion request for admin status.

**Request:**
```json
{
  "reason": "I need admin access to manage bug reports and approve Codey fixes",
  "admin_secret_hash": "sha256_hash_of_orty_shared_secret"
}
```

**Response (200 OK):**
```json
{
  "request_id": "uuid",
  "client_id": "uuid",
  "reason": "...",
  "status": "pending",
  "created_at": "ISO timestamp"
}
```

**Errors:**
- `400` - Client already has admin status
- `400` - Promotion request already pending
- `401` - Invalid admin secret hash

### 2. List Promotion Requests (Admin Only)

**GET** `/v1/clients/promotion/requests?status=pending`

List promotion requests, optionally filtered by status.

**Query Parameters:**
- `status` (optional): `pending`, `approved`, `rejected`, or omit for all

**Response (200 OK):**
```json
{
  "requests": [
    {
      "request_id": "uuid",
      "client_id": "uuid",
      "client_name": "My Client",
      "reason": "...",
      "status": "pending",
      "created_at": "ISO timestamp"
    }
  ],
  "total": 1
}
```

### 3. Approve Promotion (Admin Only)

**POST** `/v1/clients/promotion/approve`

Approve a promotion request and grant admin status.

**Request:**
```json
{
  "request_id": "uuid"
}
```

**Response (200 OK):**
```json
{
  "client_id": "uuid",
  "name": "My Client",
  "preferences": {
    "promoted_at": "ISO timestamp"
  },
  "is_primary": false,
  "created_at": "ISO timestamp",
  "last_seen_at": "ISO timestamp"
}
```

### 4. Reject Promotion (Admin Only)

**POST** `/v1/clients/promotion/reject`

Reject a promotion request.

**Request:**
```json
{
  "request_id": "uuid",
  "reason": "Insufficient justification for admin access"
}
```

**Response (200 OK):**
```json
{
  "status": "rejected",
  "request_id": "uuid"
}
```

### 5. List Admin Clients (Admin Only)

**GET** `/v1/clients/admin/list`

List all clients with admin status.

**Response (200 OK):**
```json
[
  {
    "client_id": "uuid",
    "name": "Primary Root Client",
    "preferences": {},
    "is_primary": true,
    "created_at": "ISO timestamp",
    "last_seen_at": "ISO timestamp"
  }
]
```

### 6. Get Current Client Status

**GET** `/v1/auth/me`

Get current client info including admin status.

**Response (200 OK):**
```json
{
  "client_id": "uuid",
  "name": "My Client",
  "preferences": {},
  "is_primary": false,
  "created_at": "ISO timestamp",
  "last_seen_at": "ISO timestamp",
  "auth_method": "bearer",
  "is_admin": false
}
```

## Usage Example

### Step 1: Client Requests Promotion

```python
import hashlib
import requests

# Client credentials
client_id = "your-client-id"
access_token = "your-access-token"

# Hash the admin secret (from documentation/setup)
admin_secret = "OrtyIAmYourFather"
admin_secret_hash = hashlib.sha256(admin_secret.encode()).hexdigest()

# Submit promotion request
response = requests.post(
    "http://localhost:8080/v1/clients/me/promotion/request",
    headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    },
    json={
        "reason": "I need admin access to manage bug reports",
        "admin_secret_hash": admin_secret_hash,
    },
)

print(response.json())
# {"request_id": "...", "status": "pending", ...}
```

### Step 2: Admin Reviews Request

```python
# Admin credentials
admin_token = "admin-access-token"

# List pending requests
response = requests.get(
    "http://localhost:8080/v1/clients/promotion/requests?status=pending",
    headers={"Authorization": f"Bearer {admin_token}"},
)

requests_list = response.json()
print(f"Pending requests: {requests_list['total']}")

# Approve a request
request_id = requests_list['requests'][0]['request_id']
response = requests.post(
    "http://localhost:8080/v1/clients/promotion/approve",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={"request_id": request_id},
)

print(f"Approved: {response.json()['name']}")
```

### Step 3: Client Checks Status

```python
# Client checks their admin status
response = requests.get(
    "http://localhost:8080/v1/auth/me",
    headers={"Authorization": f"Bearer {access_token}"},
)

client_info = response.json()
print(f"Is admin: {client_info['is_admin']}")
# Is admin: True
```

## Database Schema

### clients table
```sql
ALTER TABLE clients ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;
```

### client_promotion_requests table
```sql
CREATE TABLE client_promotion_requests (
    request_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_client_id TEXT,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    FOREIGN KEY(client_id) REFERENCES clients(client_id)
);
```

## Admin Permissions

Admin clients can:
- ✓ Approve/reject promotion requests
- ✓ List all clients
- ✓ Revoke any access token
- ✓ Introspect any access token
- ✓ Create new clients
- ✓ Manage bots
- ✓ Access admin-only endpoints

Regular clients can:
- ✓ Manage their own preferences
- ✓ Request promotion to admin
- ✓ Revoke their own tokens
- ✓ View their own info

## Security Considerations

### Secret Hygiene
- The admin secret (`ORTY_SHARED_SECRET`) is only used for:
  - Initial setup (creating first admin client)
  - Hash verification in promotion requests
- The secret is **never** stored in promotion requests
- Only the SHA-256 hash is transmitted

### Audit Trail
- All promotion requests are recorded
- Reviewer identity is tracked (`reviewer_client_id`)
- Rejection reasons are stored
- Status changes are timestamped

### Revocation
- Admin status can be manually revoked via database if needed
- All access tokens can be revoked by any admin
- Client tokens can be rotated to force re-authentication

## Evolution Contract Compliance

### §1 User Precedence Rules ✓
- User controls who becomes admin (approval required)
- Admin secret proves legitimate access
- Rejection reason can be provided

### §2 Self-Evolution Rules ✓
- Changes are auditable (promotion requests table)
- Rollback possible (revoke admin status)
- Atomic changes (one request at a time)

### §4 Security Rules ✓
- Secret never transmitted (hash only)
- Least privilege (default: no admin)
- Admin actions require authentication

## Troubleshooting

### "Invalid admin secret" error
- Ensure you're hashing the exact secret (case-sensitive)
- Check for whitespace in the secret
- Verify the secret matches `ORTY_SHARED_SECRET` in `.env`

### "Already pending" error
- Client can only have one pending request at a time
- Wait for admin to review existing request
- Or contact an admin to reject the pending request

### "Admin access required" error
- Your client doesn't have admin status yet
- Request promotion or contact an admin
- Check `/v1/auth/me` to verify `is_admin` field

## Next Steps

1. **UI Integration**: Add promotion request UI to web interface
2. **Notifications**: Notify admins of new requests
3. **Auto-approval**: Auto-approve requests from trusted sources
4. **Expiry**: Add expiration to pending requests
5. **Rate limiting**: Limit promotion requests per client
