import json

from fastapi.testclient import TestClient

from churn.api import MODEL_DIR, app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_matches_trained_model():
    metrics = json.loads((MODEL_DIR / "matvarden.json").read_text())

    with TestClient(app) as client:
        response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "commit": metrics["commit"],
        "run_id": metrics["run_id"],
        "roc_auc": metrics["roc_auc"],
        "model_sha256": metrics["model_sha256"],
    }


def test_predict():
    kund = {
        "alder": 42,
        "manader_som_kund": 18,
        "manadskostnad": 399,
        "data_gb_per_manad": 25,
        "supportarenden_12m": 3,
        "region": "Stockholm",
        "abonnemang": "Bas",
    }

    with TestClient(app) as client:
        response = client.post("/predict", json=kund)

    assert response.status_code == 200
    assert 0 <= response.json()["churn_risk"] <= 1


def test_predict_invalid_data():
    kund = {
        "alder": -5,
        "manader_som_kund": 18,
        "manadskostnad": 399,
        "data_gb_per_manad": 25,
        "supportarenden_12m": 3,
        "region": "Stockholm",
        "abonnemang": "Bas",
    }

    with TestClient(app) as client:
        response = client.post("/predict", json=kund)

    assert response.status_code == 422
