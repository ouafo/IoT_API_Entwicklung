import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Raumklima | KICaGEM",
    page_icon="🌡️",
    layout="wide",
)


SENSOR_CONFIG = {
    "temperature": {
        "label": "Temperatur",
        "icon": "🌡️",
        "unit": "°C",
    },
    "humidity": {
        "label": "Luftfeuchtigkeit",
        "icon": "💧",
        "unit": "%",
    },
    "co2": {
        "label": "CO₂-Konzentration",
        "icon": "🌫️",
        "unit": "ppm",
    },
    "light": {
        "label": "Lichtintensität",
        "icon": "💡",
        "unit": "Lux",
    },
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
    st.caption("Raumklimaprognosen (+7 Tage)")

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

st.title("🌡️ Raumklimaprognosen (Wochenvorschau)")
st.markdown(
    "Berechnet aus den letzten historischen Datensätzen des ausgewählten Raums "
    "den erwarteten Verlauf in **genau 7 Tagen** (gleicher Wochentag) unter "
    "Berücksichtigung der festen Raumattribute (**Kapazität, Fläche und Fensteranzahl**)."
)
st.divider()


# ---------------------------------------------------------
# LOAD ROOMS (ONLY room_id)
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
rooms_df["room_id"] = rooms_df["room_id"].astype(str)
rooms_df = rooms_df.drop_duplicates(subset=["room_id"], keep="first")

col_r, col_s, col_n = st.columns(3)

with col_r:
    selected_room = st.selectbox(
        "Raum auswählen",
        options=rooms_df["room_id"].tolist(),
    )

room_info = rooms_df[rooms_df["room_id"] == selected_room].iloc[0].to_dict()

with col_s:
    selected_sensor = st.selectbox(
        "Messgröße auswählen",
        options=list(SENSOR_CONFIG.keys()),
        format_func=lambda s: f"{SENSOR_CONFIG[s]['icon']} {SENSOR_CONFIG[s]['label']}",
    )

with col_n:
    sample_count = st.slider(
        "Anzahl historischer Datensätze (N)",
        min_value=10,
        max_value=30,
        value=15,
    )


# ---------------------------------------------------------
# READ-ONLY ROOM ATTRIBUTES & AVAILABLE TIMERANGE
# ---------------------------------------------------------

fixed_capacity = int(room_info.get("capacity", 40))
fixed_area = float(room_info.get("area", 100.0))
fixed_windows = int(room_info.get("window_count", 4))

time_range_text = ""
try:
    bounds = api.get_room_time_range(selected_room, sensor_type=selected_sensor)
    time_range_text = (
        f" · Verfügbarer Datenzeitraum: `{bounds.get('StartDateTime')}` "
        f"bis `{bounds.get('EndDateTime')}`"
    )
except RuntimeError:
    pass

st.info(
    f"**Feste Raumattribute für {selected_room}:** "
    f"Kapazität **{fixed_capacity} Personen** · "
    f"Fläche **{fixed_area:.0f} m²** · "
    f"Fenster **{fixed_windows}**"
    f"{time_range_text}"
)


# ---------------------------------------------------------
# LOAD FORECAST + PAIRED HISTORY
# ---------------------------------------------------------

try:
    payload = api.get_room_forecasts(
        room_id=selected_room,
        sensor_type=selected_sensor,
        limit=sample_count,
    )
except RuntimeError as exc:
    st.error(f"Raumprognose konnte nicht geladen werden: {exc}")
    st.stop()

history_df = pd.DataFrame(payload.get("history", []))
forecast_df = pd.DataFrame(payload.get("forecast", []))

if history_df.empty or forecast_df.empty:
    st.warning(
        f"Für {selected_room} liegen aktuell keine ausreichenden "
        f"{SENSOR_CONFIG[selected_sensor]['label']}-Messwerte vor."
    )
    st.stop()

history_df["timestamp"] = pd.to_datetime(history_df["timestamp"], utc=True)
forecast_df["timestamp"] = pd.to_datetime(forecast_df["timestamp"], utc=True)

sensor_label = SENSOR_CONFIG[selected_sensor]["label"]
sensor_unit = payload.get("unit") or SENSOR_CONFIG[selected_sensor]["unit"]
target_weekday_en = payload.get("target_weekday") or ""
target_weekday = WEEKDAY_DE.get(target_weekday_en, target_weekday_en)


# ---------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------

st.divider()
st.subheader(f"Kennzahlen – {sensor_label} ({target_weekday} nächste Woche)")

hist_avg = history_df["value"].mean()
fc_avg = forecast_df["value"].mean()
delta_avg = fc_avg - hist_avg

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        f"Ø Ist-Verlauf (letzte {len(history_df)})",
        format_value(hist_avg, sensor_unit),
    )

with col2:
    st.metric(
        f"Ø Prognose ({target_weekday} +7d)",
        format_value(fc_avg, sensor_unit),
        delta=f"{delta_avg:+.2f} {sensor_unit}",
    )

with col3:
    st.metric(
        "Prognose Spanne (Min / Max)",
        f"{forecast_df['value'].min():.2f} – {forecast_df['value'].max():.2f} {sensor_unit}",
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
        name=f"Ist-Verlauf ({sensor_label})",
        line={"width": 3, "color": "#2ca02c"},
        marker={"size": 8},
        customdata=comparison_df["Uhrzeit_Prognose"],
        hovertemplate="Ist (%{x}): %{y:.2f} " + sensor_unit + "<br>Zielzeitpunkt (+7d): %{customdata}<extra></extra>",
    )
)

fig_overlay.add_trace(
    go.Scatter(
        x=comparison_df["Uhrzeit_Ist"],
        y=comparison_df["Prognose"],
        mode="lines+markers",
        name=f"Prognose (+7 Tage / {target_weekday})",
        line={"width": 3, "dash": "dash", "color": "#d62728"},
        marker={"size": 8, "symbol": "diamond"},
        customdata=comparison_df["Uhrzeit_Prognose"],
        hovertemplate="Prognose (%{customdata}): %{y:.2f} " + sensor_unit + "<extra></extra>",
    )
)

fig_overlay.update_layout(
    title=f"{sensor_label} – Überlagerter Verlauf ({selected_room})",
    xaxis_title="Messzeitpunkt (Ausgangsreihe) ↔ Korrespondierender Zeitpunkt (+7 Tage)",
    yaxis_title=f"{sensor_label} ({sensor_unit})",
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
        line={"width": 2.5, "color": "#2ca02c"},
    )
)

fig_timeline.add_trace(
    go.Scatter(
        x=forecast_df["timestamp"],
        y=forecast_df["value"],
        mode="lines+markers",
        name="Prognose (+7 Tage)",
        line={"width": 2.5, "dash": "dash", "color": "#d62728"},
    )
)

fig_timeline.update_layout(
    xaxis_title="Zeitpunkt (UTC)",
    yaxis_title=f"{sensor_label} ({sensor_unit})",
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
    f"Ist-Wert ({sensor_unit})": history_df["value"].round(2),
    "Zeitpunkt (+7 Tage)": forecast_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"),
    f"Prognose ({sensor_unit})": forecast_df["value"].round(2),
    f"Differenz ({sensor_unit})": (forecast_df["value"] - history_df["value"]).round(2),
})

st.dataframe(table_df, use_container_width=True, hide_index=True)

st.caption("Quelle: KICaGEM On-Demand Room Climate Forecast API (Read-Only PostgreSQL + feste Raumattribute → +7 Tage).")