import json

import websocket #NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
import uuid
from terminalcolors import tcolor, color_text
import queue_loader
import ws_ops_menu
import ws_ops_menu2_wip

# server_address = "127.0.0.1:8188"  # local
# server_address = "192.168.0.44:8188"  # (remote-lan windows)
# server_address = "192.168.0.37:8188"  # (remote-lan linux1)
server_address = "192.168.86.218:8188"  # (remote-lan linux2)
client_id = str(uuid.uuid4())

# create new websocket object and connect, timeout=10
ws = websocket.WebSocket()
ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id), timeout=10)

# load up the queue with some prompts and return a list of their prompt IDss
prompt_id_list = queue_loader.run(server_address, client_id)

print(color_text("Prompts Queued", tcolor.GREEN))
# liste the prompt IDS
if prompt_id_list is not None:
    for item in prompt_id_list:
        print(color_text(f'{item}', tcolor.GREEN))

# run menu
ws_ops_menu.run(ws, server_address)
# ws_ops_menu2_wip.run(ws, server_address)

ws.close()