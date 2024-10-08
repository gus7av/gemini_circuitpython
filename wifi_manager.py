import time
import wifi
import os

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
    print(f"Network {ssid} has been added.")


# Function to scan available networks
def scan_available_networks():
    print("Scanning for available networks...")
    available_networks = [net.ssid for net in wifi.radio.start_scanning_networks()]
    wifi.radio.stop_scanning_networks()
    return available_networks


# Function to connect to Wi-Fi with retry limit and delay
def connect_to_wifi(ssid, password, retries=3, delay=5):
    for attempt in range(retries):
        try:
            wifi.radio.connect(ssid, password)
            print(f"Connected to Wi-Fi: {wifi.radio.ipv4_address}")
            return True
        except Exception as e:
            print(f"Failed to connect to {ssid} (Attempt {attempt + 1}/{retries}): {e}")
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
            print(f"Trying to connect to {ssid}...")
            connected = connect_to_wifi(ssid, password)
            if connected:
                break
    # If no known networks work, ask the user whether to retry or add a new network
    while not connected:
        action = input(
            "Failed to connect to a known Wi-Fi network. Do you want to (r)etry or (a)dd a new network?: "
        ).lower()
        if action == "r":
            available_networks = (
                scan_available_networks()
            )  # Re-scan for available networks
            for ssid, password in known_networks:
                if ssid in available_networks:
                    print(f"Retrying connection to {ssid}...")
                    connected = connect_to_wifi(ssid, password)
                    if connected:
                        break
        elif action == "a":
            ssid = input("Enter Wi-Fi SSID: ")
            password = input("Enter Wi-Fi password: ")
            connected = connect_to_wifi(ssid, password)
            if connected:
                add_network_to_config(ssid, password)
    return connected
