
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


# ==================================================
# 1. KONFIGURATION
# ==================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_FILE = BASE_DIR / "data" / "room_climate_C2_005.csv"
MODEL_DIR = BASE_DIR / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

FREQUENCY = "15min"

# Prognosehorizonte:
# 1 = 15 Minuten
# 2 = 30 Minuten
# 3 = 45 Minuten
# 4 = 60 Minuten
HORIZONS = [1, 2, 3, 4]

# Vergangene Temperaturwerte
LAGS = [1, 2, 4, 8, 96, 672]

ROOM_ID = "C-C2.005"

TRAIN_RATIO = 0.8

RANDOM_STATE = 42


# ==================================================
# 2. DATEN LADEN UND VALIDIEREN
# ==================================================

print("\n========== DATENAUFBEREITUNG ==========")

df = pd.read_csv(DATA_FILE)

required_columns = [
    "timestamp",
    "temperature_c"
]

missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing_columns:
    raise ValueError(
        f"Fehlende CSV-Spalten: {missing_columns}"
    )

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce"
)

df["temperature_c"] = pd.to_numeric(
    df["temperature_c"],
    errors="coerce"
)

df = df.dropna(
    subset=["timestamp"]
)

df = df.sort_values("timestamp")


# Diagnoseinformationen aus der Aggregation
if "distinct_temperature_values" in df.columns:

    print(
        "Maximale Anzahl unterschiedlicher Temperaturwerte "
        "innerhalb eines Intervalls:",
        df["distinct_temperature_values"].max()
    )

if "source_rows" in df.columns:

    print(
        "Anzahl ursprünglicher Datensätze:",
        df["source_rows"].sum()
    )


# Doppelte Zeitstempel überprüfen
duplicate_mask = df.duplicated(
    subset=["timestamp"],
    keep=False
)

duplicate_rows = df[duplicate_mask]

if not duplicate_rows.empty:

    conflicting_values = (
        duplicate_rows
        .groupby("timestamp")["temperature_c"]
        .nunique()
    )

    conflicting_timestamps = (
        conflicting_values[conflicting_values > 1]
    )

    if not conflicting_timestamps.empty:

        raise ValueError(
            "Widersprüchliche Temperaturwerte für "
            "identische Zeitstempel gefunden. "
            f"Anzahl betroffener Zeitstempel: "
            f"{len(conflicting_timestamps)}"
        )

    print(
        "Redundante Datensätze:",
        len(duplicate_rows)
    )

    df = df.drop_duplicates(
        subset=["timestamp"],
        keep="first"
    )


# Eindeutige Zeitreihe erstellen
series = (
    df.set_index("timestamp")["temperature_c"]
    .sort_index()
)

if series.empty:
    raise ValueError("Die Zeitreihe enthält keine Daten.")

if series.index.has_duplicates:
    raise ValueError("Zeitstempel sind weiterhin nicht eindeutig.")


# Einheitliches 15-Minuten-Raster
full_index = pd.date_range(
    start=series.index.min(),
    end=series.index.max(),
    freq=FREQUENCY,
    tz="UTC"
)

series = series.reindex(full_index)

print("\nAnzahl Zeitintervalle:", len(series))

print(
    "Fehlende Temperaturwerte:",
    series.isna().sum()
)

print(
    "Anteil fehlender Temperaturwerte:",
    f"{series.isna().mean() * 100:.2f}%"
)

print(
    "Letzter vorhandener Temperaturwert:",
    series.last_valid_index()
)


# ==================================================
# 3. FEATURE ENGINEERING
# ==================================================

def create_features(data, horizon):
    """
    Erzeugt Features für die Temperaturprognose.

    Die Features basieren ausschließlich auf Informationen,
    die zum jeweiligen Prognoseursprung bekannt sind.
    """

    features = pd.DataFrame(index=data.index)

    # Aktuellste bekannte Temperatur
    features["temperature_current"] = data

    # Vergangene Temperaturwerte
    for lag in LAGS:

        features[f"temperature_lag_{lag}"] = (
            data.shift(lag)
        )

    # Zeitpunkt der zukünftigen Prognose
    target_time = (
        data.index
        + pd.Timedelta(minutes=15 * horizon)
    )

    hour = (
        target_time.hour
        + target_time.minute / 60
    )

    day_of_week = target_time.day_of_week

    # Zyklische Zeitmerkmale
    features["hour_sin"] = np.sin(
        2 * np.pi * hour / 24
    )

    features["hour_cos"] = np.cos(
        2 * np.pi * hour / 24
    )

    features["weekday_sin"] = np.sin(
        2 * np.pi * day_of_week / 7
    )

    features["weekday_cos"] = np.cos(
        2 * np.pi * day_of_week / 7
    )

    return features


# ==================================================
# 4. TRAINING UND EVALUATION
# ==================================================

print("\n========== MODELLTRAINING ==========")

results = []

for horizon in HORIZONS:

    horizon_minutes = horizon * 15

    print(
        f"\nTrainiere Prognose für +{horizon_minutes} Minuten"
    )

    # Features erstellen
    X = create_features(series, horizon)

    # Zielwert liegt in der Zukunft
    y = series.shift(-horizon)

    target_timestamp = (
        series.index
        + pd.Timedelta(minutes=horizon_minutes)
    )

    dataset = X.copy()

    dataset["target"] = y

    dataset["target_timestamp"] = target_timestamp

    feature_columns = X.columns.tolist()

    # Unvollständige Beobachtungen entfernen
    dataset = dataset.dropna()

    # Chronologischer Split anhand des Zielzeitpunkts
    split_timestamp = series.index[
        int(len(series) * TRAIN_RATIO)
    ]

    train = dataset[
        dataset["target_timestamp"] < split_timestamp
    ]

    test = dataset[
        dataset["target_timestamp"] >= split_timestamp
    ]

    if train.empty or test.empty:

        raise ValueError(
            "Trainings- oder Testdaten sind leer."
        )

    X_train = train[feature_columns]
    y_train = train["target"]

    X_test = test[feature_columns]
    y_test = test["target"]

    print("Trainingsdaten:", len(train))
    print("Testdaten:", len(test))

    # --------------------------------------------------
    # 4.1 Persistence-Baseline
    # --------------------------------------------------

    baseline_predictions = (
        X_test["temperature_current"]
    )

    baseline_mae = mean_absolute_error(
        y_test,
        baseline_predictions
    )

    baseline_rmse = np.sqrt(
        mean_squared_error(
            y_test,
            baseline_predictions
        )
    )

    # --------------------------------------------------
    # 4.2 Random Forest
    # --------------------------------------------------

    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=15,
        min_samples_leaf=2,
        random_state=RANDOM_STATE,
        n_jobs=-1
    )

    model.fit(
        X_train,
        y_train
    )

    predictions = model.predict(X_test)

    model_mae = mean_absolute_error(
        y_test,
        predictions
    )

    model_rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions
        )
    )

    # --------------------------------------------------
    # 4.3 Modellvergleich
    # --------------------------------------------------

    if model_mae < baseline_mae:

        selected_model_type = "random_forest"

        # Für den späteren Produktiveinsatz
        # mit allen verfügbaren Daten trainieren.
        production_model = RandomForestRegressor(
            n_estimators=300,
            max_depth=15,
            min_samples_leaf=2,
            random_state=RANDOM_STATE,
            n_jobs=-1
        )

        production_model.fit(
            dataset[feature_columns],
            dataset["target"]
        )

    else:

        selected_model_type = "persistence"

        production_model = None

    # Verbesserung gegenüber der Baseline
    if baseline_mae > 0:

        improvement_percent = (
            (baseline_mae - model_mae)
            / baseline_mae
        ) * 100

    else:

        improvement_percent = 0.0

    # --------------------------------------------------
    # 4.4 Ergebnisse speichern
    # --------------------------------------------------

    results.append({

        "horizon_minutes": horizon_minutes,

        "baseline_mae": baseline_mae,

        "baseline_rmse": baseline_rmse,

        "random_forest_mae": model_mae,

        "random_forest_rmse": model_rmse,

        "improvement_percent": improvement_percent,

        "selected_model": selected_model_type,

        "training_samples": len(train),

        "test_samples": len(test)

    })

    # --------------------------------------------------
    # 4.5 Modell speichern
    # --------------------------------------------------

    model_path = (
        MODEL_DIR
        / f"temperature_{horizon_minutes}min.joblib"
    )

    joblib.dump(

        {

            "model": production_model,

            "model_type": selected_model_type,

            "feature_columns": feature_columns,

            "room_id": ROOM_ID,

            "horizon_minutes": horizon_minutes,

            "baseline_mae": baseline_mae,

            "random_forest_mae": model_mae

        },

        model_path

    )

    print(f"Baseline MAE: {baseline_mae:.4f} °C")
    print(f"Baseline RMSE: {baseline_rmse:.4f} °C")

    print(f"Random Forest MAE: {model_mae:.4f} °C")
    print(f"Random Forest RMSE: {model_rmse:.4f} °C")

    print(
        f"Verbesserung gegenüber Baseline: "
        f"{improvement_percent:.2f}%"
    )

    print(
        f"Ausgewähltes Verfahren: {selected_model_type}"
    )


# ==================================================
# 5. EVALUATION SPEICHERN
# ==================================================

results_df = pd.DataFrame(results)

results_df.to_csv(
    BASE_DIR / "evaluation_results.csv",
    index=False
)

print("\n========== EVALUATION ==========")

print(
    results_df.to_string(index=False)
)


# ==================================================
# 6. PROGNOSE DER NÄCHSTEN 60 MINUTEN
# ==================================================

print("\n========== TEMPERATURPROGNOSE ==========")

forecasts = []

for horizon in HORIZONS:

    horizon_minutes = horizon * 15

    model_path = (
        MODEL_DIR
        / f"temperature_{horizon_minutes}min.joblib"
    )

    bundle = joblib.load(model_path)

    model = bundle["model"]

    model_type = bundle["model_type"]

    feature_columns = bundle["feature_columns"]

    # Features erzeugen
    features = create_features(
        series,
        horizon
    )

    # Letzten vollständig verfügbaren Prognoseursprung finden
    valid_features = features.dropna(
        subset=feature_columns
    )

    if valid_features.empty:

        raise ValueError(
            "Keine vollständigen Features für die Prognose vorhanden."
        )

    latest_features = valid_features.iloc[[-1]]

    forecast_origin = latest_features.index[0]

    # Modellabhängige Prognose
    if model_type == "persistence":

        prediction = latest_features[
            "temperature_current"
        ].iloc[0]

    else:

        prediction = model.predict(
            latest_features[feature_columns]
        )[0]

    forecast_timestamp = (
        forecast_origin
        + pd.Timedelta(minutes=horizon_minutes)
    )

    forecasts.append({

        "room_id": ROOM_ID,

        "forecast_origin": forecast_origin,

        "forecast_timestamp": forecast_timestamp,

        "horizon_minutes": horizon_minutes,

        "model_type": model_type,

        "predicted_temperature_c": prediction

    })


# ==================================================
# 7. PROGNOSEN SPEICHERN
# ==================================================

forecast_df = pd.DataFrame(forecasts)

forecast_df.to_csv(
    BASE_DIR / "forecasts.csv",
    index=False
)

print(
    forecast_df.to_string(index=False)
)

print("\nForecasting erfolgreich abgeschlossen.")
