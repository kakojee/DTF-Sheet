# kakojee Print Nest — dual deployment

This branch adds deployment scaffolding around the existing Streamlit app. It does not change the packing algorithm or replace the production branch.

## Architecture

- **Online/cloud instance:** Linux VM running the app in Docker, published over HTTPS with Tailscale Funnel.
- **Shop instance:** Windows PC running the same app locally for shop use and local Wi-Fi.
- These are separate running instances. They do not share current uploads, generated outputs, sessions, or order history.

## Production defaults retained

- 23-inch roll width
- 89.9-inch maximum sheet length
- 0.5-inch spacing
- 300 DPI transparent PNG export
- Original artwork pixels/dimensions preserved; exact 90-degree rotation only

## A. Windows shop deployment

1. Install Python 3.11+ from https://www.python.org/downloads/windows/ and enable **Add Python to PATH**.
2. Download this branch as ZIP and extract it to a permanent folder such as `C:\kakojee\PrintNest`.
3. Double-click `setup_windows.bat` once.
4. Double-click `start_windows.bat` to run on the shop PC.
5. For devices on the same shop Wi-Fi, run `start_shop_wifi.bat`. Use `ipconfig` to find the PC's IPv4 address, then browse to `http://PC-IP:8501`. Allow Python through Windows Firewall on **Private networks only**.

Keep the PC switched on and the app's command window running while staff use the local version.

## B. Online/cloud deployment without buying a domain

The proposed free-tier cloud host is Oracle Cloud Infrastructure Always Free. Oracle currently lists an Ampere A1 allowance equivalent to up to 2 OCPUs and 12 GB memory per month, but Always Free capacity is only available in the account's home region and may be unavailable at a given time. Signup requires payment-card verification. Review Oracle's current terms and cost controls before provisioning. References:
- https://www.oracle.com/in/cloud/free/
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

Suggested VM: Ubuntu ARM64 on an Always Free eligible Ampere A1 shape. Do not select paid shapes, paid block volumes, paid IPs, or other non-Always-Free resources unless you have reviewed the price and intentionally accept it.

On the VM:
1. Install Docker Engine and the Docker Compose plugin using the official Docker instructions for Ubuntu: https://docs.docker.com/engine/install/ubuntu/
2. Copy this repository branch to the VM.
3. From the repository folder run `docker compose up -d --build`.
4. Check health/logs with `docker compose ps` and `docker compose logs -f printnest`.

The Compose file binds host port 8501 to **127.0.0.1 only**. Do not open port 8501 to the internet.

### Publish the cloud app with Tailscale Funnel

Tailscale Funnel provides a public HTTPS `*.ts.net` address without buying a domain. Its Personal plan is currently listed as free for individuals; Funnel is documented as beta, has bandwidth limits, and is subject to Tailscale's plan and product terms:
- https://tailscale.com/pricing
- https://tailscale.com/docs/features/tailscale-funnel

On the Ubuntu VM:
1. Install Tailscale using https://tailscale.com/download/linux and sign in to your Tailscale account.
2. Ensure MagicDNS and HTTPS certificates are enabled and Funnel is permitted in the tailnet policy.
3. Run `sudo tailscale funnel --bg --https=443 http://127.0.0.1:8501`.
4. Run `sudo tailscale funnel status` and note the generated `https://<machine>.<tailnet>.ts.net` URL.

Tailscale Funnel exposes the service to the public internet. The existing app has no login, so anyone who gets the URL can upload artwork and use it. Do not treat a hard-to-guess URL as authentication. Before using real customer artwork, add app authentication or use Tailscale Serve/private access for users who can sign in to your tailnet. Funnel also depends on the VM, Docker service, and network remaining up.

## C. Temporary public link from the Windows shop PC

For short tests only, install Cloudflare Tunnel on Windows and run `cloudflare_quick_tunnel_windows.bat` after the app starts. It creates a temporary `trycloudflare.com` URL that changes when restarted and has no uptime guarantee. Do not treat it as the permanent website.

## Important scope and limitations

- This branch uses the current repository app as-is. It is deployment scaffolding, not a fix to the gangsheet packing engine.
- Online and local instances are independent. Uploads, outputs and sessions are not synchronised.
- The app currently has no sign-in or persistent shared order history.
- This branch does not automatically configure an Oracle account, VM, Tailscale account, DNS, firewall or billing.
- Do not expose port 8501 directly to the public internet.
- Keep original PNGs and exported sheets in your own backup storage.
- Test PNG dimensions, copy counts, 0.5-inch spacing, sheet limits and cutting lanes before production.
