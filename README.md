# Weather Insights

A Flask web app that combines my two weather projects in one place. Users create an account,
then:

- **Compare two cities:** enter any two city names and a time range (1-5 years) to get a
  side-by-side table (average highs and lows, extremes, rainy days, total rain, wind),
  plain-English takeaways, temperature and rainfall charts, and a CSV download.
- **Predict next-day high temperature:** enter a city and 2-5 years of history. The app trains
  Linear Regression and Random Forest models with a time-based train/test split, compares them
  with two baselines ("same as today" and "monthly average"), and shows the error metrics,
  predicted vs. actual chart, feature importance, and a next-day prediction.

Every comparison and prediction run is saved to the user's account in a SQLite database.

## Tech
Python, Flask, SQLite, pandas, scikit-learn, matplotlib, requests, gunicorn, Docker,
GitHub Actions. Weather data from the free Open-Meteo geocoding and historical weather APIs.

## Features
- Register / log in / log out with hashed passwords, sessions and CSRF protection
- Users can only see, download or delete their own saved results
- Clear error messages for unknown cities, invalid inputs and weather-service outages
- 21 automated tests; the weather API is replaced by a fake in tests, so CI never needs the
  network

## Run locally
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000, create an account, and try "San Jose" vs. "Seattle".

## Tests and lint
```
pip install -r requirements-dev.txt
flake8 .
pytest
```

## CI/CD pipeline (.github/workflows/ci.yml)
| Job | Runs on | What it does |
|---|---|---|
| **test** | every push and pull request | flake8 and pytest on Python 3.11 and 3.12 |
| **docker** | after tests pass | builds the Docker image, starts it, and checks `/health` |
| **deploy** | pushes to `main`, after the other jobs pass | calls the Render deploy hook |

## Deploy on Render
1. Push this folder to GitHub.
2. On render.com, create a Web Service from the repo with Runtime set to **Docker**.
3. Add environment variables `SECRET_KEY` (a long random string) and `COOKIE_SECURE=1`.
4. Add a persistent disk mounted at `/app/instance` so the database survives restarts.
5. Copy the service's Deploy Hook URL into a GitHub Actions secret named
   `RENDER_DEPLOY_HOOK_URL`. Every push to `main` that passes the tests then deploys.

## Limitations
- City search uses the top Open-Meteo match, so ambiguous names may pick a different city
  (the page always shows which one it used)
- The archive runs about a week behind, so the "next-day" prediction is for the day after the
  most recent available data
- Open-Meteo values are modeled grid data, not official station records
- SQLite suits a demo; Postgres would be the next step for many users

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0).
