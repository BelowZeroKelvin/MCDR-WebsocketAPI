from websocket_api.main import MessageMediator

# ==========
# modifiable variable
# ==========

HOST = "127.0.0.1"
PORT = 5000

# ==========
# end
# ==========

PLUGIN_METADATA = {
    'id': 'websocket_api',
    'version': '1.0.0',
    'name': 'WebsocketAPI',
    'description': 'Provide websocket support for other plugins',
    'author': 'ZeroKelvin',
    'link': 'https://github.com/BelowZeroKelvin/MCDR-WebsocketAPI',
    'dependencies': {
        'mcdreforged': '>=1.0.0'
    }
}

message_mediator = None  # type: MessageMediator


def on_load(server, old_module):
    global message_mediator, config
    if old_module is not None and old_module.message_mediator is not None:
        message_mediator = old_module.message_mediator
    else:
        message_mediator = MessageMediator(server, host=HOST, port=PORT)
        message_mediator.wsapi_server.start()


def on_unload(server):
    global message_mediator
    if message_mediator is not None:
        message_mediator.wsapi_server.stop()
    message_mediator = None


def register(event_name, event_handler, force=False):
    return message_mediator.event_registry.register(event_name, event_handler, force)


def unregister(event_name):
    return message_mediator.event_registry.unregister(event_name)
