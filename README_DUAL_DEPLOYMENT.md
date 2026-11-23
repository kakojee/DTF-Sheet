# kakojee Print Nest — dual deployment

This branch adds deployment scaffolding around the existing Streamlit app. It does not change the packing algorithm or replace the production branch.

## Production defaults retained
- 23-inch roll width
- 89.9-inch maximum sheet length
- 0.5-inch spacing
- 300 DPI transparent PNG export
- Original artwork pixels/dimensions preserved; exact 90-degree rotation only

## Windows shop deployment
1. Install Python 3.11+ from https://www.python.org/downloads/windows/ and enable **Add Python to PATH**.
2. Download this branch as ZIP and extract it to a permanent folder such as `C:\kakojee\PrintNest`.
3. Open Command Prompt in that folder and run:
   `py -3 -m venv .venv`
   `.venv\Scripts\python -m pip install --upgrade pip`
   `.venv\Scripts\pip install -r requirements.txt`
4. Run `.venv\Scripts\python -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501`.
5. On the shop PC open http://localhost:8501. Other devices on the same Wi-Fi can use http://SHOP-PC-IP:8501. Use `ipconfig` to find the PC IPv4 address. Allow Python on Private networks only in Windows Firewall.

## Temporary access from anywhere without a domain
Cloudflare Quick Tunnel can provide a temporary public HTTPS address:
1. Start the app locally.
2. Install cloudflared using https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/.
3. Run `cloudflared tunnel --url http://localhost:8501`.
4. Use the generated `https://...trycloudflare.com` URL. It changes when restarted and is intended for testing, not a stable permanent production address.

Important: the app currently has no sign-in. Anyone who obtains the URL can use it. Do not expose sensitive artwork or customer files through an open public link unless you accept that access model. For sustained use, add authentication or put it behind a protected access layer.

## Cloud VM deployment
A Linux cloud VM can run this app in Docker:
`docker compose up -d --build`
Check logs with:
`docker compose logs -f printnest`

The Streamlit service listens on port 8501 inside the container. Do not expose that port directly to the public internet. Put it behind HTTPS and an access-control layer.

Oracle Cloud Always Free capacity is subject to region/account availability and free-tier terms; signup and verification are required and capacity is not guaranteed. Review account billing and do not enable paid resources without checking pricing first.

## Important scope and limitations
- Online and local deployments are separate instances. Uploads, sessions and generated files are not synchronised.
- The app currently does not have persistent shared order history or staff logins.
- This branch uses the current repository app as-is. It is deployment scaffolding, not a fix to the gangsheet packing engine.
- Test PNG dimensions, copy counts, spacing and cut lanes before production.
