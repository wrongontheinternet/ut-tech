#!/usr/bin/python2
import shlex
from functools import partial
from time import sleep

import click

from core import delete_local_files, run_container, stop_container, build_base_container, run_in_container as _run_in_container
from config import SSH_SERVER_IP, ROOT_PW

@click.group()
def cli():
    pass

@cli.command()
@click.argument('dir')
@click.option('--container_name', default='ltsp', help='Name of runc container')
def clean(dir, container_name):
    stop_container(container_name)
    delete_local_files(dir)

@cli.command()
@click.argument('dir')
@click.option('--container_name', default='ltsp', help='Name of runc container')
def install(dir, container_name):
    """
    Pulls a new ubuntu container and does minimal setup
    """
    container_name = container_name.encode('utf-8')
    def run_in_container(cmd):
        print(_run_in_container(container_name, shlex.split(cmd)))
    build_base_container(dir)
    run_container(dir, container_name)
    # Update the apt-cache on the host (important for )
    run_in_container("apt-get update")

    # TODO: I'm having trouble with apt when my host is on a different version
    # of ubuntu than the client. This is obviously pretty exciting, and I'm
    # not sure why this is a problem now but wasn't last year. More work is
    # required - although at this stage blowing away this ubuntu install is
    # not a bad choice.

    # Install the very minimum needed to get the client to build
    # We don't want to install the SSH server because we assume that the host
    # is already running SSH, and systemd will actually try to do useful things
    # wth the server if it's being installed, which will fail if the port is
    # unavailable, and give lots of prompting about overwriting the SSH config
    # which is bind-mounted from the host.
    run_in_container('apt-get install -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" -y ltsp-server')

    # Hack around broken timezone symlinking
    # https://bugs.launchpad.net/ltsp/+bug/1660392
    # TODO: Check if this is still needed
    run_in_container("rm -f /usr/share/ltsp/plugins/ltsp-build-client/Ubuntu/035-copy-timezone")

    # Build the fat client (we use lubuntu because of the low resource use,
    # is easier to use than unity and will run on the crutech P4's)
    run_in_container("ltsp-build-client --fat-client-desktop lubuntu-desktop")


    # Update the keys for the host which we're running under, not the container
    # This causes a duplicate in the ssh_known_hosts which is a little annoying
    run_in_container("ltsp-update-sshkeys {}".format(SSH_SERVER_IP))
    # Fix the ssh known hosts so users don't get a DNS Spoofing warning
    run_in_container("sed 's/^[^# ][^ ]* /* /' -i /opt/ltsp/amd64/etc/ssh/ssh_known_hosts")

    # Set up the fat client root key
    run_in_container('ltsp-chroot bash -c "echo root:{} | chpasswd"'.format(ROOT_PW))
    # Remove some of the bloatware
    run_in_container("ltsp-chroot apt-get remove xscreensaver abiword audacious blueman bluez gnumeric pidgin transmission guvcview sylpheed cups evolution* --auto-remove -y")
    # Install elective requirements
    ## Install lmms
    run_in_container("ltsp-chroot apt-get install -y lmms")
    ## Install dependancies for pybotwar
    run_in_container("ltsp-chroot apt-get install -y python3-pip python3-pyqt4 build-essential python-dev swig")
    run_in_container("ltsp-chroot -r pip3 install -y box2d")
    ## Install dependancies for NavUber
    run_in_container("ltsp-chroot -r pip3 install -y matplotlib networkx")
    ## The rest of pybotwar is copied manually to peoples home directories at present.
    # Set up the updated wine ppa (needs to be http so we can proxy it)
    # We need to allow i386 packages because wine is the worst
    run_in_container("ltsp-chroot dpkg --add-architecture i386")
    # Need to use http otherwise we can't proxy the packages
    run_in_container("ltsp-chroot apt-add-repository 'http://dl.winehq.org/wine-builds/ubuntu/'")
    run_in_container("ltsp-chroot apt-get update")
    run_in_container("ltsp-chroot apt-get install -y --install-recommends winehq-stable")
    # wine_gecko and wine_mono (using pre-downloaded msi's because upstream is terrible)
    run_in_container("mkdir -p /opt/ltsp/amd64/usr/share/wine/gecko/")
    run_in_container("mv /root/wine_gecko-2.47-x86_64.msi /opt/ltsp/amd64/usr/share/wine/gecko/")
    run_in_container("mkdir -p /opt/ltsp/amd64/usr/share/wine/mono/")
    run_in_container("mv /root/wine-mono-4.6.4.msi /opt/ltsp/amd64/usr/share/wine/mono/")
    # TODO: Install everything we need for Game Strategy
    run_in_container("ltsp-chroot apt-get install -y bzflag")
    # === Do other chroot setup here ===

    run_in_container("ltsp-update-image")

    stop_container(container_name)




if __name__ == '__main__':
    cli()
