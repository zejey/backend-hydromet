# Hydromet Backend Deployment Guide

This guide provides step-by-step instructions for deploying the Hydromet Backend in local and production-like environments.

---

## 🛠 Prerequisites

Ensure you have the following installed:
- **[Docker](https://www.docker.com/)** & **Docker Compose**
- **[Git](https://git-scm.com/)**
- **[Railway CLI](https://docs.railway.app/guides/cli)** (for cloud deployment)

---

## 🏠 Local Deployment (Docker)

Local deployment uses Docker Compose to orchestrate the FastAPI application and a PostgreSQL database.

### 1. Configure Environment Variables
Create a `.env` file in the root directory:
```env
OPENWEATHER_API_KEY=your_openweather_key_here
SEMAPHORE_API_KEY=your_semaphore_key_here
BREVO_API_KEY=your_brevo_key_here
BREVO_SENDER=your_sender_email@example.com
```

### 2. Launch the Application
Run the following command to build and start the services:
```bash
docker compose up -d --build
```
The API will be available at [http://localhost:8000].

### 3. Initialize the Database (Seeding)
Once the containers are running, populate the database with initial data (Admin, Barangays, Hotlines):
```bash
docker compose run --rm seed
```

### 4. Train ML Models
The application requires trained models in the `models/` directory. If they are missing, run:
```bash
docker compose exec app python app/scripts/train_multi_models.py --csv app/data/training_data.csv
```

---

## 🚂 Railway Deployment (Cloud)

Railway is recommended for its seamless PostgreSQL integration and support for Docker-based builds.

### 1. Setup Database
1. Go to your [Railway Dashboard](https://railway.app/).
2. Click **New Project** -> **Provision PostgreSQL**.
3. Railway will automatically inject `PGHOST`, `PGUSER`, `PGPASSWORD`, etc., which the application will use.

### 2. Configure Environment Variables
In the **Variables** tab of your Railway service, add:
- `OPENWEATHER_API_KEY`
- `SEMAPHORE_API_KEY`
- `ENVIRONMENT=production`
- *Any other variables listed in the Reference Table below.*

### 3. Persistent Storage (Important)
Since ML models are saved to the filesystem, they will be lost on re-deployment unless you mount a volume.
1. In Railway, go to the **Settings** tab of your service.
2. Under **Volumes**, click **Add Volume**.
3. Set the Mount Path to `/app/models`.

### 4. Deploy
You can deploy by connecting your GitHub repository or using the CLI:
```bash
railway up
```

### 5. Running Seeding on Railway
To initialize the database on Railway, run the seeding script via the Railway CLI or as a one-off job:
```bash
railway run python scripts/seed_data.py
```

---

## 📋 Environment Variable Reference

| Variable | Required | Description |
| :--- | :--- | :--- |
| `OPENWEATHER_API_KEY` | **Yes** | API Key for weather data collection. |
| `DB_HOST` / `PGHOST` | **Yes** | Database host address. |
| `DB_NAME` / `PGDATABASE` | **Yes** | Database name. |
| `DB_USER` / `PGUSER` | **Yes** | Database username. |
| `DB_PASSWORD` / `PGPASSWORD` | **Yes** | Database password. |
| `SEMAPHORE_API_KEY` | No | API Key for SMS notifications. |
| `BREVO_API_KEY` | No | API Key for Email notifications. |
| `ENVIRONMENT` | No | `development` or `production`. |
| `FORECAST_RUNNER_ENABLED` | No | Set to `true` to enable background hazard monitoring. |

---

## 🔍 Troubleshooting

> [!TIP]
> **Database Connection Issues**: Ensure your database container is healthy before the app starts. Docker Compose handles this via the `condition: service_healthy` check.

> [!WARNING]
> **Missing Models**: If the `/health` endpoint reports `ml_model_ready: false`, ensure the `models/` volume is correctly mounted and training has been completed.
