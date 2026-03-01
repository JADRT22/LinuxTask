import evdev
import os

def test_access():
    print(f"User: {os.getlogin()}")
    print("Testing access to input devices...")
    try:
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        if not devices:
            print("FAILED: No devices found.")
            return False
        
        print(f"SUCCESS: Found {len(devices)} devices accessible.")
        for dev in devices:
            print(f" - {dev.path}: {dev.name}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

if __name__ == "__main__":
    if test_access():
        print("\nAll systems go! LinuxTask should work now.")
    else:
        exit(1)
