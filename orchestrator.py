import serial
import time
import sys

# Replace 'COM3' and 'COM5' with your actual ports
PORT_1 = 'COM3'
PORT_2 = 'COM5'
BAUD_RATE = 115200


def initialize_boards():
    print(f"Connecting to {PORT_1} and {PORT_2}...")
    try:
        b1 = serial.Serial(PORT_1, BAUD_RATE, timeout=0.5)
        b2 = serial.Serial(PORT_2, BAUD_RATE, timeout=0.5)

        # Give Arduino time to reset after opening the serial port
        time.sleep(2)

        # Clear the initial startup messages from the buffer
        b1.reset_input_buffer()
        b2.reset_input_buffer()

        print("Successfully connected to both boards!\n")
        return b1, b2
    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure your Arduino IDE Serial Monitor is CLOSED.")
        sys.exit(1)


def read_responses(board_1, board_2, wait_time=0.1):
    """Reads and prints whatever the boards send back."""
    time.sleep(wait_time)

    while board_1.in_waiting > 0:
        response = board_1.readline().decode('utf-8').strip()
        if response:
            print(f"[Board 1 - {PORT_1}]: {response}")

    while board_2.in_waiting > 0:
        response = board_2.readline().decode('utf-8').strip()
        if response:
            print(f"[Board 2 - {PORT_2}]: {response}")


if __name__ == "__main__":
    board_1, board_2 = initialize_boards()

    print("--- INTERACTIVE DUAL-BOARD CONTROLLER ---")
    print("Type your command (e.g., '12:UP 3:DOWN') and press Enter.")
    print("Type 'exit' or 'quit' to close the program.\n")

    while True:
        # 1. Wait for user input interactively
        user_input = input("Enter command >>> ").strip()

        # 2. Check if user wants to exit
        if user_input.lower() in ['exit', 'quit']:
            print("Closing connections...")
            board_1.close()
            board_2.close()
            break

        # Ignore empty inputs (if you just press Enter)
        if not user_input:
            # We still read responses in case a previous movement just finished
            read_responses(board_1, board_2, wait_time=0)
            continue

        # 3. Send the command to both boards simultaneously
        command_bytes = f"{user_input}\n".encode('utf-8')
        board_1.write(command_bytes)
        board_2.write(command_bytes)

        # 4. Read the immediate "ACK" (Acknowledge) messages from the boards
        read_responses(board_1, board_2, wait_time=0.1)

        # Note: Since the movement takes about 2.5 seconds, the "Done." message
        # will show up the next time you press Enter, or you can just wait.