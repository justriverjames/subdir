# SubDir Deployment Guide

Simple guide for deploying SubDir to a VPS.

---

## Local Development

```bash
# Terminal 1: API
cd api
npm install
npm start

# Terminal 2: Web UI
cd web
npm install
npm start

# Access
# Web UI: http://localhost:7734
# API: http://localhost:7733
```

---

## VPS Deployment (e.g., neptune.hammond.im)

### Prerequisites

- VPS with Node.js 16+ installed
- Domain pointed to VPS (e.g., subdir.hammond.im)
- Optional: Cloudflare for CDN/caching

### Step 1: Install Node.js (if not installed)

```bash
# SSH into VPS
ssh user@your-vps

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify
node --version
npm --version
```

### Step 2: Clone Repository

```bash
cd /opt
sudo git clone https://github.com/martiantux/subdir.git
cd subdir
sudo chown -R $USER:$USER .
```

### Step 3: Install Dependencies

```bash
# API
cd /opt/subdir/api
npm install

# Web UI
cd /opt/subdir/web
npm install
```

### Step 4: Setup PM2 (Process Manager)

```bash
# Install PM2
sudo npm install -g pm2

# Start API
cd /opt/subdir/api
pm2 start server.js --name subdir-api

# Start Web UI
cd /opt/subdir/web
pm2 start server.js --name subdir-web

# Save PM2 config
pm2 save

# Setup PM2 to start on boot
pm2 startup
# Follow the command it outputs
```

### Step 5: Setup Nginx Reverse Proxy

```bash
# Install Nginx
sudo apt install nginx -y

# Create config
sudo nano /etc/nginx/sites-available/subdir
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name subdir.hammond.im;  # Change to your domain

    # Web UI
    location / {
        proxy_pass http://localhost:7734;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # API
    location /api/ {
        proxy_pass http://localhost:7733;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Cache API responses
        add_header Cache-Control "public, max-age=3600";
    }
}
```

Enable and start:

```bash
sudo ln -s /etc/nginx/sites-available/subdir /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 6: Setup SSL (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d subdir.hammond.im
```

### Step 7: Setup Cloudflare (Optional)

1. Add DNS A record: `subdir` → `your-vps-ip`
2. Enable proxy (orange cloud)
3. SSL/TLS mode: Full (strict)
4. Page Rule for `/api/*`: Cache Everything, Edge TTL 1 hour

---

## Updating Data

To update subreddit metadata:

```bash
cd /opt/subdir/scanner

# First time only
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with Reddit credentials

# Run scanner
python main.py --metadata
python main.py --threads

# Restart API (picks up new database)
pm2 restart subdir-api
```

### Automate with Cron

```bash
crontab -e
```

Add:
```
# Update weekly (Sundays at 2 AM)
0 2 * * 0 cd /opt/subdir/scanner && source venv/bin/activate && python main.py --metadata && python main.py --threads && pm2 restart subdir-api
```

---

## Monitoring

### Check Services

```bash
# PM2 status
pm2 status
pm2 logs subdir-api
pm2 logs subdir-web

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Restart if needed
pm2 restart subdir-api
pm2 restart subdir-web
```

### Database

```bash
# Check size
du -h /opt/subdir/data/subreddit_scanner.db

# Backup
cp /opt/subdir/data/subreddit_scanner.db /opt/subdir/backups/db_$(date +%Y%m%d).db
```

---

## Troubleshooting

### API not responding
```bash
pm2 logs subdir-api
pm2 restart subdir-api
```

### Web UI not loading
```bash
pm2 logs subdir-web
pm2 restart subdir-web
```

### Nginx errors
```bash
sudo nginx -t
sudo systemctl status nginx
sudo systemctl restart nginx
```

### Port already in use
```bash
# Find process using port
sudo lsof -i :7733
sudo lsof -i :7734

# Kill if needed
pm2 stop all
pm2 start all
```

---

## Security

### Firewall

```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### Updates

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Update Node.js packages
cd /opt/subdir/api && npm update
cd /opt/subdir/web && npm update
pm2 restart all
```

---

## Cost

**Minimal VPS:**
- Hetzner CPX11: €4.51/month (~$5) - 2GB RAM, 40GB storage
- DigitalOcean Basic: $6/month - 1GB RAM, 25GB storage
- Vultr Regular: $6/month - 1GB RAM, 25GB storage

**Additional:**
- Domain: ~$10-15/year
- Cloudflare: Free

**Total: ~$5-6/month**

---

## Done!

Your SubDir instance is now running at:
- Web UI: https://subdir.hammond.im
- API: https://subdir.hammond.im/api/health

Next: Announce on r/selfhosted and r/datahoarder!
