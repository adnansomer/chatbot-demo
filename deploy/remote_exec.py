"""One-off SSH helper for the Huawei Cloud ECS deployment.

Credentials are read from environment variables (SSH_HOST, SSH_USER,
SSH_PASS) so nothing sensitive is written to disk. Not part of the
application; used only from the terminal during deployment.

Usage:
    python remote_exec.py "some remote command"
    python remote_exec.py --put local_path remote_path
    python remote_exec.py --putdir local_dir remote_dir
"""

from __future__ import annotations

import os
import posixpath
import stat
import sys

import paramiko


def connect() -> paramiko.SSHClient:
    host = os.environ["SSH_HOST"]
    user = os.environ["SSH_USER"]
    password = os.environ["SSH_PASS"]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=20,
                   look_for_keys=False, allow_agent=False)
    return client


def run(client: paramiko.SSHClient, command: str) -> int:
    stdin, stdout, stderr = client.exec_command(command, get_pty=True)
    for line in stdout:
        print(line, end="")
    err = stderr.read().decode(errors="replace")
    if err.strip():
        print(err, file=sys.stderr, end="")
    return stdout.channel.recv_exit_status()


def put_file(sftp: paramiko.SFTPClient, local: str, remote: str) -> None:
    remote_dir = posixpath.dirname(remote)
    mkdirs(sftp, remote_dir)
    sftp.put(local, remote)


def mkdirs(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    if not remote_dir or remote_dir == "/":
        return
    try:
        sftp.stat(remote_dir)
        return
    except FileNotFoundError:
        pass
    mkdirs(sftp, posixpath.dirname(remote_dir))
    try:
        sftp.mkdir(remote_dir)
    except OSError:
        pass


def put_dir(sftp: paramiko.SFTPClient, local_dir: str, remote_dir: str) -> None:
    mkdirs(sftp, remote_dir)
    for name in os.listdir(local_dir):
        if name in (".venv", "__pycache__", ".git"):
            continue
        local_path = os.path.join(local_dir, name)
        remote_path = posixpath.join(remote_dir, name)
        if os.path.isdir(local_path):
            put_dir(sftp, local_path, remote_path)
        else:
            sftp.put(local_path, remote_path)


def main() -> None:
    client = connect()
    try:
        if sys.argv[1] == "--put":
            sftp = client.open_sftp()
            put_file(sftp, sys.argv[2], sys.argv[3])
            print(f"uploaded {sys.argv[2]} -> {sys.argv[3]}")
            sftp.close()
        elif sys.argv[1] == "--putdir":
            sftp = client.open_sftp()
            put_dir(sftp, sys.argv[2], sys.argv[3])
            print(f"uploaded dir {sys.argv[2]} -> {sys.argv[3]}")
            sftp.close()
        else:
            code = run(client, sys.argv[1])
            sys.exit(code)
    finally:
        client.close()


if __name__ == "__main__":
    main()
