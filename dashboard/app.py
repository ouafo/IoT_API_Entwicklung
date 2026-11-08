import streamlit as st

from config import DASHBOARD_TITLE, DASHBOARD_ICON
from api_client import api


st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon=DASHBOARD_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)


# ---------------------------------------------------------
# DESIGN
# ---------------------------------------------------------

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        [data-testid="stMetric"] {
            background-color: rgba(128, 128, 128, 0.08);
            padding: 18px;
            border-radius: 12px;
            border: 1px solid rgba(128, 128, 128, 0.15);
        }

        div[data-testid="stMetricValue"] {
            font-size: 1.8rem;
            font-weight: 650;
        }

        .dashboard-subtitle {
            color: #808080;
            font-size: 1rem;
            margin-top: -12px;
        }
    </style>
    """,
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("KI-gestütztes Campus-, Gebäude- und Energiemanagement")

    st.divider()

    st.markdown("### Navigation")
    st.markdown("**Übersicht**")
    st.page_link("pages/1_Wetter.py", label="Wetterprognosen", icon="🌤️")
    st.page_link("pages/2_Raumklima.py", label="Raumklimaprognosen", icon="🌡️")
    st.page_link("pages/3_Energie.py", label="Energieprognosen", icon="⚡")

    st.divider()

    if st.button("🔄 Daten aktualisieren", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("KICaGEM Analytics Dashboard")

st.markdown(
    '<p class="dashboard-subtitle">'
    'Zentrale Analyse der Wetter-, Raumklima- und Energieprognosen'
    '</p>',
    unsafe_allow_html=True
)

st.divider()


# ---------------------------------------------------------
# API STATUS
# ---------------------------------------------------------

try:
    health = api.health_check()
    st.success("Verbindung zur KICaGEM API erfolgreich.")

except RuntimeError as exc:
    st.error(f"Die KICaGEM API ist momentan nicht erreichbar: {exc}")
    st.info(
        "Bitte starte zuerst eure FastAPI-Anwendung "
        "und überprüfe die Einstellungen in dashboard/.env."
    )
    st.stop()


# ---------------------------------------------------------
# LOAD FORECAST OVERVIEWS
# ---------------------------------------------------------

weather_count = 0
weather_stations = 0
room_count = 0
room_forecast_count = 0
energy_room_count = 0
energy_forecast_count = 0

errors = []


try:
    stations = api.get_weather_stations()
    weather_stations = len(stations) if isinstance(stations, list) else 0

    weather_count = sum(
        item.get("ForecastCount", 0)
        for item in stations
        if isinstance(item, dict)
    )

except RuntimeError as exc:
    errors.append(f"Wetter: {exc}")


try:
    rooms_response = api.get_rooms_with_forecasts()

    rooms = rooms_response.get("value", [])
    room_count = len(rooms)

    room_forecast_count = sum(
        room.get("forecast_count", 0)
        for room in rooms
    )

except RuntimeError as exc:
    errors.append(f"Raumklima: {exc}")


try:
    energy_rooms = api.get_energy_rooms()

    energy_room_count = len(energy_rooms)

    energy_forecast_count = sum(
        room.get("forecast_count", 0)
        for room in energy_rooms
    )

except RuntimeError as exc:
    errors.append(f"Energie: {exc}")


# ---------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------

st.subheader("Systemübersicht")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="Wetterstationen",
        value=weather_stations,
        help="Anzahl der Stationen mit verfügbaren Wetterprognosen."
    )

with col2:
    st.metric(
        label="Räume mit Raumklimadaten",
        value=room_count,
        help="Anzahl der von der Forecast-API gelisteten Räume."
    )

with col3:
    st.metric(
        label="Räume mit Energieprognosen",
        value=energy_room_count,
        help="Anzahl der von der Energie-Forecast-API gelisteten Räume."
    )


st.divider()

st.subheader("Verfügbare Prognosedatensätze")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Wetterprognosen", weather_count)

with col2:
    st.metric("Raumklimaprognosen", room_forecast_count)

with col3:
    st.metric("Energieprognosen", energy_forecast_count)


# ---------------------------------------------------------
# ERRORS
# ---------------------------------------------------------

if errors:
    st.warning(
        "Einige Bereiche konnten nicht geladen werden. "
        "Bitte prüfe die jeweiligen API-Endpunkte."
    )

    for error in errors:
        st.caption(error)


# ---------------------------------------------------------
# NAVIGATION CARDS
# ---------------------------------------------------------

st.divider()

st.subheader("Prognosebereiche")

col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown("### 🌤️ Wetter")
        st.write(
            "Analysiere Temperatur, Luftfeuchtigkeit, "
            "Luftdruck, Wind und Niederschlag."
        )
        st.page_link(
            "pages/1_Wetter.py",
            label="Wetter-Dashboard öffnen",
            icon="🌦️"
        )

with col2:
    with st.container(border=True):
        st.markdown("### 🌡️ Raumklima")
        st.write(
            "Untersuche die prognostizierte Temperatur "
            "einzelner Räume und deren zeitliche Entwicklung."
        )
        st.page_link(
            "pages/2_Raumklima.py",
            label="Raumklima-Dashboard öffnen",
            icon="🌡️"
        )

with col3:
    with st.container(border=True):
        st.markdown("### ⚡ Energie")
        st.write(
            "Analysiere den prognostizierten "
            "Energieverbrauch einzelner Räume."
        )
        st.page_link(
            "pages/3_Energie.py",
            label="Energie-Dashboard öffnen",
            icon="⚡"
        )


st.divider()

st.caption(
    "KICaGEM Analytics | Datenbereitstellung über die bestehende FastAPI"
)