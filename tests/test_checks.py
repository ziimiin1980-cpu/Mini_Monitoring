import httpx
import pytest

from app import checks
from app.checks import check_http, check_process, check_tcp, run_check

# ---------- HTTP ----------


class FakeResponse:
    def __init__(self, status_code: int, url: str = "https://example.com/"):
        self.status_code = status_code
        self.url = url


class FakeClient:
    """Заглушка httpx.Client: запоминает вызов и возвращает заданный ответ."""

    calls: list[tuple[str, str]] = []
    last_kwargs: dict = {}
    response = FakeResponse(200)
    exception: Exception | None = None

    def __init__(self, *args, **kwargs):
        FakeClient.last_kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(self, method, url):
        FakeClient.calls.append((method, url))
        if FakeClient.exception is not None:
            raise FakeClient.exception
        return FakeClient.response


@pytest.fixture
def fake_http(monkeypatch):
    FakeClient.calls = []
    FakeClient.last_kwargs = {}
    FakeClient.response = FakeResponse(200)
    FakeClient.exception = None
    monkeypatch.setattr("app.checks.http.httpx.Client", FakeClient)
    return FakeClient


def test_http_ok_with_default_expectations(fake_http):
    outcome = check_http({"url": "https://example.com"}, timeout=3)

    assert outcome.ok is True
    assert outcome.status_code == 200
    assert outcome.error is None
    assert outcome.latency_ms is not None


def test_http_passes_method_and_url(fake_http):
    check_http({"url": "https://example.com/health", "method": "head"})

    assert fake_http.calls == [("HEAD", "https://example.com/health")]


def test_http_reports_unexpected_status(fake_http):
    fake_http.response = FakeResponse(500)

    outcome = check_http({"url": "https://example.com"})

    assert outcome.ok is False
    assert outcome.status_code == 500
    assert "500" in outcome.error


def test_http_supports_custom_expected_status(fake_http):
    fake_http.response = FakeResponse(204)

    outcome = check_http({"url": "https://example.com", "expected_status": 204})

    assert outcome.ok is True


def test_http_timeout(fake_http):
    fake_http.exception = httpx.ConnectTimeout("timeout")

    outcome = check_http({"url": "https://example.com"}, timeout=2)

    assert outcome.ok is False
    assert "Таймаут" in outcome.error


def test_http_connection_error(fake_http):
    fake_http.exception = httpx.ConnectError("connection refused")

    outcome = check_http({"url": "https://example.com"})

    assert outcome.ok is False
    assert "Ошибка запроса" in outcome.error


def test_http_without_url(fake_http):
    outcome = check_http({})

    assert outcome.ok is False
    assert "url" in outcome.error
    assert fake_http.calls == []


def test_http_sends_browser_headers(fake_http):
    check_http({"url": "https://example.com"})

    headers = fake_http.last_kwargs["headers"]
    assert "Mozilla/5.0" in headers["User-Agent"]
    assert "Accept" in headers


def test_http_custom_user_agent(fake_http):
    check_http({"url": "https://example.com", "user_agent": "MyMonitor/1.0"})

    assert fake_http.last_kwargs["headers"]["User-Agent"] == "MyMonitor/1.0"


def test_http_accept_any_status_success(fake_http):
    fake_http.response = FakeResponse(403)

    outcome = check_http({"url": "https://example.com", "accept_any_status": True})

    assert outcome.ok is True
    assert outcome.status_code == 403
    assert outcome.error is None


def test_http_accept_any_status_still_fails_on_5xx(fake_http):
    fake_http.response = FakeResponse(503)

    outcome = check_http({"url": "https://example.com", "accept_any_status": True})

    assert outcome.ok is False
    assert "503" in outcome.error


# ---------- TCP ----------


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def tcp_calls(monkeypatch):
    """Подменяет подключение по TCP и запоминает переданные аргументы."""
    calls: list[tuple[tuple[str, int], float]] = []
    state: dict[str, Exception | None] = {"error": None}

    def fake_create_connection(address, timeout=None):
        calls.append((address, timeout))
        if state["error"] is not None:
            raise state["error"]
        return FakeSocket()

    monkeypatch.setattr("app.checks.tcp.socket.create_connection", fake_create_connection)
    return calls, state


def test_tcp_ok(tcp_calls):
    calls, _ = tcp_calls

    outcome = check_tcp({"host": "127.0.0.1", "port": 5432}, timeout=4)

    assert outcome.ok is True
    assert outcome.latency_ms is not None
    assert calls == [(("127.0.0.1", 5432), 4)]


def test_tcp_timeout(tcp_calls):
    _, state = tcp_calls
    state["error"] = TimeoutError("timed out")

    outcome = check_tcp({"host": "10.0.0.1", "port": 80}, timeout=1)

    assert outcome.ok is False
    assert "Таймаут" in outcome.error


def test_tcp_connection_refused(tcp_calls):
    _, state = tcp_calls
    state["error"] = ConnectionRefusedError(10061, "connection refused")

    outcome = check_tcp({"host": "127.0.0.1", "port": 9})

    assert outcome.ok is False
    assert "Не удалось подключиться" in outcome.error


def test_tcp_does_not_connect_for_invalid_config(tcp_calls):
    calls, _ = tcp_calls

    bad_port = check_tcp({"host": "127.0.0.1", "port": 0})
    no_host = check_tcp({"host": "", "port": 80})

    assert bad_port.ok is False
    assert no_host.ok is False
    assert calls == []


# ---------- Процесс ----------


class FakeProcess:
    def __init__(self, pid: int, name: str | None):
        self.pid = pid
        self.info = {"name": name}


@pytest.fixture
def fake_processes(monkeypatch):
    processes: list[FakeProcess] = [FakeProcess(1234, "python.exe")]
    monkeypatch.setattr("app.checks.process.psutil.process_iter", lambda attrs=None: processes)
    return processes


def test_process_found_case_insensitive(fake_processes):
    outcome = check_process({"name": "Python.EXE"})

    assert outcome.ok is True
    assert outcome.details == {"name": "Python.EXE", "pid": 1234}


def test_process_not_found(fake_processes):
    outcome = check_process({"name": "nginx.exe"})

    assert outcome.ok is False
    assert "не найден" in outcome.error


def test_process_without_name(fake_processes):
    outcome = check_process({})

    assert outcome.ok is False
    assert "имя процесса" in outcome.error


# ---------- Диспетчер ----------


def test_run_check_unknown_type():
    outcome = run_check("ftp", {})

    assert outcome.ok is False
    assert "Неизвестный тип проверки" in outcome.error


def test_run_check_dispatches_to_process_checker(fake_processes):
    outcome = run_check("process", {"name": "python.exe"})

    assert outcome.ok is True


def test_run_check_never_raises(monkeypatch):
    def broken_checker(config, timeout):
        raise RuntimeError("внутренняя поломка")

    monkeypatch.setitem(checks.CHECKERS, "http", broken_checker)

    outcome = run_check("http", {"url": "https://example.com"})

    assert outcome.ok is False
    assert "Непредвиденная ошибка" in outcome.error
