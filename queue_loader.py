import json
import random
from urllib import request
from terminalcolors import tcolor, color_text

# =======================================================================
# call the /prompt endpoint (POST)
def queue_prompt(prompt_workflow, server_address, client_id):
    request_payload = {"prompt": prompt_workflow, "client_id": client_id}
    json_payload = json.dumps(request_payload).encode('utf-8')
    url = "http://{}/prompt".format(server_address)
    req_headers = {'Content-Type': 'application/json'}
    prompt_req = request.Request(url, data=json_payload, headers=req_headers, method='POST')
    # send request and get the response
    with request.urlopen(prompt_req) as response:
        response_content = response.read()
        return json.loads(response_content) # return prompt_id

# =======================================================================
# get a node via its title
def get_node(prompt_workflow, title):
    # find node by title (case-insensitive)
    lower_title = title.lower()

    for prompt_id in prompt_workflow:
        node = prompt_workflow[prompt_id]
        node_title = node["_meta"]["title"].lower()
        if node_title == lower_title:
            return node

    print(color_text(f"Warning: No node found with title '{title}'.", tcolor.RED))
    return None  # Return None if no matching node is found

# =======================================================================
# main function
def run(server_address, client_id):

    # Load workflow API data from file
    prompt_workflow = json.load(open('workflow_api.json'))

    # list of positive prompts
    prompt_list = [
        "photo of a man sitting in a cafe",
        "photo of a woman standing in the middle of a busy street",
        "drawing of a cat sitting in a tree",
        "beautiful scenery nature glass bottle landscape, purple galaxy bottle",
        "beach on a sunny day",
        "a scene inside a snow globe",
        "dark and forboding scenery inside a glass bottle",
        "field on a sunny day",
        "a scene inside a micro environment "
    ]

    # Retrieve nodes from workflow
    chkpoint_loader_node = get_node(prompt_workflow, 'Load Checkpoint')
    prompt_pos_node = get_node(prompt_workflow, 'Pos Prompt')
    empty_latent_img_node = get_node(prompt_workflow, 'Empty Latent Image')
    ksampler_node = get_node(prompt_workflow, 'KSampler')
    save_image_node = get_node(prompt_workflow, 'Save Image')
    load_image_node = get_node(prompt_workflow, 'Load Image')
    load_imagemask_node = get_node(prompt_workflow, 'Load Image (as Mask)')

    # set path according to os comfy server is running on
    path = "SD1-5/sd_v1-5_vae.ckpt"  # unix, linux, macos
    # path = "SD1-5\\sd_v1-5_vae.ckpt" # for windows

    # setup workflow nodes
    chkpoint_loader_node["inputs"]["ckpt_name"] = path
    empty_latent_img_node["inputs"]["width"] = 512
    empty_latent_img_node["inputs"]["height"] = 640
    empty_latent_img_node["inputs"]["batch_size"] = 4

    # store prompt id for each job when added to queue
    prompt_id_list = []

    # Process each prompt
    for index, prompt in enumerate(prompt_list):
        prompt_pos_node["inputs"]["text"] = prompt
        ksampler_node["inputs"]["seed"] = random.randint(1, 18446744073709551614)
        # high steps to slow things down a bit
        ksampler_node["inputs"]["steps"] = 50
        file_prefix = prompt[:100]
        save_image_node["inputs"]["filename_prefix"] = file_prefix

        # everything set, add entire prompt/workflow to queue, get response
        response = queue_prompt(prompt_workflow, server_address, client_id)

        # extract the prompt_id from the response and add to list
        pid = response['prompt_id']
        prompt_id_list.append(pid)

    # return the list of prompt_ids
    return prompt_id_list
