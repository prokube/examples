from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import monotonic, sleep

from fastapi.testclient import TestClient

from clef_server.app import MAX_CONTENT_LENGTH, create_app

REQUEST = {
    "model": "clef-flash",
    "state": {"board": [".........."], "active_piece": "T"},
    "questions": {
        "move": {
            "type": "choice",
            "instructions": "Choose a placement",
            "criteria": {"r0-c3": "Flat placement", "r1-c4": "Upright placement"},
        },
        "risk": {
            "type": "score",
            "instructions": "Rate the board risk",
            "criteria": ["low", "medium", "high"],
        },
        "safe": {
            "type": "noul",
            "instructions": "Is this board safe?",
        },
    },
}

RESPONSE = {
    "model": "clef-flash",
    "answers": {
        "move": {
            "type": "choice",
            "choice": "r0-c3",
            "confidence": 0.8,
            "probabilities": {"r0-c3": 0.8, "r1-c4": 0.2},
        },
        "risk": {
            "type": "score",
            "score": 0.3,
            "confidence": 0.7,
            "legend": {"0": "low", "1": "medium", "2": "high"},
            "probabilities": {"0": 0.7, "1": 0.3, "2": 0.0},
        },
        "safe": {"type": "noul", "noul": 0.9},
    },
    "usage": {"input_tokens": 128, "output_tokens": 0},
}


class FakeAdapter:
    model_name = "clef-flash"

    def __init__(self, response: dict[str, object] | Exception = RESPONSE) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def decide(self, request: dict[str, object]) -> dict[str, object]:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def client(
    factory: Callable[[], FakeAdapter],
    max_content_length: int = MAX_CONTENT_LENGTH,
) -> TestClient:
    return TestClient(create_app(factory, max_content_length))


def wait_until_ready(test_client: TestClient) -> None:
    deadline = monotonic() + 1
    while monotonic() < deadline:
        if test_client.get("/health/ready").status_code == 200:
            return
        sleep(0.01)
    raise AssertionError("model did not become ready")


def test_systemone_returns_all_answer_types_and_usage() -> None:
    adapter = FakeAdapter()

    with client(lambda: adapter) as test_client:
        wait_until_ready(test_client)
        response = test_client.post("/v1/systemone", json=REQUEST)

    assert response.status_code == 200
    assert response.json() == RESPONSE
    assert adapter.requests == [
        {
            **REQUEST,
            "questions": {
                **REQUEST["questions"],
                "safe": {**REQUEST["questions"]["safe"], "criteria": None},
            },
        }
    ]


def test_model_is_initialized_once() -> None:
    calls = 0
    adapter = FakeAdapter()

    def factory() -> FakeAdapter:
        nonlocal calls
        calls += 1
        return adapter

    with client(factory) as test_client:
        wait_until_ready(test_client)
        assert test_client.post("/v1/systemone", json=REQUEST).status_code == 200
        assert test_client.post("/v1/systemone", json=REQUEST).status_code == 200

    assert calls == 1


def test_health_reflects_successful_model_loading() -> None:
    with client(FakeAdapter) as test_client:
        wait_until_ready(test_client)
        assert test_client.get("/health/live").json() == {"status": "live"}
        assert test_client.get("/health/ready").json() == {"status": "ready"}


def test_health_reflects_failed_model_loading() -> None:
    def fail() -> FakeAdapter:
        raise RuntimeError("sensitive model path")

    with client(fail) as test_client:
        response = test_client.get("/health/ready")
        deadline = monotonic() + 1
        while response.json() == {"status": "loading"} and monotonic() < deadline:
            sleep(0.01)
            response = test_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "failed"}
        live_response = test_client.get("/health/live")
        assert live_response.status_code == 503
        assert live_response.json() == {"status": "failed"}
        assert test_client.post("/v1/systemone", json=REQUEST).status_code == 503


def test_readiness_transitions_while_model_loads() -> None:
    release = Event()

    def load() -> FakeAdapter:
        release.wait(timeout=1)
        return FakeAdapter()

    with client(load) as test_client:
        assert test_client.get("/health/live").status_code == 200
        response = test_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "loading"}
        release.set()
        wait_until_ready(test_client)


def test_validation_errors_do_not_echo_request_content() -> None:
    invalid = {
        **REQUEST,
        "state": "secret state",
        "questions": {
            "move": {"type": "choice", "criteria": {}},
        },
    }

    with client(FakeAdapter) as test_client:
        wait_until_ready(test_client)
        response = test_client.post("/v1/systemone", json=invalid)

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid SystemOne request"}
    assert "secret state" not in response.text


def test_null_state_is_preserved_for_inference() -> None:
    adapter = FakeAdapter()
    request = {**REQUEST, "state": None}

    with client(lambda: adapter) as test_client:
        wait_until_ready(test_client)
        response = test_client.post("/v1/systemone", json=request)

    assert response.status_code == 200
    assert adapter.requests[0]["state"] is None


def test_single_option_questions_are_accepted() -> None:
    request = {
        **REQUEST,
        "questions": {
            "move": {"type": "choice", "criteria": {"only": "Only legal move"}},
            "risk": {"type": "score", "criteria": ["Only level"]},
        },
    }

    with client(FakeAdapter) as test_client:
        wait_until_ready(test_client)
        response = test_client.post("/v1/systemone", json=request)

    assert response.status_code == 200


def test_noul_rejects_unknown_criteria_keys() -> None:
    invalid = {
        **REQUEST,
        "questions": {
            "safe": {"type": "noul", "criteria": {"maybe": "Uncertain"}},
        },
    }

    with client(FakeAdapter) as test_client:
        wait_until_ready(test_client)
        response = test_client.post("/v1/systemone", json=invalid)

    assert response.status_code == 422


def test_inference_errors_are_safe() -> None:
    adapter = FakeAdapter(RuntimeError("CUDA allocation details"))

    with client(lambda: adapter) as test_client:
        wait_until_ready(test_client)
        response = test_client.post("/v1/systemone", json=REQUEST)

    assert response.status_code == 500
    assert response.json() == {"detail": "Decision inference failed"}
    assert "CUDA" not in response.text


def test_inference_is_serialized() -> None:
    active = 0
    maximum_active = 0
    lock = Lock()

    class SlowAdapter(FakeAdapter):
        def decide(self, request: dict[str, object]) -> dict[str, object]:
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            sleep(0.05)
            with lock:
                active -= 1
            return super().decide(request)

    with client(SlowAdapter) as test_client:
        wait_until_ready(test_client)
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda _index: test_client.post("/v1/systemone", json=REQUEST),
                    range(2),
                )
            )

    assert [response.status_code for response in responses] == [200, 200]
    assert maximum_active == 1


def test_rejects_oversized_requests_before_parsing() -> None:
    with client(FakeAdapter, max_content_length=8) as test_client:
        response = test_client.post(
            "/v1/systemone",
            content=b"{}",
            headers={"content-length": "9"},
        )

    assert response.status_code == 413


def test_rejects_oversized_chunked_requests() -> None:
    def chunks():
        yield b'{"state":'
        yield b'"too large"}'

    with client(FakeAdapter, max_content_length=8) as test_client:
        response = test_client.post(
            "/v1/systemone",
            content=chunks(),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
