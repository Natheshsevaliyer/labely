# Labely-API-Service-2.0

# 0 Health Check

## 0.1 Root endpoint
```bash
curl -X GET "http://localhost:8001/"
```

## 0.2 Check system health
```bash
curl -X GET "http://localhost:8001/health"
```

# 1. Authentication

## 1.1 Registor
```bash
curl -X POST "https://labelyapi.tiktik.in/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "arunakil413@gmail.com",
    "username": "Arun",
    "password": "Qwerty@1"
  }' | jq
```

## 1.2 Login
```bash
curl -X POST "http://localhost:8001/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@gmail.com",
    "password": "Qwerty@1"
  }' | jq

TOKEN=$(curl -s -X POST "http://localhost:8001/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"arunakil413@gmail.com","password":"Qwerty@1"}' | jq -r '.data.access_token')
```
## 1.3 Get current user info
```bash
curl -X GET "http://localhost:8001/api/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

## 1.4 Forgot password
```bash
curl -X POST "http://localhost:8001/api/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "arunakil413@gmail.com"
  }'
```

## 1.4 Reset password
```bash
curl -X POST "http://localhost:8001/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "your-reset-token",
    "new_password": "NewTest@123",
    "confirm_password": "NewTest@123"
  }'
```

## 1.5 Change password
```bash
curl -X POST "http://localhost:8001/api/auth/change-password" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "Test@123",
    "new_password": "NewTest@123",
    "confirm_password": "NewTest@123"
  }'
```

## 1.6 Logout
```bash
curl -X POST "http://localhost:8081/api/v1/auth/logout" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "nZVgPtVUb6-vVpWt8CzaCRK10KI5AdEMZgefbgHA21cWliWU2FotDxSNOPIezP16TWGKLjlYFS1ojTR2KhntPw"
  }' | jq
```

# 2. Orders (Label Generation)

## 2.1 Get available SRPs
```bash
curl -X GET "http://localhost:8001/api/orders/available-srps?days_back=12" \
  -H "Authorization: Bearer $TOKEN" | jq
```

## 2.2 Generate labels
```bash
curl -X POST "http://localhost:8001/api/orders/generate-labels" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "srp": "SRP",
    "quantity": 2
  }' | jq
```

## Stream

```bash
# Stream status updates
curl -N -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/api/sse/process/37/stream"

# Or get status once
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/api/sse/process/37/status"
```

## 2.3 Check process status
```bash
curl -X GET "http://localhost:8001/api/orders/process/3/status" \
  -H "Authorization: Bearer $TOKEN" | jq
```

## 3. Download Files

## 3.1 Download merged labels PDF
```bash
curl -X GET "http://localhost:8001/api/download/labels/44" \
  -H "Authorization: Bearer $TOKEN" \
  --output merged_labels.pdf
```

## 3.1 Download labels only PDF
```bash
curl -X GET "http://localhost:8001/api/download/labels-only/44" \
  -H "Authorization: Bearer $TOKEN" \
  --output labels.pdf
```
## 3.1 Download labels only PDF
```bash
curl -X GET "http://localhost:8001/api/download/report/44" \
  -H "Authorization: Bearer $TOKEN" \
  --output report.pdf
```

## 3.2 Download individual order report
```bash
curl -X GET "http://localhost:8001/api/download/report/1_309292690-A" \
  -H "Authorization: Bearer $TOKEN" \
  --output report_309292690-A.pdf
```

## 3.3 Download tracking CSV (for Mirakl import)
```bash
curl -X GET "http://localhost:8001/api/download/tracking/1" \
  -H "Authorization: Bearer $TOKEN" \
  --output tracking_import.csv
```

## 3.4 Download complete archive
```bash
curl -X GET "http://localhost:8001/api/download/archive/1" \
  -H "Authorization: Bearer $TOKEN" \
  --output process_archive.zip
```

# 4. Tracking

## 4.1 Get orders ready for tracking update

```bash
curl -X GET "http://localhost:8001/api/tracking/ready-orders?start_date=2026-01-01&end_date=2026-02-24&page=1&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

## 4.2 Bulk update tracking numbers

```bash
curl -X POST "http://localhost:8001/api/tracking/bulk-update" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_ids": ["309292694-A"],
    "force_update": false
  }'
```

## 4.3 Force bulk update (ignore validation)

```bash
curl -X POST "http://localhost:8001/api/tracking/bulk-update" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_ids": ["309292690-A", "309292688-A"],
    "force_update": true
  }'
```

## 4.4 Check Batch Status

```bash
curl -X GET "http://localhost:8001/api/tracking/batch/58b7acff-d001-47e9-868a-2d7144f16b33/status" \
  -H "Authorization: Bearer $TOKEN" | jq
```

## 4.5. List All Tracking Batches
```bash
curl -X GET "http://localhost:8001/api/tracking/batches?page=1&limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq
```

## 4.6. Check Legacy Process Status
```bash
curl -X GET "http://localhost:8001/api/tracking/status/1" \
  -H "Authorization: Bearer $TOKEN" | jq
```

# 5. Shipment

## 5.1 Get ready shipments by date

```bash
curl -X GET "http://localhost:8001/api/shipment/ready-by-date?start_date=2026-01-01&end_date=2026-02-24" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.2 Get ready shipments with carrier filter

```bash
curl -X GET "http://localhost:8001/api/shipment/ready-by-date?start_date=2026-01-01&end_date=2026-02-19&carrier_filter=Colissimo" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.3 Validate shipments

```bash
curl -X POST "http://localhost:8001/api/shipment/validate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_ids": ["309292694-A"],
    "force_confirm": false
  }'
```

## 5.4 Confirm shipments

```bash
curl -X POST "http://localhost:8001/api/shipment/confirm" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_ids": ["309292694-A"],
    "validate_only": false,
    "force_confirm": false
  }'
```

## 5.5 Validate only (dry run)
```bash
curl -X POST "http://localhost:8001/api/shipment/confirm" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_ids": ["309292690-A", "309292688-A"],
    "validate_only": true,
    "force_confirm": false
  }'
```

## 5.6 Force confirm shipments (ignore validation)
```bash
curl -X POST "http://localhost:8001/api/shipment/confirm" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "order_ids": ["309292690-A", "309292688-A"],
    "validate_only": false,
    "force_confirm": true
  }'
```

## 5.7 Confirm shipments by date range
```bash
curl -X POST "http://localhost:8001/api/shipment/confirm-by-date?start_date=2024-01-01&end_date=2024-12-31" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.8 Confirm shipments by date with carrier filter
```bash
curl -X POST "http://localhost:8001/api/shipment/confirm-by-date?start_date=2024-01-01&end_date=2024-12-31&carrier_filter=Colissimo&max_orders=5" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.9 Get batch status
```bash
curl -X GET "http://localhost:8001/api/shipment/batch/0b959fbc-ae03-457e-8a07-8a87cd876fe3/status" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.10 List all batches
```bash
curl -X GET "http://localhost:8001/api/shipment/batches?page=1&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.11 Get shipment history
```bash
curl -X GET "http://localhost:8001/api/shipment/history?start_date=2024-01-01&end_date=2024-12-31&page=1&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

## 5.12 Get specific shipment details
```bash
curl -X GET "http://localhost:8001/api/shipment/309292690-A" \
  -H "Authorization: Bearer $TOKEN"
```
```bash
curl -X GET "http://localhost:8001/api/v1/orders/unified-sales"
  -H "Authorization: Bearer $TOKEN"
 ```
# 6. Dashboard

## 6.1 Get simple dashboard
```bash
curl -X GET "http://localhost:8001/api/dashboard/simple" \
  -H "Authorization: Bearer $TOKEN"
```

# Mirakl API Doc

## GET Order List
```bash
curl -G "https://showroomprive2-dev.mirakl.net/api/orders" \
  -H "Authorization: a51102aa-70df-48c2-a8a3-32028ebf2557" \
  -H "Accept: application/json" \
  --data-urlencode "carrier_manager=SRP" \
  --data-urlencode "order_state_codes=SHIPPING" | jq | grep "order_id"
```


curl -X POST "https://label.terone.showroomprive.net/s9duk98x6r6cx2qztwzsy/api/label/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept: application/json" \
  -d "grant_type=password" \
  -d "client_id=0926096f-c191-41b2-a90b-959aa839db65" \
  -d "username=EM Developpement" \
  -d "password=pqLj)@560s" | jq

curl -X POST "https://label.terone.showroomprive.net/s9duk98x6r6cx2qztwzsy/api/label/v1/create" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "referenceId": "309293435",
    "referenceSource": "SRP",
    "mode": "Shipping"
  }'