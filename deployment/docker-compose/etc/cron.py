#!/usr/bin/env python3

import time
import subprocess
import sys

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

if __name__ == "__main__":
    try:
        print(sys.argv)
        stime = int(sys.argv[1])
        command = sys.argv[2]
    except ValueError:
        eprint("Invalid int param for cron.py")
        exit(1)
    except IndexError:
        eprint("Missing command to be executed")
        exit(1)
    while True:
        time.sleep(stime)
        try:
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError as cpe:
            eprint(cpe.stderr)
            exit(cpe.returncode)
