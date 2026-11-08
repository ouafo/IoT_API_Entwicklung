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
    "Analyse der prognostizierten Raumtemperaturen "
    "und der historischen Messwerte."
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
# FORECAST DATA
# ---------------------------------------------------------

try:
    forecast_payload = api.get_room_forecasts(
        selected_room,
        limit=1000
    )

except RuntimeError as exc:
    st.error(f"Raumprognosen konnten nicht geladen werden: {exc}")
    st.stop()


forecast_df = to_dataframe(forecast_payload)

if forecast_df.empty:
    st.warning("Für diesen Raum sind keine Prognosen vorhanden.")
    st.stop()


required_columns = {
    "forecast_timestamp",
    "forecast_origin",
    "predicted_temperature_c",
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

forecast_df["predicted_temperature_c"] = pd.to_numeric(
    forecast_df["predicted_temperature_c"],
    errors="coerce"
)

forecast_df["horizon_minutes"] = pd.to_numeric(
    forecast_df["horizon_minutes"],
    errors="coerce"
)

forecast_df = forecast_df.dropna(
    subset=[
        "forecast_timestamp",
        "predicted_temperature_c"
    ]
)

if forecast_df.empty:
    st.warning("Die Prognose enthält keine gültigen Temperaturwerte.")
    st.stop()


# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

try:
    summary = api.get_room_forecast_summary(selected_room)

except RuntimeError:
    summary = {}


st.divider()
st.subheader("Prognosekennzahlen")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Durchschnittstemperatur",
        (
            f'{summary["average_temperature_c"]:.2f} °C'
            if summary.get("average_temperature_c") is not None
            else "–"
        )
    )

with col2:
    st.metric(
        "Minimale Temperatur",
        (
            f'{summary["minimum_temperature_c"]:.2f} °C'
            if summary.get("minimum_temperature_c") is not None
            else "–"
        )
    )

with col3:
    st.metric(
        "Maximale Temperatur",
        (
            f'{summary["maximum_temperature_c"]:.2f} °C'
            if summary.get("maximum_temperature_c") is not None
            else "–"
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


# ---------------------------------------------------------
# HISTORICAL MEASUREMENTS
# ---------------------------------------------------------

start_datetime, end_datetime = utc_range(days=7)

try:
    measurements_payload = api.get_room_measurements(
        room_id=selected_room,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        sensor_type="temperature"
    )

    measurements_df = to_dataframe(measurements_payload)

except RuntimeError as exc:
    measurements_df = pd.DataFrame()
    st.warning(f"Historische Messwerte konnten nicht geladen werden: {exc}")


# ---------------------------------------------------------
# CHART
# ---------------------------------------------------------

st.divider()
st.subheader("Temperaturverlauf")

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
                name="Gemessene Temperatur",
                line={"width": 2}
            )
        )


fig.add_trace(
    go.Scatter(
        x=selected_forecasts["forecast_timestamp"],
        y=selected_forecasts["predicted_temperature_c"],
        mode="lines+markers",
        name="Prognostizierte Temperatur",
        line={"width": 3, "dash": "dash"},
        marker={"size": 9}
    )
)

fig.update_layout(
    title=f"Raumtemperatur – {selected_room}",
    xaxis_title="Zeitpunkt",
    yaxis_title="Temperatur (°C)",
    hovermode="x unified",
    height=480,
    margin={"l": 20, "r": 20, "t": 60, "b": 20}
)

st.plotly_chart(fig, use_container_width=True)


if measurements_df.empty:
    st.info(
        "Es liegen keine historischen Temperaturmesswerte "
        "für den ausgewählten Zeitraum vor."
    )


# ---------------------------------------------------------
# FORECAST TABLE
# ---------------------------------------------------------

st.divider()
st.subheader("Prognosedetails")

display_columns = [
    "room_id",
    "forecast_origin",
    "forecast_timestamp",
    "horizon_minutes",
    "predicted_temperature_c",
    "model_type",
    "data_age_hours",
    "is_stale",
    "status",
]

available_columns = [
    column for column in display_columns
    if column in forecast_df.columns
]

st.dataframe(
    forecast_df[available_columns].sort_values(
        "forecast_timestamp"
    ),
    use_container_width=True,
    hide_index=True
)

st.caption(
    "Quelle: KICaGEM Room Forecast- und Measurements-API."
)