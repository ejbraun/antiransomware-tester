"""
Python script that runs on VM startup and insures that the guest module will be
ran with admin privileges.
"""
from guest import mainFunc
import time
import ctypes
import sys
import google.auth.exceptions

def is_admin():
    """
    Return: True if admin. Else, False
    Checks if shell that script is running in has admin privileges.
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if is_admin():
    while True:
        try:
            # Attempt to execute mainFunc() (exists in guest.py)
            mainFunc()
            break
        # Default application credentials were not found and is due to the fact that VM is not running in cloud.
        except google.auth.exceptions.DefaultCredentialsError:
            print("Not running in cloud.")
            # Wait 10 seconds before trying again.
            time.sleep(10)
        # Unexpected error encountered and loop should be exited.
        except Exception:
            print("Unexpected exception encountered")
            raise
# If python script is not running as admin, launch new shell with admin privileges
else:
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
