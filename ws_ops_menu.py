import json
import os
import uuid
import time
from io import BytesIO
from terminalcolors import tcolor, color_text
from urllib import request, parse, error
from PIL import Image
from pynput import keyboard
from tqdm import tqdm

#  endpoints
# https://github.com/comfyanonymous/ComfyUI/blob/61b3f15f8f2bc0822cb98eac48742fb32f6af396/server.py#L97

# Global flag to help stop show_progress()
interrupt_flag = False

def get_system_stats(server_address):
    url = f"http://{server_address}/system_stats"

    with request.urlopen(url) as response:

        clr = tcolor.BRIGHT_MAGENTA
        response_data = json.loads(response.read().decode('utf-8'))
        opsys = response_data['system']['os']
        python_vers = response_data["system"]["python_version"]
        print(color_text(f"OS: {opsys}\nPython: {python_vers}", clr))

        # GPU information
        if "devices" in response_data and isinstance(response_data["devices"], list):
            for gpu in response_data["devices"]:
                name = gpu.get("name", "Unknown")
                vram_total = gpu.get("vram_total", 0)
                vram_free = gpu.get("vram_free", 0)
                torch_vram_total = gpu.get("torch_vram_total", 0)
                torch_vram_free = gpu.get("torch_vram_free", 0)

                print(color_text(f"GPU Name: {name}", clr))
                print(color_text(f"Total VRAM: {vram_total}\nFree VRAM: {vram_free}", clr))
                print(color_text(f"PyTorch Total VRAM: {torch_vram_total}\nPyTorch Free VRAM: {torch_vram_free}\n", clr))

        # return if data is required outside this function
        return response_data

# ===================================================================================
def show_progress(ws):

    queue_remaining = 0
    prompt_id = None  # keep track of prompt_id

    global interrupt_flag
    # Start the listener
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    print("Press ESC to return to the menu.")

    # Initialize the progress bar outside the loop
    progress_bar = None

    while True:

        if interrupt_flag:
            print("\nProgress interrupted!")
            break

        # receive data.
        out = ws.recv()

        if isinstance(out, str):
            message = json.loads(out)

            # print(message['type'])
            if message['type'] == 'executing':
                data = message['data']
                node_id = data['node']
                if prompt_id != data['prompt_id']:  # new prompt_id
                    prompt_id = data['prompt_id']
                    print(color_text(f'\nprompt_id: {prompt_id}', tcolor.BRIGHT_YELLOW))
                    # print('\r')
                if node_id is not None:
                    # get node class based on id
                    node_class = get_node_class(node_id)
                    print(color_text(f'Executing: Node {node_id} ({node_class})', tcolor.BRIGHT_YELLOW))
                elif data['node'] is None and queue_remaining == 0:
                    break  # Execution is done
            elif message['type'] == 'status':
                data = message['data']['status']['exec_info']
                if queue_remaining != data['queue_remaining']:
                    queue_remaining = data['queue_remaining']
            elif message['type'] == 'progress':
                data = message['data']
                # Initialize the progress bar
                if not progress_bar:
                    # Custom format: percentage and bar only
                    custom_format = color_text('{l_bar}{bar}| {n_fmt}/{total_fmt} steps', tcolor.BRIGHT_YELLOW)
                    # Initialize the progress bar when first progress message is received
                    progress_bar = tqdm(total=data['max'], ncols=60, bar_format=custom_format, desc="Progress")
                progress_bar.n = data['value']
                progress_bar.refresh()
                # When progress is complete for current job
                if data['value'] == data['max']:
                    print("\r")
        else:
            break # previews are binary data

    # stop listener when the function ends
    listener.stop()  # stop listener
    listener.join()  # Wait for  thread to finish
    interrupt_flag = False

# ===================================================================================
def on_press(key):
    global interrupt_flag
    if key == keyboard.Key.esc:
        interrupt_flag = True
        return

# ===================================================================================
def get_queue(server_address):
    # create the GET request
    req = request.Request(f"http://{server_address}/queue", method='GET')

    # send request and get response
    with request.urlopen(req) as response:
        response_data = json.loads(response.read().decode('utf-8'))

        # display queue_running item
        if response_data.get("queue_running"):
            print(color_text("\nQueue (Running):", tcolor.BRIGHT_YELLOW))
            queue_item = response_data["queue_running"][0]
            queue_item_id = queue_item[0]
            queue_item_prompt_id = queue_item[1]
            print(color_text(f"id={queue_item_id}, prompt_id={queue_item_prompt_id}", tcolor.MAGENTA))

        # display queue_pending items
        if response_data.get("queue_pending"):
            print(color_text("Queue (Pending):", tcolor.BRIGHT_YELLOW))
            for queue_item in response_data["queue_pending"]:
                queue_item_id = queue_item[0]
                queue_item_prompt_id = queue_item[1]
                print(color_text(f"id={queue_item_id}, prompt_id={queue_item_prompt_id}", tcolor.MAGENTA))

        # return if data is required outside this function
        return response_data

# ===================================================================================
# clears the pending queue, the current-running job will still complete.
def clear_queue(server_address):
    # payload for request to clear the queue
    clear_queue_payload = {'clear': True}
    json_payload = json.dumps(clear_queue_payload).encode('utf-8') # conv to json
    url = "http://{}/queue".format(server_address)
    req_headers = {'Content-Type': 'application/json'}

    # create the POST request
    clear_request = request.Request(url, data=json_payload, headers=req_headers, method='POST')

    # send the request and get response
    with request.urlopen(clear_request) as response:
        print(color_text(f"Response status: {response.status} : {response.reason}", tcolor.BRIGHT_YELLOW))
        # return response
        return response

# ===================================================================================
def delete_queue_item(server_address):

    # first get list of pending jobs
    response = get_queue(server_address)

    # Ask the user to input a queue ID to delete it from queue pending
    queue_id = input(color_text("\nPlease enter the queue ID to delete: ", tcolor.BRIGHT_GREEN))
    prompt_id = None
    # search for queue id and corresponding prompt id
    for task in response["queue_pending"]:
        if str(queue_id) == str(task[0]):
            prompt_id = task[1]  # get prompt_id
            break

    if prompt_id is not None:

        # payload for the request to delete a specific queue item
        delete_payload = {'delete': [prompt_id]}
        json_payload = json.dumps(delete_payload).encode('utf-8')  # Convert to JSON
        url = "http://{}/queue".format(server_address)
        req_headers = {'Content-Type': 'application/json'}

        # create the POST request to delete the specific queue item
        delete_request = request.Request(url, data=json_payload, headers=req_headers, method='POST')

        # send request and get response
        with request.urlopen(delete_request) as response:
            print(color_text(f"Deleted prompt_id {prompt_id} from queue_pending", tcolor.BRIGHT_YELLOW))
            print(color_text(f"Response status: {response.status} : {response.reason}", tcolor.BRIGHT_YELLOW))
    else:
        print(color_text(f'Prompt not found in queue. Maybe currently running or already finished.', tcolor.RED))

# ===================================================================================
# Cancels (Interrupts) the current running job
def cancel_running(server_address):
    # create the POST request
    url = f"http://{server_address}/interrupt"
    req_headers = {'Content-Type': 'application/json'}
    interrupt_request = request.Request(url, headers=req_headers, method='POST')

    # send request and get the response
    with request.urlopen(interrupt_request) as response:
        return response

# ===================================================================================
# Gets the history of all completed jobs (prompts) and their outputs
def get_history(server_address, use_prompt_id=False):
    url = None
    if use_prompt_id:
        prompt_id = input("Enter or Paste a prompt ID: ")
        url = "http://{}/history/{}".format(server_address, prompt_id)
    else:
        url = "http://{}/history".format(server_address)

    with request.urlopen(url) as response:
        response_data = json.loads(response.read().decode('utf-8'))

        for key in response_data.keys():
            job_id = response_data[key]["prompt"][0]
            prompt_id = response_data[key]["prompt"][1]
            client_id = response_data[key]["prompt"][3]["client_id"]

            filenames_temp = []  # Initialize an empty list for temp filenames
            filenames_output = []  # Initialize an empty list for output filenames
            output_data = response_data[key].get("outputs", {})
            for node_data in output_data.values():
                for img in node_data.get("images", []):
                    subfolder = img.get("subfolder")
                    filename = img["filename"]
                    if subfolder:  # Check if subfolder is not empty
                        filename = f'{subfolder}/{filename}'

                    if img.get("type") == "temp":
                        filenames_temp.append(filename)
                    elif img.get("type") == "output":
                        filenames_output.append(filename)

            print(f'client_id={client_id}\nqueue_id={job_id}\nprompt_id={prompt_id}:')
            # Print temp filenames if available
            if filenames_temp:
                print('filenames (temp):')
                for filename in filenames_temp:
                    print(filename)

            # Print output filenames if available
            if filenames_output:
                print('filenames (output):')
                for filename in filenames_output:
                    print(filename)
                print('\n')

        return response_data

# ===================================================================================
def get_embeddings(server_address):
    try:
        # Construct the URL for the embeddings endpoint
        url = f"http://{server_address}/embeddings"

        # Create the GET request
        req = request.Request(url, method='GET')

        # send request and get response
        with request.urlopen(req) as response:
            if response.status == 200:
                # Process the response here if needed
                embeddings = json.loads(response.read().decode('utf-8'))

                # show embeddings files
                print(f"Embeddings:")
                for embedding in embeddings:
                    print(f"{embedding}")

                return embeddings
            else:
                print(f"Error: {response.status} - {response.reason}")
                return None
    except error.URLError as e:
        print(f"URLError: {e.reason}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# ===================================================================================
def upload_image(server_address, subfolder=None):

    image_path = input("Enter or paste image path: ")
    if not os.path.isfile(image_path):
        print(color_text("image_path does not exist", tcolor.RED))
        return

    # Load the image
    image = Image.open(image_path)

    # convert image to bytes
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format=image.format)
    img_byte_arr = img_byte_arr.getvalue()

    # Boundary for multipart form data
    boundary = uuid.uuid4().hex

    # headers
    req_headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }

    # payload
    payload = [
        f'--{boundary}',
        'Content-Disposition: form-data; name="image"; filename="{}"'.format(image_path),
        f'Content-Type: image/{image.format.lower()}',
        '',
        img_byte_arr.decode('latin1')
    ]

    # Include subfolder in payload if provided
    if subfolder:
        payload.extend([
            f'--{boundary}',
            'Content-Disposition: form-data; name="subfolder"',
            '',
            subfolder
        ])

    payload = "\r\n".join(payload) + f"\r\n--{boundary}--\r\n"
    payload = payload.encode('latin1')

    # create the POST request
    upload_request = request.Request(
        f"http://{server_address}/upload/image",
        data=payload, headers=req_headers, method='POST'
    )

    # send request and get response
    with request.urlopen(upload_request) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        print(f"file uploaded: {response_data['name']}")
        print(f"subfolder: {response_data['subfolder']}")
        print(f"type: {response_data['type']}")
        return response.read()

# ===================================================================================
def upload_mask(server_address, mask_image_path, original_image_info):

    if not os.path.isfile(mask_image_path):
        print("Mask image path does not exist")
        return

    # Load the mask image
    image = Image.open(mask_image_path)

    # Convert the mask image to bytes
    img_byte_arr = BytesIO()
    image.save(img_byte_arr, format=image.format)
    img_byte_arr = img_byte_arr.getvalue()

    # Boundary for multipart form data
    boundary = uuid.uuid4().hex

    # Headers for the request
    req_headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}'
    }

    # Payload for the request
    payload = [
        f'--{boundary}',
        f'Content-Disposition: form-data; name="image"; filename="{os.path.basename(mask_image_path)}"',
        f'Content-Type: image/{image.format.lower()}',
        '',
        img_byte_arr.decode('latin1')
    ]

    # Include original image info in payload if provided
    if original_image_info:
        payload.extend([
            f'--{boundary}',
            'Content-Disposition: form-data; name="original_ref"',
            '',
            json.dumps(original_image_info)
        ])

    payload = "\r\n".join(payload) + f"\r\n--{boundary}--\r\n"
    payload = payload.encode('latin1')

    # Create the POST request to upload the mask
    upload_request = request.Request(
        f"http://{server_address}/upload/mask",
        data=payload, headers=req_headers, method='POST'
    )

    # send request and get response
    with request.urlopen(upload_request) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        print(f"Mask file uploaded: {response_data.get('name', 'N/A')}")
        print(f"Subfolder: {response_data.get('subfolder', 'Not provided')}")
        print(f"Type: {response_data.get('type', 'N/A')}")
        return response.read()

# ===================================================================================
def get_object_info(server_address, node_class=None):

    url = f"http://{server_address}/object_info"

    if node_class:
        url +=f'/{node_class}'

    # Create the GET request to fetch the queue items
    req = request.Request(url, method='GET')

    # send request and get response
    with request.urlopen(req) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        # Print the parsed JSON data with indentation
        print(json.dumps(response_data, indent=2))

# ===================================================================================
def get_view(server_address, type=None, subfolder=None, preview=None, channel=None):

    filename = input("Enter or paste filename: ")

    # Construct the URL for the request
    base_url = f"http://{server_address}/view"

    # Prepare the query parameters
    params = {'filename': filename}
    if type is not None:
        params['type'] = type
    if subfolder is not None:
        params['subfolder'] = subfolder
    if preview is not None:
        params['preview'] = preview
    if channel is not None:
        params['channel'] = channel

    # Encode query parameters and append to URL
    query_string = parse.urlencode(params)
    url = f"{base_url}?{query_string}"

    # Create the GET request
    req = request.Request(url, method='GET')

    # send request and get response
    try:
        with request.urlopen(req) as response:
            if response.status == 200:
                image_data = response.read()

                # Open the image data using PIL
                image = Image.open(BytesIO(image_data))

                # Show the image
                image.show()
            elif response.status == 404:
                print("Error: File not found.")
            else:
                print(f"Error: {response.status}")
    except Exception as e:
        print(f"An error occurred: {e}")

# ===================================================================================
def get_prompt(server_address):
    # only gives total queue remaining items
    req = request.Request(f"http://{server_address}/prompt", method='GET')

    # send request and get response
    with request.urlopen(req) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        print(response_data)
        queue_remaining = response_data["exec_info"]["queue_remaining"]
        print(color_text(f"Queue remaining: {queue_remaining}", tcolor.BRIGHT_YELLOW))

# ===================================================================================
def extensions(server_address):
    with request.urlopen(f"http://{server_address}/extensions") as response:
        return json.loads(response.read())

# ===================================================================================
def display_menu(menu_items):
    column_width = 30
    max_rows = 8

    clr = tcolor.BRIGHT_GREEN

    print(color_text("\nComfyUI WebSockets API:", tcolor.BLUE))

    # we want the menu items to appear in rows of 5, and overflow over to next col as necessary
    # total columns needed
    total_columns = -(-len(menu_items) // max_rows)  # Ceiling division for total columns

    for i in range(max_rows):
        line = ''

        for col in range(total_columns):
            pos = col * max_rows + i  # Calc positionq

            if pos < len(menu_items):
                # Append the menu option to the line, left-justified
                line += menu_items[pos].ljust(column_width)
        print(color_text(line, clr))

# ===================================================================================
# get a node's class fromo node id in current workflow
def get_node_class(node_id):
    # Open and read the JSON file
    with open('workflow_api.json', 'r') as file:
        workflow_data = json.load(file)

    # Check if the node_id exists and return its class name
    if node_id in workflow_data:
        return workflow_data[node_id].get("class_type", "")
    else:
        return ""

# ===================================================================================
# Main function to handle command line arguments
def run(ws, server_address):

    # # Generate a unique client ID
    # client_id = str(uuid.uuid4())
    #
    # # Establish a WebSocket connection
    # # ws = websocket.WebSocket()
    # # ws.connect(f"ws://{server_address}/ws?clientId={client_id}")

    menu_items = [
        "[1] System Stats",
        "[2] Show Progress",
        "[3] Get Queue",
        "[4] Clear Queue",
        "[5] Delete Queue item",
        "[6] Cancel Running",
        "[7] Get History",
        "[8] Get History (Prompt)",
        "[9] Get View",
        "[10] Upload Image",
        "[11] Upload Mask",
        "[12] Get Prompt",
        "[13] Get Object Info",
        "[14] Get Embeddings",
        "[Q] Quit"
    ]

    while True:
        # Displaying the menu

        display_menu(menu_items)

        # get user input
        choice = input(color_text("Enter your choice: ", tcolor.BLUE))

        if choice == '1':
            get_system_stats(server_address)
        elif choice == '2':
            show_progress(ws)
        elif choice == '3':
            get_queue(server_address)
        elif choice == '4':
            clear_queue(server_address)
        elif choice == '5':
            delete_queue_item(server_address)
        elif choice == '6':
            cancel_running(server_address)
        elif choice == '7':
            get_history(server_address, use_prompt_id=False)
        elif choice == '8':
            get_history(server_address, use_prompt_id=True)
        elif choice == '9':
            get_view(server_address)
        elif choice == '10':
            upload_image(server_address)
        elif choice == '11':
            mask_image_path = 'mask.png'  # Replace with the path to your mask image
            original_image_info = {
                'filename': 'cake.png',
                'subfolder': '',  # optional
                'type': 'input'  # or 'temp' based on your categorization
            }
            upload_mask(server_address, mask_image_path, original_image_info)
        elif choice == '12':
            get_prompt(server_address)
        elif choice == '13':
            get_object_info(server_address, node_class='KSampler')
        elif choice == '14':
            get_embeddings(server_address)
        elif choice == 'q':
            # "Exiting the loop & program
            break
        else:
            print(color_text("Invalid choice. Please try again.", tcolor.RED))

        time.sleep(1)

    ws.close()





