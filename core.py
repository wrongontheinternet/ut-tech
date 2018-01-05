from __future__ import print_function

import os
import requests
import shutil
import time
from requests.exceptions import ConnectionError, MissingSchema  # TODO: Once mocker is py3 compliant, six-ify this
from subprocess import check_output, call, STDOUT

# Directory in which mocker stores the untar-ed ubuntu layers
MOCKER_UBUNTU_DIR = os.path.join(
    os.path.expanduser('~'), 'mocker/library_ubuntu/layers/contents/')

def delete_local_files(dir):
    shutil.rmtree(dir)
    shutil.rmtree(MOCKER_UBUNTU_DIR)

def download_ubuntu(reuse_existing=True):
    ''' Download the latest stable ubuntu docker image & return its path

        NOTE: This uses a _LOT_ more mobile data than you expect :(
    '''
    if os.path.exists(MOCKER_UBUNTU_DIR):
        if reuse_existing:
            return MOCKER_UBUNTU_DIR
        else:
            shutil.rmtree(MOCKER_UBUNTU_DIR)

    # Use mocker to pull the Docker layers
    # pip install git+https://github.com/wrongontheinternet/mocker
    from mocker.pull import PullCommand

    kwargs = {"<name>": "ubuntu", "<tag>": "latest"}
    try:
        PullCommand(**kwargs).run(**kwargs)
    except OSError:
        raise
        # The layers are stored as tar files, which internally have device nodes
        # in the filesystem. To create these the user unfortunately needs root
        # permissions. Everything in the script unfortunately needs to be root.
        exit("Unfortunately you need root permissions to untar devices")

    return MOCKER_UBUNTU_DIR


def test_apt_cache(cache_url="http://127.0.0.1:3142"):
    ''' Tests to see if in apt-cache is running.
    Either returns the URL of a valid apt cache, or None.
    '''
    try:
        r = requests.get(cache_url)
        # TODO: Have better check to make sure this is an apt repository
        if "APT" in r.text:
            return cache_url
    except ConnectionError:
        pass
    except MissingSchema:
        return test_apt_cache("http://{}".format(cache_url))
    # At this point either we couldn't connect or didn't seem valid
    user_cache_url = raw_input(
        "Unable to guess APT-Cache please enter URL (default port is 3142): ")
    if user_cache_url:
        return test_apt_cache(user_cache_url)
    else:
        return None

def build_base_container(dest_path, base_path=None):
    ''' Downloads a base ubuntu image, copies it with valid config
    '''
    # Check to make sure the passed base path is valid, download agin if not
    if base_path is None or not os.path.exists(base_path):
        base_path = download_ubuntu()
    # Expand the given path
    dest_path = os.path.expanduser(dest_path)
    # Ensure the destination path does not exist
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
    # TODO: Ensure that all the paths leading up to dest_path exist
    # Copy the base image across.
    # I can't work out how to get this to work, it seems to barf copying
    # probably some sparse or dev file which shutil is trying to do a buffered
    # read of.
    # shutil.copytree(base_path, dest_path, symlinks=True)
    # Copy it over like a caveman
    if check_output("cp -a {} {}".format(
            MOCKER_UBUNTU_DIR, dest_path), shell=True):
        raise IOError("Unable to copy to {}".format(dest_path))
    # Copy over the runc config file (we do not need the metadata)
    shutil.copy('systemd.config.json', os.path.join(dest_path, "config.json"))
    # Configure the container to load from our apt cache
    apt_cache = test_apt_cache()
    if apt_cache:
        with open(os.path.join(
                dest_path, 'etc/apt/apt.conf.d/01proxy'), 'w') as f:
            f.write('Acquire::http {{ Proxy "{cache_url}"; }};\n'.format(
                    cache_url=apt_cache))

def run_in_container(container_name, cmd):
    ''' Runs a command inside a container & returns output.
    Designed to be used with functools.partial to specify the container name.
    '''
    # TODO: Check if exec is complaining about the container not running
    return check_output(["runc", "exec", "-t", container_name] + cmd)

def run_container(container_path, requested_name):
    ''' Starts a container
    '''
    # TODO: Check error conditions
    to_return = check_output(
        ["runc", "run", "-d", "-b", container_path, requested_name],
        stderr=STDOUT)
    # Give systemd enough time to actually spin up
    time.sleep(10)
    return to_return

def stop_container(container_name):
    ''' Stops a container
    '''
    kill_output = check_output(
        ["runc", "exec", container_name, "kill", "-SIGRTMIN+3", "1"],
        stderr=STDOUT)
    # Give systemd enough time to actually spin down
    time.sleep(7)
    # And now reap the resources allocated in runc
    delete_output = check_output(
        ["runc", "delete", container_name], stderr=STDOUT)
