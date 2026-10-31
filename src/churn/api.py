import json
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

from churn.data import FEATURES, skapa_features

MODEL_DIR = Path(__file__).resolve().parents[2] / "outputs"


class Kund(BaseModel):
    alder: int = Field(ge=0)
    manader_som_kund: int = Field(ge=0)
    manadskostnad: float = Field(ge=0)
    data_gb_per_manad: float = Field(ge=0)
    supportarenden_12m: int = Field(ge=0)
    region: str
    abonnemang: str


class Prediction(BaseModel):
    churn_risk: float


class ModelVersion(BaseModel):
    commit: str
    run_id: str
    roc_auc: float
    model_sha256: str


def to_row(kund: Kund) -> pd.DataFrame:
    df = pd.DataFrame([kund.model_dump()])
    return skapa_features(df)[FEATURES]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = joblib.load(MODEL_DIR / "modell.joblib")
    app.state.version = json.loads((MODEL_DIR / "matvarden.json").read_text())
    yield


app = FastAPI(title="Churn Prediction API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version", response_model=ModelVersion)
def version() -> dict[str, str | float]:
    return app.state.version


@app.post("/predict", response_model=Prediction)
def predict(kund: Kund) -> Prediction:
    model = app.state.model
    probability = model.predict_proba(to_row(kund))[0, 1]
    return Prediction(churn_risk=round(float(probability), 3))
