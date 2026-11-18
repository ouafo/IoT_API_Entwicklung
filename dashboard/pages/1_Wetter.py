import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Wetterprognosen | KICaGEM",
    page_icon="🌤️",
    layout="wide",
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

WEEKDAY_DE = {
    "Monday": "Montag",
    "Tuesday": "Dienstag",
    "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag",
    "Friday": "Freitag",
    "Saturday": "Samstag",
    "Sunday": "Sonntag",
}


def format_value(value, unit):
    if value is None or pd.isna(value):
        return "–"
    return f"{float(value):.2f} {unit}"


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Wetterprognosen (+7 Tage)")

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

st.title("🌤️ Wetterprognosen (Wochenvorschau)")
st.markdown(
    "Vergleich der letzten historischen Messwerte aus der Datenbank mit dem "
    "**prognostizierten Verlauf in genau 7 Tagen** (gleicher Wochentag)."
)
st.divider()


# ---------------------------------------------------------
# WEATHER STATIONS & FILTERS
# ---------------------------------------------------------

try:
    stations = api.get_weather_stations()
except RuntimeError as exc:
    st.error(f"Wetterstationen konnten nicht geladen werden: {exc}")
    st.stop()

if not isinstance(stations, list) or not stations:
    st.warning("Aktuell sind keine Wetterstationen verfügbar.")
    st.stop()

station_ids = [
    s["BuildingID"] for s in stations
    if isinstance(s, dict) and s.get("BuildingID")
]

col1, col2, col3 = st.columns(3)

with col1:
    selected_station = st.selectbox(
        "Wetterstation",
        options=station_ids,
    )

station_info = next(
    (s for s in stations if s.get("BuildingID") == selected_station),
    {},
)
available_sensors = [
    s for s in SENSOR_LABELS
    if s in station_info.get("AvailableSensors", list(SENSOR_LABELS.keys()))
]

with col2:
    selected_sensor = st.selectbox(
        "Messgröße",
        options=available_sensors,
        format_func=lambda val: SENSOR_LABELS.get(val, val),
    )

with col3:
    sample_count = st.slider(
        "Anzahl historischer Datensätze (N)",
        min_value=10,
        max_value=30,
        value=15,
    )


# ---------------------------------------------------------
# LOAD FORECAST + PAIRED HISTORY
# ---------------------------------------------------------

try:
    payload = api.get_weather_forecasts(
        building_id=selected_station,
        sensor_type=selected_sensor,
        limit=sample_count,
    )
except RuntimeError as exc:
    st.error(f"Wetterprognose konnte nicht geladen werden: {exc}")
    st.stop()

history_df = pd.DataFrame(payload.get("History", []))
forecast_df = pd.DataFrame(payload.get("Forecast", []))

if history_df.empty or forecast_df.empty:
    st.warning(
        f"Für Station {selected_station} ({SENSOR_LABELS[selected_sensor]}) "
        "liegen aktuell keine ausreichenden Messwerte vor."
    )
    st.stop()

history_df["timestamp"] = pd.to_datetime(history_df["timestamp"], utc=True)
forecast_df["timestamp"] = pd.to_datetime(forecast_df["timestamp"], utc=True)

unit = payload.get("MeasureUnitCode") or UNIT_LABELS.get(selected_sensor, "")
target_weekday_en = payload.get("TargetWeekday") or ""
target_weekday = WEEKDAY_DE.get(target_weekday_en, target_weekday_en)


# ---------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------

st.divider()
st.subheader(f"Kennzahlen – {SENSOR_LABELS[selected_sensor]} ({target_weekday} nächste Woche)")

hist_avg = history_df["value"].mean()
fc_avg = forecast_df["value"].mean()
delta_avg = fc_avg - hist_avg

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        f"Ø Ist-Verlauf (letzte {len(history_df)})",
        format_value(hist_avg, unit),
    )

with col2:
    st.metric(
        f"Ø Prognose ({target_weekday} +7d)",
        format_value(fc_avg, unit),
        delta=f"{delta_avg:+.2f} {unit}",
    )

with col3:
    st.metric(
        "Prognose Spanne (Min / Max)",
        f"{forecast_df['value'].min():.2f} – {forecast_df['value'].max():.2f} {unit}",
    )

with col4:
    st.metric(
        "Ausgewertete Datenbasis",
        f"{len(history_df)} Datensätze",
    )


# ---------------------------------------------------------
# CHART 1: OVERLAID EVOLUTION (IST VS. PROGNOSE +7 TAGE)
# ---------------------------------------------------------

st.divider()
st.subheader("Direkter Evolutionsvergleich: Ist-Verlauf vs. Prognose (+7 Tage)")

comparison_df = pd.DataFrame({
    "Uhrzeit_Ist": history_df["timestamp"].dt.strftime("%d.%m. %H:%M"),
    "Uhrzeit_Prognose": forecast_df["timestamp"].dt.strftime("%d.%m. %H:%M"),
    "Ist": history_df["value"].values,
    "Prognose": forecast_df["value"].values,
})

fig_overlay = go.Figure()

fig_overlay.add_trace(
    go.Scatter(
        x=comparison_df["Uhrzeit_Ist"],
        y=comparison_df["Ist"],
        mode="lines+markers",
        name="Ist-Verlauf (Ausgangsdaten)",
        line={"width": 3, "color": "#1f77b4"},
        marker={"size": 8},
        customdata=comparison_df["Uhrzeit_Prognose"],
        hovertemplate="Ist (%{x}): %{y:.2f} " + unit + "<br>Zielzeitpunkt (+7d): %{customdata}<extra></extra>",
    )
)

fig_overlay.add_trace(
    go.Scatter(
        x=comparison_df["Uhrzeit_Ist"],
        y=comparison_df["Prognose"],
        mode="lines+markers",
        name=f"Prognose (+7 Tage / {target_weekday})",
        line={"width": 3, "dash": "dash", "color": "#ff7f0e"},
        marker={"size": 8, "symbol": "diamond"},
        customdata=comparison_df["Uhrzeit_Prognose"],
        hovertemplate="Prognose (%{customdata}): %{y:.2f} " + unit + "<extra></extra>",
    )
)

fig_overlay.update_layout(
    title=f"{SENSOR_LABELS[selected_sensor]} – Überlagerter Verlauf (Station {selected_station})",
    xaxis_title="Messzeitpunkt (Ausgangsreihe) ↔ Korrespondierender Zeitpunkt (+7 Tage)",
    yaxis_title=f"{SENSOR_LABELS[selected_sensor]} ({unit})",
    hovermode="x unified",
    height=460,
    margin={"l": 20, "r": 20, "t": 60, "b": 20},
)

st.plotly_chart(fig_overlay, use_container_width=True)


# ---------------------------------------------------------
# CHART 2: CHRONOLOGICAL TIMELINE
# ---------------------------------------------------------

st.subheader("Chronologischer Zeitstrahl (Ist → +7 Tage)")

fig_timeline = go.Figure()

fig_timeline.add_trace(
    go.Scatter(
        x=history_df["timestamp"],
        y=history_df["value"],
        mode="lines+markers",
        name="Ist-Verlauf",
        line={"width": 2.5, "color": "#1f77b4"},
    )
)

fig_timeline.add_trace(
    go.Scatter(
        x=forecast_df["timestamp"],
        y=forecast_df["value"],
        mode="lines+markers",
        name="Prognose (+7 Tage)",
        line={"width": 2.5, "dash": "dash", "color": "#ff7f0e"},
    )
)

fig_timeline.update_layout(
    xaxis_title="Zeitpunkt (UTC)",
    yaxis_title=f"{SENSOR_LABELS[selected_sensor]} ({unit})",
    hovermode="x unified",
    height=360,
    margin={"l": 20, "r": 20, "t": 30, "b": 20},
)

st.plotly_chart(fig_timeline, use_container_width=True)


# ---------------------------------------------------------
# COMPARISON TABLE
# ---------------------------------------------------------

st.divider()
st.subheader("Tabellarische Gegenüberstellung")

table_df = pd.DataFrame({
    "Zeitpunkt (Ist)": history_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"),
    f"Ist-Wert ({unit})": history_df["value"].round(2),
    "Zeitpunkt (+7 Tage)": forecast_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"),
    f"Prognose ({unit})": forecast_df["value"].round(2),
    f"Differenz ({unit})": (forecast_df["value"] - history_df["value"]).round(2),
})

st.dataframe(table_df, use_container_width=True, hide_index=True)

st.caption("Quelle: KICaGEM On-Demand Weather Forecast API (Read-Only PostgreSQL → +7 Tage).")