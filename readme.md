# MCDR Websocket API

> 一个为其他 `MCDR` 插件提供 `WebSocket` 服务的 API，仅在 `MCDR 1.0` 及以上版本运行

<span style='color:#f00'><i><b>该插件目前还在测试，欢迎 issue</b></i></span>

## 快速开始

首先，你需要将 `WebsocketAPI.py` 和 `websocket_api` 目录 放入 `plugin` 目录下  
然后，在 `PLUGIN_METADATA` 中添加该 API 的依赖

```
{
    // ...
    "dependencies": {
        "mcdreforged": ">=1.0.0"
    }
    // ...
}
```

引入 API 实例并使用 `register` 方法注册你的插件事件，并得到一个[接口](#interface)

```python
websocket_api = server.get_plugin_instance('websocket_api')
interface = websocket_api.register(event_name, event_handler)
```

## 实例方法

### register(event_name, event_handler, force=False)

注册一个事件以供 WebSocket 交互

#### 参数

`event_name` 你要注册的事件名（推荐使用插件 id）  
`event_handler` websocket 客户端触发该事件的[回调函数](#event-handler)  
`force` 是否强制注册。如果之前有注册过该事件但未销毁，可使用 `force = True` 来强制覆盖

#### 返回值

如果该事件之前注册过，且未使用 `force = True` 强制覆盖，则返回 `None`。否则，将返回一个可供调用的[接口](#interface)

### unregister(event_name)

注销一个之前注册过的事件

#### 参数

`event_name` 事件名

#### 返回值

如果该事件之前注册过，则返回 `True` 。否则返回 `False`

## <span id='interface'>接口方法</span>

### send(client_id, message)

将一条消息发送给某个连接客户端

#### 参数

`client_id` 客户端 id ，可从[回调函数](#event-handler)的参数中得到  
`message` 发送的数据，该数据可以为字典，列表等可被 JSON 序列化的数据结构

#### 返回值

如果发送成功，则返回 `True`，否则，返回 `False`

### broadcast(message)

将一条消息发送给所有连接的客户端

#### 参数

`message` 发送的数据，该数据可以为字典，列表等可被 JSON 序列化的数据结构

#### 返回值

如果发送成功，则返回 `True`，否则，返回 `False`

## <span id='event-handler'>事件回调函数</span>

### event_handler(server, data)

#### 参数

`server` MCDR 的 server 接口，与 MCDR 事件回调函数的 server 参数一致  
`data` 一个包括多个字段的字典

| 字段名 | 字段说明         |
| ------ | ---------------- |
| client | 客户端 id        |
| data   | 客户端发送的数据 |

## Websocket 数据格式

-   该数据需要进行 JSON 序列化处理

```
{
    "type": "event",
    "event": "{event_name}", // 事件名称
    "data": "{data}" // 发送的数据
}
```
