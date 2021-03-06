import unittest
import threading
import time
import asyncio
import socket
import json
import io
import pytest
import datetime
from nabd import nabd
from mock import NabIOMock


class SocketIO(io.RawIOBase):
    """ Use RawIOBase for buffering lines """

    def __init__(self, sock):
        self.sock = sock

    def read(self, sz=-1):
        if sz == -1:
            sz = 0x7FFFFFFF
        return self.sock.recv(sz)

    def seekable(self):
        return False

    def write(self, b):
        return self.sock.send(b)

    def close(self):
        return self.sock.close()

    def settimeout(self, timeout):
        return self.sock.settimeout(timeout)


class TestNabd(unittest.TestCase):
    def nabd_thread_loop(self, kwargs):
        nabd_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(nabd_loop)
        self.nabd = nabd.Nabd(self.nabio)
        with self.nabd_cv:
            self.nabd_cv.notify()
        self.nabd.run()
        nabd_loop.close()

    def setUp(self):
        self.nabio = NabIOMock()
        self.nabd_cv = threading.Condition()
        with self.nabd_cv:
            self.nabd_thread = threading.Thread(
                target=self.nabd_thread_loop, args=[self]
            )
            self.nabd_thread.start()
            self.nabd_cv.wait()
        time.sleep(1)  # make sure Nabd was started

    def tearDown(self):
        self.nabd.stop()
        self.nabd_thread.join(5)

    def test_init(self):
        self.assertEqual(self.nabio.left_ear, 0)
        self.assertEqual(self.nabio.right_ear, 0)
        self.assertEqual(self.nabio.left_led, None)
        self.assertEqual(self.nabio.center_led, None)
        self.assertEqual(self.nabio.right_led, None)
        self.assertEqual(self.nabio.bottom_led, "pulse((255, 0, 255))")
        self.assertEqual(self.nabio.nose_led, None)

    def service_socket(self):
        s = socket.socket()
        s.connect(("0.0.0.0", 10543))
        s.settimeout(5.0)
        return SocketIO(s)

    def test_state(self):
        s = self.service_socket()
        try:
            packet = s.readline()
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "idle")
        finally:
            s.close()

    def test_sleep_wakeup(self):
        s1 = self.service_socket()
        s2 = self.service_socket()
        try:
            packet = s1.readline()  # state packet
            packet = s2.readline()  # state packet
            s1.write(b'{"type":"sleep","request_id":"test_id"}\r\n')
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "test_id")
            self.assertEqual(packet_j["status"], "ok")
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "asleep")
            packet = s2.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "asleep")
            s1.write(b'{"type":"wakeup","request_id":"wakeup_request"}\r\n')
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "wakeup_request")
            self.assertEqual(packet_j["status"], "ok")
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "idle")
            packet = s2.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "idle")
        finally:
            s1.close()
            s2.close()

    def test_sleep_message_wakeup(self):
        s1 = self.service_socket()
        s2 = self.service_socket()
        try:
            packet = s1.readline()  # state packet
            packet = s2.readline()  # state packet
            s1.write(b'{"type":"sleep","request_id":"test_id"}\r\n')
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "test_id")
            self.assertEqual(packet_j["status"], "ok")
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "asleep")
            packet = s2.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "asleep")
            s2.write(
                b'{"type":"command",'
                b'"request_id":"command_request_1","sequence":[]}\r\n'
            )
            s2.write(
                b'{"type":"command",'
                b'"request_id":"command_request_2","sequence":[]}\r\n'
            )
            s1.write(b'{"type":"wakeup","request_id":"wakeup_request"}\r\n')
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "wakeup_request")
            self.assertEqual(packet_j["status"], "ok")
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "playing")
            packet = s2.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "playing")
            time.sleep(3)  # give time to play sequence
            packet = s2.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "command_request_1")
            self.assertEqual(packet_j["status"], "ok")
            time.sleep(3)  # give time to play sequence
            packet = s2.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "command_request_2")
            self.assertEqual(packet_j["status"], "ok")
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "idle")
            packet = s2.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "idle")
        finally:
            s1.close()
            s2.close()

    def test_info_id_required(self):
        s1 = self.service_socket()
        try:
            packet = s1.readline()  # state packet
            s1.write(b'{"type":"info","request_id":"test_id"}\r\n')
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "test_id")
            self.assertEqual(packet_j["status"], "error")
            self.assertEqual(packet_j["class"], "MalformedPacket")
        finally:
            s1.close()

    def test_info(self):
        s1 = self.service_socket()
        self.assertEqual(self.nabio.played_infos, [])
        try:
            packet = s1.readline()  # state packet
            # [25 {3 3 3 3 3 3 3 3 3 3 3 3 3 3 3 0 0 0 0 0 0 0 0 0}] // soleil
            s1.write(
                b'{"type":"info",'
                b'"info_id":"weather","request_id":"test_id",'
                b'"animation":{"tempo":25,"colors":['
                b'{"left":"ffff00","center":"ffff00","right":"ffff00"},'
                b'{"left":"ffff00","center":"ffff00","right":"ffff00"},'
                b'{"left":"ffff00","center":"ffff00","right":"ffff00"},'
                b'{"left":"ffff00","center":"ffff00","right":"ffff00"},'
                b'{"left":"ffff00","center":"ffff00","right":"ffff00"},'
                b'{"left":"000000","center":"000000","right":"000000"},'
                b'{"left":"000000","center":"000000","right":"000000"},'
                b'{"left":"000000","center":"000000","right":"000000"}]}}'
                b"\r\n"
            )
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "test_id")
            self.assertEqual(packet_j["status"], "ok")
            time.sleep(10)  # give time to play info once
            last_info = self.nabio.played_infos.pop()
            self.assertEqual(
                last_info,
                {
                    "tempo": 25,
                    "colors": [
                        {
                            "left": "ffff00",
                            "center": "ffff00",
                            "right": "ffff00",
                        },
                        {
                            "left": "ffff00",
                            "center": "ffff00",
                            "right": "ffff00",
                        },
                        {
                            "left": "ffff00",
                            "center": "ffff00",
                            "right": "ffff00",
                        },
                        {
                            "left": "ffff00",
                            "center": "ffff00",
                            "right": "ffff00",
                        },
                        {
                            "left": "ffff00",
                            "center": "ffff00",
                            "right": "ffff00",
                        },
                        {
                            "left": "000000",
                            "center": "000000",
                            "right": "000000",
                        },
                        {
                            "left": "000000",
                            "center": "000000",
                            "right": "000000",
                        },
                        {
                            "left": "000000",
                            "center": "000000",
                            "right": "000000",
                        },
                    ],
                },
            )
            # [25 {3 3 3 3 3 3 3 3 3 3 3 3 3 3 3 0 0 0 0 0 0 0 0 0}] // soleil
            s1.write(
                b'{"type":"info","info_id":"weather",'
                b'"request_id":"clear_id"}\r\n'
            )
            packet = s1.readline()  # response packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "clear_id")
            self.assertEqual(packet_j["status"], "ok")
            time.sleep(20)  # make sure info is not played
            self.assertEqual(self.nabio.played_infos, [])
        finally:
            s1.close()

    def test_command(self):
        s1 = self.service_socket()
        try:
            packet = s1.readline()  # state packet
            s1.write(
                b'{"type":"command","request_id":"test_id",'
                b'"sequence":{"audio":['
                b'"weather/fr/signature.mp3","weather/fr/today.mp3",'
                b'"weather/fr/sky/0.mp3","weather/fr/temp/42.mp3",'
                b'"weather/fr/temp/degree.mp3",'
                b'"weather/fr/temp/signature.mp3"],'
                b'"choregraphy":"streaming"}}\r\n'
            )
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "playing")
            s1.settimeout(15.0)
            packet = s1.readline()  # response packet
            s1.settimeout(5.0)
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["request_id"], "test_id")
            self.assertEqual(packet_j["status"], "ok")
            last_sequence = self.nabio.played_sequences.pop()
            self.assertEqual(
                last_sequence,
                {
                    "audio": [
                        "weather/fr/signature.mp3",
                        "weather/fr/today.mp3",
                        "weather/fr/sky/0.mp3",
                        "weather/fr/temp/42.mp3",
                        "weather/fr/temp/degree.mp3",
                        "weather/fr/temp/signature.mp3",
                    ],
                    "choregraphy": "streaming",
                },
            )
            packet = s1.readline()  # new state packet
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "idle")
        finally:
            s1.close()

    def test_expiration_not_expired(self):
        s1 = self.service_socket()
        try:
            packet = s1.readline()  # state packet
            now = datetime.datetime.now()
            expiration = now + datetime.timedelta(minutes=3)
            packet = (
                '{"type":"command","request_id":"test_id",'
                '"sequence":{"audio":['
                '"weather/fr/signature.mp3","weather/fr/today.mp3",'
                '"weather/fr/sky/0.mp3","weather/fr/temp/42.mp3",'
                '"weather/fr/temp/degree.mp3",'
                '"weather/fr/temp/signature.mp3"],'
                '"choregraphy":"streaming"},'
                '"expiration":"' + expiration.isoformat() + '"}\r\n'
            )
            s1.write(packet.encode("utf8"))
            packet = s1.readline()  # new state packet
            print(f"packet={packet}")
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "state")
            self.assertEqual(packet_j["state"], "playing")
        finally:
            s1.close()

    def test_expiration_expired(self):
        s1 = self.service_socket()
        try:
            packet = s1.readline()  # state packet
            now = datetime.datetime.now()
            expiration = now + datetime.timedelta(minutes=-1)
            packet = (
                '{"type":"command","request_id":"test_id",'
                '"sequence":{"audio":['
                '"weather/fr/signature.mp3","weather/fr/today.mp3",'
                '"weather/fr/sky/0.mp3","weather/fr/temp/42.mp3",'
                '"weather/fr/temp/degree.mp3",'
                '"weather/fr/temp/signature.mp3"],'
                '"choregraphy":"streaming"},'
                '"expiration":"' + expiration.isoformat() + '"}\r\n'
            )
            s1.write(packet.encode("utf8"))
            packet = s1.readline()  # new state packet
            print(f"packet={packet}")
            packet_j = json.loads(packet.decode("utf8"))
            self.assertEqual(packet_j["type"], "response")
            self.assertEqual(packet_j["status"], "expired")
        finally:
            s1.close()
