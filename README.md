> ⚠️ **Note**: This project is in very early stages of development and not ready for production use.

# 🧭 Lotse

<p align="center">
  <img src="lotse-ui/public/lotse.webp" width="300" alt="Lotse Logo">
</p>

## 🌟 Overview

**Lotse** is a modern cloud platform that goes beyond traditional serverless options. Instead of just deploying single functions, you can deploy complete projects in any programming language you prefer.

It's built on Kubernetes but hides the complexity, giving you both enterprise-level reliability and a simple developer experience. You get a user-friendly interface to manage your apps, access development environments remotely, and control everything through an API if needed.

It was built for people who do not want to write any YAML or Dockerfiles, but still need to deploy applications on a Kubernetes cluster.

> **Why "Lotse"?** Lotse is the German word for "pilot" or "navigator", reflecting its role in guiding packages through the complexities of deployment and execution.

## ✨ Key Features

- 📦 **Multi-Language Support**: Deploy Python, all sort of binaries (Go, .NET etc.), and custom containers via REST endpoints or Lotse UI

- 🔄 **Advanced Container Management**: Kubernetes container provisioning with improved status monitoring and lifecycle management

- 🔧 **Cluster Management**: Complete Kubernetes cluster administration capabilities

- 🖥️ **Interactive Terminal Access**: Direct terminal access to running containers

- 🔀 **Version Management**: Deploy packages in user specified versioning

- 🔌 **Proxy Support**: Automatic proxy configuration

## 📸 Screenshots & Demonstrations

![Overview](assets/overview.png)

Check out our [Screenshots and Demonstrations](SCREENSHOTS.md) to see Lotse in action

## 🔧 Technical Stack

- 🐍 **Backend**: FastAPI (Python)

- 🅰️ **Frontend**: Angular

- ☸️ **Container Orchestration**: Kubernetes

- 🐘 **Database**: PostgreSQL

- 📨 **Message Queue**: ActiveMQ (for async operations)

- 🧰 **Development Tools**: VS Code

## 🏁 Getting Started

### Prerequisites

- Kubernetes command line tool (kubectl)
- Docker Desktop
- Kubernetes enabled in Docker Desktop or any other Kubernetes cluster
- Python 3.13.2
- Node.js >= 20

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/Picoba-Solutions-GmbH/lotse.git
cd lotse

# Bootstrap Kubernetes environment
./startup.ps1

# Access points after startup
# UI: http://kubernetes.docker.internal/lotse/ui
# API Docs: http://kubernetes.docker.internal/lotse/docs

# For local debugging:
# 1. Start PostgreSQL
docker-compose up -d

# 2. Configure environment
cp .env.example .env

# 3. Start backend (VS Code)
python -m venv venv
pip install -r requirements.txt
# Press F5 to start - Swagger UI opens at localhost:8000/docs

# 4. Start UI development server
cd lotse-ui
npm i
npm run start
```

## 🗄️ Database Migrations

The database schema is managed with [Alembic](https://alembic.sqlalchemy.org/) migrations (similar to Entity Framework migrations).
Migration files live in `migrations/versions/`. Pending migrations are applied automatically when Lotse starts.

```bash
# After changing an entity in src/database/models/, create a migration and review the generated file
alembic revision --autogenerate -m "add column x to packages"

# Apply / revert migrations manually (uses the POSTGRES_* variables from .env)
alembic upgrade head
alembic downgrade -1

# Show all migrations and the current state of the database
alembic history --verbose
alembic current

# Run against another database
alembic -x url=postgresql://user:password@host:5432/lotse upgrade head
```

Every applied migration is recorded in the `migration_history` table (revision, operation and timestamp).
`alembic_version` holds the current revision. Databases created before migrations were introduced are detected
on startup and marked as being on the initial migration (`0001_initial`).

## 🔄 Deploying from Git

Instead of uploading a zip and a `config.yaml` for every version, connect a package to a Git repository
(**Git Sources** in the UI). Lotse checks the repository regularly and deploys new tags.

1. Put the package into a repository (or a folder of a monorepo), exactly as you would zip it:
   ```
   my-package/
     config.yaml        # same format as for uploads; the version is taken from the tag
     main.py
     requirements.txt
   ```
2. In Lotse, open **Git Sources → Connect Repository**. Enter the HTTPS URL, the folder, the tag prefix (default `v`)
   and, for private repositories, a read-only personal access token (stored as a Kubernetes secret).
3. `git tag v1.3.0 && git push --tags` → version `1.3.0` is deployed and becomes the default (with auto sync on).

- **Rollback:** set an older version as default, or deploy an older tag from the tag list. Auto sync only reacts to
  *new* tags, so it never undoes a rollback.
- **Secrets stay out of Git:** declare the variable without a value (`- {name: DB_PASSWORD, secret: true}`) and set it
  once in Lotse. Every synced version takes over empty values from the previous default version.
- **Webhook (optional):** Lotse polls every 2 minutes by default. GitHub, Gitea and Azure DevOps webhooks trigger an
  immediate check (see the webhook dialog of a source).
- Python and container packages are supported. Compiled apps: see below.
- Settings: `GIT_SYNC_ENABLED`, `GIT_SSL_CAINFO` (CA bundle for internal Git servers),
  `GIT_ALLOW_FILE_URLS` (local testing only).

## 📦 Deploying container images (.NET, Go, …)

Compiled apps are deployed as container images. CI builds and pushes the image, Lotse deploys it.

1. An admin adds the registry under **Registries**: Azure Container Registry, GitHub (ghcr.io), GitLab, Docker Hub
   or any other registry. Credentials are stored as a Kubernetes secret. Pods pull images either with the cluster's
   own access, with a pull secret Lotse creates from the credentials, or with an existing pull secret.
2. With a **discovery path** (e.g. `lotse`) and **register new images** on, every image below it becomes a package
   automatically (`myacr.azurecr.io/lotse/order-service` → package `order-service`). Otherwise connect images one by
   one under **Sources → Container images**.
3. CI: `docker build -t myacr.azurecr.io/lotse/order-service:1.3.0 . && docker push …` → version `1.3.0` is
   deployed, pinned to the image digest. Tags that aren't versions (`latest`, `sha-…`) are ignored.

Arguments, environment variables (including secrets), volumes and the timeout are set in Lotse and carried over to
every new image version. Run arguments are passed to the container as `args` (the image's `ENTRYPOINT` stays).

**Alternative: deploy file in Git.** Keep the settings versioned in Git and let the Git tag pick the image:
```yaml
# config.yaml in a Git source
package_name: order-service
runtime: container
image: myacr.azurecr.io/lotse/order-service:{{version}}
```
`git tag v1.3.0` deploys image tag `1.3.0`. If CI hasn't pushed the image yet, Lotse retries on the next check.

Settings: `REGISTRY_CA_BUNDLE` (internal CA, defaults to `GIT_SSL_CAINFO`), `REGISTRY_INSECURE_HOSTS`
(registries reached via plain http, comma separated).

## 🔐 Authentication

For demo purposes the authentication is diabled. You can enable it by setting the environment variable `ENABLE_AUTH` to `true`.

## 📁 Project Structure

```
.
├── src/                 # Core Python backend
├── lotse-ui/            # Angular frontend
├── k8s/                 # Kubernetes configurations
├── samples/             # Example projects
└── docker-compose.yml   # Local development setup
```

## 🧪 Sample Projects

The framework includes several example projects demonstrating different use cases:

- 📊 Plotly Dash

- 🖼️ Gradio

- 📈 Streamlit

- 🎨 NiceGUI

- 🐍 Hello world script

- 🌐 FastAPI web application

- ☕ Go binary with Gin framework

- 🎯 .NET Blazor binary

- 🐳 Custom container with entrypoint

## 👥 Contributing

We welcome contributions from the community! Please read our contribution guidelines before submitting a pull request.

> 🚧 **Note**: Detailed contribution guidelines coming soon!

## 📝 License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

> 📜 For more information, visit: [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

---

⭐ **Star this repo if you find it useful!**\
📣 **Issues and PRs welcome!**

_This project is under active development. Documentation will be updated as the project evolves._
