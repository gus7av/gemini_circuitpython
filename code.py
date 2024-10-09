import sdmount
import board
import wifi_manager
import time
import wifi
import socketpool
import ssl
import adafruit_requests
import json
import os
import sys
import displayio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
from adafruit_display_shapes.rect import Rect


# Define the Google API key and model
model = "pro"
api_key = os.getenv("GEMINI_API_KEY")


# Define instructions for the model
instructions = "Keep the answer short but informative. No markdown formatting or emojis please."

# Define the request headers
headers = {"Content-Type": "application/json"}

connection = wifi_manager.wifi_connection_manager()

# colors
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

# Create a rectangle the size of the display (background color)
background = Rect(0, 0, board.DISPLAY.width, board.DISPLAY.height, fill=0x000000)
main_group.append(background)

# Text area for chat log using the new font
chat_log = label.Label(custom_font, text="", scale=1, color=WHITE_TEXT)
chat_log.anchor_point = (0, 0)
chat_log.anchored_position = (padding, padding)  # Adjust to fit top-left
main_group.append(chat_log)

# Text area for user input using the new font
user_input_area = label.Label(custom_font, text="> Type your message...", scale=1, color=0x00FF00)
user_input_area.anchor_point = (0, 0)
user_input_area.anchored_position = (padding, input_position)  # Adjust to fit above bottom edge
main_group.append(user_input_area)


# Function to wrap text based on screen width
def wrap_text(text, max_width):
    words = text.split(" ")
    wrapped_lines = []
    current_line = ""

    for word in words:
        if (
            custom_font.get_bounding_box()[0] * len(current_line + word)
            <= max_width
        ):
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
        if text_width > display.width - (padding*2):  # Adjust for padding
            user_input_area.anchored_position = (
                display.width - text_width - padding,
                input_position,
            )  # Move left
        else:
            user_input_area.anchored_position = (padding, input_position)  # Reset to original position
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

            # Wait for keypress to go to the next page
            sys.stdin.read(1)  # Wait for keypress

        current_page += 1

    # After the last page, clear the input area so new text can be entered
    user_input_area.text = "> "
    display.refresh()

# Helper function to show countdown with explanation
def countdown_with_explanation(seconds, explanation, text_color=GREY_TEXT):
    for i in range(seconds, 0, -1):
        # Create combined message with explanation and countdown
        countdown_message = f"{explanation} Retrying in {i} seconds..."
        update_chat_log(countdown_message, text_color)
        time.sleep(1)  # Wait for 1 second between each countdown update

# Accumulate chat history
chat_history = []

def gemini_chat():
    global model
    pool = socketpool.SocketPool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl.create_default_context())
    display.refresh()

    while True:
        # Get user input
        user_input = capture_user_input()
        if not user_input:
            continue
        update_chat_log("Waiting for response...", GREY_TEXT)

        # Prepare payload with system instruction and user input
        temp_chat_history = chat_history.copy()  # Temporary history for sending, excluding user input for now
        temp_chat_history.append({"role": "user", "parts": [{"text": user_input}]})

        data = {
            "system_instruction": {"parts": [{"text": instructions}]},
            "contents": temp_chat_history,  # Send the user input in the request but not add to permanent history yet
            "generationConfig": {"maxOutputTokens": 200},
            "safety_settings": [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}]
        }

        json_data = json.dumps(data)

        # Set maximum retries and initial retry counter
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-{model}:generateContent?key={api_key}"
                response = requests.post(url, headers=headers, data=json_data)

                if response.status_code == 200:
                    # Success: process the response and break out of retry loop
                    response_data = response.json()
                    candidates = response_data.get("candidates", [])
                    if candidates:
                        model_response_text = candidates[0]["content"]["parts"][0]["text"]
                        model_response_text = model_response_text.replace("\n", " ")

                        # Add user input and model response to chat history
                        chat_history.append({"role": "user", "parts": [{"text": user_input}]})
                        chat_history.append({"role": "model", "parts": [{"text": model_response_text}]})

                        update_chat_log(model_response_text)
                    break  # Exit retry loop after successful response

                elif response.status_code == 429:
                    # Handle rate limiting
                    if model == "pro":
                        model = "flash"  # Switch model to 'flash'
                        update_chat_log("Request limit exceeded. Retrying with flash model...", GREY_TEXT)
                    else:
                        # If already on 'flash', wait and retry
                        countdown_with_explanation(60, "Request limit exceeded.", GREY_TEXT)
                        retry_count += 1

                elif response.status_code in [500, 503]:
                    # Handle server errors with shorter wait
                    countdown_with_explanation(5, "Service unavailable.", GREY_TEXT)
                    retry_count += 1

                else:
                    # Handle other errors and stop retries
                    update_chat_log(f"HTTP Error: {response.status_code}", GREY_TEXT)
                    break

            except Exception as e:
                update_chat_log(f"Error: {e}", GREY_TEXT)
                break  # Stop retries after an exception

        # If retries are exhausted, log failure
        if retry_count >= max_retries:
            update_chat_log("Failed to get a response after 3 retries.", GREY_TEXT)


# Main function
def main():
    if connection:
        print("Starting Gemini chat function...")
        gemini_chat()
    else:
        print("Failed to connect to Wi-Fi. Exiting.")

# Run the main function
main()
