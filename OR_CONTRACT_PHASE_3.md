Orty Model Distribution Contract (Phase 3)
1. Overview
Alfred is transitioning from bundled GGUF models (APK Assets) to a Hybrid Download Model.
•
Client behavior: Alfred uses Orty Cloud Inference if a local model is missing, while simultaneously downloading the model in the background.
•
Server behavior: Orty hosts GGUF files and provides a streaming endpoint for distribution.
2. Server API Specification (Orty)
A. Model Download (Public)
Used by Alfred during onboarding or background "upgrades."
•
Endpoint: GET /v1/models/{model_id}/download
•
Headers:
◦
Accept: application/octet-stream
◦
Range: bytes=0- (Optional, for future resume support)
•
Response:
◦
200 OK + Content-Length (Total GGUF size)
◦
Crucial: Must use a Streaming Response to avoid OOM on Cloud Run.
B. Model Registry (Public)
Used by Alfred to identify the correct file size and version.
•
Endpoint: GET /v1/models
•
Response Shape:
JSON
[
  {
    "id": "llama-3-8b-instruct-q4_k_m.gguf",
    "name": "Llama 3 8B (Medium Quant)",
    "size_bytes": 4920000000,
    "sha256": "...",
    "is_default": true
  }
]
C. Admin Model Upload (Private)
Used by sync_model_repo.py to seed the Cloud Run environment.
•
Endpoint: POST /v1/admin/models/upload
•
Headers:
◦
x-orty-admin-secret: <YOUR_SECRET_KEY>
◦
Content-Type: multipart/form-data
•
Query Params: model_id=<filename>
3. Server Implementation Requirements (Python/FastAPI)
To support 1GB+ GGUF files on Google Cloud Run, the following logic must be implemented:
1.
Mount GCS Bucket: Models should be stored in a Google Cloud Storage bucket and mounted to /models in the container.
2.
Streaming Response: Use FileResponse or a custom generator.
Python
@app.get("/v1/models/{model_id}/download")
async def download(model_id: str):
    path = f"/models/{model_id}"
    return FileResponse(path, media_type='application/octet-stream', filename=model_id)
3.
Cloud Run Settings:
◦
Timeout: Set to 3600 seconds.
◦
HTTP/2: Enabled.
◦
Memory: Minimum 512MB (streaming doesn't require high RAM).
4. Workstation Sync Script (sync_model_repo.py)
The local Python script must be updated with a --push-to-cloud flag:
1.
Read llm.model.id from local.properties.
2.
Locate the file in C:\Users\ortlu\models.
3.
Stream the file to the Orty Admin endpoint using requests.
5. Alfred Client Logic (Background Upgrade)
Hybrid Routing Protocol:
•
State Check: ModelRepository.isModelAvailable()
•
Action If False:
i.
Call OrtyApi.chat() for immediate response.
ii.
Check DownloadManager or ModelDownloadWorker. If not running, start it.
•
Action If True:
i.
Call LlamaCppLocalLlmEngine.generateResponse().
ii.
Do not hit Orty API.
Atomic Swap:
Alfred writes to model.gguf.tmp. Only when the stream closes successfully is the file renamed to model.gguf. This prevents the JNI bridge from attempting to load a corrupted/partial file and crashing.
6. Security Contract
1.
Public Endpoints: Model downloads should be restricted by API Key or Auth Token if bandwidth costs become a concern.
2.
Admin Endpoint: Must be protected by ORTY_ADMIN_SECRET environment variable in Cloud Run.
3.
Local Storage: Alfred stores models in context.getExternalFilesDir("models"). This directory is private to the app but accessible for large file writes.
