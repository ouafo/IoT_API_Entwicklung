import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Energieprognosen | KICaGEM",
    page_icon="⚡",
    layout="wide",
)


WEEKDAY_DE = {
    "Monday": "Montag",
    "Tuesday": "Dienstag",
    "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag",
    "Friday": "Freitag",
    "Saturday": "Samstag",
    "Sunday": "Sonntag",
}


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Energieprognosen (+7 Tage)")

    st.divider()

    st.page_link("app.py", label="Gesamtübersicht", icon="🏠")
    st.page_link("pages/1_Wetter.py", label="Wetter", icon="🌤️")
    st.page_link("pages/2_Raumklima.py", label="Raumklima", icon="🌡️")

    st.divider()

    if st.button("🔄 Aktualisieren", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("⚡ Energieprognosen (Wochenvorschau)")
st.markdown(
    "Berechnet aus den letzten historischen Verbrauchsintervallen des ausgewählten Raums "
    "den prognostizierten Energieverbrauch in **genau 7 Tagen** (gleicher Wochentag) "
    "unter Einbezug der festen Raumattribute (**Fläche und Kapazität**)."
)
st.divider()


# ---------------------------------------------------------
# LOAD ROOMS (ONLY room_id)
# ---------------------------------------------------------

try:
    energy_rooms = api.get_energy_rooms()
except RuntimeError as exc:
    st.error(f"Energieräume konnten nicht geladen werden: {exc}")
    st.stop()

if not isinstance(energy_rooms, list) or not energy_rooms:
    st.warning("Die API hat keine Energieräume zurückgegeben.")
    st.stop()

rooms_df = pd.DataFrame(energy_rooms)
rooms_df["room_id"] = rooms_df["room_id"].astype(str)
rooms_df = rooms_df.drop_duplicates(subset=["room_id"], keep="first")

col_r, col_n = st.columns([2, 1])

with col_r:
    selected_room = st.selectbox(
        "Raum auswählen",
        options=rooms_df["room_id"].tolist(),
    )

room_info = rooms_df[rooms_df["room_id"] == selected_room].iloc[0].to_dict()

with col_n:
    sample_count = st.slider(
        "Anzahl historischer Intervalle (N)",
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
    bounds = api.get_room_time_range(selected_room, sensor_type="energy_import")
    time_range_text = (
        f" · Verfügbarer Energiedaten-Zeitraum: `{bounds.get('StartDateTime')}` "
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
    payload = api.get_energy_forecasts(
        room_id=selected_room,
        limit=sample_count,
    )
except RuntimeError as exc:
    st.error(f"Energieprognose konnte nicht geladen werden: {exc}")
    st.stop()

history_df = pd.DataFrame(payload.get("history", []))
forecast_df = pd.DataFrame(payload.get("forecast", []))

if history_df.empty or forecast_df.empty:
    st.warning(
        f"Für {selected_room} liegen aktuell keine ausreichenden "
        "Energiedaten vor."
    )
    st.stop()

history_df["timestamp"] = pd.to_datetime(history_df["timestamp"], utc=True)
forecast_df["timestamp"] = pd.to_datetime(forecast_df["timestamp"], utc=True)

unit = payload.get("unit", "kWh")
target_weekday_en = payload.get("target_weekday") or ""
target_weekday = WEEKDAY_DE.get(target_weekday_en, target_weekday_en)


# ---------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------

st.divider()
st.subheader(f"Kennzahlen – Energieverbrauch ({target_weekday} nächste Woche)")

hist_sum = history_df["value"].sum()
fc_sum = forecast_df["value"].sum()
delta_sum = fc_sum - hist_sum

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        f"Gesamtverbrauch (letzte {len(history_df)})",
        f"{hist_sum:.3f} {unit}",
    )

with col2:
    st.metric(
        f"Prognose Gesamt ({target_weekday} +7d)",
        f"{fc_sum:.3f} {unit}",
        delta=f"{delta_sum:+.3f} {unit}",
    )

with col3:
    st.metric(
        "Ø Verbrauch pro Intervall",
        f"{forecast_df['value'].mean():.4f} {unit}",
    )

with col4:
    st.metric(
        "Ausgewertete Datenbasis",
        f"{len(history_df)} Intervalle",
    )


# ---------------------------------------------------------
# CHART 1: OVERLAID EVOLUTION (IST VS. PROGNOSE +7 TAGE)
# ---------------------------------------------------------

st.divider()
st.subheader("Direkter Evolutionsvergleich: Ist-Verbrauch vs. Prognose (+7 Tage)")

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
        name="Ist-Verbrauch (Ausgangsdaten)",
        line={"width": 3, "color": "#1f77b4"},
        marker={"size": 8},
        customdata=comparison_df["Uhrzeit_Prognose"],
        hovertemplate="Ist (%{x}): %{y:.4f} kWh<br>Zielzeitpunkt (+7d): %{customdata}<extra></extra>",
    )
)

fig_overlay.add_trace(
    go.Scatter(
        x=comparison_df["Uhrzeit_Ist"],
        y=comparison_df["Prognose"],
        mode="lines+markers",
        name=f"Prognose (+7 Tage / {target_weekday})",
        line={"width": 3, "dash": "dash", "color": "#9467bd"},
        marker={"size": 8, "symbol": "diamond"},
        customdata=comparison_df["Uhrzeit_Prognose"],
        hovertemplate="Prognose (%{customdata}): %{y:.4f} kWh<extra></extra>",
    )
)

fig_overlay.update_layout(
    title=f"Energieverbrauch – Überlagerter Verlauf ({selected_room})",
    xaxis_title="Messzeitpunkt (Ausgangsreihe) ↔ Korrespondierender Zeitpunkt (+7 Tage)",
    yaxis_title=f"Verbrauch ({unit})",
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
    go.Bar(
        x=history_df["timestamp"],
        y=history_df["value"],
        name="Ist-Verbrauch",
        marker_color="#1f77b4",
    )
)

fig_timeline.add_trace(
    go.Bar(
        x=forecast_df["timestamp"],
        y=forecast_df["value"],
        name="Prognose (+7 Tage)",
        marker_color="#9467bd",
    )
)

fig_timeline.update_layout(
    xaxis_title="Zeitpunkt (UTC)",
    yaxis_title=f"Verbrauch ({unit})",
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
    f"Ist-Verbrauch ({unit})": history_df["value"].round(4),
    "Zeitpunkt (+7 Tage)": forecast_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"),
    f"Prognose ({unit})": forecast_df["value"].round(4),
    f"Differenz ({unit})": (forecast_df["value"] - history_df["value"]).round(4),
})

st.dataframe(table_df, use_container_width=True, hide_index=True)

st.caption("Quelle: KICaGEM On-Demand Energy Forecast API (Read-Only PostgreSQL + feste Raumattribute → +7 Tage).")