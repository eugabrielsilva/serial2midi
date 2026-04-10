# WARNING: Development continued here: https://codeberg.org/obsoleszenz/serial2midi

# Serial2MIDI

This CLI tool allows you to "convert" your serial device to virtual midi device. It also supports sending midi back to the serial device.
You can use this tool with ALSA & Jack. This tool is handy with microcontrollers like arduino uno/mega which don't support USB Midi.


## Features

- Supports ALSA & Jack as audio backends
- You can set name & baud rate
- Full duplex, this means you can not only receive midi but also send midi back to the serial device
- Auto reconnect, if you disconnect the serial device, the virtual midi device is still there and continues working if you plug the serial device in again 
- select the target serial device directly (GUI selector or CLI argument)
- supports midi sysex identity, usb pid/vid...


## Examples

Convert `/dev/ttyUSB0` to a midi device
```
serial2midi --cli --device /dev/ttyUSB0
```

List all connected usb serial devices and it's properties
```
serial2midi --list
```

Convert usb serial device to a virtual midi device with the name "MidiFoo"
```
serial2midi --cli --device /dev/ttyUSB0 --name "MidiFoo"
```

Set the baudrate
```
serial2midi --cli --device /dev/ttyUSB0 --baud-rate 96000 --name "MidiFoo"
```

# Install

## Arch

There is a PKGBUILD in the [AUR](https://aur.archlinux.org/packages/serial2midi-git/). Download it and install it like any other PKGBUILD or use an AUR helper like yay.

`yay -S serial2midi-git`

## From git/source

1. Clone this repository `git clone https://github.com/jikstra/serial2midi.git`
2. cd into the folder `cd serial2midi`
3. install python dependencies with `pip install -r dependencies.txt`
4. run the tool with `python main.py`
5. Optionally, copy it to a folder in your path, for example `cp main.py /usr/bin/serial2midi`

The `dependencies.txt` file also includes PyInstaller, so the same install step works whether you are using a virtual environment or a system/global Python environment.

## Build

Build with PyInstaller:

```bash
./build.sh
```

The script will:
- use the active virtual environment when available
- fall back to `./venv/bin/python` or `python3`
- install PyInstaller automatically if it is missing
- set `MACOSX_DEPLOYMENT_TARGET=11.0` automatically on macOS (if not already defined)
- build `dist/serial2midi.app` by default on macOS
- build `dist/serial2midi` (single file) on Linux
- apply ad-hoc signing and remove quarantine attributes on macOS

To override the macOS deployment target explicitly:

```bash
MACOSX_DEPLOYMENT_TARGET=16.0 ./build.sh
```

If the macOS app still closes unexpectedly, run the generated debug launcher:

```bash
./dist/run_serial2midi_debug.sh
```

It writes boot output to `~/serial2midi_boot.log`.

# Usage
```
usage: serial2midi [-h] [--name NAME] [--baud-rate BAUD_RATE]
                   [--device DEVICE_PATH] [--sleep-interval SLEEP_INTERVAL]
                   [--list] [--gui] [--cli]

Convert a USB Serial device to a Midi device

options:
  -h, --help            show this help message and exit
  --name NAME           Name of the virtual midi device (default:
                        Serial2MIDI)
  --device DEVICE_PATH  Serial device path, for example /dev/ttyUSB0
                        (required in --cli mode) (default: None)
  --baud-rate BAUD_RATE
                        Baud rate of serial device (default: 115200)
  --sleep-interval SLEEP_INTERVAL
                        How many seconds we wait between looking for
                        reconnected device. Float is possible. (default:
                        0.3)
  --list                List available devices (default: False)
  --gui                 Open graphical interface (default: False)
  --cli                 Force terminal mode instead of GUI (default: False)
```

## GUI

The project now also includes a graphical interface (Tkinter).

Default behavior:
- `python main.py` opens the GUI
- `python main.py --cli` starts in terminal mode

Run GUI:
```
python main.py --gui
```

In the GUI you can:
- configure MIDI name and baud rate (dropdown)
- select a device from a dropdown list
- refresh the device list using the Refresh Devices button
- start/stop the Serial <-> MIDI bridge
- monitor logs in real time
- automatically save settings in `serial2midi_config.json`


# Hacking

## Logging

Currently you can change the log level by manually adjusting the `LOG_LEVELS` array. 
