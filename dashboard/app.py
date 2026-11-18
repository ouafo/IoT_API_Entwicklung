from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="KICaGEM | Campus & Energie Dashboard",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .hero-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        padding: 1.4rem 1.8rem;
        border-radius: 12px;
        color: #ffffff;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.12);
    }
    .hero-box h1 {
        margin: 0;
        font-size: 1.85rem;
        font-weight: 700;
        color: #ffffff;
    }
    .hero-box p {
        margin: 0.35rem 0 0 0;
        font-size: 0.98rem;
        color: #cbd5e1;
    }
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 0.85rem 1rem;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
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


def build_mini_comparison_chart(
    history_list: list[dict],
    forecast_list: list[dict],
    title: str,
    unit: str,
    hist_color: str,
    fc_color: str,
) -> go.Figure | None:
    """Create a compact overlaid Ist vs. +7-day Forecast chart."""
    if not history_list or not forecast_list:
        return None

    h_df = pd.DataFrame(history_list)
    f_df = pd.DataFrame(forecast_list)

    h_df["timestamp"] = pd.to_datetime(h_df["timestamp"], utc=True)
    f_df["timestamp"] = pd.to_datetime(f_df["timestamp"], utc=True)

    labels = h_df["timestamp"].dt.strftime("%H:%M")
    target_labels = f_df["timestamp"].dt.strftime("%d.%m. %H:%M")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=h_df["value"],
            mode="lines+markers",
            name="Ist (letzte 15)",
            line={"width": 2.5, "color": hist_color},
            marker={"size": 6},
            hovertemplate="%{x}: %{y:.2f} " + unit + "<extra>Ist</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=f_df["value"],
            mode="lines+markers",
            name="Prognose (+7d)",
            line={"width": 2.5, "dash": "dash", "color": fc_color},
            marker={"size": 6, "symbol": "diamond"},
            customdata=target_labels,
            hovertemplate="%{customdata}: %{y:.2f} " + unit + "<extra>Prognose</extra>",
        )
    )

    fig.update_layout(
        title={"text": title, "font": {"size": 15}},
        xaxis_title="Uhrzeit",
        yaxis_title=unit,
        hovermode="x unified",
        height=275,
        margin={"l": 10, "r": 10, "t": 42, "b": 10},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 11},
        },
    )
    return fig


with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Campus-, Gebäude- & Energiemanagement")

    st.divider()

    st.page_link("app.py", label="Gesamtübersicht", icon="🏠")
    st.page_link("pages/1_Wetter.py", label="Wetterprognosen", icon="🌤️")
    st.page_link("pages/2_Raumklima.py", label="Raumklimaprognosen", icon="🌡️")
    st.page_link("pages/3_Energie.py", label="Energieprognosen", icon="⚡")

    st.divider()

    if st.button("🔄 Daten aktualisieren", use_container_width=True):
        st.rerun()


target_date = datetime.now() + timedelta(days=7)
target_weekday_de = WEEKDAY_DE.get(target_date.strftime("%A"), target_date.strftime("%A"))

st.markdown(
    f"""
    <div class="hero-box">
        <h1>🏢 KICaGEM – Campus & Energie Leitstand</h1>
        <p>
            Echtzeit-Überblick über Gebäude, Raumklima, Energieverbrauch und
            7-Tage-Wochenprognosen (Zieltag: <b>{target_weekday_de}, {target_date.strftime('%d.%m.%Y')}</b>)
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


health_ok = False
db_status = "offline"
latency_str = "–"

try:
    health = api.health_check()
    health_ok = health.get("status") == "healthy"
    db_info = health.get("database", {})
    db_status = db_info.get("status", "unbekannt")
    latency = db_info.get("latency_ms")
    latency_str = f"{latency} ms" if latency is not None else "–"
except RuntimeError as exc:
    st.error(f"Backend nicht erreichbar: {exc}")
    st.stop()

try:
    rooms_payload = api.get_rooms_with_forecasts()
    rooms = rooms_payload.get("value", [])
except RuntimeError:
    rooms = []

try:
    energy_rooms = api.get_energy_rooms()
    if not isinstance(energy_rooms, list):
        energy_rooms = []
except RuntimeError:
    energy_rooms = []

try:
    stations = api.get_weather_stations()
    if not isinstance(stations, list):
        stations = []
except RuntimeError:
    stations = []

rooms_df = pd.DataFrame(rooms)
energy_room_ids = [r["full_room_id"] for r in energy_rooms if "full_room_id" in r]

buildings = (
    sorted(rooms_df["building"].dropna().unique().tolist())
    if not rooms_df.empty and "building" in rooms_df.columns
    else []
)
station_ids = [
    s["BuildingID"] for s in stations
    if isinstance(s, dict) and s.get("BuildingID")
]


kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

with kpi1:
    st.metric(
        "System & Datenbank",
        "Online" if health_ok else "Eingeschränkt",
        delta=f"DB: {db_status} ({latency_str})",
    )

with kpi2:
    st.metric(
        "Erfasste Gebäude",
        len(buildings),
        delta=f"{', '.join(buildings)}" if buildings else None,
    )

with kpi3:
    st.metric(
        "Überwachte Räume",
        len(rooms_df),
        delta=f"{len(energy_room_ids)} mit Energiezähler",
    )

with kpi4:
    st.metric(
        "Wetterstationen",
        len(station_ids),
        delta=f"Stationen: {', '.join(station_ids)}" if station_ids else None,
    )

with kpi5:
    st.metric(
        "Prognose-Zieltag",
        f"{target_weekday_de}",
        delta=f"+7 Tage ({target_date.strftime('%d.%m.')})",
    )


st.divider()
st.subheader("📊 Schnellvergleich auf einen Blick: Ist-Verlauf vs. Prognose (+7 Tage)")

if not rooms_df.empty:
    sel_col1, sel_col2, sel_col3 = st.columns([1, 1, 2])

    with sel_col1:
        preview_building = st.selectbox(
            "Gebäude für Vorschau",
            options=buildings,
            index=0,
        )

    building_rooms_df = rooms_df[rooms_df["building"] == preview_building]
    preview_room_options = building_rooms_df["full_room_id"].tolist()

    with sel_col2:
        preview_room = st.selectbox(
            "Raum für Vorschau",
            options=preview_room_options,
            index=0,
        )

    selected_meta = building_rooms_df[
        building_rooms_df["full_room_id"] == preview_room
    ].iloc[0].to_dict()

    with sel_col3:
        st.info(
            f"**Ausgewählter Raum {preview_room}:** "
            f"Kapazität **{selected_meta.get('capacity', 40)} Personen** · "
            f"Fläche **{selected_meta.get('area', 100.0):.0f} m²** · "
            f"Fenster **{selected_meta.get('window_count', 4)}**"
        )

    chart_col1, chart_col2, chart_col3 = st.columns(3)

    # 1. Weather Temperature Preview
    with chart_col1:
        weather_station_target = (
            preview_building if preview_building in station_ids
            else (station_ids[0] if station_ids else None)
        )
        if weather_station_target:
            try:
                w_data = api.get_weather_forecasts(
                    building_id=weather_station_target,
                    sensor_type="temperature",
                    limit=15,
                )
                fig_w = build_mini_comparison_chart(
                    w_data.get("History", []),
                    w_data.get("Forecast", []),
                    title=f"🌤️ Außentemperatur (Geb. {weather_station_target})",
                    unit=w_data.get("MeasureUnitCode", "°C"),
                    hist_color="#0284c7",
                    fc_color="#f97316",
                )
                if fig_w:
                    st.plotly_chart(fig_w, use_container_width=True)
            except RuntimeError:
                st.info("Keine aktuellen Wetterdaten für diese Station.")
        st.page_link("pages/1_Wetter.py", label="→ Zu den Wetterprognosen", icon="🌤️")

    # 2. Room Climate Preview
    with chart_col2:
        try:
            r_data = api.get_room_forecasts(
                room_id=preview_room,
                sensor_type="temperature",
                limit=15,
            )
            fig_r = build_mini_comparison_chart(
                r_data.get("history", []),
                r_data.get("forecast", []),
                title=f"🌡️ Raumtemperatur ({preview_room})",
                unit=r_data.get("unit", "°C"),
                hist_color="#16a34a",
                fc_color="#dc2626",
            )
            if fig_r:
                st.plotly_chart(fig_r, use_container_width=True)
        except RuntimeError:
            st.info(f"Für {preview_room} liegen keine Raumklimadaten vor.")
        st.page_link("pages/2_Raumklima.py", label="→ Zu den Raumklimaprognosen", icon="🌡️")

    # 3. Energy Consumption Preview (uses preview_room if metered, otherwise first metered room)
    with chart_col3:
        energy_target_room = (
            preview_room if preview_room in energy_room_ids
            else (energy_room_ids[0] if energy_room_ids else None)
        )
        if energy_target_room:
            try:
                e_data = api.get_energy_forecasts(
                    room_id=energy_target_room,
                    limit=15,
                )
                fig_e = build_mini_comparison_chart(
                    e_data.get("history", []),
                    e_data.get("forecast", []),
                    title=f"⚡ Energieverbrauch ({energy_target_room})",
                    unit=e_data.get("unit", "kWh"),
                    hist_color="#2563eb",
                    fc_color="#9333ea",
                )
                if fig_e:
                    st.plotly_chart(fig_e, use_container_width=True)
            except RuntimeError:
                st.info(f"Für {energy_target_room} liegen keine Energiedaten vor.")
        else:
            st.info("Keine Energiezähler-Daten verfügbar.")
        st.page_link("pages/3_Energie.py", label="→ Zu den Energieprognosen", icon="⚡")


st.divider()
st.subheader("🏛️ Campus-Struktur & Raumübersicht")

if not rooms_df.empty:
    struct_col1, struct_col2 = st.columns([1, 1.6])

    with struct_col1:
        building_summary = (
            rooms_df.groupby("building", as_index=False)
            .agg(
                Raeume=("room_id", "count"),
                Kapazitaet=("capacity", "sum"),
                Flaeche_m2=("area", "sum"),
            )
        )
        fig_buildings = px.bar(
            building_summary,
            x="building",
            y="Raeume",
            text="Raeume",
            color="building",
            title="Überwachte Räume pro Gebäude",
            labels={"building": "Gebäude", "Raeume": "Anzahl Räume"},
        )
        fig_buildings.update_traces(textposition="outside")
        fig_buildings.update_layout(
            showlegend=False,
            height=330,
            margin={"l": 10, "r": 10, "t": 45, "b": 10},
        )
        st.plotly_chart(fig_buildings, use_container_width=True)

    with struct_col2:
        rooms_df["Energiezähler"] = rooms_df["full_room_id"].isin(energy_room_ids).map(
            {True: "✅ Ja", False: "–"}
        )
        display_df = rooms_df[
            ["building", "room_id", "full_room_id", "capacity", "area", "window_count", "Energiezähler"]
        ].rename(
            columns={
                "building": "Gebäude",
                "room_id": "Raum",
                "full_room_id": "Vollständige ID",
                "capacity": "Kapazität (Pers.)",
                "area": "Fläche (m²)",
                "window_count": "Fenster",
            }
        )
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=330,
        )
else:
    st.info("Keine Raumdaten aus der Datenbank geladen.")

st.caption("KICaGEM IoT & AI Analytics Platform · Read-Only PostgreSQL · 7-Tage-Wochenprognose")