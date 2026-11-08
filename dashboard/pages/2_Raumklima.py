
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Raumklima | KICaGEM",
    page_icon="🌡️",
    layout="wide"
)


# ---------------------------------------------------------
# SENSOR CONFIGURATION
# ---------------------------------------------------------

SENSOR_CONFIG = {
    "temperature": {
        "label": "Temperatur",
        "icon": "🌡️",
        "unit": "°C",
        "measurement_label": "Gemessene Temperatur",
        "forecast_label": "Prognostizierte Temperatur",
    },
    "humidity": {
        "label": "Luftfeuchtigkeit",
        "icon": "💧",
        "unit": "%",
        "measurement_label": "Gemessene Luftfeuchtigkeit",
        "forecast_label": "Prognostizierte Luftfeuchtigkeit",
    },
    "co2": {
        "label": "CO₂-Konzentration",
        "icon": "🌫️",
        "unit": "ppm",
        "measurement_label": "Gemessene CO₂-Konzentration",
        "forecast_label": "Prognostizierte CO₂-Konzentration",
    },
    "light": {
        "label": "Lichtintensität",
        "icon": "💡",
        "unit": "Lux",
        "measurement_label": "Gemessene Lichtintensität",
        "forecast_label": "Prognostizierte Lichtintensität",
    },
}


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def to_dataframe(payload):
    if isinstance(payload, dict):
        return pd.DataFrame(payload.get("value", []))

    if isinstance(payload, list):
        return pd.DataFrame(payload)

    return pd.DataFrame()


def utc_range(days=7):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    return (
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds")
    )


def format_value(value, unit):
    if value is None or pd.isna(value):
        return "–"

    return f"{float(value):.2f} {unit}"


def get_sensor_options(room_info):
    """
    Returns sensor types available for the selected room.
    """

    available_sensors = room_info.get("available_sensors", [])

    if not isinstance(available_sensors, list):
        available_sensors = []

    return [
        sensor
        for sensor in available_sensors
        if sensor in SENSOR_CONFIG
    ]


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Raumklimaprognosen")

    st.divider()

    st.page_link("app.py", label="Gesamtübersicht", icon="🏠")
    st.page_link("pages/1_Wetter.py", label="Wetter", icon="🌤️")
    st.page_link("pages/3_Energie.py", label="Energie", icon="⚡")

    st.divider()

    if st.button("🔄 Aktualisieren", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("🌡️ Raumklimaprognosen")

st.markdown(
    """
    Analyse historischer Raumklimamesswerte und KI-gestützter Prognosen.

    Wähle einen Raum und eine Messgröße aus, um den bisherigen Verlauf
    und die prognostizierte Entwicklung zu untersuchen.
    """
)

st.divider()


# ---------------------------------------------------------
# LOAD ROOMS
# ---------------------------------------------------------

try:
    rooms_payload = api.get_rooms_with_forecasts()

except RuntimeError as exc:
    st.error(f"Räume konnten nicht geladen werden: {exc}")
    st.stop()


rooms = rooms_payload.get("value", [])

if not rooms:
    st.warning("Die API hat keine Räume zurückgegeben.")
    st.stop()


rooms_df = pd.DataFrame(rooms)

if "room_id" not in rooms_df.columns:
    st.error("Die Raumliste enthält kein Feld 'room_id'.")
    st.stop()


rooms_df["room_id"] = rooms_df["room_id"].astype(str)

available_rooms = rooms_df["room_id"].tolist()

selected_room = st.selectbox(
    "Raum auswählen",
    options=available_rooms
)

selected_room_info = rooms_df[
    rooms_df["room_id"] == selected_room
].iloc[0].to_dict()


# ---------------------------------------------------------
# ROOM STATUS
# ---------------------------------------------------------

status = selected_room_info.get("status", "unbekannt")
is_stale = bool(selected_room_info.get("is_stale", False))

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Raum", selected_room)

with col2:
    st.metric("Prognosestatus", status)

with col3:
    age = selected_room_info.get("data_age_hours")

    st.metric(
        "Datenalter",
        f"{float(age):.2f} Stunden" if age is not None else "–"
    )


if status == "no_forecast":
    st.warning(
        "Für diesen Raum existieren aktuell keine Prognosedaten."
    )

    comment = selected_room_info.get("comment")

    if comment:
        st.info(comment)

    st.stop()


if is_stale:
    st.warning(
        "Die Eingangsdaten dieser Prognose sind laut API veraltet."
    )


# ---------------------------------------------------------
# SENSOR SELECTION
# ---------------------------------------------------------

available_sensors = get_sensor_options(selected_room_info)

if not available_sensors:
    st.warning(
        "Für diesen Raum wurden keine unterstützten Prognose-Sensoren "
        "zurückgegeben. Bitte prüfe die verfügbaren Sensoren in der API."
    )
    st.stop()


selected_sensor = st.selectbox(
    "Messgröße auswählen",
    options=available_sensors,
    format_func=lambda sensor: (
        f"{SENSOR_CONFIG[sensor]['icon']} "
        f"{SENSOR_CONFIG[sensor]['label']}"
    )
)

sensor_config = SENSOR_CONFIG[selected_sensor]
sensor_label = sensor_config["label"]
sensor_unit = sensor_config["unit"]


st.caption(
    f"Ausgewählte Messgröße: **{sensor_label}** "
    f"({selected_sensor})"
)


# ---------------------------------------------------------
# FORECAST DATA
# ---------------------------------------------------------

try:
    forecast_payload = api.get_room_forecasts(
        room_id=selected_room,
        limit=1000,
        sensor_type=selected_sensor
    )

except RuntimeError as exc:
    st.error(f"Raumprognosen konnten nicht geladen werden: {exc}")
    st.stop()


forecast_df = to_dataframe(forecast_payload)

if forecast_df.empty:
    st.warning(
        f"Für {selected_room} liegen keine Prognosen für "
        f"{sensor_label} vor."
    )
    st.stop()


# Support for the previous temperature-only response format.
if (
    "predicted_value" not in forecast_df.columns
    and "predicted_temperature_c" in forecast_df.columns
):
    forecast_df["predicted_value"] = (
        forecast_df["predicted_temperature_c"]
    )


required_columns = {
    "forecast_timestamp",
    "forecast_origin",
    "predicted_value",
    "horizon_minutes",
}

missing_columns = required_columns - set(forecast_df.columns)

if missing_columns:
    st.error(
        "In der Prognoseantwort fehlen folgende Felder: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()


forecast_df["forecast_timestamp"] = pd.to_datetime(
    forecast_df["forecast_timestamp"],
    utc=True,
    errors="coerce"
)

forecast_df["forecast_origin"] = pd.to_datetime(
    forecast_df["forecast_origin"],
    utc=True,
    errors="coerce"
)

forecast_df["predicted_value"] = pd.to_numeric(
    forecast_df["predicted_value"],
    errors="coerce"
)

forecast_df["horizon_minutes"] = pd.to_numeric(
    forecast_df["horizon_minutes"],
    errors="coerce"
)

forecast_df = forecast_df.dropna(
    subset=[
        "forecast_timestamp",
        "predicted_value",
        "horizon_minutes",
    ]
)

if forecast_df.empty:
    st.warning(
        f"Die Prognose enthält keine gültigen Werte für {sensor_label}."
    )
    st.stop()


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

try:
    summary = api.get_room_forecast_summary(
        room_id=selected_room,
        sensor_type=selected_sensor
    )

except RuntimeError as exc:
    summary = {}
    st.warning(f"Prognosekennzahlen konnten nicht geladen werden: {exc}")


st.divider()
st.subheader(f"Prognosekennzahlen – {sensor_label}")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        f"Durchschnitt ({sensor_unit})",
        format_value(
            summary.get("average_value"),
            sensor_unit
        )
    )

with col2:
    st.metric(
        f"Minimum ({sensor_unit})",
        format_value(
            summary.get("minimum_value"),
            sensor_unit
        )
    )

with col3:
    st.metric(
        f"Maximum ({sensor_unit})",
        format_value(
            summary.get("maximum_value"),
            sensor_unit
        )
    )

with col4:
    st.metric(
        "Anzahl Prognosen",
        summary.get("forecast_count", len(forecast_df))
    )


# ---------------------------------------------------------
# HORIZON FILTER
# ---------------------------------------------------------

horizons = sorted(
    forecast_df["horizon_minutes"]
    .dropna()
    .astype(int)
    .unique()
    .tolist()
)

if not horizons:
    st.warning("Es wurden keine gültigen Prognosehorizonte gefunden.")
    st.stop()


selected_horizon = st.selectbox(
    "Prognosehorizont",
    options=horizons,
    format_func=lambda value: f"{value} Minuten"
)


selected_forecasts = forecast_df[
    forecast_df["horizon_minutes"] == selected_horizon
].copy()

selected_forecasts = selected_forecasts.sort_values(
    "forecast_timestamp"
)

if selected_forecasts.empty:
    st.warning("Für diesen Prognosehorizont liegen keine Daten vor.")
    st.stop()


# ---------------------------------------------------------
# HISTORICAL MEASUREMENTS
# ---------------------------------------------------------

start_datetime, end_datetime = utc_range(days=7)

try:
    measurements_payload = api.get_room_measurements(
        room_id=selected_room,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        sensor_type=selected_sensor
    )

    measurements_df = to_dataframe(measurements_payload)

except RuntimeError as exc:
    measurements_df = pd.DataFrame()

    st.warning(
        f"Historische Messwerte konnten nicht geladen werden: {exc}"
    )


# ---------------------------------------------------------
# PREPARE HISTORICAL DATA
# ---------------------------------------------------------

if not measurements_df.empty:
    required_measurement_columns = {
        "StartDateTime",
        "MeasureContent",
    }

    missing_measurement_columns = (
        required_measurement_columns - set(measurements_df.columns)
    )

    if missing_measurement_columns:
        st.warning(
            "Die historische Messwertantwort enthält nicht alle "
            "erforderlichen Felder: "
            + ", ".join(sorted(missing_measurement_columns))
        )
        measurements_df = pd.DataFrame()

    else:
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

        measurements_df = measurements_df.sort_values(
            "StartDateTime"
        )


# ---------------------------------------------------------
# CHART
# ---------------------------------------------------------

st.divider()
st.subheader(f"{sensor_label} – Messwerte und Prognose")

fig = go.Figure()


if not measurements_df.empty:
    fig.add_trace(
        go.Scatter(
            x=measurements_df["StartDateTime"],
            y=measurements_df["MeasureContent"],
            mode="lines",
            name=sensor_config["measurement_label"],
            line={"width": 2}
        )
    )


fig.add_trace(
    go.Scatter(
        x=selected_forecasts["forecast_timestamp"],
        y=selected_forecasts["predicted_value"],
        mode="lines+markers",
        name=sensor_config["forecast_label"],
        line={"width": 3, "dash": "dash"},
        marker={"size": 9}
    )
)


fig.update_layout(
    title=f"{sensor_label} – {selected_room}",
    xaxis_title="Zeitpunkt",
    yaxis_title=f"{sensor_label} ({sensor_unit})",
    hovermode="x unified",
    height=480,
    margin={"l": 20, "r": 20, "t": 60, "b": 20}
)


st.plotly_chart(fig, use_container_width=True)


if measurements_df.empty:
    st.info(
        f"Es liegen keine historischen {sensor_label}-Messwerte "
        "für den ausgewählten Zeitraum vor. "
        "Die Prognose wird trotzdem angezeigt."
    )


# ---------------------------------------------------------
# FORECAST TABLE
# ---------------------------------------------------------

st.divider()
st.subheader("Prognosedetails")


display_columns = [
    "room_id",
    "sensor_type",
    "forecast_origin",
    "forecast_timestamp",
    "horizon_minutes",
    "predicted_value",
    "unit",
    "model_type",
    "data_age_hours",
    "is_stale",
    "status",
]

available_columns = [
    column
    for column in display_columns
    if column in selected_forecasts.columns
]


display_df = selected_forecasts[available_columns].copy()

display_df = display_df.sort_values(
    "forecast_timestamp"
)


st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True
)


# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------

st.caption(
    "Quelle: KICaGEM Room Forecast- und Measurements-API. "
    "Prognosen werden anhand historischer Raumklimadaten erstellt."
)
