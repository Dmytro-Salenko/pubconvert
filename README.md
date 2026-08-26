# PubConvert

Convert Microsoft Publisher (.pub) files to **PDF**, **Word (.docx)**, or **SVG**.  
Free, no signup, no cloud services — runs entirely on your server.

---

## Quick Start with Docker

```bash
git clone git@github.com:YOUR_USERNAME/pubconvert.git
cd pubconvert
cp .env.example .env
docker compose up -d --build
```

Open **http://localhost:8080** in your browser.

---

## Local Development (without Docker)

> **Requires:** Python 3.11+, LibreOffice installed and `soffice` in PATH.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export MAX_UPLOAD_MB=25
export CONVERSION_TIMEOUT=120
export TMP_DIR=/tmp/pubconvert

uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000**.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | `25` | Maximum upload file size in MB |
| `CONVERSION_TIMEOUT` | `120` | LibreOffice conversion timeout in seconds |
| `COFFEE_URL` | *(empty)* | "Buy me a coffee" link. Leave empty to hide |
| `TMP_DIR` | `/tmp/pubconvert` | Temporary directory for conversion jobs |

All variables are set in `.env` (not committed to git).  
See `.env.example` for a template.

---

## How Conversion Works

| Format | Method |
|---|---|
| **PDF** | Direct: `soffice --convert-to pdf` via LibreOffice Draw |
| **SVG** | Direct: `soffice --convert-to svg` via LibreOffice Draw |
| **DOCX** | Two-step: PUB → PDF (Draw), then PDF → DOCX (Writer) |

> **Note:** DOCX conversion is best-effort. Publisher files use complex layouts
> that don't translate perfectly to Word format. PDF gives the highest fidelity.

Uploaded files are automatically deleted after **10 minutes**.

---

## Deploy to Google Compute Engine

### 1. Create a VM

In Google Cloud Console → Compute Engine → Create Instance:

- **Machine type:** `e2-medium` (2 vCPU, 4 GB RAM) or larger
- **Boot disk:** Ubuntu 22.04 LTS, 20 GB SSD
- **Firewall:** check ✅ "Allow HTTP traffic"
- **Networking → Network tags:** add `http-server`

### 2. SSH into the VM

```bash
gcloud compute ssh YOUR_INSTANCE_NAME --zone YOUR_ZONE
```

### 3. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

### 4. Clone and run

```bash
git clone git@github.com:YOUR_USERNAME/pubconvert.git
cd pubconvert
cp .env.example .env
nano .env   # set COFFEE_URL if needed

docker compose up -d --build
```

### 5. Open firewall for port 8080

If you didn't check "Allow HTTP traffic" during VM creation, create a firewall rule:

```bash
gcloud compute firewall-rules create allow-pubconvert \
    --direction=INGRESS \
    --action=ALLOW \
    --rules=tcp:8080 \
    --target-tags=http-server \
    --source-ranges=0.0.0.0/0
```

### 6. Access the app

Open `http://EXTERNAL_IP:8080` in your browser.

Find your external IP:
```bash
gcloud compute instances describe YOUR_INSTANCE_NAME \
    --zone YOUR_ZONE \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

### Auto-restart after reboot

Docker Compose `restart: unless-stopped` handles container restarts.  
To ensure Docker itself starts on boot:

```bash
sudo systemctl enable docker
```

---

## Production (later, with domain + HTTPS)

When you're ready for a domain, add a reverse proxy:

### Caddy (recommended, auto-HTTPS)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

`/etc/caddy/Caddyfile`:
```
pubconvert.example.com {
    reverse_proxy localhost:8080
}
```

```bash
sudo systemctl reload caddy
```

### Nginx (alternative)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/pubconvert`:
```nginx
server {
    listen 80;
    server_name pubconvert.example.com;
    client_max_body_size 30M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/pubconvert /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d pubconvert.example.com
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check → `{"status": "ok"}` |
| `GET` | `/api/config` | Public config for frontend |
| `POST` | `/api/convert` | Upload `.pub` + `format` (pdf/docx/svg) → download URL |
| `GET` | `/api/files/{job_id}/{filename}` | Download converted file |

---

## Tech Stack

- **Python 3.11** + **FastAPI**
- **LibreOffice** (headless) for conversion
- **Tailwind CSS** (CDN) for styling
- **Docker** — single container, non-root user

No database. No Redis. No external services.

---

## License

MIT
