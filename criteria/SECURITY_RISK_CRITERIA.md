# Security Risk Criteria

This document defines what the project considers a security-sensitive capability.

## Command Execution
The ability to cause the operating system to execute a command, start a process, or run an external program.

Examples:
- Running shell commands
    - os.system
    - os.popen
    - subprocess 
    - shell = True
    - bash 
    - sh -c
    - powershell
    - cmd.exe
- Starting processes
    - subprocess.run
    - subprocess.Popen
    - subprocess.call
    - subprocess.check_call
    - os.spawn
- Executing external programs
    - execve
    - execv
    - execvp
    - spawn
    - .exe
    - .bat
    - .cmd
    - .sh

## File-System Access
Examples:
- Reading files
    - open(
    - read(
    - read_text(
    - Path.read_text
    - cat
    - less
    - head
    - tail
- Writing or modifying files
    - write(
    - write_text(
    - Path.write_text
    - append
- Deleting files
    - os.remove
    - os.unlink
    - Path.unlink
    - shutil.rmtree
    - rm
- Accessing directories
    - os.listdir
    - os.scandir
    - os.walk
    - Path.iterdir
    - Path.glob
    - glob.glob
    - mkdir
    - os.makedirs
    - shutil.copy
    - shutil.move

## Network Access
Examples:
- Making HTTP/HTTPS requests
    - requests.get
    - requests.post
    - requests.put
    - requests.delete
    - urllib.request
    - http.client
    - httpx
    - aiohttp
- Connecting to external servers
    - socket.connect
    - socket.create_connections
    - connect(
    - ftp
    - paramiko
- Downloading data from the internet
    - requests.get
    - urllib.request.urlretrieve
    - urlopen
    - wget
    - curl
    - download