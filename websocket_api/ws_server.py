import base64
import hashlib
from enum import Enum
import socket
import struct
import threading
import time
import typing
import string
import random


class ClientState(Enum):
    DISCONNECT = 0
    CONNECT = 1


class ServerState(Enum):
    OPEN = 0
    CLOSE = 1


class OPCODE:
    EXTRA = 0x0
    TEXT = 0x1
    BIN = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


class WebsocketError(Exception):
    pass


class ClientClosingError(WebsocketError):
    pass


class ClientClosedError(WebsocketError):
    pass


class ProtocolError(WebsocketError):
    pass


class WSClient():
    def __init__(self, conn: 'socket.__socket'):
        self.__conn = conn
        self.__state = ClientState.DISCONNECT
        self.__prev_recv_time = time.time()
        self.__id = ''.join(random.sample(string.ascii_letters, 8))
        # locks
        self.__read_lock = threading.Lock()
        # handshake
        self.__handshake()

    # ==========
    # properties
    # ==========

    @property
    def id(self):
        return self.__id

    # ==========
    # handshake
    # ==========

    def __check_request_header(self, request_headers):
        if 'Upgrade' not in request_headers or request_headers["Upgrade"] != 'websocket':
            raise ProtocolError("Error connection protocol")
        elif "Sec-WebSocket-Key" not in request_headers:
            raise ProtocolError("No Sec-Websocket-Key")

    def __make_response(self, request_headers):

        key = request_headers.get('Sec-WebSocket-Key') + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        resp_key = base64.standard_b64encode(hashlib.sha1(key.encode()).digest()).decode()
        res_header = {
            'Upgrade': 'websocket',
            'Connection': 'Upgrade',
            'Sec-WebSocket-Accept': resp_key,
        }
        response = 'HTTP/1.1 101 Switching Protocols\r\n'
        for i in res_header:
            response += '%s: %s\r\n' % (i, res_header[i])
        response += '\r\n'
        return response

    def __handshake(self):
        request = self.__conn.recv(1024).strip().decode('utf-8', 'ignore').split('\r\n')
        header = dict([line.split(': ', 1) for line in request[1:]])

        self.__check_request_header(header)
        response = self.__make_response(header)

        self.__conn.send(response.encode())
        self.set_state(ClientState.CONNECT)

    # ==========
    # state
    # ==========

    def set_state(self, state: 'ClientState'):
        self.__state = state

    def in_state(self, state: 'ClientState'):
        return self.__state == state

    def is_connected(self):
        return self.in_state(ClientState.CONNECT)

    # ==========
    # receive
    # ==========

    def __read_opcode(self):
        byte = self.__conn.recv(1)
        if byte is None:
            self.__on_client_closing("Received empty payload")
            return
        return byte[0] & 0xf

    def __read_payload_length(self):
        length = self.__conn.recv(1)[0] & 0x7f
        if length == 126:
            length, = struct.unpack('>H', self.__conn.recv(2))
        elif length == 127:
            length, = struct.unpack('>Q', self.__conn.recv(8))
        return length

    def __read_mask(self):
        return self.__conn.recv(4)

    def __read_data(self, length, mask):
        data = self.__conn.recv(length)
        decoded = bytearray()
        for i in range(length):
            decoded.append(data[i] ^ mask[i % 4])
        return decoded.decode('utf-8', 'ignore')

    def __update_prev_recv_time(self, timestamp=None):
        self.__prev_recv_time = timestamp or time.time()

    def get_prev_recv_time(self):
        return self.__prev_recv_time

    def recv(self):
        if self.in_state(ClientState.CONNECT):
            with self.__read_lock:
                try:
                    opcode = self.__read_opcode()
                    length = self.__read_payload_length()
                    mask = self.__read_mask()

                    self.__update_prev_recv_time()

                    if opcode == OPCODE.TEXT:
                        return opcode, self.__read_data(length, mask)
                    elif opcode == OPCODE.CLOSE:
                        self.__read_data(length, mask)
                        self.__on_client_closing("Received close packet")
                    elif opcode == OPCODE.PONG:
                        self.__on_recv_pong()
                    return opcode, None
                except ConnectionAbortedError as e:
                    raise ClientClosedError()
        else:
            raise ClientClosedError("Client is in disconnect state")

    # ==========
    # send
    # ==========

    def send(self, data):
        if self.in_state(ClientState.CONNECT):
            data = data.encode('utf-8')
            buffer = struct.pack('>B', 0x80 | OPCODE.TEXT)
            if len(data) > 126:
                if len(data) < 1024:  # 126 <= len < 1024
                    buffer += struct.pack('>BH', 126, len(data))
                else:  # len >= 1024
                    buffer += struct.pack('>BQ', 127, len(data))
            else:  # len < 126
                buffer += struct.pack('>B', len(data))
            buffer += data
            try:
                self.__conn.send(buffer)
            except ConnectionResetError:
                self.__on_client_closing()
        else:
            raise ClientClosedError("Client is in disconnect state")

    def ping(self):
        if self.in_state(ClientState.CONNECT):
            buffer = struct.pack('>B', 0x80 | OPCODE.PING)
            buffer += struct.pack('>B', 0)
            try:
                self.__conn.send(buffer)
            except ConnectionResetError:
                self.__on_client_closing()
        else:
            raise ClientClosedError("Client is in disconnect state")

    # ==========
    # close
    # ==========

    def close(self):
        if self.in_state(ClientState.CONNECT):
            self.set_state(ClientState.DISCONNECT)
            self.__conn.close()
            return True
        return False

    # ==========
    # event handler
    # ==========

    def __on_client_closing(self, info):
        self.__conn.close()
        raise ClientClosingError(info)

    def __on_recv_pong(self):
        # print(self.id, "received pong")
        self.__update_prev_recv_time()


class HeartBeat():
    def __init__(self, ws_server: 'WSServer', timeout=60, interval=30):
        self.server = ws_server
        self.timeout = timeout
        self.interval = interval
        self.prev_hreatbeat_time = None
        self.is_shutdown = True

    def handle(self):
        self.is_shutdown = False
        self.prev_hreatbeat_time = time.time()
        while self.is_shutdown is False:
            now = time.time()
            if now - self.prev_hreatbeat_time >= self.interval:
                self.prev_hreatbeat_time = now
                timeout_clients = []
                for client in self.server.clients:
                    if now - client.get_prev_recv_time() >= self.timeout:
                        timeout_clients.append(client)
                while timeout_clients:
                    self.server.close_client(timeout_clients[0])
                for client in self.server.clients:
                    client.ping()
            time.sleep(0.1)

    def shutdown(self):
        self.is_shutdown = True


class WSHandler:

    def __init__(self, ws_server: 'WSServer'):
        self.server = ws_server

    def on_client_connect(self, client):
        pass

    def on_client_message(self, client, message):
        pass

    def on_client_disconnect(self, client):
        pass


class WSServer:
    def __init__(self, host="127.0.0.1", port=5000, ws_handler: 'typing.Type[WSHandler]' = None):
        self.__ws_handler = ws_handler(self) or WSHandler(self)
        self.__heartbeat = None
        self.clients = set()  # type: typing.MutableSet[WSClient]
        self.__state = ServerState.CLOSE

        self.__delete_lock = threading.Lock()

        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.bind((host, port))

    def get_ws_handler(self):
        return self.__ws_handler

    def start(self):
        self.__socket.listen(10)
        if self.__heartbeat is not None:
            self.__start_heartbeat()
        self.set_state(ServerState.OPEN)
        while self.in_state(ServerState.OPEN):
            try:
                conn, host = self.__socket.accept()
            except OSError:
                break
            threading.Thread(target=self.__handle, args=(conn,)).start()

    def stop(self):
        if self.__heartbeat is not None:
            self.__heartbeat.shutdown()
        clients = self.clients.copy()
        self.clients.clear()
        for client in clients:
            client.close()
        self.set_state(ServerState.CLOSE)
        self.__socket.close()

    # ==========
    # state
    # ==========

    def set_state(self, state: 'ClientState'):
        self.__state = state

    def in_state(self, state: 'ClientState'):
        return self.__state == state

    # ==========
    # client
    # ==========

    def __get_client(self, client_id):
        for client in self.clients:
            if client_id == client.id:
                return client
        return None

    def get_clients(self):
        return list(map(lambda client: client.id, self.clients))

    def close_client(self, client):
        if client in self.clients:
            self.__on_close(client)
            client.close()
            return True
        return False

    # ==========
    # interface
    # ==========

    def send_message(self, client_id, message):
        if self.in_state(ServerState.CLOSE):
            return False
        client = self.__get_client(client_id)
        if client is None:
            return False
        try:
            client.send(message)
        except ClientClosingError:
            self.__on_close(client)
            return False
        return True

    def broadcast_message(self, message):
        if self.in_state(ServerState.CLOSE):
            return False
        for client in self.clients:
            try:
                client.send(message)
            except ClientClosingError:
                self.__on_close(client)
                pass
        return True

    # ==========
    # server handle
    # ==========

    def __handle(self, conn):
        try:
            client = WSClient(conn)
        except ProtocolError as e:
            # print(e)
            return
        self.__on_open(client)
        while client.is_connected():
            try:
                opcode, message = client.recv()
            except ClientClosingError:
                self.__on_close(client)
                break
            except ClientClosedError:
                break
            if opcode == OPCODE.TEXT:
                self.__on_message(client, message)

    def __on_open(self, client):
        self.clients.add(client)
        self.__ws_handler.on_client_connect(client)

    def __on_message(self, client, message):
        self.__ws_handler.on_client_message(client, message)

    def __on_close(self, client):
        with self.__delete_lock:
            if client in self.clients:
                self.__ws_handler.on_client_disconnect(client)
                self.clients.remove(client)

    # ==========
    # heartbeat
    # ==========

    def with_heartbeat(self, heartbeat: HeartBeat):
        self.__heartbeat = heartbeat

    def __start_heartbeat(self):
        threading.Thread(target=self.__heartbeat.handle, name='WSHeartBeatThread').start()
