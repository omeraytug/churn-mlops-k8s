# Churn API on Kubernetes

Individual fork of the team pipeline [pytt156/churn-mlops-pipeline](https://github.com/pytt156/churn-mlops-pipeline). It adds deployment of the churn prediction API to Kubernetes, locally in kind and in the course cloud cluster.

Live service: https://omer-aytug.89-167-53-206.sslip.io/version

## Pipeline

Every push and pull request to `main` runs `.github/workflows/ci.yml`:

1. `test` (Python 3.11–3.13), `datakontroll` (pandera schema) and `dependency-scan` (pip-audit)
2. `train`: trains the model and signs `modell.joblib` and `matvarden.json`
3. `evaluate`: verifies the model's hash and signature, ROC AUC ≥ 0.70, no regression against the champion model
4. `docker-smoke` and `docker-api-smoke`: build and smoke-test the images, the API on both amd64 and arm64
5. `publish` and `publish-api`: push the tested images to GHCR, tagged with the commit SHA (only on `main`)
6. `deploy-production`: deploys the API to the cloud cluster (only on `main`, after approval)

## Kubernetes manifests

- `k8s/deployment.yaml`: 2 replicas, resource requests and limits, startup/readiness/liveness probes on `/health`
- `k8s/service.yaml`: ClusterIP service on port 80
- `k8s/cloud/ingress.yaml`: HTTPS ingress, cloud only
- `k8s/kind/quota.yaml`: the same quota and defaults as the cloud namespace, kind only

The image in `k8s/deployment.yaml` is a template value. The pipeline sets the image to the current commit's SHA at deploy time, never `latest`.

## Environments

### Cloud

The `deploy-production` job deploys to the `production` environment, which requires approval and only accepts the `main` branch. It applies the manifests, waits for the rollout, and checks that `/version` through the ingress reports the deployed commit. If the rollout or that check fails, it rolls back automatically.

### kind

```bash
export KUBECONFIG=~/.kube/kind-churn.yaml
kind create cluster --name churn

SHA=$(git rev-parse origin/main)
kubectl apply -f k8s/kind/
kubectl set image -f k8s/deployment.yaml "api=ghcr.io/omeraytug/churn-mlops-k8s-api:$SHA" --local -o yaml | kubectl apply -f -
kubectl apply -f k8s/service.yaml
kubectl rollout status deployment/churn-api

kubectl port-forward svc/churn-api 8080:80
curl -s localhost:8080/version
```

The API image is published for both amd64 and arm64 under the same tag, so kind and the cloud cluster run the same image.

## Rollout strategy

Rolling update with `maxSurge: 1` and `maxUnavailable: 0`: a new pod has to pass its readiness probe before an old pod is removed, so the service never loses capacity.

- The API is stateless and the request format is the same across model versions, so old and new pods can serve side by side.
- Blue/green would keep two full copies running and use the entire memory quota of the namespace for as long as both run.
- Canary needs traffic splitting and enough traffic to compare versions, which this service does not have.
- A rollback is one command, and the pipeline runs it automatically when a deploy fails.

Update to a new version and roll back:

```bash
kubectl set image deployment/churn-api "api=ghcr.io/omeraytug/churn-mlops-k8s-api:<sha>"
kubectl rollout status deployment/churn-api

kubectl rollout undo deployment/churn-api
kubectl rollout history deployment/churn-api
```

## Operations plan

**Before deploy**, the pipeline stops bad data and bad models: pandera schema validation, a dependency scan, ROC AUC ≥ 0.70, a regression gate against the champion model and a provenance check of the model file.

**In production**, the real outcome (whether a customer churns) arrives months later, so the service is watched through proxies:

- the distribution of predicted `churn_risk` compared with the training data
- input data compared with the training data: new categories, shifted distributions, schema changes
- error rate and latency of the API

**What happens then:**

| Signal | Action |
|---|---|
| The service fails health checks or errors after a deploy | Roll back (`kubectl rollout undo`, automatic in the pipeline) |
| Predictions or input data drift but the service is healthy | Alert, then retrain on new data through the pipeline, where the validation and regression gates decide |
| Real outcomes show that the model got worse | Roll back to the previous version, then retrain |

The weekly scheduled pipeline run is the natural place for a drift check and retraining.
