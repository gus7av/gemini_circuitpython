import board
import time
import wifi
import socketpool
import ssl
import adafruit_requests
import json
import os
import sys
import displayio
import sdcardio
import storage
import gc
import re
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font


pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

sd = sdcardio.SDCard(board.SD_SPI(), board.SD_CS)
vfs = storage.VfsFat(sd)
storage.mount(vfs, "/sd")

# Define the Google API key and model
api_key = os.getenv("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

# Define instructions for the model
instructions = "Keep all answers short but informative. Please do not use emojis or markdown formatting."

# Define the request headers
headers = {"Content-Type": "application/json"}

# Accumulate chat history
chat_history = []

# Color definitions
GREY_TEXT = 0x808080
WHITE_TEXT = 0xDDDDDD

# Create a display group after Wi-Fi connection is established
main_group = displayio.Group()

# Set up display elements
display = board.DISPLAY
display.auto_refresh = False
display.root_group = main_group  # Assign the group to the display

# Load the custom font
custom_font = bitmap_font.load_font("/fonts/spleen-8x16.bdf")  # Adjust path as needed

# Calulate positions
line_height = custom_font.get_bounding_box()[1] * 1.25  # default line spacing
display_lines = display.height // line_height
log_lines = int(display_lines - 1)
log_height = log_lines * line_height
padding = (display.height - (display_lines * line_height)) // 2
input_position = log_height + padding

# Text area for chat log using the new font
chat_log = label.Label(custom_font, text="", scale=1, color=WHITE_TEXT)
chat_log.anchor_point = (0, 0)
chat_log.anchored_position = (padding, padding)  # Adjust to fit top-left
main_group.append(chat_log)

# Text area for user input using the new font
user_input_area = label.Label(
    custom_font, text="> ", scale=1, color=0x00FF00
)
user_input_area.anchor_point = (0, 0)
user_input_area.anchored_position = (
    padding,
    input_position,
)  # Adjust to fit above bottom edge
main_group.append(user_input_area)

display.refresh()

# Read known Wi-Fi networks from config.txt
def read_known_networks():
    if "config.txt" not in os.listdir("/sd"):
        # If config.txt does not exist, return an empty list
        return []
    with open("sd/config.txt", "r") as file:
        networks = []
        for line in file:
            ssid, password = line.strip().split(",")
            networks.append((ssid, password))
    return networks


# Add new Wi-Fi network to config.txt
def add_network_to_config(ssid, password):
    with open("sd/config.txt", "a") as file:
        file.write(f"{ssid},{password}\n")
    update_chat_log(f"Network {ssid} has been added.", GREY_TEXT)


# Function to scan available networks
def scan_available_networks():
    update_chat_log("Scanning for available networks...", GREY_TEXT)
    available_networks = [net.ssid for net in wifi.radio.start_scanning_networks()]
    wifi.radio.stop_scanning_networks()
    return available_networks


# Function to connect to Wi-Fi with retry limit and delay
def connect_to_wifi(ssid, password, retries=3, delay=5):
    for attempt in range(retries):
        try:
            wifi.radio.connect(ssid, password)
            update_chat_log(f"Connected to Wi-Fi: {wifi.radio.ipv4_address}", GREY_TEXT)
            return True
        except Exception as e:
            update_chat_log(f"Failed to connect to {ssid} (Attempt {attempt + 1}/{retries}): {e}", GREY_TEXT)
            time.sleep(delay)
    return False


# Handle Wi-Fi connection
def wifi_connection_manager():
    known_networks = read_known_networks()
    available_networks = scan_available_networks()
    connected = False

    # Try only the known networks that are available
    for ssid, password in known_networks:
        if ssid in available_networks:
            update_chat_log(f"Trying to connect to {ssid}...", GREY_TEXT)
            connected = connect_to_wifi(ssid, password)
            if connected:
                break
    # If no known networks work, ask the user whether to retry or add a new network
    while not connected:
        update_chat_log("Failed to connect to a known Wi-Fi network. Do you want to (r)etry or (a)dd a new network?: ", GREY_TEXT)
        action = capture_user_input().lower()
        if action == "r":
            available_networks = (
                scan_available_networks()
            )  # Re-scan for available networks
            for ssid, password in known_networks:
                if ssid in available_networks:
                    update_chat_log(f"Retrying connection to {ssid}...", GREY_TEXT)
                    connected = connect_to_wifi(ssid, password)
                    if connected:
                        break
        elif action == "a":
            update_chat_log("Enter Wi-Fi SSID", GREY_TEXT)
            ssid = capture_user_input()
            update_chat_log("Enter Wi-Fi password")
            password = capture_user_input()
            connected = connect_to_wifi(ssid, password)
            if connected:
                add_network_to_config(ssid, password)
    return connected

# Function to wrap text based on screen width
def wrap_text(text, max_width):
    words = text.split(" ")
    wrapped_lines = []
    current_line = ""

    for word in words:
        if custom_font.get_bounding_box()[0] * len(current_line + word) <= max_width:
            current_line += word + " "
        else:
            wrapped_lines.append(current_line.strip())
            current_line = word + " "
    if current_line:
        wrapped_lines.append(current_line.strip())
    return wrapped_lines


# Capture user input from stdin with backspace handling
def capture_user_input():
    user_input = ""
    while True:
        char = sys.stdin.read(1)
        if char == "\n":  # Enter key to submit input
            break
        elif (
            char == "\x08" or char == "\x7f"
        ):  # Handle backspace (Delete or Backspace keys)
            if len(user_input) > 0:
                user_input = user_input[:-1]  # Remove last character
        else:
            user_input += char  # Add character to input
        # Update display input
        user_input_area.text = "> " + user_input  # Update text with current input

        # Calculate width of input text
        text_width = custom_font.get_bounding_box()[0] * len(user_input_area.text)

        # Adjust anchored position to keep text within bounds
        if text_width > display.width - (padding * 2):  # Adjust for padding
            user_input_area.anchored_position = (
                display.width - text_width - padding,
                input_position,
            )  # Move left
        else:
            user_input_area.anchored_position = (
                padding,
                input_position,
            )  # Reset to original position
        display.refresh()  # Refresh the display to show updated input
    return user_input


# Update chat log with line wrapping and optional text color
def update_chat_log(text, color=WHITE_TEXT):  # Default color is white
    max_width = display.width - (padding * 2)  # Adjust to fit screen width
    wrapped_text_lines = wrap_text(text, max_width)

    # Start pagination
    total_lines = len(wrapped_text_lines)
    total_pages = (total_lines + log_lines - 1) // log_lines
    current_page = 0

    # Update the text color for chat_log
    chat_log.color = color

    # reset input field
    user_input_area.anchored_position = (padding, input_position)

    while current_page < total_pages:
        # Calculate which lines to display on this page
        start_line = current_page * log_lines
        end_line = min(start_line + log_lines, total_lines)

        # Display the lines that fit on this page
        chat_log.text = "\n".join(wrapped_text_lines[start_line:end_line])
        display.refresh()

        if current_page < total_pages - 1:
            # Write message in the input field to prompt scrolling
            user_input_area.text = "> Press any key to scroll..."
            display.refresh()
            sys.stdin.read(1)

        current_page += 1

    user_input_area.text = "> "
    display.refresh()


def prepare_gemini_request(user_input, history=chat_history, inst=instructions):
    history.append({"role": "user", "parts": [{"text": user_input}]})

    data = {
        "system_instruction": {"parts": [{"text": inst}]},
        "contents": history,
        "generationConfig": {"maxOutputTokens": 200},
        "safety_settings": [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        ],
    }

    json_data = json.dumps(data)
    return json_data


def send_request():
    global chat_history
    try:
        gc.collect()
        with requests.post(url, headers=headers, data=json_data, timeout=10) as response:
            update_chat_log("Waiting for response...", GREY_TEXT)

            if response.status_code == 200:
                # Success: process response
                response_data = response.json()
                candidates = response_data.get("candidates", [])
                if candidates:
                    model_response_text = candidates[0]["content"]["parts"][0]["text"]
                    model_response_text = model_response_text.replace("\n", " ")
                    model_response_text = model_response_text.replace("*", "")
                    model_response_text = re.sub(r'\s+', ' ', model_response_text).strip()

                    gc.collect()
                    chat_history.append({"role": "model", "parts": [{"text": model_response_text}]})

                    if len(chat_history) > 20:
                        gc.collect()
                        chat_history = chat_history[2:]

                    update_chat_log(model_response_text)
                return True  # Indicate success

            elif response.status_code == 429:
                update_chat_log("Request limit exceeded. Retrying in 2 minutes", GREY_TEXT)
                time.sleep(120)
                return False  # Indicate retry is needed

            elif response.status_code in [500, 503]:
                time.sleep(5)
                return False  # Retryable errors

            else:
                update_chat_log(f"HTTP Error: {response.status_code}", GREY_TEXT)
                return True  # Non-retryable error

    except Exception as e:
        update_chat_log(f"Error: {e}", GREY_TEXT)
        return True  # Non-retryable error


def handle_request_with_retry():
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        if send_request():
            break
        retry_count += 1

    if retry_count >= max_retries:
        gc.collect()
        chat_history.pop()
        update_chat_log("Failed to get a response. Try again later...", GREY_TEXT)


new_message = True
new_input = True

# Main function
while True:
    while not wifi.radio.connected:
        wifi_connection_manager()
        time.sleep(2)
        update_chat_log("Type your message...", GREY_TEXT)

    if new_message:
        new_message = False
        user_input = capture_user_input()
        if not user_input:
            continue

    if new_input:
        new_input = False
        update_chat_log("Preparing message...", GREY_TEXT)
        gc.collect()
        json_data = prepare_gemini_request(user_input)

        max_retries = 3
        retry_count = 0

    if wifi.radio.connected:
        new_message = True
        new_input = True
        handle_request_with_retry()

