#this is a quick, sample send socket script for use with harpoon.
# put in the host, port and apikey (same one that is located in harpoon.conf/socket_api)
# then from a cli, send the commmand via 'python sendit.py <HASH> <label>' where hash is the hash on the torrent client,
# and label is the label given to the hash on the client

from jsonsocket import Client
import sys

host = 'localhost'
port = 50007
hash = sys.argv[1]
label = sys.argv[2]

data = {
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

