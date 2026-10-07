"""whisper_server.py without a model or a graphics card: who listens on the port, the model path for whisper-server,
control characters, bringing back a server that died.

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_core*.py"
"""
import atexit
import http.server
import logging
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("ORBIT_TEST_ROOT") or Path(__file__).resolve().parent.parent)  # another copy: before/after
if "app.config" not in sys.modules:  # nothing a test does may touch the real data folder or Claude Code
    _tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
    atexit.register(shutil.rmtree, _tmp, True)
    os.environ["ORBIT_DATA_DIR"], os.environ["ORBIT_CLAUDE_DIR"] = str(_tmp / "data"), str(_tmp / "claude")
    sys.path.insert(0, str(ROOT))
    logging.getLogger().addHandler(logging.NullHandler())  # the code's warnings aren't test output

from app import config, whisper_server as ws  # noqa: E402

assert "orbit-test-" in str(config.DATA_DIR), config.DATA_DIR

# A stand-in for whisper-server.exe: listens on the port only after a "model load" (argv: port, delay, prefix).
FAKE_SERVER = r"""
import http.server, sys, time
port, delay, prefix = int(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
time.sleep(delay)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == prefix + "/health" else 404)
        self.end_headers()
    def log_message(self, *a):
        pass
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


class Impostor:
    """Another program that took the port first: counts what it gets."""

    def __init__(self):
        hits = self.hits = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()

            def do_POST(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"text": "!powershell -c start calc. Ode\\u0161li."}')

            def log_message(self, *a):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Listeners(unittest.TestCase):
    def test_own_listener_and_free_port(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            self.assertEqual(ws._listeners(port), set())  # bound, not listening
            s.listen()
            self.assertEqual(ws._listeners(port), {os.getpid()})
        self.assertEqual(ws._listeners(port), set())

    def test_ipv6_listener_counts(self):
        try:
            s = socket.socket(socket.AF_INET6)
        except OSError:
            self.skipTest("bez IPv6")
        with s:
            s.bind(("::1", 0))
            s.listen()
            self.assertEqual(ws._listeners(s.getsockname()[1]), {os.getpid()})


class ModelArg(unittest.TestCase):
    def test_plain_path_stays(self):
        model = Path(r"C:\Users\josef\orbit\models\ggml-large-v3.bin")
        self.assertEqual(ws._model_arg(model, Path(r"C:\Users\josef\orbit\whisper")), str(model))

    def test_cyrillic_folder_goes_relative(self):
        model = Path("C:\\Users\\\u041e\u043b\u0435\u0433\\AppData\\Local\\Orbit\\models\\ggml-large-v3.bin")
        cwd = Path("C:\\Users\\\u041e\u043b\u0435\u0433\\AppData\\Local\\Programs\\Orbit\\whisper")
        self.assertEqual(ws._model_arg(model, cwd), r"..\..\..\Orbit\models\ggml-large-v3.bin")

    def test_short_path_when_relative_does_not_help(self):
        top = Path(tempfile.mkdtemp(prefix="orbit-test-"))
        self.addCleanup(shutil.rmtree, top, True)
        folder = top / "\u041e\u043b\u0435\u0433"
        folder.mkdir()
        model = folder / "ggml-dummy.bin"
        model.write_bytes(b"x")
        arg = ws._model_arg(model, Path(r"C:\Windows"))
        short = ws._short_path(model)
        if not short.isascii():
            self.skipTest("8.3 jména jsou na tomhle disku vypnutá")
        self.assertEqual(arg, short)
        self.assertTrue(Path(arg).is_file())


class CleanText(unittest.TestCase):
    def test_control_characters_go(self):
        self.assertEqual(ws.clean_text("ahoj\x1b[2J světe\x07\x00 jak\x9b se máš"), "ahoj [2J světe jak se máš")
        self.assertEqual(ws.clean_text(" Dobrý\tden,\nPepo. "), "Dobrý den, Pepo.")


class FakeLaunch(unittest.TestCase):
    """_launch with a Python stand-in for whisper-server.exe (only Popen is replaced)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="orbit-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "models").mkdir()
        (self.tmp / "models" / "ggml-fake.bin").write_bytes(b"x")
        self.patches = {"MODELS_DIR": ws.MODELS_DIR, "_free_port": ws._free_port}
        ws.MODELS_DIR = self.tmp / "models"
        self.real_popen = subprocess.Popen
        self.delay = "0.3"

        def popen(args, **kw):  # base python.exe, so the pid that listens is the pid Orbit started
            port, prefix = args[args.index("--port") + 1], args[args.index("--request-path") + 1]
            script = self.tmp / "fake_server.py"
            script.write_text(FAKE_SERVER, encoding="utf-8")
            kw.pop("cwd", None)
            return self.real_popen([sys._base_executable, str(script), port, self.delay, prefix], **kw)

        subprocess.Popen = popen

    def tearDown(self):
        subprocess.Popen = self.real_popen
        for name, value in self.patches.items():
            setattr(ws, name, value)

    def test_ready_when_its_own_process_listens(self):
        server = ws.WhisperServer()
        try:
            server.start("ggml-fake.bin")
            self.assertTrue(server.wait_ready(0))
            self.assertEqual(ws._listeners(server._port), {server._proc.pid})
        finally:
            server.stop()

    def test_impostor_on_the_port_gets_nothing(self):
        impostor = Impostor()
        ws._free_port = lambda: impostor.port  # every try lands on the taken port
        self.delay = "30"  # the real one would still be loading its model
        server = ws.WhisperServer()
        try:
            t0 = time.time()
            with self.assertRaises(RuntimeError):
                server.start("ggml-fake.bin")
            self.assertLess(time.time() - t0, 10)
            self.assertFalse(server.wait_ready(0))
            self.assertEqual(impostor.hits, [])  # not even /health with the secret prefix
        finally:
            server.stop()
            impostor.close()

    def test_moves_to_another_port_when_one_is_taken(self):
        impostor = Impostor()
        ports = [impostor.port]
        real_free = self.patches["_free_port"]
        ws._free_port = lambda: ports.pop() if ports else real_free()
        server = ws.WhisperServer()
        try:
            server.start("ggml-fake.bin")
            self.assertTrue(server.wait_ready(0))
            self.assertNotEqual(server._port, impostor.port)
            self.assertEqual(impostor.hits, [])
        finally:
            server.stop()
            impostor.close()

    def test_transcribe_refuses_a_port_someone_else_listens_on(self):
        server = ws.WhisperServer()
        impostor = Impostor()
        try:
            server.start("ggml-fake.bin")
            with server._lock:  # as if the port changed hands since the start
                server._port = impostor.port
            server._lost = lambda proc: False
            with self.assertRaises(RuntimeError):
                server.transcribe(ws.np.zeros(16000, dtype=ws.np.int16))
            self.assertEqual(impostor.hits, [])
        finally:
            server.stop()
            impostor.close()


class Recovery(unittest.TestCase):
    """_recover with a fake _launch, no processes."""

    def setUp(self):
        self.saved = ws.RESTART_DELAYS, ws._gpu_here
        ws.RESTART_DELAYS = (0, 0, 0, 0)
        ws._gpu_here = lambda: True

    def tearDown(self):
        ws.RESTART_DELAYS, ws._gpu_here = self.saved

    def server(self, launch):
        events = []
        server = ws.WhisperServer(on_event=lambda kind, text: events.append(kind))
        server._launch = launch
        server._watch = lambda proc, epoch: None
        server._model, server._epoch, server._recovering = "m", 1, True
        return server, events

    def test_an_oserror_ends_with_failed(self):
        def launch(epoch, cpu):
            raise OSError(1455, "Stránkovací soubor je příliš malý")
        server, events = self.server(launch)
        server._recover(1)
        self.assertEqual(events, ["restarting", "failed"])
        self.assertFalse(server._recovering)
        t0 = time.time()
        with self.assertRaises(RuntimeError):
            server.transcribe(ws.np.zeros(16000, dtype=ws.np.int16))
        self.assertLess(time.time() - t0, 2)

    def test_watch_thread_never_dies_quietly(self):
        server, events = self.server(None)
        del server._watch

        class Proc:
            pid = 1

            def wait(self):
                return 0xC0000005

        proc = Proc()
        server._proc = proc
        server._recover = lambda epoch: (_ for _ in ()).throw(ValueError("boom"))
        server._watch(proc, 1)
        self.assertEqual(events, ["failed"])
        self.assertFalse(server._recovering)

    def test_card_not_back_yet_is_not_the_processor_for_good(self):
        calls = []

        class Proc:
            pid = 1

            def poll(self):
                return None

        def launch(epoch, cpu):
            calls.append(cpu)
            if not cpu and len(calls) < 3:  # the driver is still resetting
                raise ws._EarlyExit("Vulkan nejde")
            server._proc = proc = Proc()
            return proc, "cpu" if cpu else "gpu", "" if cpu else "Radeon"

        server, events = self.server(launch)
        server._recover(1)
        self.assertEqual(calls, [False, False, False])
        self.assertEqual(server.backend, "gpu")
        self.assertFalse(server._no_gpu)
        self.assertEqual(events, ["restarting", "backend", "restarted"])

    def test_processor_on_the_last_try(self):
        calls = []

        class Proc:
            pid = 1

            def poll(self):
                return None

        def launch(epoch, cpu):
            calls.append(cpu)
            if not cpu:
                raise ws._EarlyExit("Vulkan nejde")
            server._proc = proc = Proc()
            return proc, "cpu", ""

        server, events = self.server(launch)
        server._recover(1)
        self.assertEqual(calls, [False, False, False, False, True])
        self.assertEqual(server.backend, "cpu")
        self.assertEqual(events[-1], "restarted")


if __name__ == "__main__":
    unittest.main()
