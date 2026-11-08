
from pathlib import Path
import sys
import math

import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# --------------------------------------------------
# 1. Projektpfad und Datenbankverbindung
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import get_conn, put_conn


BASE_DIR = Path(__file__).resolve().parent
RESULT_DIR = BASE_DIR / "results"

RESULT_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 2. Konfiguration
# --------------------------------------------------

HORIZONS = {
    1: 15,
    2: 30,
    4: 60,
}

FREQUENCY = "15min"
MINIMUM_SAMPLES = 2000

FEATURE_LAGS = [1, 2, 4, 8, 96, 672]


# --------------------------------------------------
# 3. Daten direkt aus PostgreSQL laden
# --------------------------------------------------

SQL_QUERY = """
WITH aggregated AS (
    SELECT
        building,
        room_location,
        start,
        MAX("Wirkenergie_Import_L123_T1") AS energy_kwh,
        AVG("Wirkleistung_L123_sum") AS power_w
    FROM public.room_energy
    WHERE "Wirkenergie_Import_L123_T1" IS NOT NULL
    GROUP BY building, room_location, start
),

lagged AS (
    SELECT
        building,
        room_location,
        start,
        energy_kwh,
        power_w,

        LAG(energy_kwh) OVER (
            PARTITION BY building, room_location
            ORDER BY start
        ) AS previous_energy,

        LAG(start) OVER (
            PARTITION BY building, room_location
            ORDER BY start
        ) AS previous_start

    FROM aggregated
)

SELECT
    building,
    room_location,
    start,
    energy_kwh - previous_energy AS consumption_kwh,
    power_w

FROM lagged

WHERE previous_energy IS NOT NULL
  AND start - previous_start = INTERVAL '15 minutes'
  AND energy_kwh >= previous_energy
  AND start >= (
      SELECT MAX(start) - INTERVAL '18 months'
      FROM public.room_energy
  )

ORDER BY building, room_location, start;
"""


def load_energy_data():

    conn = get_conn()

    try:
        with conn.cursor() as cursor:
            cursor.execute(SQL_QUERY)
            rows = cursor.fetchall()

        columns = [
            "building",
            "room_location",
            "start",
            "consumption_kwh",
            "power_w",
        ]

        df = pd.DataFrame(rows, columns=columns)

        print(f"\nGeladene Datensätze: {len(df):,}")

        return df

    finally:
        put_conn(conn)


# --------------------------------------------------
# 4. Feature Engineering
# --------------------------------------------------

def prepare_features(df):

    df = df.copy()

    df["start"] = pd.to_datetime(df["start"], utc=True)

    df = (
        df.sort_values("start")
        .drop_duplicates(subset="start", keep="last")
        .set_index("start")
    )

    # Regelmäßige 15-Minuten-Zeitreihe herstellen
    df = df.asfreq(FREQUENCY)

    # Zeitmerkmale
    df["hour"] = df.index.hour
    df["day_of_week"] = df.index.day_of_week
    df["is_weekend"] = (
        df.index.day_of_week >= 5
    ).astype(int)

    # Vergangene Verbrauchswerte
    for lag in FEATURE_LAGS:
        df[f"consumption_lag_{lag}"] = (
            df["consumption_kwh"].shift(lag)
        )

    # Vergangene Leistung verwenden
    df["power_lag_1"] = df["power_w"].shift(1)
    df["power_lag_4"] = df["power_w"].shift(4)

    # Rollierende Mittelwerte ausschließlich aus der Vergangenheit
    past_consumption = df["consumption_kwh"].shift(1)

    df["rolling_mean_4"] = (
        past_consumption.rolling(4).mean()
    )

    df["rolling_mean_96"] = (
        past_consumption.rolling(96).mean()
    )

    df["rolling_mean_672"] = (
        past_consumption.rolling(672).mean()
    )

    feature_columns = (
        ["hour", "day_of_week", "is_weekend"]
        + [
            f"consumption_lag_{lag}"
            for lag in FEATURE_LAGS
        ]
        + [
            "power_lag_1",
            "power_lag_4",
            "rolling_mean_4",
            "rolling_mean_96",
            "rolling_mean_672",
        ]
    )

    return df, feature_columns


# --------------------------------------------------
# 5. Modelltraining und Evaluation
# --------------------------------------------------

def train_room(building, room, room_df):

    print(f"\n{'=' * 60}")
    print(f"Raum: {building}-{room}")
    print(f"{'=' * 60}")

    df, feature_columns = prepare_features(room_df)

    X = df[feature_columns]

    evaluation_results = []
    forecast_results = []

    for steps, horizon_minutes in HORIZONS.items():

        print(f"\nPrognosehorizont: {horizon_minutes} Minuten")

        y = df["consumption_kwh"].shift(-steps)

        valid = X.notna().all(axis=1) & y.notna()

        X_valid = X.loc[valid]
        y_valid = y.loc[valid]

        if len(X_valid) < MINIMUM_SAMPLES:
            print(
                f"Zu wenige Trainingsdaten: {len(X_valid):,}"
            )
            continue

        # Chronologische Aufteilung: 70 / 15 / 15
        n = len(X_valid)

        train_end = int(n * 0.70)
        validation_end = int(n * 0.85)

        X_train = X_valid.iloc[:train_end]
        y_train = y_valid.iloc[:train_end]

        X_test = X_valid.iloc[validation_end:]
        y_test = y_valid.iloc[validation_end:]

        if len(X_test) == 0:
            continue

        model = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )

        model.fit(X_train, y_train)

        # Evaluation
        predictions = model.predict(X_test)

        mae = mean_absolute_error(
            y_test,
            predictions
        )

        rmse = math.sqrt(
            mean_squared_error(y_test, predictions)
        )

        # Persistence-Baseline
        baseline_predictions = (
            X_test["consumption_lag_1"].to_numpy()
        )

        baseline_mae = mean_absolute_error(
            y_test,
            baseline_predictions
        )

        print(f"Random Forest MAE: {mae:.5f} kWh")
        print(f"Random Forest RMSE: {rmse:.5f} kWh")
        print(f"Baseline MAE: {baseline_mae:.5f} kWh")

        evaluation_results.append({
            "building": building,
            "room": room,
            "horizon_minutes": horizon_minutes,
            "samples": len(X_valid),
            "mae": mae,
            "rmse": rmse,
            "baseline_mae": baseline_mae,
        })

        # Finales Modell mit allen verfügbaren Labels trainieren.
        # Das Modell bleibt ausschließlich im Arbeitsspeicher.
        final_model = RandomForestRegressor(
            n_estimators=200,
            max_depth=15,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )

        final_model.fit(X_valid, y_valid)

        # Aktuelle Prognose
        latest_features = X.dropna().tail(1)

        if not latest_features.empty:

            latest_prediction = final_model.predict(
                latest_features[feature_columns]
            )[0]

            latest_timestamp = latest_features.index[-1]

            forecast_results.append({
                "building": building,
                "room": room,
                "forecast_origin": latest_timestamp,
                "forecast_timestamp": (
                    latest_timestamp
                    + pd.Timedelta(minutes=horizon_minutes)
                ),
                "horizon_minutes": horizon_minutes,
                "predicted_consumption_kwh": max(
                    0.0,
                    float(latest_prediction)
                ),
                "model_type": "RandomForest",
            })

    return evaluation_results, forecast_results


# --------------------------------------------------
# 6. Hauptprogramm
# --------------------------------------------------

def main():

    print("\nENERGY FORECASTING - KICaGEM")
    print("=" * 60)

    data = load_energy_data()

    if data.empty:
        print("Keine Energiedaten gefunden.")
        return

    all_evaluations = []
    all_forecasts = []

    rooms = data.groupby(
        ["building", "room_location"]
    )

    print(f"\nGefundene Räume: {len(rooms)}")

    for (building, room), room_df in rooms:

        evaluations, forecasts = train_room(
            building,
            room,
            room_df
        )

        all_evaluations.extend(evaluations)
        all_forecasts.extend(forecasts)

    # Ergebnisse lokal speichern
    evaluation_df = pd.DataFrame(all_evaluations)
    forecast_df = pd.DataFrame(all_forecasts)

    evaluation_path = RESULT_DIR / "evaluation_results.csv"
    forecast_path = RESULT_DIR / "forecasts.csv"

    evaluation_df.to_csv(
        evaluation_path,
        index=False
    )

    forecast_df.to_csv(
        forecast_path,
        index=False
    )

    print("\n" + "=" * 60)
    print("TRAINING ABGESCHLOSSEN")
    print("=" * 60)

    print(f"Trainierte Modelle: {len(all_evaluations)}")
    print(f"Erstellte Prognosen: {len(all_forecasts)}")

    print(f"\nEvaluation: {evaluation_path}")
    print(f"Prognosen: {forecast_path}")


if __name__ == "__main__":
    main()
