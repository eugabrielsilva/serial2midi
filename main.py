#!/usr/bin/python

import rtmidi
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
import tkinter as tk
from tkinter import ttk

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

#LOG_LEVELS = [LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR, LogLevel.DEBUG]
LOG_LEVELS = [LogLevel.INFO]
LOG_HOOKS = []

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
    def __init__(self, name, baud_rate, sleep_interval, device_path):
        self.name = name
        self.sleep_interval = sleep_interval
        self.baud_rate = baud_rate
        self.start_time = time.time()
        self.device_path = device_path

        self.should_stop = False
        self._trigger_interrupt = None
        

    async def run(self):
        virtualMidiInput = rtmidi.MidiIn()
        virtualMidiInput.set_client_name(self.name)
        virtualMidiInput.open_virtual_port(self.name)
        virtualMidiOutput = rtmidi.MidiOut()
        virtualMidiOutput.set_client_name(self.name)
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

async def findDevices():
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
        #identity = sysexIdentityRequest(port_info.device)
        
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
        self.config_path = "serial2midi_config.json"
        self.root = tk.Tk()
        self.root.title("Serial2MIDI")
        self.root.geometry("820x560")

        self.log_queue = queue.Queue()
        self.serial_to_midi = None
        self.bridge_thread = None
        self.list_thread = None
        self.device_options = {}
        self.baud_rate_options = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
        self.gui_sleep_interval = 0.3

        self.name_var = tk.StringVar(value="Serial2MIDI")
        self.baud_rate_var = tk.StringVar(value="115200")
        self.selected_device_var = tk.StringVar(value="Select a device")
        self.status_var = tk.StringVar(value="Stopped")

        self._load_config()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain_log_queue)

        self.log_hook = lambda message: self.log_queue.put(message)
        LOG_HOOKS.append(self.log_hook)

    def _load_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                config = json.load(config_file)
            self.name_var.set(str(config.get("name", "Serial2MIDI")))
            saved_baud_rate = str(config.get("baud_rate", "115200"))
            if saved_baud_rate not in self.baud_rate_options:
                self.baud_rate_options.append(saved_baud_rate)
            self.baud_rate_var.set(saved_baud_rate)
            self.selected_device_var.set(str(config.get("selected_device", "Select a device") or "Select a device"))
        except Exception:
            pass

    def _save_config(self):
        config = {
            "name": self.name_var.get().strip() or "Serial2MIDI",
            "baud_rate": self.baud_rate_var.get().strip() or "115200",
            "selected_device": self.selected_device_var.get().strip() or "Select a device"
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as config_file:
                json.dump(config, config_file, indent=2)
        except Exception:
            self.log_queue.put("[WARN] Could not save settings")

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        config = ttk.LabelFrame(frame, text="Configuration", padding=10)
        config.pack(fill=tk.X)

        ttk.Label(config, text="MIDI Name").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(config, textvariable=self.name_var, width=26).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(config, text="Baud Rate").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        self.baud_rate_combo = ttk.Combobox(config, textvariable=self.baud_rate_var, state="readonly", width=26)
        self.baud_rate_combo["values"] = self.baud_rate_options
        self.baud_rate_combo.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(config, text="Device").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        self.device_combo = ttk.Combobox(config, textvariable=self.selected_device_var, state="readonly", width=64)
        self.device_combo["values"] = ["Select a device"]
        self.device_combo.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=4, pady=4)

        actions = ttk.Frame(frame, padding=(0, 10, 0, 10))
        actions.pack(fill=tk.X)

        self.start_button = ttk.Button(actions, text="Start Bridge", command=self.start_bridge)
        self.start_button.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_button = ttk.Button(actions, text="Stop Bridge", command=self.stop_bridge, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 8))

        self.refresh_button = ttk.Button(actions, text="Refresh Devices", command=self.refresh_devices)
        self.refresh_button.pack(side=tk.LEFT)

        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.RIGHT)

        log_frame = ttk.LabelFrame(frame, text="Logs", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_box = tk.Text(log_frame, wrap=tk.WORD, height=20)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_box.configure(state=tk.DISABLED)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_box.configure(yscrollcommand=scrollbar.set)

        self.refresh_devices()

    def append_log(self, message):
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, message + "\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _drain_log_queue(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.append_log(message)
        self.root.after(100, self._drain_log_queue)

    def _read_and_validate_config(self):
        name = self.name_var.get().strip() or "Serial2MIDI"
        selected = self.selected_device_var.get().strip()
        if selected not in self.device_options or self.device_options[selected] is None:
            raise ValueError("Please select a device")
        device_path = self.device_options[selected]

        try:
            baud_rate = int(self.baud_rate_var.get().strip())
        except ValueError:
            raise ValueError("Baud rate must be an integer")

        return name, baud_rate, self.gui_sleep_interval, device_path

    def start_bridge(self):
        if self.bridge_thread is not None and self.bridge_thread.is_alive():
            self.log_queue.put("Bridge is already running")
            return

        try:
            name, baud_rate, sleep_interval, device_path = self._read_and_validate_config()
        except ValueError as exc:
            self.log_queue.put("[ERROR] " + str(exc))
            return

        self._save_config()

        self.serial_to_midi = Serial2Midi(name, baud_rate, sleep_interval, device_path)

        def runner():
            try:
                asyncio.run(self.serial_to_midi.run())
            except Exception:
                self.log_queue.put(traceback.format_exc())
            finally:
                self.log_queue.put("Bridge stopped")
                self.root.after(0, self._set_stopped_state)

        self.bridge_thread = threading.Thread(target=runner, daemon=True)
        self.bridge_thread.start()

        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.status_var.set("Running")
        self.log_queue.put("Bridge started")

    def _set_stopped_state(self):
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.status_var.set("Stopped")

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
            async for port_info in findDevices():
                devices.append(port_info)
            return devices

        def update_device_selector(devices):
            auto_label = "Select a device"
            previous_selection = self.selected_device_var.get().strip() or auto_label
            options = {auto_label: None}
            values = [auto_label]

            for port_info in devices:
                label = "{} | {}".format(port_info.device_path, port_info.usb_description or "Unknown USB device")
                options[label] = port_info.device_path
                values.append(label)

            self.device_options = options
            self.device_combo["values"] = values

            if previous_selection in options:
                self.selected_device_var.set(previous_selection)
            else:
                self.selected_device_var.set(auto_label)

            self.log_queue.put("Found {} device(s)".format(len(devices)))
            self._save_config()

        def runner():
            try:
                self.log_queue.put("Refreshing device list...")
                devices = asyncio.run(gather_devices())
                self.root.after(0, lambda: update_device_selector(devices))
            except Exception:
                self.log_queue.put(traceback.format_exc())

        self.list_thread = threading.Thread(target=runner, daemon=True)
        self.list_thread.start()

    def on_close(self):
        self._save_config()
        if self.serial_to_midi is not None:
            self.serial_to_midi.stop()
        try:
            LOG_HOOKS.remove(self.log_hook)
        except ValueError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

async def main():
    import argparse

    parser = argparse.ArgumentParser(prog='serial2midi', description='Convert a USB Serial device to a Midi device', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--name', dest='name', default='Serial2MIDI',
                        help='Name of the virtual midi device')
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
        gui = Serial2MidiGUI()
        gui.run()
        return 0

    if args.device_path is None:
        print("--device is required in --cli mode. Use --list to discover available devices.")
        return 1

    serial_to_midi = Serial2Midi(args.name, args.baud_rate, args.sleep_interval, args.device_path)

    
    import signal
    for sig in ('TERM', 'HUP', 'INT'):
        signal.signal(getattr(signal, 'SIG'+sig), lambda signo, _frame: serial_to_midi.stop());

    await serial_to_midi.run()

if __name__ == '__main__':
    asyncio.run(main())
