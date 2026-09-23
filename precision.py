name: Keep Streamlit App Awake

on:
  schedule:
    - cron: "0 */6 * * *"    # every 6 hours
  workflow_dispatch:          # manual trigger from the Actions tab

jobs:
  wake:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Playwright
        run: |
          pip install playwright
          playwright install chromium --with-deps

      - name: Wake the app
        env:
          STREAMLIT_URL: ${{ vars.STREAMLIT_URL }}
        run: python .github/scripts/wake_streamlit.py
