#!/usr/bin/env python3
import argparse
import os
import shutil
import stat
import subprocess
import sys
import time

from concurrent.futures import ProcessPoolExecutor

from utility.utils import is_windows_platform

PORT_MIN = 11000
PORT_MAX = 65535
PORT_RANGE = 500

__file_path__ = os.path.dirname(os.path.realpath(__file__))

CONFLUX_BINARY = "conflux.exe" if is_windows_platform() else "conflux"

def print_testcase_result(color, glyph, script, start_time):
    print(color[1] + glyph + " Testcase " + script + "\telapsed: " + str(int(time.time() - start_time)) + " seconds" + color[0], flush=True)

def run_single_test(py, script, test_dir, index, port_min, port_max):
    try:
        # Make sure python thinks it can write unicode to its stdout
        "\u2713".encode("utf_8").decode(sys.stdout.encoding)
        TICK = "✓ "
        CROSS = "✖ "
        CIRCLE = "○ "
    except UnicodeDecodeError:
        TICK = "P "
        CROSS = "x "
        CIRCLE = "o "

    BOLD, BLUE, RED, GREY = ("", ""), ("", ""), ("", ""), ("", "")
    if os.name == "posix" or os.name == "nt":
        # primitive formatting on supported
        # terminal via ANSI escape sequences:
        BOLD = ("\033[0m", "\033[1m")
        BLUE = ("\033[0m", "\033[0;34m")
        RED = ("\033[0m", "\033[0;31m")
        GREY = ("\033[0m", "\033[1;30m")
    print("Running " + script, flush=True)
    port_min = port_min + (index * PORT_RANGE) % (port_max - port_min)
    start_time = time.time()
    try:
        subprocess.check_output(
            args=[py, script, "--randomseed=1", f"--port-min={port_min}"],
            stdin=None,
            cwd=test_dir,
        )
    except subprocess.CalledProcessError as err:
        print_testcase_result(RED, CROSS, script, start_time)
        print("Output of " + script + "\n" + err.output.decode("utf-8"), flush=True)
        raise err
    print_testcase_result(BLUE, TICK, script, start_time)

def run():
    start_time = time.time()
    dir_name = os.path.join(__file_path__, "tmp")
    if not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)

    conflux_path = os.path.join(dir_name, CONFLUX_BINARY)
    if not os.path.exists(conflux_path):
        build_conflux(conflux_path)

    parser = argparse.ArgumentParser(usage="%(prog)s [options]")
    parser.add_argument(
        "--max-workers",
        dest="max_workers",
        default=5,
        type=int,
    )
    parser.add_argument(
        "--port-max",
        dest="port_max",
        default=PORT_MAX,
        type=int,
    )
    parser.add_argument(
        "--port-min",
        dest="port_min",
        default=PORT_MIN,
        type=int,
    )

    options = parser.parse_args()

    TEST_SCRIPTS = []

    test_dir = os.path.dirname(os.path.realpath(__file__))
    test_subdirs = [
        "",  # include test_dir itself
    ]

    slow_tests = {"random_test.py", "same_root_test.py"}
    # TODO(zz): enable sync_test if proof validation issue fixed
    long_manual_tests = {"fuzz_test.py", "sync_test.py"}

    for subdir in test_subdirs:
        subdir_path = os.path.join(test_dir, subdir)
        for file in os.listdir(subdir_path):
            if file.endswith("_test.py"):
                rel_path = os.path.join(subdir, file)
                if rel_path not in slow_tests and rel_path not in long_manual_tests:
                    TEST_SCRIPTS.append(rel_path)

    executor = ProcessPoolExecutor(max_workers=options.max_workers)
    test_results = []

    py = "python3"
    if hasattr(sys, "getwindowsversion"):
        py = "python"

    i = 0
    # Start slow tests first to avoid waiting for long-tail jobs
    for script in slow_tests:
        f = executor.submit(
            run_single_test, py, script, test_dir, i, options.port_min, options.port_max
        )
        test_results.append((script, f))
        i += 1
    for script in TEST_SCRIPTS:
        f = executor.submit(
            run_single_test, py, script, test_dir, i, options.port_min, options.port_max
        )
        test_results.append((script, f))
        i += 1

    failed = set()
    for script, f in test_results:
        try:
            f.result()
        except subprocess.CalledProcessError as err:
            print("CalledProcessError " + repr(err))
            failed.add(script)

    print("Elapsed: " + str(int(time.time() - start_time)) + " seconds", flush=True)

    if len(failed) > 0:
        print("The following test fails: ")
        for c in failed:
            print(c)
        sys.exit(1)


def build_conflux(conflux_path):
    destination_path = os.path.join(__file_path__, "tmp", "conflux_tmp")
    if os.path.exists(destination_path):
        shutil.rmtree(destination_path)

    clone_command = "git clone https://github.com/Conflux-Chain/conflux-rust.git"
    clone_with_path = clone_command + " " + destination_path
    os.system(clone_with_path)

    origin_path = os.getcwd()
    os.chdir(destination_path)
    os.system("cargo build --release --bin conflux")

    path = os.path.join(destination_path, "target", "release", CONFLUX_BINARY)
    shutil.copyfile(path, conflux_path)

    if not is_windows_platform():
        st = os.stat(conflux_path)
        os.chmod(conflux_path, st.st_mode | stat.S_IEXEC)

    os.chdir(origin_path)


if __name__ == "__main__":
    run()
