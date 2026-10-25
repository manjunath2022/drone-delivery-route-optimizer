

import itertools
import math
import time
from io import StringIO

import folium
import pandas as pd
import requests
import streamlit as st
from folium.plugins import Fullscreen
from streamlit_folium import st_folium


# -----------------------------
# Built-in drone specifications
# -----------------------------
DEFAULT_DRONES = pd.DataFrame([
    {
        "Drone": "ARK 20",
        "Payload_kg": 8,
        "Range_km": 30,
        "Cruise_kmh": 72,
        "MTOW_kg": 25,
        "Battery_mAh": 30000,
        "Efficiency_pct": 5.0,
        "Altitude_m": 4000,
    },
    {
        "Drone": "ARK 40",
        "Payload_kg": 8,
        "Range_km": 30,
        "Cruise_kmh": 72,
        "MTOW_kg": 25,
        "Battery_mAh": 30000,
        "Efficiency_pct": 5.0,
        "Altitude_m": 4000,
    },
    {
        "Drone": "ARK 80",
        "Payload_kg": 30,
        "Range_km": 30,
        "Cruise_kmh": 90,
        "MTOW_kg": 120,
        "Battery_mAh": 80000,
        "Efficiency_pct": 1.6,
        "Altitude_m": 3300,
    },
    {
        "Drone": "Fengzhou 90",
        "Payload_kg": 20,
        "Range_km": 70,
        "Cruise_kmh": 108,
        "MTOW_kg": 96,
        "Battery_mAh": 120000,
        "Efficiency_pct": 0.83,
        "Altitude_m": None,
    },
    {
        "Drone": "ARK 150",
        "Payload_kg": 50,
        "Range_km": 20,
        "Cruise_kmh": 61.2,
        "MTOW_kg": 149,
        "Battery_mAh": 62000,
        "Efficiency_pct": 5.0,
        "Altitude_m": 4500,
    },
])


# -----------------------------
# Distance / route mathematics
# -----------------------------
def haversine_km(a, b):
    """Great-circle distance between (lat, lon) points."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def route_distance(order, points):
    return sum(
        haversine_km(points[order[i]], points[order[i + 1]])
        for i in range(len(order) - 1)
    )


def nearest_neighbor(points):
    """Return route indices starting and ending at depot index 0."""
    remaining = set(range(1, len(points)))
    route = [0]

    while remaining:
        current = route[-1]
        nxt = min(
            remaining,
            key=lambda j: haversine_km(points[current], points[j])
        )
        route.append(nxt)
        remaining.remove(nxt)

    route.append(0)
    return route


def two_opt(route, points):
    """Improve a route by reversing route sections."""
    improved = True
    best = route[:]

    while improved:
        improved = False
        best_distance = route_distance(best, points)

        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                d = route_distance(candidate, points)

                if d + 1e-9 < best_distance:
                    best = candidate
                    best_distance = d
                    improved = True
                    break

            if improved:
                break

    return best


def optimize_route(points):
    """
    Exact TSP for <= 9 delivery points.
    For larger jobs, use nearest-neighbour + 2-opt.
    """
    n = len(points)

    if n <= 10:
        delivery_indices = list(range(1, n))
        best = None
        best_d = float("inf")

        for perm in itertools.permutations(delivery_indices):
            route = [0] + list(perm) + [0]
            d = route_distance(route, points)

            if d < best_d:
                best_d = d
                best = route

        return best

    return two_opt(nearest_neighbor(points), points)


# -----------------------------
# OpenStreetMap geocoding
# -----------------------------
@st.cache_data(show_spinner=False)
def geocode_place(place):
    """
    Geocode a user-entered place using Nominatim.
    The application identifies itself with a custom User-Agent and spaces
    requests to respect the public service policy.
    """
    time.sleep(1.05)

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place,
        "format": "jsonv2",
        "limit": 1,
    }
    headers = {
        "User-Agent": "College-Drone-Delivery-Route-Optimizer/1.0"
    }

    response = requests.get(
        url, params=params, headers=headers, timeout=15
    )
    if response.status_code == 429:
        raise ValueError(
            "OpenStreetMap's geocoder is temporarily rate-limiting requests. "
            "Wait and try again, or provide Latitude and Longitude columns in "
            "your location CSV to skip geocoding."
        )
    response.raise_for_status()
    data = response.json()

    if not data:
        raise ValueError(f"Location not found: {place}")

    return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]


def parse_location_csv(uploaded_file):
    """
    Accepted columns:
      Name, Location, Payload_kg
      Latitude and Longitude are optional; supply both to skip geocoding.

    Example:
      Depot, Vellore, 0, 12.9165, 79.1325
      Hospital 1, Katpadi, 5, 12.9692, 79.1559
    """
    df = pd.read_csv(uploaded_file)

    required = {"Name", "Location"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Location CSV is missing columns: {', '.join(sorted(missing))}"
        )

    if "Payload_kg" not in df.columns:
        df["Payload_kg"] = 0.0

    coordinate_columns = {"Latitude", "Longitude"}
    present_coordinates = coordinate_columns.intersection(df.columns)
    if present_coordinates and present_coordinates != coordinate_columns:
        raise ValueError(
            "Location CSV must include both Latitude and Longitude columns."
        )

    columns = ["Name", "Location", "Payload_kg"]
    if present_coordinates:
        columns.extend(["Latitude", "Longitude"])

    return df[columns].copy()


def location_coordinates(row):
    latitude = row.get("Latitude")
    longitude = row.get("Longitude")

    latitude_missing = pd.isna(latitude) or str(latitude).strip() == ""
    longitude_missing = pd.isna(longitude) or str(longitude).strip() == ""

    if latitude_missing != longitude_missing:
        raise ValueError(
            f"Provide both Latitude and Longitude for {row['Name']}, or leave "
            "both blank to look up the location."
        )

    if not latitude_missing:
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Latitude and Longitude for {row['Name']} must be numbers."
            ) from exc

        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise ValueError(
                f"Coordinates for {row['Name']} are outside valid latitude/"
                "longitude ranges."
            )

        location = row.get("Location")
        if pd.isna(location) or not str(location).strip():
            location = f"{latitude}, {longitude}"
        return latitude, longitude, str(location), "Provided coordinates"

    location = row.get("Location")
    if pd.isna(location) or not str(location).strip():
        raise ValueError(
            f"Enter a Location or provide coordinates for {row['Name']}."
        )

    latitude, longitude, address = geocode_place(str(location).strip())
    return latitude, longitude, str(location).strip(), address


def parse_drone_csv(uploaded_file):
    """
    Required drone columns:
      Drone, Payload_kg, Range_km, Cruise_kmh

    Optional:
      MTOW_kg, Battery_mAh, Efficiency_pct, Altitude_m
    """
    df = pd.read_csv(uploaded_file)

    required = {"Drone", "Payload_kg", "Range_km", "Cruise_kmh"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Drone CSV is missing columns: {', '.join(sorted(missing))}"
        )

    for col in [
        "MTOW_kg",
        "Battery_mAh",
        "Efficiency_pct",
        "Altitude_m",
    ]:
        if col not in df.columns:
            df[col] = None

    return df


def make_map(route_df, route_distance_km, selected_drone):
    center_lat = route_df["Latitude"].mean()
    center_lon = route_df["Longitude"].mean()

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=6,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    Fullscreen().add_to(fmap)

    # Route line
    coords = route_df[["Latitude", "Longitude"]].values.tolist()

    folium.PolyLine(
        coords,
        weight=5,
        opacity=0.85,
        tooltip=f"Optimized drone route: {route_distance_km:.2f} km",
    ).add_to(fmap)

    for i, row in route_df.iterrows():
        is_depot = row["Stop"] == 0
        popup = (
            f"<b>{'DEPOT' if is_depot else 'DELIVERY'}</b><br>"
            f"{row['Name']}<br>"
            f"Stop: {row['Stop']}<br>"
            f"Payload: {row['Payload_kg']:.1f} kg"
        )

        folium.Marker(
            [row["Latitude"], row["Longitude"]],
            popup=popup,
            tooltip=row["Name"],
            icon=folium.Icon(
                icon="home" if is_depot else "send",
                prefix="glyphicon",
            ),
        ).add_to(fmap)

    folium.map.Marker(
        [center_lat, center_lon],
        icon=folium.DivIcon(
            html=(
                '<div style="font-size:12px; font-weight:bold; '
                'background:white; padding:3px;">'
                f"{selected_drone}</div>"
            )
        ),
    ).add_to(fmap)

    return fmap


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(
    page_title="Drone Delivery Route Optimizer",
    page_icon="🚁",
    layout="wide",
)

st.title("🚁 Drone Delivery Route Optimizer")
st.caption(
    "Multi-location delivery planning with drone selection, route optimization "
    "and an interactive OpenStreetMap world map."
)

st.warning(
    "Planning/demo software only. Real drone operations require aviation "
    "regulatory approval, airspace/no-fly-zone checks, weather and battery-reserve "
    "validation."
)

with st.sidebar:
    st.header("1. Drone data")

    drone_file = st.file_uploader(
        "Upload drone CSV (optional)",
        type=["csv"],
        key="drone_csv",
    )

    if drone_file:
        try:
            drones = parse_drone_csv(drone_file)
            st.success(f"Loaded {len(drones)} drone models.")
        except Exception as e:
            st.error(str(e))
            drones = DEFAULT_DRONES.copy()
    else:
        drones = DEFAULT_DRONES.copy()

    st.dataframe(drones, use_container_width=True, hide_index=True)

    st.header("2. Location data")

    location_file = st.file_uploader(
        "Upload delivery CSV (optional)",
        type=["csv"],
        key="location_csv",
    )

    st.header("3. Route assumptions")

    range_mode = st.radio(
        "Interpret drone range as",
        ["Total mission distance", "One-way distance"],
        index=0,
    )

    reserve_pct = st.slider(
        "Battery/range safety reserve (%)",
        min_value=0,
        max_value=50,
        value=20,
        step=5,
    )

    service_minutes = st.number_input(
        "Loading/unloading time per delivery (min)",
        min_value=0,
        max_value=120,
        value=5,
        step=1,
    )

    optimize_for = st.selectbox(
        "Choose best drone based on",
        ["Minimum total time", "Minimum distance"],
    )


if location_file:
    try:
        locations = parse_location_csv(location_file)
    except Exception as e:
        st.error(str(e))
        st.stop()
else:
    st.subheader("Enter delivery locations")

    default_text = """Name,Location,Payload_kg,Latitude,Longitude
Depot,Vellore,0,12.9165,79.1325
Delivery 1,Katpadi,5,12.9692,79.1559
Delivery 2,Sathuvachari,5,12.9255,79.1332
Delivery 3,Bagayam,8,12.8777,79.1328
Delivery 4,Virudhampet,5,12.9079,79.1328
"""

    location_text = st.text_area(
        "CSV format: Name,Location,Payload_kg,Latitude,Longitude "
        "(coordinates are optional; enter both to skip geocoding)",
        value=default_text,
        height=180,
    )

    try:
        locations = pd.read_csv(StringIO(location_text))
    except Exception as e:
        st.error(f"Invalid location CSV format: {e}")
        st.stop()

    if "Payload_kg" not in locations.columns:
        locations["Payload_kg"] = 0.0


st.subheader("Delivery locations")
st.dataframe(locations, use_container_width=True, hide_index=True)

if len(locations) < 2:
    st.info("Add at least one depot and one delivery location.")
    st.stop()

if st.button("🚀 Calculate Best Delivery Route", type="primary"):
    with st.spinner("Finding coordinates and optimizing the route..."):
        try:
            geocoded = []

            for _, row in locations.iterrows():
                lat, lon, location, display_name = location_coordinates(row)
                geocoded.append({
                    "Name": str(row["Name"]),
                    "Location": location,
                    "Payload_kg": float(row["Payload_kg"]),
                    "Latitude": lat,
                    "Longitude": lon,
                    "Address": display_name,
                })

            geo_df = pd.DataFrame(geocoded)

            points = list(
                zip(geo_df["Latitude"], geo_df["Longitude"])
            )

            route = optimize_route(points)
            ordered = geo_df.iloc[route].copy().reset_index(drop=True)

            ordered["Stop"] = range(len(ordered))
            ordered.loc[0, "Name"] = "DEPOT: " + ordered.loc[0, "Name"]
            ordered.loc[len(ordered) - 1, "Name"] = (
                "RETURN: " + ordered.loc[len(ordered) - 1, "Name"]
            )

            total_distance = route_distance(route, points)

            # Delivery payload: maximum simultaneously carried payload
            delivery_payloads = geo_df.iloc[1:]["Payload_kg"].sum()
            max_single_payload = geo_df.iloc[1:]["Payload_kg"].max()

            results = []

            for _, drone in drones.iterrows():
                capacity = float(drone["Payload_kg"])
                max_range = float(drone["Range_km"])
                speed = float(drone["Cruise_kmh"])

                payload_ok = (
                    max_single_payload <= capacity
                    and delivery_payloads <= capacity
                )

                effective_range = max_range * (1 - reserve_pct / 100)

                if range_mode == "Total mission distance":
                    range_ok = total_distance <= effective_range
                else:
                    # Each leg must fit within the usable one-way range.
                    range_ok = all(
                        haversine_km(points[route[i]], points[route[i + 1]])
                        <= effective_range
                        for i in range(len(route) - 1)
                    )

                flight_hours = total_distance / speed
                flight_minutes = flight_hours * 60
                total_time = flight_minutes + service_minutes * (len(geo_df) - 2)

                feasible = payload_ok and range_ok

                results.append({
                    "Drone": drone["Drone"],
                    "Payload capacity (kg)": capacity,
                    "Required payload (kg)": delivery_payloads,
                    "Route (km)": round(total_distance, 2),
                    "Usable range (km)": round(effective_range, 2),
                    "Cruise speed (km/h)": speed,
                    "Flight time (min)": round(flight_minutes, 2),
                    "Service time (min)": round(
                        service_minutes * (len(geo_df) - 2), 2
                    ),
                    "Total mission time (min)": round(total_time, 2),
                    "Payload OK": payload_ok,
                    "Range OK": range_ok,
                    "Feasible": feasible,
                })

            result_df = pd.DataFrame(results)
            feasible_df = result_df[result_df["Feasible"]].copy()

            if feasible_df.empty:
                st.error(
                    "No drone can complete this mission under the selected "
                    "payload, range and reserve assumptions."
                )
                st.dataframe(
                    result_df, use_container_width=True, hide_index=True
                )
                st.stop()

            if optimize_for == "Minimum total time":
                best = feasible_df.sort_values(
                    "Total mission time (min)"
                ).iloc[0]
            else:
                best = feasible_df.sort_values(
                    "Route (km)"
                ).iloc[0]

            st.session_state["route_df"] = ordered
            st.session_state["result_df"] = result_df
            st.session_state["best"] = best
            st.session_state["total_distance"] = total_distance

        except Exception as e:
            st.error(
                f"Could not calculate the route: {e}"
            )
            st.stop()


if "best" in st.session_state:
    best = st.session_state["best"]
    ordered = st.session_state["route_df"]
    result_df = st.session_state["result_df"]
    total_distance = st.session_state["total_distance"]

    st.success(
        f"BEST DRONE: {best['Drone']} | "
        f"Distance: {best['Route (km)']:.2f} km | "
        f"Total time: {best['Total mission time (min)']:.2f} min"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Best drone", best["Drone"])
    c2.metric("Route distance", f"{best['Route (km)']:.2f} km")
    c3.metric("Flight time", f"{best['Flight time (min)']:.2f} min")
    c4.metric("Total mission time", f"{best['Total mission time (min)']:.2f} min")

    st.subheader("🗺️ Optimized world map")

    fmap = make_map(
        ordered,
        total_distance,
        best["Drone"],
    )
    st_folium(
        fmap,
        use_container_width=True,
        height=650,
    )

    st.subheader("📊 Drone comparison")
    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("📍 Optimized delivery order")
    display_cols = [
        "Stop",
        "Name",
        "Location",
        "Payload_kg",
        "Latitude",
        "Longitude",
    ]
    st.dataframe(
        ordered[display_cols],
        use_container_width=True,
        hide_index=True,
    )

    csv_output = ordered[display_cols].to_csv(index=False)

    st.download_button(
        "⬇️ Download optimized route CSV",
        data=csv_output,
        file_name="optimized_drone_route.csv",
        mime="text/csv",
    )

    st.info(
        "The displayed map is an interactive OpenStreetMap map. "
        "The optimization uses geographic great-circle distance because "
        "drones are not restricted to road networks."
    )
