# Deploy Agilink as a hosted link (client just opens a URL)

Goal: a URL like `https://agilink-demo.yourdomain.com` you send to the client.
They open it in any browser — **no install, no key, no Docker, nothing** — and
can even "Install" it as an app (icon on desktop/phone) because it's a PWA. The
OpenRouter key lives on the **server**, so the client never touches it.

There are two ways. Pick one.

---

## Option A — Persistent hosting (recommended for a real demo)

A small always-on server + a domain. ~15 minutes, ~$4–6/month.

1. **Get a VM.** Any provider: Hetzner (cheapest), DigitalOcean, Vultr, etc.
   Ubuntu 22.04+, 2 GB RAM min (4 GB comfortable). Note its public IP.

2. **Point a domain at it.** In your DNS, add an `A` record:
   `agilink-demo.yourdomain.com → <server IP>`. (Any subdomain you own.)

3. **Put the code on the server** (either is fine):
   - `git clone <your repo>` and `cd` into it, **or**
   - copy the folder up with `scp -r ./ocr_agilink user@IP:~/agilink`

4. **Configure + deploy** (on the server, from the repo root):
   ```bash
   cp deploy/env.prod .env
   nano .env          # set DOMAIN, VLLM_API_KEY, CHAT_API_KEY, passwords
   bash deploy/deploy.sh
   ```
   Docker installs itself if missing, HTTPS is issued automatically by Caddy.

5. **Send the client:** `https://agilink-demo.yourdomain.com`
   On first visit they can click the browser's **Install** icon to get a desktop/
   phone app icon. Done.

Update later: `git pull && docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build`

---

## Option B — Instant link, no server (for a quick "try it now" test)

Expose the stack already running on **your** machine to a temporary public URL
with a free tunnel. Good when you just want the client to try it while you're
around. The link dies when you stop the tunnel / your machine.

1. Make sure the app is up locally (`docker compose up -d`) → it's on `:3000`.
2. Install the tunnel once and run it:
   ```bash
   # Cloudflare (no account needed for a quick URL):
   #   Linux:  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared && chmod +x cloudflared
   ./cloudflared tunnel --url http://localhost:3000
   ```
   It prints a public `https://<random>.trycloudflare.com` URL — send that.
   (`ngrok http 3000` works the same if you prefer ngrok.)

⚠️ This exposes whatever data is in your local instance to anyone with the URL.
For a client test, **start from a clean instance** (`docker compose down -v && docker compose up -d`) so they see an empty app to load their own fiches into.

---

## Notes
- The client needs **nothing** installed — just the link (Option A) or the
  temporary link (Option B). No API key, no Git, no Docker on their side.
- Costs: hosting (Option A) + OpenRouter usage (both) are billed to **you**,
  since the key is server-side. Set an OpenRouter spend limit if you want a cap.
- To restrict who can open it, put a simple password on Caddy (basicauth) — ask
  and I'll add it.
