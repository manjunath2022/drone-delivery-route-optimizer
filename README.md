# Drone Delivery Route Optimizer

A Streamlit website for optimizing drone delivery routes. It geocodes locations
with OpenStreetMap, compares available drones against payload and range
assumptions, displays the selected route on an interactive map, and exports the
route as CSV.

## Run locally

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Deploy on Render's free plan

1. Put this project in a GitHub repository, including `app.py`, `requirements.txt`,
   `.python-version`, and `render.yaml`.
2. In Render, choose **New +** → **Blueprint** and connect that repository.
3. Render reads `render.yaml` and creates the web service on the free plan.
4. Choose **Apply** to build and deploy. Render provides the website URL when
   deployment completes.

The app uses OpenStreetMap's public Nominatim service to look up location
coordinates. Its public geocoding service is rate-limited, so location lookups
are spaced out; avoid repeatedly submitting the same large delivery list.

This is planning/demo software, not flight authorization. Verify regulatory,
airspace, weather, and battery-reserve requirements before any real operation.
