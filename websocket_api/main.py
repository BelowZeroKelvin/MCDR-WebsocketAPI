import json
from typing import TYPE_CHECKING
from .ws_server import WSHandler, WSServer, HeartBeat
import threading

if TYPE_CHECKING:
    from mcdreforged.plugin.server_interface import ServerInterface


class WSAPIServerHandler(WSHandler):

    def set_mediator(self, mediator):
        self.mediator = mediator

    @staticmethod
    def __parse_client_message(message):
        try:
            data = json.loads(message)
        except json.decoder.JSONDecodeError:
            return False, "wrong data format"
        if not isinstance(data, dict):
            return False, "wrong data format"
        if 'event' not in data or 'data' not in data:
            return False, "incomplete data"
        return True, data

    def on_client_connect(self, client):
        threading.current_thread().setName(f"WSAPIClient <id:{client.id}>")

    def on_client_message(self, client, message):
        result, data = self.__parse_client_message(message)
        if result:
            self.mediator.to_event(client.id, data['event'], data['message'])
        else:
            self.mediator.error_to_client(client.id, data)

    def on_client_disconnect(self, client):
        pass


class WSAPIServer:
    def __init__(self, mediator, host="127.0.0.1", port=5000):
        self.server = WSServer(host, port, WSAPIServerHandler)
        self.server.with_heartbeat(heartbeat=HeartBeat(self.server))
        self.server.get_ws_handler().set_mediator(mediator)

    def start(self):
        threading.Thread(target=self.server.start, name="WSAPIServer").start()

    def stop(self):
        self.server.stop()


class MessageMediator:
    def __init__(self, mcdr_interface: 'ServerInterface', host="127.0.0.1", port="5000"):
        self.wsapi_server = WSAPIServer(self, host, port)
        self.event_registry = EventRegistry(self)
        self.mcdr_interface = mcdr_interface

    def to_client(self, event_name, client_id, message):
        data = json.dumps({
            'type': 'event',
            'event': event_name,
            'message': message
        })
        return self.wsapi_server.server.send_message(client_id, data)

    def broadcast_client(self, event_name, message):
        data = json.dumps({
            'type': 'event',
            'event': event_name,
            'message': message
        })
        return self.wsapi_server.server.broadcast_message(data)

    def error_to_client(self, client_id, error):
        data = json.dumps({
            'type': 'error',
            'message': error
        })
        return self.wsapi_server.server.send_message(client_id, data)

    def to_event(self, client_id, event_name, message):
        event = self.event_registry.get_event(event_name)
        if event is None:
            return False
        data = {
            'client': client_id,
            'data': message
        }
        try:
            event['handler'](self.mcdr_interface, data)
            return True
        except Exception as e:
            # print(type(e), e)
            return False


class EventInterface:
    def __init__(self, mediator: 'MessageMediator', event):
        self.__mediator = mediator
        self.__event = event

    def send(self, client_id, message):
        return self.__mediator.to_client(self.__event["name"], client_id, message)

    def broadcast(self, message):
        return self.__mediator.broadcast_client(self.__event["name"], message)


class EventRegistry:
    def __init__(self, mediator: 'MessageMediator'):
        self.registered_events = dict()
        self.mediator = mediator
        self.id_counter = 0

    def register(self, event_name: str, event_handler, force=False):
        if not force and event_name in self.registered_events:
            return None
        self.id_counter += 1
        event = dict(
            id=self.id_counter,
            name=event_name,
            handler=event_handler
        )
        self.registered_events[event_name] = event
        return EventInterface(self.mediator, event)

    def unregister(self, event_name):
        if event_name in self.registered_events:
            self.registered_events.pop(event_name)
            return True
        return False

    def get_all_events(self):
        return self.registered_events

    def get_event(self, target):
        if isinstance(target, str) and target in self.registered_events:
            return self.registered_events[target]

        elif isinstance(target, int):
            for event in self.registered_events:
                if target == event["id"]:
                    return event
        return None
