import serial
import time
import sys

# Define ports for all 3 possible boards (change these to your actual COM ports)
PORTS = {
    1: '/dev/cu.usbmodem1101',
    2: 'COM5',
    3: 'COM6'
}
BAUD_RATE = 115200


def initialize_boards(use_b1=True, use_b2=True, use_b3=True):
    """
    Initializes only the boards that are set to True.
    Returns a dictionary of active board connections.
    """
    active_boards = {}
    flags = {1: use_b1, 2: use_b2, 3: use_b3}

    print("--- Initialization ---")
    for board_id, should_use in flags.items():
        if should_use:
            port = PORTS[board_id]
            print(f"Connecting to Board {board_id} on {port}...")
            try:
                # Open serial connection
                board_conn = serial.Serial(port, BAUD_RATE, timeout=0.5)
                active_boards[board_id] = board_conn
            except Exception as e:
                print(f"Error connecting to Board {board_id}: {e}")
                print("Make sure your Arduino IDE Serial Monitor is CLOSED.")
                sys.exit(1)
        else:
            print(f"Board {board_id} is disabled via arguments. Skipping.")

    # If no boards are active, stop the program
    if not active_boards:
        print("No boards were initialized. Exiting program.")
        sys.exit(1)

    # Give Arduino time to reset after opening the serial port
    print("\nWaiting for boards to initialize...")
    time.sleep(2)

    # Clear the initial startup messages from the buffer for all active boards
    for board_conn in active_boards.values():
        board_conn.reset_input_buffer()

    print(f"Successfully connected to {len(active_boards)} board(s)!\n")
    return active_boards


def read_responses(active_boards, wait_time=0.1):
    """Reads and prints whatever the active boards send back."""
    time.sleep(wait_time)

    # Iterate dynamically only over the boards that were actually initialized
    for board_id, board_conn in active_boards.items():
        while board_conn.in_waiting > 0:
            response = board_conn.readline().decode('utf-8').strip()
            if response:
                print(f"[Board {board_id} - {PORTS[board_id]}]: {response}")


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Here you can easily turn boards ON or OFF.
    # E.g., if you only have two boards right now, set use_b3 to False.
    active_boards = initialize_boards(use_b1=True, use_b2=False, use_b3=False)

    print("--- INTERACTIVE MULTI-BOARD CONTROLLER ---")
    print("Type your command (e.g., '12:UP 3:DOWN') and press Enter.")
    print("Type 'exit' or 'quit' to close the program.\n")

    while True:
        # 1. Wait for user input interactively
        user_input = input("Enter command >>> ").strip()

        # 2. Check if user wants to exit
        if user_input.lower() in ['exit', 'quit']:
            print("Closing connections...")
            for board_conn in active_boards.values():
                board_conn.close()
            break

        # Ignore empty inputs
        if not user_input:
            read_responses(active_boards, wait_time=0)
            continue

        # 3. Send the command to all ACTIVE boards simultaneously
        command_bytes = f"{user_input}\n".encode('utf-8')
        for board_conn in active_boards.values():
            board_conn.write(command_bytes)

        # 4. Read the immediate "ACK" messages
        read_responses(active_boards, wait_time=0.1)