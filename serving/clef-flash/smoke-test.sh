#!/usr/bin/env bash
set -euo pipefail

INFERENCE_SERVICE="${INFERENCE_SERVICE:-clef-flash}"
NAMESPACE="${NAMESPACE:-default}"
API_KEY="${API_KEY:-${INFERENCE_SERVICE_API_KEY:-}}"

if [[ -z "${API_BASE:-}" ]]; then
  API_BASE="$(
    kubectl get inferenceservice "${INFERENCE_SERVICE}" \
      -n "${NAMESPACE}" \
      -o jsonpath='{.status.url}'
  )"
fi

if [[ -z "${API_BASE}" ]]; then
  printf 'InferenceService status.url is empty\n' >&2
  exit 1
fi

if [[ "${API_BASE}" == */serving/* && "${API_BASE}" != */svc/serving/* ]]; then
  API_BASE="${API_BASE/\/serving\//\/svc\/serving\/}"
fi

headers=(-H "content-type: application/json")
if [[ -n "${API_KEY}" ]]; then
  headers+=(-H "x-api-key: ${API_KEY}")
fi

response="$(mktemp)"
trap 'rm -f "${response}"' EXIT

curl --fail-with-body --silent --show-error \
  "${API_BASE%/}/v1/systemone" \
  "${headers[@]}" \
  --output "${response}" \
  --data @- <<'EOF'
{
  "model": "clef-flash",
  "state": {
    "invoice": {
      "vendor": "Acme",
      "total": 1250,
      "currency": "USD",
      "status": "overdue"
    }
  },
  "questions": {
    "status": {
      "type": "choice",
      "instructions": "What is the invoice status?",
      "criteria": {
        "paid": "Invoice is paid",
        "overdue": "Invoice is past due",
        "draft": "Invoice has not been sent"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgently should this invoice be handled?",
      "criteria": ["Can wait", "This week", "Today"]
    },
    "large": {
      "type": "noul",
      "instructions": "Is the total above 1000 USD?"
    }
  }
}
EOF

jq -e '
  .answers.status.choice as $status_choice |
  .model == "clef-flash" and
  .answers.status.type == "choice" and
  (["paid", "overdue", "draft"] | index($status_choice)) != null and
  (.answers.status.probabilities | keys | sort) == ["draft", "overdue", "paid"] and
  ([.answers.status.probabilities[]] | all(. >= 0 and . <= 1)) and
  (([.answers.status.probabilities[]] | add) - 1 | fabs < 0.001) and
  .answers.urgency.type == "score" and
  (.answers.urgency.score | type == "number") and
  (.answers.urgency.score >= 0 and .answers.urgency.score <= 2) and
  (.answers.urgency.probabilities | keys | sort) == ["0", "1", "2"] and
  ([.answers.urgency.probabilities[]] | all(. >= 0 and . <= 1)) and
  (([.answers.urgency.probabilities[]] | add) - 1 | fabs < 0.001) and
  .answers.large.type == "noul" and
  (.answers.large.noul | type == "number") and
  (.answers.large.noul >= 0 and .answers.large.noul <= 1)
' "${response}" >/dev/null

printf 'CLEF-Flash choice, score, and noul answers validated at %s\n' \
  "${API_BASE%/}/v1/systemone"
