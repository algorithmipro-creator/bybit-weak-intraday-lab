# VPS deployment notes

Minimal VPS: 2 vCPU, 4 GB RAM, 80+ GB disk for short tests. For full-universe tick-level scans use more disk and RAM.

## Ubuntu quick setup

```bash
sudo apt update
sudo apt install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

## Deploy

```bash
git clone <your-repo-url> bybit-weak-intraday-lab
cd bybit-weak-intraday-lab
cp .env.example .env
docker compose up --build -d
```

Open for a private/dev deployment:

- UI: `http://SERVER_IP:8501`
- API: `http://SERVER_IP:8000/docs`

## Firewall

For a quick private test, expose only SSH and the Streamlit UI:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8501/tcp
sudo ufw enable
```

Avoid exposing port `8000` publicly unless it is protected. For production, put the UI/API behind Caddy or Nginx and restrict API access with authentication, IP allowlists, or a private network.

The backend includes basic request limits for scan range, full-universe scans and job id paths. These are safety rails for private use, not public authentication.

## Data hygiene

The archive cache can grow quickly. Keep it under `./data/bybit_archive_cache` and periodically remove old symbols/dates:

```bash
du -sh ./data/bybit_archive_cache
```
