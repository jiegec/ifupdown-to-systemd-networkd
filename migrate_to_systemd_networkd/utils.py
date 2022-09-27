import os
import subprocess

import click

# https://stackoverflow.com/a/2600847/2148614


class AutoVivification(dict):
    """Implementation of perl's autovivification feature."""

    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value


def ask_write_file(dest: str, data: str):
    if os.path.exists(dest):
        # check if file differs
        orig = open(dest, "r").read()
        if orig == data:
            print("Configuration {} not changed".format(dest))
            return

        print("Showing diff of {}".format(dest))
        proc = subprocess.Popen(
            args=["diff", "-u", dest, "-"], executable="diff", stdin=subprocess.PIPE
        )
        if proc.stdin is not None:
            proc.stdin.write(data.encode("utf-8"))
            proc.stdin.close()
        proc.wait()
    else:
        print("New configuration {}".format(dest))
        print(data)

    if click.confirm("Write to {}".format(dest)):
        with open(dest, "w") as f:
            f.write(data)


def probe_systemd():
    output = subprocess.check_output(
        executable="systemctl", args=["systemctl", "--version"]
    )
    lines = list(output.decode("utf-8").split("\n"))
    version = int(lines[0].split(" ")[1])
    print("Found systemd version {}".format(version))
    return version
