#!/usr/bin/python

import serial
import serial.tools.list_ports
import time
import traceback
import sys
import threading
import json
import os
from enum import Enum
import asyncio
import queue

MIDI_SYSEX = 0xF0
MIDI_SYSEX_TYPE_NON_REALTIME = 0x7E
MIDI_SYSEX_END = 0xF7
MIDI_SYSEX_GENERAL_INFORMATION = 0x06
MIDI_SYSEX_REQUEST_IDENTITY = 0x01
MIDI_SYSEX_REPLY_IDENTITY = 0x02

class LogLevel(Enum):
    INFO = 1,
    WARN = 2,
    ERROR = 3,
    DEBUG = 4,
    VERBOSE = 5

LOG_LEVELS = [LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR]
LOG_HOOKS = []
MIDI_PORT_NAME = "Serial2MIDI"

def logger(level: LogLevel):
    if level not in LOG_LEVELS:
        return lambda * args: None

    def emit(*args):
        message = "[" + level.name + "] " + " ".join(str(arg) for arg in args)
        print(message)
        for hook in LOG_HOOKS:
            try:
                hook(message)
            except Exception:
                pass

    return emit

error = logger(LogLevel.ERROR)
warn = logger(LogLevel.WARN)
debug = logger(LogLevel.DEBUG)
info = logger(LogLevel.INFO)
verbose = logger(LogLevel.VERBOSE)

# Small helper, see https://stackoverflow.com/questions/2352181/how-to-use-a-dot-to-access-members-of-dictionary
class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

class MidiError(Exception):
    pass

def find_device_port_by_serial_attribute(serial_attribute):
    #context = pyudev.Context()
    #for device in context.list_devices().match_attribute("serial", "0000:00:1a.0"):
    #    return device.device_node
    #return ""
    for p in serial.tools.list_ports.comports():
        device_path = p.device
        context = pyudev.Context()
        device = pyudev.Devices.from_device_file(filename=device_path, context=context)
        for a in device.ancestors:
            try:
                _serial = a.attributes.get('serial').decode('utf-8')
                print(_serial)
                if _serial == serial_attribute:
                    return device_path
            except:
                pass

    return ""



def logException(e):
    error("ERROR", e)
    print(traceback.format_exc())
    print(sys.exc_info()[0])


def serial_set_callback(serial, cb, on_exception):
    interrupt_event = threading.Event()
    def worker():
        try:
            while not interrupt_event.is_set():
                buf = serial.read(3)
                cb(buf)
        except Exception as e:
            on_exception(e)
        verbose("Stopped worker")
        
    thread = threading.Thread(target=worker)
    thread.start()

    def stop():
        interrupt_event.set()
        thread.join()
                
    return stop

class Serial2Midi():
    def __init__(self, baud_rate, sleep_interval, device_path):
        self.name = MIDI_PORT_NAME
        self.sleep_interval = sleep_interval
        self.baud_rate = baud_rate
        self.start_time = time.time()
        self.device_path = device_path

        self.should_stop = False
        self._trigger_interrupt = None
        

    async def run(self):
        try:
            import rtmidi
        except Exception as exc:
            raise RuntimeError(
                "python-rtmidi could not be loaded. Rebuild the app in the target macOS environment."
            ) from exc

        def safe_set_client_name(midi_client, name):
            # Some backends (for example CoreMIDI) do not support changing client names.
            try:
                midi_client.set_client_name(name)
            except NotImplementedError:
                warn("MIDI backend does not support changing client name; using default backend name")

        virtualMidiInput = rtmidi.MidiIn()
        safe_set_client_name(virtualMidiInput, self.name)
        virtualMidiInput.open_virtual_port(self.name)
        virtualMidiOutput = rtmidi.MidiOut()
        safe_set_client_name(virtualMidiOutput, self.name)
        virtualMidiOutput.open_virtual_port(self.name)

        found_device = True
        while self.should_stop is False:
            device_path = self.device_path

            info("Device path: " + device_path)
            try:
                serialMidi = None
                try:
                    serialMidi = serial.Serial(device_path, self.baud_rate, timeout=1, exclusive=True)
                except serial.SerialException as e:
                    if found_device == True:
                        info("Could not connect to ", device_path, ". Error: " + str(e))
                        found_device = False
                    time.sleep(self.sleep_interval)
                    continue
                except Exception as e:
                    logException(e)
                    serialMidi.close()

                info("Opened device \"{}\" as \"{}\" with baud rate of {}".format(device_path, self.name, self.baud_rate))
                found_device = True

                interrupt = threading.Event()
                self._trigger_interrupt = lambda: interrupt.set()

                virtualMidiInput.set_callback(lambda midi_message, time: self.process_serial_output(midi_message[0], serialMidi))

                def on_serial_exception(exception):
                    logException(exception)
                    self._trigger_interrupt()
                stop_serial = serial_set_callback(serialMidi, lambda buf: self.process_serial_input(buf, virtualMidiOutput), on_serial_exception)

                interrupt.wait()
                
                verbose("Interrupted main loop")
                
                stop_serial()
                serialMidi.close()
            except Exception as e:
                logException(e)

            time.sleep(self.sleep_interval)
        
        virtualMidiInput.close_port()
        virtualMidiOutput.close_port()
        verbose("Main loop exit")
    
    def trigger_interrupt(self):
        if self._trigger_interrupt is not None:
            verbose("Triggering interrupt")
            self._trigger_interrupt()
    
    def stop(self):
        if self.should_stop is True:
            return
        print("\n")
        info("Stopping...")
        self.should_stop = True
        self.trigger_interrupt()
    
    def process_serial_input(self, buf, virtualMidiOutput):
        len_buf = len(buf)
        if len_buf == 3:
            split = [buf[i] for i in range (0, len(buf))]
            info(self.time_since_start(), "[MIDI <-]", hex(split[0]), hex(split[1]), hex(split[2]))
            virtualMidiOutput.send_message(buf)
        elif len_buf > 0:
            warn("Buffer incomplete")

    def process_serial_output(self, buf, serialMidi):
        try:
            if buf is not None:
                info(self.time_since_start(), "[MIDI ->]", hex(buf[0]), hex(buf[1]), hex(buf[2]))
                serialMidi.write(buf)
        except Exception as e:
            logException(e)
            self.trigger_interrupt()

    def time_since_start(self):
        return time.time() - self.start_time

def deviceIsExclusive(device, timeout=4):
    try:
        serial.Serial(device, 115200, timeout=3, exclusive=True)
    except serial.serialutil.SerialException:
        return False
    return True

def sysexIdentityRequest(device, timeout=4):
    try:
        serialMidi = serial.Serial(device, 115200, timeout=3, exclusive=True)
    except serial.serialutil.SerialException:
        return False

    def readOneByte():
        return int.from_bytes(serialMidi.read(), 'little', signed=False)

    def cleanBufferFromSysEx():
        while readOneByte() != MIDI_SYSEX_END:
            pass

    def tryParsingSysexIdentityReply():
        sysex_byte = readOneByte()
        if sysex_byte != MIDI_SYSEX:
            debug('Received 0x{:02X}, but waiting for MIDI_SYSEX (0x{:02X})...'.format(sysex_byte, MIDI_SYSEX))
            return False

        debug('received sysex message...')

        sysex_nonrealtime_type = readOneByte()
        if sysex_nonrealtime_type != MIDI_SYSEX_TYPE_NON_REALTIME:
            debug('Received sysex type of 0x{:02X}, but expected MIDI_SYSEX_TYPE_NON_REALTIME (0x{:02X}). Aborting.'.format(sysex_nonrealtime_type, MIDI_SYSEX_TYPE_NON_REALTIME))
            return False

        sysex_channel = readOneByte()
        debug('sysex channel is 0x{:02X}'.format(sysex_channel))

        sysex_general_information = readOneByte()
        if sysex_general_information != MIDI_SYSEX_GENERAL_INFORMATION:
            raise MidiError('[err] Received sysex action of 0x{:02X}, but expected MIDI_SYSEX_GENERAL_INFORMATION (0x{:02X}) Aborting.'.format(sysex_general_information, MIDI_SYSEX_GENERAL_INFORMATION))

        sysex_reply_identity = readOneByte()
        if sysex_reply_identity != MIDI_SYSEX_REPLY_IDENTITY:
            raise MidiError('Received sysex reply of 0x{:02X}, but expected MIDI_SYSEX_REPLY_IDENTITY (0x{:02X})'.format(sysex_reply_identity, MIDI_SYSEX_REPLY_IDENTITY))

        manufacturer_id = readOneByte()
        family_code_one = readOneByte()
        family_code_two = readOneByte()
        model_number_one = readOneByte()
        model_number_two = readOneByte()
        version_number_one = readOneByte()
        version_number_two = readOneByte()
        version_number_three = readOneByte()
        version_number_four = readOneByte()

        identity = {
            "manufacturer": "0x{:02x}".format(manufacturer_id),
            "family_code": "{}.{}".format(family_code_one, family_code_two),
            "model_number": "{}.{}".format(model_number_one, model_number_two),
            "version": "{}.{}.{}.{}".format(version_number_one, version_number_two, version_number_three, version_number_four)
        }

        sysex_end = readOneByte()
        if sysex_end != MIDI_SYSEX_END:
            raise MidiError('Received byte of 0x{:02X}, but expected MIDI_SYSEX_END (0x{:02X}) Aborting.'.format(sysex_end, MIDI_SYSEX_END))

        return identity

    # We need to wait until the arduino is ready to read...
    start = time.time()

    while time.time() - start < 3.0:
        if serialMidi.in_waiting > 0:
            identity = tryParsingSysexIdentityReply()
            if identity is not False:
                return identity



    serialMidi.write(bytearray([
        MIDI_SYSEX,
        MIDI_SYSEX_TYPE_NON_REALTIME,
        0x1,
        MIDI_SYSEX_GENERAL_INFORMATION, 
        MIDI_SYSEX_REQUEST_IDENTITY,
        MIDI_SYSEX_END
    ]))
    serialMidi.flush()
    debug("Sent request")

    while time.time() - start < timeout:
        identity = tryParsingSysexIdentityReply()
        if identity is not False:
            return identity
    return False

async def findDevices(probe_identity=True):
    import serial.tools.list_ports

    async def task(port_info):

        device_info = dotdict({
            'device_path': port_info.device,
            'usb_description': port_info.product,
            'usb_vid': port_info.vid,
            'usb_pid': port_info.pid,
            'usb_location': port_info.location,
            'usb_manufacturer': port_info.manufacturer,
            'exclusive': deviceIsExclusive(port_info.device),
            'midi_identity': dotdict({
                'manufacturer': None,
                'family_code': None,
                'model_number': None,
                'version': None
            })

        })

        if probe_identity:
            identity = False
            try:
                identity = await asyncio.to_thread(sysexIdentityRequest, port_info.device)
            except Exception as e:
                print("\nError in sysexIdentityRequest():\n {}".format(traceback.format_exc()))

            if identity is not False:
                device_info.midi_identity = dotdict({
                    'manufacturer': identity['manufacturer'],
                    'family_code': identity['family_code'],
                    'model_number': identity['model_number'],
                    'version': identity['version']
                })
        return device_info

    ports = serial.tools.list_ports.comports()
    for device_info_task in asyncio.as_completed([task(port_info) for port_info in ports]):
        device_info = await device_info_task
        yield device_info


async def listDevices():
    print("# Devices")
    i = 0

    async for port_info in findDevices():
        print(" ")
        for key, value in port_info.items():
            if key == 'midi_identity' and value is not None:
                for sub_key, sub_value in value.items():
                    print("device_info.{}.{}: {}".format(key, sub_key, sub_value))
                continue

            print("device_info.{}: {}".format(key, value))
        i += 1

    if i == 0:
        print("No devices found :/")


class Serial2MidiGUI:
    def __init__(self):
        try:
            from PySide6 import QtCore, QtWidgets
        except Exception as exc:
            raise RuntimeError("PySide6 is required for GUI mode") from exc

        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.config_path = os.path.join(os.path.expanduser("~"), ".serial2midi_config.json")
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle("Serial2MIDI")
        self.window.resize(860, 560)

        self.log_queue = queue.Queue()
        self.event_queue = queue.Queue()
        self.serial_to_midi = None
        self.bridge_thread = None
        self.list_thread = None
        self.device_options = {}
        self.baud_rate_options = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
        self.gui_sleep_interval = 0.3
        self.selected_device_value = "Select a device"
        self._closed = False

        self.baud_rate_value = "115200"

        self._load_config()

        self._build_ui()
        self.app.aboutToQuit.connect(self.on_close)

        self.timer = QtCore.QTimer(self.window)
        self.timer.timeout.connect(self._drain_queues)
        self.timer.start(100)

        self.log_hook = lambda message: self.log_queue.put(message)
        LOG_HOOKS.append(self.log_hook)

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                config = json.load(config_file)
            saved_baud_rate = str(config.get("baud_rate", "115200"))
            if saved_baud_rate not in self.baud_rate_options:
                self.baud_rate_options.append(saved_baud_rate)
            self.baud_rate_value = saved_baud_rate
            self.selected_device_value = str(config.get("selected_device", "Select a device") or "Select a device")
        except Exception:
            pass

    def _save_config(self):
        baud_rate_value = self.baud_rate_combo.currentText().strip() if hasattr(self, "baud_rate_combo") else self.baud_rate_value
        selected_device_value = self.device_combo.currentText().strip() if hasattr(self, "device_combo") else self.selected_device_value

        config = {
            "baud_rate": baud_rate_value or "115200",
            "selected_device": selected_device_value or "Select a device"
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as config_file:
                json.dump(config, config_file, indent=2)
        except Exception:
            self.log_queue.put("[WARN] Could not save settings")

    def _build_ui(self):
        QtWidgets = self.QtWidgets

        main_layout = QtWidgets.QVBoxLayout(self.window)

        config_group = QtWidgets.QGroupBox("Configuration")
        config_layout = QtWidgets.QGridLayout(config_group)

        config_layout.addWidget(QtWidgets.QLabel("MIDI Name"), 0, 0)
        fixed_name = QtWidgets.QLabel(MIDI_PORT_NAME)
        config_layout.addWidget(fixed_name, 0, 1)

        config_layout.addWidget(QtWidgets.QLabel("Baud Rate"), 0, 2)
        self.baud_rate_combo = QtWidgets.QComboBox()
        self.baud_rate_combo.addItems(self.baud_rate_options)
        self.baud_rate_combo.setCurrentText(self.baud_rate_value)
        config_layout.addWidget(self.baud_rate_combo, 0, 3)

        config_layout.addWidget(QtWidgets.QLabel("Device"), 1, 0)
        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.addItem("Select a device")
        self.device_combo.setCurrentText(self.selected_device_value)
        config_layout.addWidget(self.device_combo, 1, 1, 1, 3)

        main_layout.addWidget(config_group)

        actions_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Start Bridge")
        self.start_button.clicked.connect(self.start_bridge)
        actions_layout.addWidget(self.start_button)

        self.stop_button = QtWidgets.QPushButton("Stop Bridge")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_bridge)
        actions_layout.addWidget(self.stop_button)

        self.refresh_button = QtWidgets.QPushButton("Refresh Devices")
        self.refresh_button.clicked.connect(self.refresh_devices)
        actions_layout.addWidget(self.refresh_button)

        actions_layout.addStretch()
        self.status_label = QtWidgets.QLabel("Stopped")
        actions_layout.addWidget(self.status_label)
        main_layout.addLayout(actions_layout)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        main_layout.addWidget(self.log_box)

        self.refresh_devices()

    def append_log(self, message):
        self.log_box.appendPlainText(message)

    def _drain_queues(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.append_log(message)

        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if event_type == "devices":
                self._update_device_selector(payload)
            elif event_type == "stopped":
                self._set_stopped_state()

    def _read_and_validate_config(self):
        selected = self.device_combo.currentText().strip()
        if selected not in self.device_options or self.device_options[selected] is None:
            raise ValueError("Please select a device")
        device_path = self.device_options[selected]

        try:
            baud_rate = int(self.baud_rate_combo.currentText().strip())
        except ValueError:
            raise ValueError("Baud rate must be an integer")

        return baud_rate, self.gui_sleep_interval, device_path

    def start_bridge(self):
        if self.bridge_thread is not None and self.bridge_thread.is_alive():
            self.log_queue.put("Bridge is already running")
            return

        try:
            baud_rate, sleep_interval, device_path = self._read_and_validate_config()
        except ValueError as exc:
            self.log_queue.put("[ERROR] " + str(exc))
            return

        self._save_config()

        self.serial_to_midi = Serial2Midi(baud_rate, sleep_interval, device_path)

        def runner():
            try:
                asyncio.run(self.serial_to_midi.run())
            except Exception:
                self.log_queue.put(traceback.format_exc())
            finally:
                self.log_queue.put("Bridge stopped")
                self.event_queue.put(("stopped", None))

        self.bridge_thread = threading.Thread(target=runner, daemon=True)
        self.bridge_thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Running")
        self.log_queue.put("Bridge started")

    def _set_stopped_state(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopped")

    def stop_bridge(self):
        if self.serial_to_midi is None:
            return
        self.serial_to_midi.stop()
        self.log_queue.put("Requesting bridge stop...")

    def refresh_devices(self):
        if self.list_thread is not None and self.list_thread.is_alive():
            self.log_queue.put("A device listing is already in progress")
            return

        self._save_config()

        async def gather_devices():
            devices = []
            async for port_info in findDevices(probe_identity=False):
                devices.append(port_info)
            return devices

        def runner():
            try:
                self.log_queue.put("Refreshing device list...")
                devices = asyncio.run(gather_devices())
                self.event_queue.put(("devices", devices))
            except Exception:
                self.log_queue.put(traceback.format_exc())

        self.list_thread = threading.Thread(target=runner, daemon=True)
        self.list_thread.start()

    def _update_device_selector(self, devices):
        auto_label = "Select a device"
        current_text = self.device_combo.currentText().strip()
        previous_selection = (current_text if current_text and current_text != auto_label else None) or self.selected_device_value or auto_label
        options = {auto_label: None}
        values = [auto_label]

        for port_info in devices:
            label = "{} | {}".format(port_info.device_path, port_info.usb_description or "Unknown USB device")
            options[label] = port_info.device_path
            values.append(label)

        self.device_options = options
        self.device_combo.clear()
        self.device_combo.addItems(values)

        if previous_selection in options:
            self.device_combo.setCurrentText(previous_selection)
        else:
            self.device_combo.setCurrentText(auto_label)

        self.log_queue.put("Found {} device(s)".format(len(devices)))
        self._save_config()

    def on_close(self):
        if self._closed:
            return
        self._closed = True
        self._save_config()
        if self.serial_to_midi is not None:
            self.serial_to_midi.stop()
        try:
            LOG_HOOKS.remove(self.log_hook)
        except ValueError:
            pass

    def run(self):
        self.window.show()
        self.app.exec()


def write_crash_log(exc):
    crash_path = os.path.join(os.path.expanduser("~"), "serial2midi_crash.log")
    with open(crash_path, "w", encoding="utf-8") as crash_file:
        crash_file.write("Serial2MIDI fatal error\n\n")
        crash_file.write(str(exc) + "\n\n")
        crash_file.write(traceback.format_exc())
    return crash_path

async def main():
    import argparse

    parser = argparse.ArgumentParser(prog='serial2midi', description='Convert a USB Serial device to a Midi device', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--device', dest='device_path', default=None,
                        help='Serial device path, for example /dev/ttyUSB0 (required in --cli mode)')
    parser.add_argument('--baud-rate', dest='baud_rate', default=115200,
                        help='Baud rate of serial device')
    parser.add_argument('--sleep-interval', dest='sleep_interval', default=0.3,
                        help='How many seconds we wait between looking for reconnected device. Float is possible.')

    parser.add_argument('--list', default=False, action="store_true", help='List available devices')
    parser.add_argument('--gui', default=False, action="store_true", help='Open graphical interface')
    parser.add_argument('--cli', default=False, action="store_true", help='Force terminal mode instead of GUI')
    args = parser.parse_args()

    if args.list:
        await listDevices()
        return 0

    if args.gui or not args.cli:
        try:
            gui = Serial2MidiGUI()
            gui.run()
            return 0
        except Exception as exc:
            print("Could not start GUI mode:", exc)
            print("Try running in CLI mode with --cli")
            return 1

    if args.device_path is None:
        print("--device is required in --cli mode. Use --list to discover available devices.")
        return 1

    serial_to_midi = Serial2Midi(args.baud_rate, args.sleep_interval, args.device_path)

    
    import signal
    for sig in ('TERM', 'HUP', 'INT'):
        signal.signal(getattr(signal, 'SIG'+sig), lambda signo, _frame: serial_to_midi.stop());

    await serial_to_midi.run()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        crash_log = write_crash_log(exc)
        print("Fatal error. See crash log:", crash_log)
        raise
