# Drone Delivery Route Optimizer

A Streamlit website for optimizing drone delivery routes. It looks up city and
place names with Open-Meteo, compares available drones against payload and range
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

Edit the `Location` values in the sample CSV to use your own cities and towns,
such as `Chennai`, `Bengaluru`, or `Avadi`. Add a country if a place name is
ambiguous. Location names are looked up with Open-Meteo. Alternatively,
location CSVs can include both `Latitude` and `Longitude` columns to skip
place-name lookup.

This is planning/demo software, not flight authorization. Verify regulatory,
airspace, weather, and battery-reserve requirements before any real operation.
