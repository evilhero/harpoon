#this is a quick, sample send socket script for use with harpoon.
# put in the host, port and apikey (same one that is located in harpoon.conf/socket_api)
# then from a cli, send the commmand via 'python sendit.py <mode> <HASH> <label>' where hash is the hash on the torrent client,
# label is the label given to the hash on the client, and mode is either add or queue.

from jsonsocket import Client
import sys

host = 'localhost'
port = 50007
mode = sys.argv[1]
if mode == 'queue':
    hash = None
    label = None
else:
    hash = sys.argv[2]
    label = sys.argv[3]

data = {
    'mode': mode,
    'apikey': '#put apikeyhere',
    'hash': hash,
    'label': label
}

client = Client()
client.connect(host, port)
client.send(data)
response = client.recv()
print response
client.close()

