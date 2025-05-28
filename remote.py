import os
import logging
from dotenv import load_dotenv
import paramiko

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SSHClientWrapper:
    """
    A simple SSH client wrapper using Paramiko to execute remote commands and transfer files.
    Configuration is loaded from environment variables or can be passed directly.
    """
    def __init__(
        self,
        hostname: str = None,
        username: str = None,
        port: int = None,
        key_filepath: str = None,
        password: str = None,
        timeout: int = 10
    ):
        # Load from env if not provided
        self.hostname = hostname or os.getenv("SSH_HOST")
        self.username = username or os.getenv("SSH_USER")
        self.port = port or int(os.getenv("SSH_PORT", 22))
        self.key_filepath = key_filepath or os.getenv("SSH_KEY_PATH")
        self.password = password or os.getenv("SSH_PASSWORD")
        self.timeout = timeout
        self.client = None
        self.sftp = None

    def connect(self):
        """Establish SSH connection using key or password auth."""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_args = dict(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                timeout=self.timeout,
            )
            if self.key_filepath:
                connect_args["key_filename"] = self.key_filepath
            if self.password:
                connect_args["password"] = self.password

            logger.info(f"Connecting to {self.username}@{self.hostname}:{self.port}")
            self.client.connect(**connect_args)
            self.sftp = self.client.open_sftp()
            logger.info("SSH connection established.")
        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            raise

    def execute_command(self, command: str, timeout: int = None) -> str:
        """
        Execute a command on the remote host and return stdout. Raises on error.
        """
        if self.client is None:
            raise RuntimeError("SSH client not connected. Call connect() first.")
        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode()
        err = stderr.read().decode()
        if exit_status != 0:
            logger.error(f"Command failed ({exit_status}): {err}")
            raise RuntimeError(f"Remote command failed: {err}")
        return out

    def upload_file(self, local_path: str, remote_path: str):
        """Upload a local file to the remote host."""
        if self.sftp is None:
            raise RuntimeError("SFTP client not initialized. Call connect() first.")
        logger.info(f"Uploading {local_path} to {remote_path}")
        self.sftp.put(local_path, remote_path)

    def download_file(self, remote_path: str, local_path: str):
        """Download a file from the remote host."""
        if self.sftp is None:
            raise RuntimeError("SFTP client not initialized. Call connect() first.")
        logger.info(f"Downloading {remote_path} to {local_path}")
        self.sftp.get(remote_path, local_path)

    def close(self):
        """Close SSH and SFTP connections."""
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()
        logger.info("SSH connection closed.")
