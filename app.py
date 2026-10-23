import json
import math
import os
import pickle
import re
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request
from sklearn.exceptions import InconsistentVersionWarning

BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__)

# Le modèle a été entraîné avec scikit-learn 1.3 : une régression logistique
# se recharge sans problème dans les versions suivantes, l'avertissement est inutile
with warnings.catch_warnings():
    warnings.simplefilter("ignore", InconsistentVersionWarning)
    with open(BASE_DIR / "model.pkl", "rb") as file:
        model = pickle.load(file)

# Données de référence générées par scripts/build_reference.py
with open(BASE_DIR / "data" / "reference.json", encoding="utf-8") as file:
    reference = json.load(file)

FEATURES = list(model.feature_names_in_)
COEFS = pd.Series(model.coef_[0], index=FEATURES)
MEANS = pd.Series(reference["feature_means"])[FEATURES]
# Probabilité de retard d'un vol « moyen », point de comparaison des explications
BASE_PROBABILITY = 1 / (1 + math.exp(-(model.intercept_[0] + (COEFS * MEANS).sum())))

# Regroupement des variables pour expliquer une prédiction en langage clair.
# Temps de vol et distance vont ensemble : seuls, leurs effets se compensent.
FACTOR_GROUPS = {
    "Departure delay": ["dep_delay"],
    "Air time for this distance": ["air_time", "distance"],
    "Departure time of day": ["dep_time", "sched_dep_time", "hour", "minute",
                              "time_hour_hour", "time_hour_minute"],
    "Arrival time of day": ["arr_time", "sched_arr_time"],
    "Date and season": ["year", "month", "day", "time_hour_year",
                        "time_hour_month", "time_hour_day"],
    "Airline": [c for c in FEATURES if c.startswith("carrier_")],
    "Departure airport": [c for c in FEATURES if c.startswith("origin_")],
    "Destination": [c for c in FEATURES if c.startswith("dest_")],
    "Flight number": ["flight"],
}


def airline_name(code):
    return re.sub(r" (Inc\.|Co\.|Corporation)$", "", reference["airlines"][code])


class InvalidFlight(ValueError):
    def __init__(self, errors):
        super().__init__("invalid flight data")
        self.errors = errors


def parse_time(value):
    """Accepte "14:05", "1405" ou 1405 et renvoie l'entier HHMM utilisé par le modèle."""
    text = str(value).strip().replace(":", "")
    if not text.isdigit() or len(text) > 4:
        raise ValueError
    hhmm = int(text)
    hours, minutes = divmod(hhmm, 100)
    if hours > 24 or minutes > 59 or (hours == 24 and minutes):
        raise ValueError
    return hhmm


def to_minutes(hhmm):
    hours, minutes = divmod(hhmm, 100)
    return hours * 60 + minutes


def from_minutes(total):
    hours, minutes = divmod(total % 1440, 60)
    return hours * 100 + minutes


def gap_in_minutes(actual, scheduled):
    """Écart signé entre deux heures HHMM, en tenant compte du passage à minuit."""
    gap = to_minutes(actual) - to_minutes(scheduled)
    if gap < -720:
        gap += 1440
    elif gap > 720:
        gap -= 1440
    return gap


def clean_input(data):
    """Valide les champs reçus et complète ceux qui sont facultatifs."""
    errors = {}
    assumptions = []

    def text(name):
        return str(data.get(name) or "").strip()

    carrier = text("carrier").upper()
    origin = text("origin").upper()
    dest = text("dest").upper()
    if carrier not in reference["airlines"]:
        errors["carrier"] = "Pick one of the listed airlines."
    if origin not in reference["origins"]:
        errors["origin"] = "Departure must be EWR, JFK or LGA."
    if dest not in reference["airports"] or dest == origin:
        errors["dest"] = "Pick a destination airport."

    try:
        flight_date = date.fromisoformat(text("date"))
    except ValueError:
        errors["date"] = "Enter a valid date."

    times = {}
    for name, required in [("sched_dep_time", True), ("sched_arr_time", True),
                           ("dep_time", False), ("arr_time", False)]:
        if not text(name):
            if required:
                errors[name] = "Required."
            continue
        try:
            times[name] = parse_time(text(name))
        except ValueError:
            errors[name] = "Use a time like 14:05."

    numbers = {}
    for name, low, high in [("flight", 1, 9999), ("air_time", 10, 900),
                            ("distance", 10, 6000), ("dep_delay", -120, 1440)]:
        if not text(name):
            continue
        try:
            numbers[name] = float(text(name))
        except ValueError:
            errors[name] = "Enter a number."
            continue
        if not low <= numbers[name] <= high:
            errors[name] = f"Expected between {low} and {high}."

    route = reference["routes"].get(origin, {}).get(dest)
    if not route and "distance" not in numbers and not errors.keys() & {"origin", "dest"}:
        errors["distance"] = "No 2013 history for this route, so the distance is needed."

    if errors:
        raise InvalidFlight(errors)

    # Champs facultatifs : on complète avec des valeurs plausibles et on le signale
    sched_dep, sched_arr = times["sched_dep_time"], times["sched_arr_time"]
    if "dep_time" in times:
        dep_time = times["dep_time"]
        dep_delay = numbers.get("dep_delay", gap_in_minutes(dep_time, sched_dep))
    elif "dep_delay" in numbers:
        dep_delay = numbers["dep_delay"]
        dep_time = from_minutes(to_minutes(sched_dep) + int(dep_delay))
    else:
        dep_time, dep_delay = sched_dep, 0
        assumptions.append("Departure assumed on schedule.")

    if "arr_time" in times:
        arr_time = times["arr_time"]
    else:
        arr_time = from_minutes(to_minutes(sched_arr) + int(dep_delay))
        assumptions.append("Arrival estimated as the scheduled time plus the departure delay.")

    if "distance" in numbers:
        distance = numbers["distance"]
    else:
        distance = route["distance"]
        assumptions.append(f"Distance taken from the route: {distance:,} miles.")

    if "air_time" in numbers:
        air_time = numbers["air_time"]
    elif route:
        air_time = route["air_time"]
        assumptions.append(f"Air time set to the route's typical {air_time} minutes.")
    else:
        # Vitesse moyenne observée sur l'ensemble des vols (~ 7,9 miles par minute)
        air_time = round(distance / 7.9 + 15)
        assumptions.append(f"Air time estimated from the distance: {air_time} minutes.")

    flight = numbers.get("flight", round(MEANS["flight"]))

    return {
        "carrier": carrier, "flight": int(flight), "origin": origin, "dest": dest,
        "date": flight_date, "sched_dep_time": sched_dep, "dep_time": dep_time,
        "dep_delay": dep_delay, "sched_arr_time": sched_arr, "arr_time": arr_time,
        "air_time": air_time, "distance": distance,
    }, assumptions


def build_features(flight):
    """Reconstruit exactement les 142 colonnes vues pendant l'entraînement."""
    hour, minute = divmod(flight["sched_dep_time"], 100)

    # Dans nycflights13, time_hour est stocké en UTC (ex. "2013-01-01T10:00:00Z"
    # pour un départ prévu à 5h15) : il faut refaire la même conversion
    local = pd.Timestamp(flight["date"]) + pd.Timedelta(hours=min(hour, 23))
    time_hour = local.tz_localize("America/New_York", ambiguous=True,
                                  nonexistent="shift_forward").tz_convert("UTC")

    row = dict.fromkeys(FEATURES, 0)
    row.update({
        "year": flight["date"].year,
        "month": flight["date"].month,
        "day": flight["date"].day,
        "dep_time": flight["dep_time"],
        "sched_dep_time": flight["sched_dep_time"],
        "dep_delay": flight["dep_delay"],
        "arr_time": flight["arr_time"],
        "sched_arr_time": flight["sched_arr_time"],
        "flight": flight["flight"],
        "air_time": flight["air_time"],
        "distance": flight["distance"],
        "hour": hour,
        "minute": minute,
        "time_hour_year": time_hour.year,
        "time_hour_month": time_hour.month,
        "time_hour_day": time_hour.day,
        "time_hour_hour": time_hour.hour,
        "time_hour_minute": 0,
    })
    for column in ["carrier", "origin", "dest"]:
        dummy = f"{column}_{flight[column]}"
        if dummy in row:
            row[dummy] = 1

    return pd.DataFrame([row], columns=FEATURES).astype(float)


def explain(features):
    """Contribution de chaque groupe de variables, comparée à un vol moyen de 2013."""
    impact = COEFS * (features.iloc[0] - MEANS)
    factors = [{"label": label, "impact": round(float(impact[cols].sum()), 3)}
               for label, cols in FACTOR_GROUPS.items()]
    factors.sort(key=lambda f: abs(f["impact"]), reverse=True)
    return [f for f in factors if abs(f["impact"]) >= 0.01][:5]


def predict(data):
    flight, assumptions = clean_input(data)
    features = build_features(flight)
    probability = float(model.predict_proba(features)[0, 1])
    delayed = probability >= 0.5

    margin = abs(probability - 0.5)
    confidence = "high" if margin >= 0.3 else "moderate" if margin >= 0.15 else "low"

    route = reference["routes"].get(flight["origin"], {}).get(flight["dest"])
    if route and flight["carrier"] not in route["carriers"]:
        assumptions.append(f"{airline_name(flight['carrier'])} did not fly this route in 2013.")

    return {
        "delayed": delayed,
        "probability": round(probability, 4),
        "confidence": confidence,
        "verdict": "Likely to arrive late" if delayed else "Likely to arrive on time",
        "dep_delay": flight["dep_delay"],
        "factors": explain(features),
        "baseline": round(BASE_PROBABILITY, 4),
        "route": {
            "origin": flight["origin"],
            "dest": flight["dest"],
            "origin_name": reference["airports"][flight["origin"]],
            "dest_name": reference["airports"][flight["dest"]],
            "airline": airline_name(flight["carrier"]),
            "history": route,
        },
        "assumptions": assumptions,
    }


@app.route("/", methods=["GET", "POST"])
def home():
    result, errors = None, {}
    if request.method == "POST":
        try:
            result = predict(request.form)
        except InvalidFlight as exc:
            errors = exc.errors

        # Requête envoyée par le JavaScript : on ne renvoie que le bloc résultat
        if request.headers.get("X-Requested-With") == "fetch":
            if errors:
                return jsonify(errors=errors), 422
            return render_template("_result.html", result=result, ref=reference)

    return render_template("index.html", result=result, errors=errors,
                           form=request.form, ref=reference)


@app.post("/api/predict")
def api_predict():
    data = request.get_json(silent=True) or request.form
    if not hasattr(data, "get"):
        return jsonify(errors={"body": "Send a JSON object."}), 400
    try:
        return jsonify(predict(data))
    except InvalidFlight as exc:
        return jsonify(errors=exc.errors), 422


@app.get("/api/routes")
def api_routes():
    return jsonify(airlines=reference["airlines"], airports=reference["airports"],
                   routes=reference["routes"])


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
