# serial2midi GUI

Graphical user interface for the [serial2midi](https://github.com/Jikstra/serial2midi) script.

## Running from package

Download the corresponding executable for your operating system from the [releases page](https://github.com/eugabrielsilva/serial2midi-gui/releases) and run it. No installation is required.

## Running from source

Python is required.

Clone the repo and run the following commands in order:

1. `python3 -m venv venv` (only on the first run)
2. `source venv/bin/activate`
3. `pip install -r dependencies.txt`
4. `python3 main.py`

## Building the executable

Python is required.

Clone the repo and run the following commands in order:

1. `python3 -m venv venv` (only on the first run)
2. `source venv/bin/activate`
3. `pip install -r dependencies.txt`
4. `chmod +x build.sh`
5. `./build.sh`

The executable file will be available in the `dist` folder.
