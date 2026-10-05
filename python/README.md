# Arm controller

Run from the repository root:

```sh
python3 -m pip install -r python/requirements.txt
python3 python/controller.py
```

Set serial ports and enabled boards in `config.py`. All arms must be physically
at the bottom when the boards boot, because the firmware starts counting at zero.
Enter an arm number (1–4) to raise it and lower the others, or 9 to lower all.
`MOVE_THROUGH_MIDDLE` controls whether every selection goes through the middle.
The configured bottom target is 0.02 (900 steps); the top is 1 (45000 steps).
Type `quit` to exit.

Set motor speed using `DEFAULT_STEP_DELAY_US` in `config.py` (microseconds).
The controller prints board responses and waits for all target boards to finish before
accepting another command. A board error, restart, or timeout ends the session.

Run the tests without connecting hardware:

```sh
PYTHONPATH=python python3 -m unittest discover -s python/tests
```
