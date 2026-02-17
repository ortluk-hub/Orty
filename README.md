# Orty

Orty is a modular, on-device AI assistant built with FastAPI and designed for clean architecture, extensibility, and local-first operation. The project is currently in early alpha and focused on building a solid architectural foundation before feature expansion.

## Status

Version: v0.1.0-alpha
Current Phase: Core API + Authentication + SQLite memory
Next Phase: LLM abstraction refinement and tool execution support

---

## Current Roadmap Position

Orty is currently in **v0.1.0-alpha** and in the **Core API + Authentication + SQLite memory** phase.

### What is already in place
- FastAPI application structure and running server entrypoint
- Health endpoint
- Shared-secret request authentication
- Basic chat endpoint wired to an LLM provider call

### What comes next
The next planned milestone is **LLM abstraction refinement and tool execution support**, followed by broader automation integrations.

---


## Architecture Overview

Orty follows a clean architecture approach:

* API Layer (FastAPI routers)
* Service Layer (business logic)
* Storage Layer (persistence abstraction)
* LLM Provider Abstraction (model interface layer)

The system is designed to support:

* Local or remote LLM providers
* Pluggable storage backends
* Secure request authentication
* Future tool integration and automation

---

## Tech Stack

* Python 3.12+
* FastAPI
* Uvicorn
* SQLite (memory persistence enabled)
* OpenAI and Ollama provider support
* Git for version control

Designed to run in Termux (Android) or any Linux environment.

---

## Project Structure

```
orty/
├── service/
│   ├── api/
│   ├── llm/
│   ├── storage/
│   └── conversation/
├── main.py
├── requirements.txt
└── .env
```

Structure will evolve as persistence and conversation management are added.

---

## Setup Instructions

### 1. Clone the Repository

```
git clone https://github.com/ortluk-hub/Orty.git
cd Orty
```

### 2. Create Virtual Environment (Recommended)

```
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```
ORTY_SHARED_SECRET=your_shared_secret_here
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
# or for local models
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.2
SQLITE_PATH=data/orty.db
```

This value is required for API authentication.

---

## Running the Server

```
uvicorn main:app --host 0.0.0.0 --port 8080
```

Health check endpoint:

```
GET /health
```

Expected response:

```
{"status": "ok"}
```


Chat endpoint now supports lightweight memory persistence via SQLite:

- include optional `conversation_id` in `/chat` requests to continue a thread
- if omitted, Orty creates a new `conversation_id` and returns it in the response

---

## Authentication

All protected endpoints require the following header:

```
x-orty-secret: <your_shared_secret>
```

Requests without this header or with an invalid value will be rejected.

---

## Development Workflow

* `main` branch → Stable releases
* `dev` branch → Active development

Create features in `dev`, then push to GitHub (`git push origin dev`) to publish commits remotely.

If this repo has no remote configured yet, add one first:

```
git remote add origin https://github.com/ortluk-hub/Orty.git
```

Note: `git commit` saves changes locally only; GitHub is updated after `git push`.

Version tags are used for milestone tracking.

### GitHub credentials required for push

Configuring `origin` only sets the remote URL; you still need GitHub credentials to authenticate when pushing.

Use one of these methods:

1. **HTTPS + Personal Access Token (PAT)**
   - Username: your GitHub username
   - Password prompt: use a GitHub PAT (not your GitHub account password)
   - Security: store PAT in a credential manager or environment variable; never commit PATs into code, docs, or Git history
   - Recommended classic/fine-grained permission: repository write access (for private repos, equivalent to classic `repo` scope)

2. **SSH key authentication**
   - Create an SSH key (`ed25519` recommended)
   - Add the public key to GitHub (Settings → SSH and GPG keys)
   - Set remote to `git@github.com:ortluk-hub/Orty.git`

Without one of the above credential methods, `git push` will fail even if `origin` is configured correctly.

### Preferred GitHub transport: SSH

If HTTPS proxying is unreliable, use SSH for GitHub remotes:

```
git remote set-url origin git@github.com:ortluk-hub/Orty.git
ssh -T git@github.com
git push -u origin dev
```

If you do not yet have an SSH key:

```
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub
```

Add the printed public key to GitHub (Settings → SSH and GPG keys), then re-run:

```
ssh -T git@github.com
git push -u origin dev
```

### Troubleshooting GitHub proxy/tunnel errors (403 prevention)

If you see `CONNECT tunnel failed, response 403` on `git push`, the proxy is denying the GitHub tunnel. Use this order to prevent repeated 403s:

1. Check whether a proxy is forced by environment or Git config:

```
env | grep -i proxy
git config --global --get-regexp proxy
```

2. Remove Git-level proxy overrides so Git can use direct connectivity when available:

```
git config --global --unset http.proxy
git config --global --unset https.proxy
```

3. Retry push with GitHub excluded from proxying:

```
NO_PROXY=github.com,api.github.com GIT_CURL_VERBOSE=1 git push -u origin dev
```

4. If your organization requires proxy usage, request/confirm allowlisting for:
   - `github.com`
   - `api.github.com`
   - `codeload.github.com`

5. If HTTPS is still blocked, switch remote to SSH (usually bypasses HTTPS CONNECT restrictions):

```
git remote set-url origin git@github.com:ortluk-hub/Orty.git
ssh -T git@github.com
git push -u origin dev
```

6. Ensure GitHub auth is valid (403 can also be auth/permission related):
   - Use a PAT with `repo` scope for HTTPS, or
   - Confirm your SSH key is added to the correct GitHub account.

---

## Roadmap

* SQLite persistence layer
* Conversation management system
* LLM abstraction layer
* Tool execution framework
* Background task system
* Smart home and automation integrations
* On-device model support

---

## Philosophy

Orty is built as a system, not a script.
The focus is clean structure, modularity, and long-term scalability.

---

If you'd like, we can now:

* Add a version badge
* Add a project architecture diagram
* Prepare a v0.2 milestone plan
* Or wire in SQLite and commit the next evolutionary step

Orty is now officially documented.
