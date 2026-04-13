# serial2midi GUI

**Graphical user interface** based on the [serial2midi](https://github.com/Jikstra/serial2midi) script, featuring several improvements.

This is a **cross-platform alternative to Hairless MIDI**. It works seamlessly on **modern operating systems** to convert serial messages (from an Arduino, for example) into MIDI data.

## Running from package

Download the executable for your operating system from the [releases page](https://github.com/eugabrielsilva/serial2midi-gui/releases) and run it. **No installation is required.**

**If a release for your operating system is unavailable or does not work properly, we recommend building the executable directly on your machine.**

## Building the executable

Python 3 is required.

Clone the repo and run the following commands in order:

1. `python3 -m venv venv` (only on the first run)
2. `source venv/bin/activate`
3. `pip install -r dependencies.txt` (only on the first run)
4. `chmod +x build.sh`
5. `./build.sh`

The executable file will be available in the `dist` folder.

## Running from source

Python 3 is required.

Clone the repo and run the following commands in order:

1. `python3 -m venv venv` (only on the first run)
2. `source venv/bin/activate`
3. `pip install -r dependencies.txt` (only on the first run)
4. `python3 main.py`

## Credits

- Originally developed by [Jikstra](https://github.com/Jikstra);
- GUI and enhancements by [eugabrielsilva](https://github.com/eugabrielsilva), with assistance from Copilot.
