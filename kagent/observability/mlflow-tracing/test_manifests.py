from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import yaml

ROOT: Final = Path(__file__).parent


def test_agent_exports_to_workspace_service_when_opted_in() -> None:
    agent = yaml.safe_load((ROOT / "assistant.yaml").read_text())
    collector = list(yaml.safe_load_all((ROOT / "otel-collector.yaml").read_text()))

    declarative = agent["spec"]["declarative"]
    env = {item["name"]: item["value"] for item in declarative["deployment"]["env"]}
    endpoint = urlsplit(env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"])
    service = next(item for item in collector if item["kind"] == "Service")

    assert agent["apiVersion"] == "kagent.dev/v1alpha2"
    assert agent["kind"] == "Agent"
    assert agent["spec"]["type"] == "Declarative"
    assert declarative["runtime"] == "python"
    assert "a2aConfig" in declarative
    assert declarative["modelConfig"] == "anthropic-haiku"
    assert env["OTEL_TRACING_ENABLED"] == "true"
    assert env["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] == "grpc"
    assert endpoint.scheme == "http"
    assert endpoint.hostname == service["metadata"]["name"] == "otel-collector"
    assert endpoint.port == service["spec"]["ports"][0]["port"] == 4317


def test_collector_authenticates_http_export_when_receiving_grpc() -> None:
    documents = list(yaml.safe_load_all((ROOT / "otel-collector.yaml").read_text()))
    configmap = next(item for item in documents if item["kind"] == "ConfigMap")

    config = yaml.safe_load(configmap["data"]["config.yaml"])
    exporter = config["exporters"]["otlphttp/mlflow"]
    pipeline = config["service"]["pipelines"]["traces"]

    assert config["receivers"]["otlp"]["protocols"] == {
        "grpc": {"endpoint": "${env:MY_POD_IP}:4317"}
    }
    assert pipeline["receivers"] == ["otlp"]
    assert pipeline["exporters"] == ["otlphttp/mlflow"]
    assert exporter["endpoint"] == "${env:MLFLOW_TRACKING_URI}"
    assert exporter["headers"] == {
        "X-Mlflow-Experiment-Id": "${env:MLFLOW_EXPERIMENT_ID}"
    }
    assert exporter["auth"]["authenticator"] == "basicauth/mlflow"
    assert "basicauth/mlflow" in config["service"]["extensions"]
    assert config["extensions"]["basicauth/mlflow"]["client_auth"] == {
        "username": "${env:MLFLOW_TRACKING_USERNAME}",
        "password": "${env:MLFLOW_TRACKING_PASSWORD}",
    }


def test_collector_uses_secret_and_mesh_probes_when_deployed() -> None:
    documents = list(yaml.safe_load_all((ROOT / "otel-collector.yaml").read_text()))
    deployment = next(item for item in documents if item["kind"] == "Deployment")

    template = deployment["spec"]["template"]
    container = template["spec"]["containers"][0]
    service = next(item for item in documents if item["kind"] == "Service")

    assert {item["kind"] for item in documents} == {
        "ConfigMap",
        "Deployment",
        "Service",
    }
    assert container["image"] == "otel/opentelemetry-collector-contrib:0.159.0"
    assert container["envFrom"] == [{"secretRef": {"name": "mlflow-credentials"}}]
    assert template["spec"]["securityContext"]["runAsNonRoot"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert (
        template["metadata"]["annotations"]["sidecar.istio.io/rewriteAppHTTPProbers"]
        == "true"
    )
    assert container["readinessProbe"]["httpGet"] == {"path": "/", "port": "health"}
    assert container["livenessProbe"]["httpGet"] == {"path": "/", "port": "health"}
    assert service["spec"]["selector"].items() <= template["metadata"]["labels"].items()
    grpc_port = next(port for port in container["ports"] if port["name"] == "otlp-grpc")
    assert service["spec"]["ports"][0]["targetPort"] == grpc_port["name"]
    assert grpc_port["containerPort"] == 4317
