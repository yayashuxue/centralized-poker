from socketio import AsyncServer


sio = AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)

@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)

async def ws_emit_actions(table_id, poker_table_obj):
    # while True:
    #     is_event, event = poker_table_obj.get_next_event(0)
    #     if is_event:
    #         await sio.emit(table_id, event)
    #     else:
    #         break
    while poker_table_obj.events_pop:
        event = poker_table_obj.events_pop.pop(0)
        print("EMITTING EVENT", event)
        await sio.emit(table_id, event)
