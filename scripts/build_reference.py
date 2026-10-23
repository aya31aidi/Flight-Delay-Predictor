"""
Génère data/reference.json à partir du jeu de données nycflights13.

Le fichier contient tout ce dont l'interface a besoin et qui ne change pas
d'une prédiction à l'autre : noms des compagnies et aéroports, distances et
temps de vol typiques par route, taux de retard historiques, métriques du
modèle sur le jeu de test et moyennes des variables (pour expliquer les
prédictions).

    pip install nycflights13
    python scripts/build_reference.py
"""
import json
import pickle
from pathlib import Path

import pandas as pd
from nycflights13 import airlines, airports, flights
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent

# Quelques aéroports des territoires américains absents de la table airports
MISSING_AIRPORTS = {
    "BQN": "Rafael Hernández Airport, Aguadilla",
    "PSE": "Mercedita Airport, Ponce",
    "SJU": "Luis Muñoz Marín Intl, San Juan",
    "STT": "Cyril E. King Airport, St. Thomas",
}


def prepare_like_notebook(df):
    """Même préparation que dans le notebook, étape par étape."""
    df = df.copy()
    df["tailnum"] = df["tailnum"].fillna(df["tailnum"].mode()[0])
    df = df.set_index("tailnum")
    for col in ["dep_time", "dep_delay", "arr_time", "arr_delay", "air_time"]:
        df[col] = df[col].fillna(df[col].mean())

    df = pd.get_dummies(df, columns=["carrier", "origin", "dest"])
    bool_cols = df.select_dtypes(include=["bool"]).columns
    df[bool_cols] = df[bool_cols].astype(int)

    time_hour = pd.to_datetime(df.pop("time_hour"))
    for part in ["year", "month", "day", "hour", "minute"]:
        df[f"time_hour_{part}"] = getattr(time_hour.dt, part)

    X = df.drop("arr_delay", axis=1)
    y = df["arr_delay"] > 0
    return X, y


def model_metrics(model, X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)
    X_test = X_test[model.feature_names_in_]
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1": f1_score(y_test, y_pred),
        "roc_auc": roc_auc_score(y_test, y_proba),
        "test_size": int(len(y_test)),
        "train_size": int(len(y_train)),
        # [[vrais négatifs, faux positifs], [faux négatifs, vrais positifs]]
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }
    metrics = {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()}
    means = X_train[model.feature_names_in_].mean().round(6).to_dict()
    return metrics, means


def delay_rate(group):
    return round(float((group["arr_delay"] > 0).mean()), 4)


def build():
    with open(ROOT / "model.pkl", "rb") as f:
        model = pickle.load(f)

    carriers = [c[len("carrier_"):] for c in model.feature_names_in_ if c.startswith("carrier_")]
    origins = [c[len("origin_"):] for c in model.feature_names_in_ if c.startswith("origin_")]
    dests = [c[len("dest_"):] for c in model.feature_names_in_ if c.startswith("dest_")]

    airline_names = airlines.set_index("carrier")["name"].to_dict()
    # La table contient des apostrophes échappées ("Martha\\'s Vineyard")
    airport_names = airports.set_index("faa")["name"].str.replace("\\", "", regex=False)
    airport_names = {**MISSING_AIRPORTS, **airport_names.to_dict()}

    # Pour les statistiques on garde uniquement les vols arrivés
    landed = flights.dropna(subset=["arr_delay"])

    routes = {}
    for (origin, dest), grp in landed.groupby(["origin", "dest"]):
        routes.setdefault(origin, {})[dest] = {
            "distance": int(grp["distance"].median()),
            "air_time": int(grp["air_time"].median()),
            "flights": int(len(grp)),
            "delay_rate": delay_rate(grp),
            "carriers": sorted(grp["carrier"].unique().tolist()),
        }

    by_month = [delay_rate(g) for _, g in landed.groupby("month")]
    by_hour = {int(h): {"rate": delay_rate(g), "flights": int(len(g))}
               for h, g in landed.groupby("hour") if len(g) > 100}
    by_carrier = {c: delay_rate(g) for c, g in landed.groupby("carrier")}

    X, y = prepare_like_notebook(flights)
    metrics, means = model_metrics(model, X, y)

    reference = {
        "airlines": {c: airline_names.get(c, c) for c in carriers},
        "airports": {a: airport_names.get(a, a) for a in sorted(set(origins) | set(dests))},
        "origins": origins,
        "routes": routes,
        "stats": {
            "flights": int(len(flights)),
            "delay_rate": delay_rate(landed),
            "routes": sum(len(d) for d in routes.values()),
            "by_month": by_month,
            "by_hour": by_hour,
            "by_carrier": by_carrier,
        },
        "metrics": metrics,
        "feature_means": means,
    }

    out = ROOT / "data" / "reference.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(reference, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out.relative_to(ROOT)} écrit ({out.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    build()
