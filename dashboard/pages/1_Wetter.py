from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Wetterprognosen | KICaGEM",
    page_icon="🌤️",
    layout="wide"
)


SENSOR_LABELS = {
    "temperature": "Temperatur",
    "humidity": "Luftfeuchtigkeit",
    "barometric_pressure": "Luftdruck",
    "wind_speed": "Windgeschwindigkeit",
    "wind_direction": "Windrichtung",
    "rainfall": "Niederschlag",
}

UNIT_LABELS = {
    "temperature": "°C",
    "humidity": "%",
    "barometric_pressure": "hPa",
    "wind_speed": "m/s",
    "wind_direction": "°",
    "rainfall": "mm",
}


def to_dataframe(payload):
    if isinstance(payload, dict):
        records = payload.get("value", [])
    elif isinstance(payload, list):
        records = payload
    else:
        records = []

    return pd.DataFrame(records)


def utc_range(days=7):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    return (
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds")
    )


def format_value(value, unit):
    if pd.isna(value):
        return "–"

    return f"{float(value):.2f} {unit}"


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Wetterprognosen")

    st.divider()

    st.page_link("app.py", label="Gesamtübersicht", icon="🏠")
    st.page_link("pages/2_Raumklima.py", label="Raumklima", icon="🌡️")
    st.page_link("pages/3_Energie.py", label="Energie", icon="⚡")

    st.divider()

    if st.button("🔄 Aktualisieren", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("🌤️ Wetterprognosen")

st.markdown(
    "Analyse der Wetterprognosen für die verfügbaren Gebäude "
    "und Wetterstationen."
)

st.divider()


# ---------------------------------------------------------
# WEATHER STATIONS
# ---------------------------------------------------------

try:
    stations = api.get_weather_stations()

except RuntimeError as exc:
    st.error(f"Wetterstationen konnten nicht geladen werden: {exc}")
    st.stop()


if not isinstance(stations, list) or not stations:
    st.warning("Aktuell sind keine Wetterprognose-Stationen verfügbar.")
    st.stop()


station_ids = [
    station["BuildingID"]
    for station in stations
    if isinstance(station, dict) and station.get("BuildingID")
]

if not station_ids:
    st.warning("Die API hat keine gültigen Gebäude-IDs geliefert.")
    st.stop()


selected_building = st.selectbox(
    "Gebäude / Wetterstation",
    options=station_ids
)

station_info = next(
    (
        station for station in stations
        if station.get("BuildingID") == selected_building
    ),
    {}
)


# ---------------------------------------------------------
# FORECAST DATA
# ---------------------------------------------------------

try:
    forecast_payload = api.get_latest_weather_forecasts(
        selected_building
    )

except RuntimeError as exc:
    st.error(f"Wetterprognosen konnten nicht geladen werden: {exc}")
    st.stop()


forecast_df = to_dataframe(forecast_payload)

if forecast_df.empty:
    st.warning(
        f"Für Gebäude {selected_building} sind keine Prognosen vorhanden."
    )
    st.stop()


required_columns = {
    "SensorTypeCode",
    "ForecastDateTime",
    "ForecastOrigin",
    "HorizonMinutes",
    "PredictedValue",
}

missing_columns = required_columns - set(forecast_df.columns)

if missing_columns:
    st.error(
        "Die API-Antwort enthält nicht alle erwarteten Felder: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()


forecast_df["ForecastDateTime"] = pd.to_datetime(
    forecast_df["ForecastDateTime"],
    utc=True,
    errors="coerce"
)

forecast_df["ForecastOrigin"] = pd.to_datetime(
    forecast_df["ForecastOrigin"],
    utc=True,
    errors="coerce"
)

forecast_df["PredictedValue"] = pd.to_numeric(
    forecast_df["PredictedValue"],
    errors="coerce"
)

forecast_df["HorizonMinutes"] = pd.to_numeric(
    forecast_df["HorizonMinutes"],
    errors="coerce"
)

forecast_df = forecast_df.dropna(
    subset=["ForecastDateTime", "PredictedValue"]
)


# ---------------------------------------------------------
# FILTER
# ---------------------------------------------------------

available_sensors = [
    sensor for sensor in SENSOR_LABELS
    if sensor in forecast_df["SensorTypeCode"].unique()
]

if not available_sensors:
    st.warning("Keine bekannten Wetter-Sensortypen vorhanden.")
    st.stop()


col1, col2 = st.columns(2)

with col1:
    selected_sensor = st.selectbox(
        "Messgröße",
        options=available_sensors,
        format_func=lambda value: SENSOR_LABELS[value]
    )

with col2:
    available_horizons = sorted(
        forecast_df.loc[
            forecast_df["SensorTypeCode"] == selected_sensor,
            "HorizonMinutes"
        ].dropna().astype(int).unique().tolist()
    )

    selected_horizon = st.selectbox(
        "Prognosehorizont",
        options=available_horizons,
        format_func=lambda value: f"{value} Minuten"
    )


filtered_forecasts = forecast_df[
    (forecast_df["SensorTypeCode"] == selected_sensor)
    & (forecast_df["HorizonMinutes"] == selected_horizon)
].copy()

filtered_forecasts = filtered_forecasts.sort_values(
    "ForecastDateTime"
)

if filtered_forecasts.empty:
    st.warning("Für diese Auswahl liegen keine Prognosen vor.")
    st.stop()


latest_forecast = filtered_forecasts.iloc[-1]

unit = latest_forecast.get("MeasureUnitCode")
if not unit:
    unit = UNIT_LABELS.get(selected_sensor, "")


# ---------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------

st.divider()
st.subheader("Aktuelle Prognose")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Prognostizierter Wert",
        format_value(latest_forecast["PredictedValue"], unit)
    )

with col2:
    st.metric(
        "Prognosehorizont",
        f"{selected_horizon} Minuten"
    )

with col3:
    st.metric(
        "Datenalter",
        f'{float(latest_forecast.get("DataAgeHours", 0)):.2f} h'
    )

with col4:
    is_stale = bool(latest_forecast.get("IsStale", False))

    st.metric(
        "Datenstatus",
        "Veraltet" if is_stale else "Aktuell"
    )


if is_stale:
    st.warning(
        "Die Prognose basiert auf veralteten Eingangsdaten. "
        "Bitte beachte das Datenalter bei der Interpretation."
    )
else:
    st.success("Die Prognose ist laut API nicht als veraltet markiert.")


# ---------------------------------------------------------
# ACTUAL MEASUREMENTS
# ---------------------------------------------------------

st.divider()
st.subheader("Messwerte und Prognoseverlauf")

start_datetime, end_datetime = utc_range(days=7)

try:
    measurements_payload = api.get_weather_measurements(
        building_id=selected_building,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        sensor_type=selected_sensor
    )

    measurements_df = to_dataframe(measurements_payload)

except RuntimeError as exc:
    measurements_df = pd.DataFrame()
    st.warning(f"Historische Messwerte konnten nicht geladen werden: {exc}")


fig = go.Figure()

if not measurements_df.empty:
    measurements_df["StartDateTime"] = pd.to_datetime(
        measurements_df["StartDateTime"],
        utc=True,
        errors="coerce"
    )

    measurements_df["MeasureContent"] = pd.to_numeric(
        measurements_df["MeasureContent"],
        errors="coerce"
    )

    measurements_df = measurements_df.dropna(
        subset=["StartDateTime", "MeasureContent"]
    )

    if not measurements_df.empty:
        fig.add_trace(
            go.Scatter(
                x=measurements_df["StartDateTime"],
                y=measurements_df["MeasureContent"],
                mode="lines",
                name="Historische Messwerte",
                line={"width": 2}
            )
        )


fig.add_trace(
    go.Scatter(
        x=filtered_forecasts["ForecastDateTime"],
        y=filtered_forecasts["PredictedValue"],
        mode="lines+markers",
        name="Prognose",
        line={"width": 3, "dash": "dash"},
        marker={"size": 9}
    )
)

fig.update_layout(
    title=(
        f"{SENSOR_LABELS[selected_sensor]} – "
        f"Gebäude {selected_building}"
    ),
    xaxis_title="Zeitpunkt",
    yaxis_title=f"Wert ({unit})" if unit else "Wert",
    hovermode="x unified",
    legend_title="Datenreihe",
    height=480,
    margin={"l": 20, "r": 20, "t": 60, "b": 20}
)

st.plotly_chart(fig, use_container_width=True)


if measurements_df.empty:
    st.info(
        "Für den ausgewählten Zeitraum wurden keine historischen "
        "Messwerte zurückgegeben. Die Prognose wird trotzdem angezeigt."
    )


# ---------------------------------------------------------
# FORECAST TABLE
# ---------------------------------------------------------

st.divider()
st.subheader("Verfügbare Wetterprognosen")

display_columns = [
    "SensorTypeCode",
    "ForecastOrigin",
    "ForecastDateTime",
    "HorizonMinutes",
    "PredictedValue",
    "MeasureUnitCode",
    "DataAgeHours",
    "IsStale",
]

available_columns = [
    column for column in display_columns
    if column in forecast_df.columns
]

table_df = forecast_df[available_columns].copy()

table_df["SensorTypeCode"] = table_df["SensorTypeCode"].map(
    lambda value: SENSOR_LABELS.get(value, value)
)

st.dataframe(
    table_df.sort_values(
        ["SensorTypeCode", "HorizonMinutes"]
    ),
    use_container_width=True,
    hide_index=True
)

st.caption(
    "Quelle: KICaGEM Forecast- und WeatherMeasurements-API."
)