# do not import anything else from loss_socket besides LossyUDP
from lossy_socket import LossyUDP
# do not import anything else from socket except INADDR_ANY
from socket import INADDR_ANY
import struct

class Streamer:
    HEADER_FORMAT = "!I" # 4 byte unsigned int
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_PACKET_SIZE = 1472 # header + payload
    MAX_PAYLOAD = MAX_PACKET_SIZE - HEADER_SIZE # size of actual payload per packet
    
    def __init__(self, dst_ip, dst_port,
                 src_ip=INADDR_ANY, src_port=0):
        """Default values listen on all network interfaces, chooses a random source port,
           and does not introduce any simulated packet loss."""
        self.socket = LossyUDP()
        self.socket.bind((src_ip, src_port))
        self.dst_ip = dst_ip
        self.dst_port = dst_port

        # sequence numbers 
        self.next_seq = 0
        self.expected_seq = 0
        self.recv_buffer = {} # buffer for out-of-order packets

    def send(self, data_bytes: bytes) -> None:
        """Note that data_bytes can be larger than one packet."""
        # Your code goes here!  The code below should be changed!
        for i in range(0, len(data_bytes), self.MAX_PAYLOAD):
            chunk = data_bytes[i:i + self.MAX_PAYLOAD] # take size of max segment - header size
            header = struct.pack(self.HEADER_FORMAT, self.next_seq) # pack seq number with header
            packet = header + chunk # construct full packet, header + payload
            self.socket.sendto(packet, (self.dst_ip, self.dst_port)) 
            self.next_seq += 1 # increment sequence number


    def recv(self) -> bytes:
        """Blocks (waits) if no data is ready to be read from the connection."""
        # your code goes here!  The code below should be changed!
        
        # check if expected seq number is in the buffer
        if self.expected_seq in self.recv_buffer: 
            payload = self.recv_buffer.pop(self.expected_seq)
            self.expected_seq += 1
            return payload

        # if not in buffer, recieve until expected shows up
        while True:
            packet, addr = self.socket.recvfrom()
            if len(packet) < self.HEADER_SIZE:
                continue
            seq, = struct.unpack(self.HEADER_FORMAT, packet[:self.HEADER_SIZE])
            payload = packet[self.HEADER_SIZE:]
            if seq < self.expected_seq:
                # old or duplicate packet
                continue
            elif seq == self.expected_seq:
                # this is the expected packet
                self.expected_seq += 1
                return payload
            else:
                # out of order packet
                if seq not in self.recv_buffer:
                    # put in buffer if not already there
                    self.recv_buffer[seq] = payload

    def close(self) -> None:
        """Cleans up. It should block (wait) until the Streamer is done with all
           the necessary ACKs and retransmissions"""
        # your code goes here, especially after you add ACKs and retransmissions.
        pass
