import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import api


st.set_page_config(
    page_title="Energieprognosen | KICaGEM",
    page_icon="⚡",
    layout="wide"
)


def to_dataframe(payload):
    if isinstance(payload, list):
        return pd.DataFrame(payload)

    if isinstance(payload, dict):
        return pd.DataFrame(payload.get("value", []))

    return pd.DataFrame()


# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.title("🏢 KICaGEM")
    st.caption("Energieprognosen")

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

st.title("⚡ Energieprognosen")

st.markdown(
    "Analyse des prognostizierten Energieverbrauchs "
    "für die verfügbaren Räume."
)

st.divider()


# ---------------------------------------------------------
# LOAD ROOMS
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

if "room_id" not in rooms_df.columns:
    st.error("Die API-Antwort enthält kein Feld 'room_id'.")
    st.stop()


rooms_df["room_id"] = rooms_df["room_id"].astype(str)

selected_room = st.selectbox(
    "Raum auswählen",
    options=rooms_df["room_id"].tolist()
)

room_info = rooms_df[
    rooms_df["room_id"] == selected_room
].iloc[0].to_dict()


# ---------------------------------------------------------
# ROOM STATUS
# ---------------------------------------------------------

status = room_info.get("status", "unbekannt")
is_stale = bool(room_info.get("is_stale", False))

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Raum", selected_room)

with col2:
    st.metric("Gebäude", room_info.get("building", "–"))

with col3:
    st.metric("Prognosestatus", status)

with col4:
    age = room_info.get("data_age_hours")

    st.metric(
        "Datenalter",
        f"{float(age):.2f} Stunden" if age is not None else "–"
    )


if status == "no_forecast":
    st.warning(
        "Für diesen Raum existieren aktuell keine Energieprognosen."
    )

    comment = room_info.get("comment")
    if comment:
        st.info(comment)

    st.stop()


if is_stale:
    st.warning(
        "Die Prognose basiert auf veralteten Eingangsdaten."
    )
else:
    st.success("Die Eingangsdaten sind laut API nicht veraltet.")


# ---------------------------------------------------------
# FORECAST DATA
# ---------------------------------------------------------

try:
    forecast_payload = api.get_latest_energy_forecasts(
        selected_room
    )

except RuntimeError as exc:
    st.error(f"Energieprognosen konnten nicht geladen werden: {exc}")
    st.stop()


forecast_df = to_dataframe(forecast_payload)

if forecast_df.empty:
    st.warning("Für diesen Raum wurden keine Prognosen zurückgegeben.")
    st.stop()


required_columns = {
    "building",
    "room_id",
    "forecast_origin",
    "forecast_timestamp",
    "horizon_minutes",
    "predicted_consumption_kwh",
    "model_type",
}

missing_columns = required_columns - set(forecast_df.columns)

if missing_columns:
    st.error(
        "In der Energieprognose fehlen folgende Felder: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()


forecast_df["forecast_origin"] = pd.to_datetime(
    forecast_df["forecast_origin"],
    utc=True,
    errors="coerce"
)

forecast_df["forecast_timestamp"] = pd.to_datetime(
    forecast_df["forecast_timestamp"],
    utc=True,
    errors="coerce"
)

forecast_df["predicted_consumption_kwh"] = pd.to_numeric(
    forecast_df["predicted_consumption_kwh"],
    errors="coerce"
)

forecast_df["horizon_minutes"] = pd.to_numeric(
    forecast_df["horizon_minutes"],
    errors="coerce"
)

forecast_df = forecast_df.dropna(
    subset=[
        "forecast_timestamp",
        "predicted_consumption_kwh"
    ]
)

if forecast_df.empty:
    st.warning("Die Energieprognose enthält keine gültigen Werte.")
    st.stop()


forecast_df = forecast_df.sort_values("forecast_timestamp")


# ---------------------------------------------------------
# KPI CARDS
# ---------------------------------------------------------

st.divider()
st.subheader("Aktuelle Energieprognose")

latest_forecast = forecast_df.iloc[-1]

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Prognostizierter Verbrauch",
        f'{latest_forecast["predicted_consumption_kwh"]:.4f} kWh'
    )

with col2:
    st.metric(
        "Prognosehorizont",
        f'{int(latest_forecast["horizon_minutes"])} Minuten'
    )

with col3:
    st.metric(
        "Modell",
        str(latest_forecast["model_type"])
    )

with col4:
    st.metric(
        "Anzahl Prognosen",
        len(forecast_df)
    )


# ---------------------------------------------------------
# FORECAST CHART
# ---------------------------------------------------------

st.divider()
st.subheader("Prognostizierter Energieverbrauch")

fig = go.Figure()

fig.add_trace(
    go.Scatter(
        x=forecast_df["forecast_timestamp"],
        y=forecast_df["predicted_consumption_kwh"],
        mode="lines+markers",
        name="Prognostizierter Verbrauch",
        line={"width": 3},
        marker={"size": 10}
    )
)

fig.update_layout(
    title=f"Energieprognose – {selected_room}",
    xaxis_title="Prognosezeitpunkt",
    yaxis_title="Prognostizierter Verbrauch (kWh)",
    hovermode="x unified",
    height=480,
    margin={"l": 20, "r": 20, "t": 60, "b": 20}
)

st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# HORIZON COMPARISON
# ---------------------------------------------------------

st.divider()
st.subheader("Vergleich der Prognosehorizonte")

horizon_df = forecast_df[
    ["horizon_minutes", "predicted_consumption_kwh"]
].copy()

horizon_df = horizon_df.sort_values("horizon_minutes")

fig_horizon = go.Figure()

fig_horizon.add_trace(
    go.Bar(
        x=horizon_df["horizon_minutes"].astype(str) + " min",
        y=horizon_df["predicted_consumption_kwh"],
        text=[
            f"{value:.4f} kWh"
            for value in horizon_df["predicted_consumption_kwh"]
        ],
        textposition="outside",
        name="Energieprognose"
    )
)

fig_horizon.update_layout(
    xaxis_title="Prognosehorizont",
    yaxis_title="Prognostizierter Verbrauch (kWh)",
    height=380,
    showlegend=False,
    margin={"l": 20, "r": 20, "t": 30, "b": 20}
)

st.plotly_chart(fig_horizon, use_container_width=True)


# ---------------------------------------------------------
# FORECAST TABLE
# ---------------------------------------------------------

st.divider()
st.subheader("Prognosedetails")

display_columns = [
    "building",
    "room_id",
    "forecast_origin",
    "forecast_timestamp",
    "horizon_minutes",
    "predicted_consumption_kwh",
    "model_type",
    "data_age_hours",
    "is_stale",
    "status",
    "comment",
]

available_columns = [
    column for column in display_columns
    if column in forecast_df.columns
]

st.dataframe(
    forecast_df[available_columns],
    use_container_width=True,
    hide_index=True
)

st.caption(
    "Quelle: KICaGEM Energy Forecast API. "
    "Die Prognosewerte werden in kWh ausgewiesen."
)