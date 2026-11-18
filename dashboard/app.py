from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Gesamtübersicht | KICaGEM",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------
# CUSTOM STYLING
# ---------------------------------------------------------

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
            name="Ist-Verlauf",
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
        height=280,
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


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Gesamtübersicht")

    st.divider()

    st.page_link("app.py", label="Gesamtübersicht", icon="🏠")
    st.page_link("pages/1_Wetter.py", label="Wetterprognosen", icon="🌤️")
    st.page_link("pages/2_Raumklima.py", label="Raumklimaprognosen", icon="🌡️")
    st.page_link("pages/3_Energie.py", label="Energieprognosen", icon="⚡")

    st.divider()

    if st.button("🔄 Daten aktualisieren", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------
# HERO HEADER
# ---------------------------------------------------------

target_date = datetime.now() + timedelta(days=7)
target_weekday_de = WEEKDAY_DE.get(target_date.strftime("%A"), target_date.strftime("%A"))

st.markdown(
    f"""
    <div class="hero-box">
        <h1>🏠 Gesamtübersicht – KICaGEM Leitstand</h1>
        <p>
            Direkter Überblick über Räume, Wetterstationen, Energieverbrauch und
            7-Tage-Wochenprognosen (Zieltag: <b>{target_weekday_de}, {target_date.strftime('%d.%m.%Y')}</b>)
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# FETCH OVERVIEW DATA
# ---------------------------------------------------------

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
    stations = api.get_weather_stations()
    if not isinstance(stations, list):
        stations = []
except RuntimeError:
    stations = []

rooms_df = pd.DataFrame(rooms)
if not rooms_df.empty and "room_id" in rooms_df.columns:
    rooms_df["room_id"] = rooms_df["room_id"].astype(str)
    rooms_df = rooms_df.drop_duplicates(subset=["room_id"], keep="first")

station_ids = [
    s["BuildingID"] for s in stations
    if isinstance(s, dict) and s.get("BuildingID")
]


# ---------------------------------------------------------
# TOP KPI BAR (4 COLUMNS AT A GLANCE)
# ---------------------------------------------------------

kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric(
        "System & Datenbank",
        "Online" if health_ok else "Eingeschränkt",
        delta=f"DB: {db_status} ({latency_str})",
    )

with kpi2:
    st.metric(
        "Überwachte Räume",
        len(rooms_df),
        delta=(
            f"{int(rooms_df['capacity'].sum())} Plätze gesamt"
            if not rooms_df.empty and "capacity" in rooms_df.columns
            else None
        ),
    )

with kpi3:
    st.metric(
        "Wetterstationen",
        len(station_ids),
        delta=f"Stationen: {', '.join(station_ids)}" if station_ids else None,
    )

with kpi4:
    st.metric(
        "Prognose-Zieltag",
        target_weekday_de,
        delta=f"+7 Tage ({target_date.strftime('%d.%m.%Y')})",
    )


# ---------------------------------------------------------
# LIVE 3-DOMAIN QUICK PREVIEW (IST VS. +7 TAGE)
# ---------------------------------------------------------

st.divider()
st.subheader("📊 Schnellvergleich auf einen Blick: Ist-Verlauf vs. Prognose (+7 Tage)")

if not rooms_df.empty:
    sel_col1, sel_col2, sel_col3 = st.columns([1.2, 1, 2])

    with sel_col1:
        preview_room = st.selectbox(
            "Raum auswählen",
            options=rooms_df["room_id"].tolist(),
            index=0,
        )

    with sel_col2:
        preview_n = st.slider(
            "Historische Datenpunkte (N)",
            min_value=10,
            max_value=30,
            value=15,
        )

    selected_meta = rooms_df[
        rooms_df["room_id"] == preview_room
    ].iloc[0].to_dict()

    with sel_col3:
        st.info(
            f"**Raum {preview_room} (feste Attribute):** "
            f"Kapazität **{selected_meta.get('capacity', 40)} Personen** · "
            f"Fläche **{selected_meta.get('area', 100.0):.0f} m²** · "
            f"Fenster **{selected_meta.get('window_count', 4)}**"
        )

    chart_col1, chart_col2, chart_col3 = st.columns(3)

    # 1. Weather Temperature Preview
    with chart_col1:
        weather_station_target = station_ids[0] if station_ids else None
        if weather_station_target:
            try:
                w_data = api.get_weather_forecasts(
                    building_id=weather_station_target,
                    sensor_type="temperature",
                    limit=preview_n,
                )
                fig_w = build_mini_comparison_chart(
                    w_data.get("History", []),
                    w_data.get("Forecast", []),
                    title=f"🌤️ Außentemperatur (Station {weather_station_target})",
                    unit=w_data.get("MeasureUnitCode", "°C"),
                    hist_color="#0284c7",
                    fc_color="#f97316",
                )
                if fig_w:
                    st.plotly_chart(fig_w, use_container_width=True)
                else:
                    st.caption("Keine aktuellen Wetterdaten verfügbar.")
            except RuntimeError as exc:
                st.caption(f"Wettervorschau nicht verfügbar: {exc}")
        st.page_link("pages/1_Wetter.py", label="→ Zu den Wetterprognosen", icon="🌤️")

    # 2. Room Climate Preview
    with chart_col2:
        try:
            r_data = api.get_room_forecasts(
                room_id=preview_room,
                sensor_type="temperature",
                limit=preview_n,
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
            else:
                st.caption("Keine Raumklimadaten für diesen Raum.")
        except RuntimeError as exc:
            st.caption(f"Raumklimavorschau nicht verfügbar: {exc}")
        st.page_link("pages/2_Raumklima.py", label="→ Zu den Raumklimaprognosen", icon="🌡️")

    # 3. Energy Consumption Preview
    with chart_col3:
        try:
            e_data = api.get_energy_forecasts(
                room_id=preview_room,
                limit=preview_n,
            )
            fig_e = build_mini_comparison_chart(
                e_data.get("history", []),
                e_data.get("forecast", []),
                title=f"⚡ Energieverbrauch ({preview_room})",
                unit=e_data.get("unit", "kWh"),
                hist_color="#2563eb",
                fc_color="#9333ea",
            )
            if fig_e:
                st.plotly_chart(fig_e, use_container_width=True)
            else:
                st.caption("Keine Energiedaten für diesen Raum.")
        except RuntimeError as exc:
            st.caption(f"Energievorschau nicht verfügbar: {exc}")
        st.page_link("pages/3_Energie.py", label="→ Zu den Energieprognosen", icon="⚡")


# ---------------------------------------------------------
# ROOM INVENTORY TABLE (ONLY room_id + FIXED ATTRIBUTES)
# ---------------------------------------------------------

st.divider()
st.subheader("📋 Raumübersicht & Feste Raumattribute")

if not rooms_df.empty:
    display_df = rooms_df[
        ["room_id", "capacity", "area", "window_count", "status"]
    ].rename(
        columns={
            "room_id": "Raum-ID",
            "capacity": "Kapazität (Pers.)",
            "area": "Fläche (m²)",
            "window_count": "Fenster",
            "status": "Status",
        }
    )
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=320,
    )
else:
    st.info("Keine Raumdaten aus der Datenbank geladen.")

st.caption("KICaGEM IoT & AI Analytics Platform · Gesamtübersicht · Read-Only PostgreSQL · 7-Tage-Wochenprognose")