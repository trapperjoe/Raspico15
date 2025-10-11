import os
import urequests
import json
import hashlib
import binascii
import machine
import time
import network
from machine import Pin

# Global variable to hold the internal file structure of the device
global internal_tree

# Wi-Fi credentials (change as needed)
ssid = "YOUR_SSID"
password = "YOUR_PASSWORD"

# --- GitHub Repository Configuration ---
# Set your GitHub username and repository name here
# Repository must be public unless a personal access token is provided
user = 'YOUR_GITHUB_USERNAME'
repository = 'YOUR_REPO_NAME'
token = ''
# Default branch to be used (e.g., 'main' or 'master')
default_branch = 'main'
# Files to exclude from update or deletion
# Do not remove 'ugit.py' from this list unless you know what you are doing
ignore_files = ['/ugit.py', '/init.py']
ignore = ignore_files

# --- Static URLs for GitHub API and Raw Content Access ---
giturl = f'https://github.com/{user}/{repository}'
call_trees_url = f'https://api.github.com/repos/{user}/{repository}/git/trees/{default_branch}?recursive=1'
raw = f'https://raw.githubusercontent.com/{user}/{repository}/master/'

led = Pin("LED", Pin.OUT)

def pull(f_path, raw_url):
    """
    Downloads and saves a file from GitHub to the local file system.
    """
    print(f'Pulling {f_path} from GitHub')
    headers = {'User-Agent': 'electrocredible-ota-pico'}
    if len(token) > 0:
        headers['authorization'] = f"bearer {token}"
    r = urequests.get(raw_url, headers=headers)
    try:
        new_file = open(f_path, 'w')
        new_file.write(r.content.decode('utf-8'))
        new_file.close()
    except:
        print('Decode failed. Consider adding non-code files to ignore list.')
        try:
            new_file.close()
        except:
            print('Attempted to close file to save memory during raw file decode.')

def pull_all(tree=call_trees_url, raw=raw, ignore=ignore, isconnected=False):
    """
    Pulls all files from the GitHub repository and syncs them with the device.
    Deletes local files not found in the GitHub repository.
    """
    if not isconnected:
        wlan = wificonnect()
    os.chdir('/')
    tree = pull_git_tree()
    internal_tree = build_internal_tree()
    internal_tree = remove_ignore(internal_tree)
    print('Ignore list applied. Updated file list:')
    print(internal_tree)
    log = []
    for i in tree['tree']:
        if i['type'] == 'tree':
            try:
                os.mkdir(i['path'])
            except:
                print(f'Failed to create directory {i["path"]}, it may already exist.')
        elif i['path'] not in ignore:
            try:
                os.remove(i['path'])
                log.append(f'{i["path"]} removed from internal memory')
                internal_tree = remove_item(i['path'], internal_tree)
            except:
                log.append(f'{i["path"]} delete failed from internal memory')
                print('Failed to delete existing file')
            try:
                pull(i['path'], raw + i['path'])
                log.append(f'{i["path"]} updated')
            except:
                log.append(f'{i["path"]} failed to pull')
    if len(internal_tree) > 0:
        print('Leftover files not in GitHub tree:')
        print(internal_tree)
        for i in internal_tree:
            os.remove(i)
            log.append(f'{i} removed from internal memory')
    logfile = open('ugit_log.py', 'w')
    logfile.write(str(log))
    logfile.close()  
    print('Resetting device in 5 seconds...')
    time.sleep(5)
    machine.reset()

def wificonnect(ssid=ssid, password=password):
    """
    Connects to a Wi-Fi network using provided SSID and password.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    # Wait for connection to establish
    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
                break
        max_wait -= 1
        print('waiting for connection...')
        time.sleep(1)
    # Manage connection errors
    if wlan.status() != 3:
        print('Network Connection has failed')
    else:
        print('connected')
        status = wlan.ifconfig()
        print( 'ip = ' + status[0] )
        #blink led 3 times after WiFi connected successfully
        for _ in range(3):
            led.on()
            time.sleep(0.1)     
            led.off()
            time.sleep(0.1) 
    return wlan

def build_internal_tree():
    """
    Recursively builds a list of all files on the device and their SHA-1 hashes.
    """
    global internal_tree
    internal_tree = []
    os.chdir('/')
    for i in os.listdir():
        add_to_tree(i)
    return internal_tree

def add_to_tree(dir_item):
    """
    Helper function to recursively add files and directories to the internal tree.
    """
    global internal_tree
    if is_directory(dir_item) and len(os.listdir(dir_item)) >= 1:
        os.chdir(dir_item)
        for i in os.listdir():
            add_to_tree(i)
        os.chdir('..')
    else:
        if os.getcwd() != '/':
            subfile_path = os.getcwd() + '/' + dir_item
        else:
            subfile_path = os.getcwd() + dir_item
        try:
            internal_tree.append([subfile_path, get_hash(subfile_path)])
        except OSError:
            print(f'{dir_item} could not be added to tree')

def get_hash(file):
    """
    Computes SHA-1 hash of a given file.
    """
    o_file = open(file)
    r_file = o_file.read()
    sha1obj = hashlib.sha1(r_file)
    return binascii.hexlify(sha1obj.digest())

def get_data_hash(data):
    """
    Computes SHA-1 hash of given string data.
    """
    sha1obj = hashlib.sha1(data)
    return binascii.hexlify(sha1obj.digest())

def is_directory(file):
    """
    Checks if a given path is a directory.
    """
    try:
        return os.stat(file)[8] == 0
    except:
        return False

def pull_git_tree(tree_url=call_trees_url, raw=raw):
    """
    Fetches the Git tree structure from the GitHub API.
    """
    headers = {'User-Agent': 'electrocredible-ota-pico'}
    if len(token) > 0:
        headers['authorization'] = f"bearer {token}"
    r = urequests.get(tree_url, headers=headers)
    data = json.loads(r.content.decode('utf-8'))
    if 'tree' not in data:
        raise Exception(f'Default branch "{default_branch}" not found.')
    return data

def parse_git_tree():
    """
    Prints the directories and files in the GitHub tree.
    """
    tree = pull_git_tree()
    dirs = []
    files = []
    for i in tree['tree']:
        if i['type'] == 'tree':
            dirs.append(i['path'])
        elif i['type'] == 'blob':
            files.append([i['path'], i['sha'], i['mode']])
    print('Directories:', dirs)
    print('Files:', files)

def check_ignore(tree=call_trees_url, raw=raw, ignore=ignore):
    """
    Displays which files in the GitHub tree are ignored locally.
    """
    os.chdir('/')
    tree = pull_git_tree()
    for i in tree['tree']:
        if i['path'] not in ignore:
            print(f'{i["path"]} not in ignore')
        else:
            print(f'{i["path"]} is in ignore')

def remove_ignore(internal_tree, ignore=ignore):
    """
    Removes ignored files from the internal file list.
    """
    clean_tree = []
    int_tree = [i[0] for i in internal_tree]
    for i in int_tree:
        if i not in ignore:
            clean_tree.append(i)
    return clean_tree

def remove_item(item, tree):
    """
    Removes a specific item from a list of tracked files.
    """
    return [i for i in tree if item not in i]

def backup():
    """
    Creates a backup of the current internal files and their hashes.
    """
    int_tree = build_internal_tree()
    backup_text = "ugit Backup Version 1.0\n\n"
    for i in int_tree:
        data = open(i[0], 'r')
        backup_text += f'FN:SHA1{i[0]},{i[1]}\n'
        backup_text += '---' + data.read() + '---\n'
        data.close()
    backup = open('ugit.backup', 'w')
    backup.write(backup_text)
    backup.close()
