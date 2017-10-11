import threading
import SocketServer
import json
import harpoon
from harpoon import logger

class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        data = self.recv()
        logger.info('[API-AWARE] Incoming api request: %s' % data)
        if data['apikey'] == '8ukjkjdhkjh9817891lHJDJHAKllsdljal':
            self.send({'Status': True, 'Message': 'Successful authentication'})
            self.add_queue(data)
        else:
            self.send({'Status': False, 'Message': 'Invalid APIKEY'})

    def recv(self):
        return self._recv(self.request)

    def send(self, data):
        self._send(self.request, data)
        return self

    def _send(socket, data):
        try:
            serialized = json.dumps(data)
        except (TypeError, ValueError), e:
            raise Exception('You can only send JSON-serializable data')
        # send the length of the serialized data first
        socket.send('%d\n' % len(serialized))
        # send the serialized data
        socket.sendall(serialized)

    def _recv(socket):
        # read the length of the data, letter by letter until we reach EOL
        length_str = ''
        char = socket.recv(1)
        while char != '\n':
            length_str += char
            char = socket.recv(1)
        total = int(length_str)
        # use a memoryview to receive the data chunk by chunk efficiently
        view = memoryview(bytearray(total))
        next_offset = 0
        while total - next_offset > 0:
            recv_size = socket.recv_into(view[next_offset:], total - next_offset)
            next_offset += recv_size
        try:
            deserialized = json.loads(view.tobytes())
        except (TypeError, ValueError), e:
            raise Exception('Data received was not in JSON format')
        return deserialized

    def add_queue(self, data):
        try:
            item = data['file']
            mode = 'file'
        except:
            item = data['hash']
            mode = 'hash'

        if mode == 'file':
            logger.info('[API-AWARE] Adding file to queue via FILE %s [label:%s]' % (data['file'], data['label']))
            #harpoon.SNQUEUE.put({'mode':  'file-add',
            #                     'item':  data['file'],
            #                     'label': data['label']})

        elif mode == 'hash':
            logger.info('[API-AWARE] Adding file to queue via HASH %s [label:%s]' % (data['hash'], data['label']))
            #harpoon.SNQUEUE.put({'mode':  'hash-add',
            #                     'item':  data['hash'],
            #                     'label': data['label']})

        return


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass

#def client(ip, port, message):
#    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#    sock.connect((ip, port))
#    try:
#        sock.sendall(message)
#        response = sock.recv(1024)
#        print("Received: %s" % response)
#    finally:
#        sock.close()

#if __name__ == "__main__":
#    # Port 0 means to select an arbitrary unused port
#    HOST, PORT = "localhost", 50007

#    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
#    ip, port = server.server_address

#    # Start a thread with the server -- that thread will then start one
#    # more thread for each request
#    server_thread = threading.Thread(target=server.serve_forever)
#    # Exit the server thread when the main thread terminates
#    server_thread.daemon = True
#    server_thread.start()
#    print("Server loop running in thread: %s" % server_thread.name)

#    client(ip, port, "Hello World 1")
#    client(ip, port, "Hello World 2")
#    client(ip, port, "Hello World 3")

#    server.shutdown()
#    server.server_close()

#def _send(socket, data):
#  try:
#    serialized = json.dumps(data)
#  except (TypeError, ValueError), e:
#    raise Exception('You can only send JSON-serializable data')
#  # send the length of the serialized data first
#  socket.send('%d\n' % len(serialized))
#  # send the serialized data
#  socket.sendall(serialized)

#def _recv(socket):
#    # read the length of the data, letter by letter until we reach EOL
#    length_str = ''
#    char = socket.recv(1)
#    while char != '\n':
#        length_str += char
#        char = socket.recv(1)
#    total = int(length_str)
#    # use a memoryview to receive the data chunk by chunk efficiently
#    view = memoryview(bytearray(total))
#    next_offset = 0
#    while total - next_offset > 0:
#        recv_size = socket.recv_into(view[next_offset:], total - next_offset)
#        next_offset += recv_size
#    try:
#        deserialized = json.loads(view.tobytes())
#    except (TypeError, ValueError), e:
#        raise Exception('Data received was not in JSON format')
#    return deserialized

class listentome(object):

    def __init__(self):

        #HOST, PORT = "localhost", 50007
        #server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
        #ip, port = server.server_address
        #server_thread = threading.Thread(target=server.serve_forever, args=queue)
        #server_thread.daemon = True
        #server_thread.start()

        logger.info('[API-AWARE] Successfully sent API-AWARE into the background to monitor for connections...')
        logger.info('[API-AWARE] Now preparing to initialize queue across modules...')
        #self.queue = harpoon.QUEUE

        #logger.warn('[API-WARE] Shutdown of API occurring - is this expected?')
        #server.shutdown()
        #server.server_close()
