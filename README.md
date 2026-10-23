# ✈️ Flight Delay Predictor

Will a flight from New York land late? This project answers with a probability, the reasons behind it and the route's track record.

The model is a logistic regression trained on the **336,776 flights** that left Newark (EWR), JFK and LaGuardia (LGA) in 2013 ([nycflights13](https://github.com/tidyverse/nycflights13) dataset). A Flask web app makes it usable by anyone.

## Highlights

| | |
|---|---|
| 🎯 **Measured, not guessed** | 82.6% accuracy and 0.89 ROC-AUC on 67,356 flights the model never saw |
| 💡 **Explained predictions** | Each result lists the factors that pushed it toward late or on time |
| 🗺️ **Route-aware** | Distance, typical air time, airlines and past delay rate for 223 routes fill in automatically |
| ⏱️ **Works before takeoff** | Only the route and schedule are required; missing values are estimated and flagged |
| 📊 **Delay insights** | Interactive charts of delays by hour, month and airline |
| 🔌 **JSON API** | `POST /api/predict` returns the same answer for scripts and other apps |
| 🌗 **Polished interface** | Light and dark themes, phone friendly, still works without JavaScript |

## Model performance

Held-out test set: 20% of the data, `random_state=42`.

| Metric | Score |
|---|---|
| Accuracy | 82.6% |
| Precision (late) | 87.6% |
| Recall (late) | 68.4% |
| F1 (late) | 0.77 |
| ROC-AUC | 0.885 |

A flight counts as **late** when it arrives even one minute after its scheduled time.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000. Set `FLASK_DEBUG=1` to turn on auto-reload while developing.

## API

```bash
curl -X POST http://127.0.0.1:5000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"carrier": "UA", "origin": "EWR", "dest": "ORD", "date": "2013-12-20",
       "sched_dep_time": "18:00", "sched_arr_time": "19:35", "dep_time": "19:10"}'
```

| Field | Required | Notes |
|---|---|---|
| `carrier` | yes | Airline code, e.g. `AA`, `B6`, `UA` |
| `origin` | yes | `EWR`, `JFK` or `LGA` |
| `dest` | yes | Destination airport code |
| `date` | yes | `YYYY-MM-DD` |
| `sched_dep_time`, `sched_arr_time` | yes | `"14:05"` or `1405` |
| `dep_time`, `arr_time` | no | Actual times, estimated when missing |
| `dep_delay` | no | Minutes, computed from the departure times otherwise |
| `air_time`, `distance` | no | Minutes and miles, taken from the route otherwise |
| `flight` | no | Flight number |

The response includes `delayed`, `probability`, `confidence`, `factors`, `route` and `assumptions`. Invalid input returns status `422` with an `errors` object. `GET /api/routes` lists airlines, airports and routes.

## Project structure

```
├── app.py                  Flask app: validation, features, prediction, API
├── model.pkl               Trained logistic regression
├── data/reference.json     Route stats, model metrics, feature averages
├── scripts/build_reference.py
├── templates/
│   ├── index.html
│   └── _result.html        Result card (shared by the page and live updates)
├── static/
│   ├── styles.css
│   └── app.js              Form helpers, live results, charts
└── Projet_AI_Prédiction_des_retards_des_vols_Aya_Aidi_.ipynb
```

`data/reference.json` is generated from the dataset and the model. After retraining, rebuild it:

```bash
pip install nycflights13
python scripts/build_reference.py
```

## Limitations

- The model uses the actual departure and arrival times, so it works best once the plane is in the air.
- It learned from 2013 traffic. Airlines, schedules and airports have changed since then.
- Weather isn't part of the inputs.

---

AI project by **Aya Aidi**
