import io

from lcp import ui


class FakeKernel32:
    def __init__(self) -> None:
        self.output_cp = None
        self.input_cp = None

    def SetConsoleOutputCP(self, codepage: int) -> None:
        self.output_cp = codepage

    def SetConsoleCP(self, codepage: int) -> None:
        self.input_cp = codepage


class FakeWindll:
    def __init__(self) -> None:
        self.kernel32 = FakeKernel32()


def test_configure_windows_stdio_reconfigures_streams(monkeypatch) -> None:
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    windll = FakeWindll()
    monkeypatch.setattr(ui.sys, "platform", "win32")
    monkeypatch.setattr(ui.sys, "stdout", stdout)
    monkeypatch.setattr(ui.sys, "stderr", stderr)
    monkeypatch.setattr(ui.ctypes, "windll", windll, raising=False)

    ui._configure_windows_stdio()

    assert stdout.encoding == "utf-8"
    assert stderr.encoding == "utf-8"
    assert windll.kernel32.output_cp == 65001
    assert windll.kernel32.input_cp == 65001


def test_configure_windows_stdio_skips_non_windows(monkeypatch) -> None:
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(ui.sys, "platform", "linux")
    monkeypatch.setattr(ui.sys, "stdout", stdout)

    ui._configure_windows_stdio()

    assert stdout.errors == "strict"
