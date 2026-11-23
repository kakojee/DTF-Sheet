# Deployment checklist

1. Back up the currently deployed `app.py` in GitHub or keep the previous commit available for rollback.
2. Extract this ZIP and upload the `app.py` inside `kakojee_Print_Nest` to the root of the existing GitHub repository, replacing the existing root-level `app.py`.
3. Keep the existing repository and Streamlit app URL. The supplied `.streamlit/config.toml` can replace the existing one if desired; keep `requirements.txt` unless your repository has additional dependencies.
4. Commit the update and wait for Streamlit Community Cloud to redeploy.
5. Test with a small order first, then the 31-design / 130-copy order. Verify every copy count, transparency, spacing and sheet length before production.
6. If the app fails to start, use Streamlit app logs and revert the `app.py` commit.
