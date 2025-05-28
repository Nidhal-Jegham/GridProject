#!/usr/bin/env python3
print("🚀 test_ssh.py is running!")

from remote import SSHClientWrapper

def main():
    print("→ In main()")
    ssh = SSHClientWrapper()
    ssh.connect()
    print("→ Connected")
    info = ssh.execute_command("uname -a").strip()
    print("Remote uname -a:", info)
    ssh.close()
    print("→ Closed")

if __name__ == "__main__":
    main()
