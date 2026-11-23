# Windows shop setup

1. Install Python 3.11+ from https://www.python.org/downloads/windows/. Select **Add Python to PATH**.
2. Open the extracted app folder in File Explorer.
3. In the folder address bar type `cmd` and press Enter.
4. Run:
   ```bat
   py -3 -m venv .venv
   .venv\Scripts\python -m pip install --upgrade pip
   .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501
   ```
5. On that PC visit http://localhost:8501.
6. For another device on the same shop Wi-Fi, run `ipconfig`, find the PC's IPv4 address, then visit `http://PC-IP:8501`.
7. Keep the command window open while staff use the local version.

Do not expose the shop PC directly to the internet. For remote access use a protected tunnel and enable authentication before production use.
