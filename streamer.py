# do not import anything else from loss_socket besides LossyUDP
from lossy_socket import LossyUDP
# do not import anything else from socket except INADDR_ANY
from socket import INADDR_ANY
import struct
from concurrent.futures import ThreadPoolExecutor
from time import sleep, time

class Streamer:
    # Packet type 0=Data, 1=ACK, 2=FIN, 3=FIN ACK
    HEADER_FORMAT = "!BI" # 1 byte for packet type, 4 bytes for seq number
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

        # buffer for out-of-order packets
        self.recv_buffer = {} 
        self.closed = False

        # ACK variables
        self.awaiting_ack = False # flag for if we're waiting for ACK
        self.awaiting_ack_seq = None # seq num of ACK we are waiting for

        # FIN variables
        self.awaiting_fin_ack = False
        self.awaiting_fin_ack_seq = None
        self.received_fin = False
        
        # background listener thread
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(self.listener)

    def listener(self):
        while not self.closed:
            try: 
                packet, addr = self.socket.recvfrom()
                # packet must be at least length of header 
                if len(packet) < self.HEADER_SIZE:
                    continue
                # unpack header to get packet type and seq num
                packet_type, seq = struct.unpack(self.HEADER_FORMAT, packet[:self.HEADER_SIZE])
                if packet_type == 1:
                    # ACK packet
                    print(f"[Listener] Received ACK for seq {seq}")
                    if self.awaiting_ack_seq is not None and seq == self.awaiting_ack_seq:
                        self.awaiting_ack = True
                elif packet_type == 0:
                    # data packet
                    print(f"[Listener] Received data packet with seq {seq}")
                    payload = packet[self.HEADER_SIZE:]
                    # add to buffer if not already received
                    if seq not in self.recv_buffer:
                        self.recv_buffer[seq] = payload
                    # send back an ACK for this packet
                    ack_header = struct.pack(self.HEADER_FORMAT, 1, seq)
                    self.socket.sendto(ack_header, addr)
                    print(f"[Listener] Sent ACK for seq {seq}")
                elif packet_type == 2:
                    # FIN packet
                    print(f"[Listener] Received FIN with seq {seq}")
                    # send FIN ACK 
                    fin_ack_header = struct.pack(self.HEADER_FORMAT, 3, seq)
                    self.socket.sendto(fin_ack_header, addr)
                    print(f"[Listener] Sent FIN ACK for seq {seq}")
                    self.received_fin = True
                elif packet_type == 3:
                    # FIN ACK packet
                    print(f"[Listener] Received FIN ACK for seq {seq}")
                    if self.awaiting_fin_ack_seq is not None and seq == self.awaiting_fin_ack_seq:
                        self.awaiting_fin_ack = True
            except Exception as e:
                print("listener died")
                print(e)

    def send(self, data_bytes: bytes) -> None:
        """Note that data_bytes can be larger than one packet."""
        # Your code goes here!  The code below should be changed!
        for i in range(0, len(data_bytes), self.MAX_PAYLOAD):
            chunk = data_bytes[i:i + self.MAX_PAYLOAD] # take size of max segment - header size
            # create header for data packet with type 0 and seq num
            header = struct.pack(self.HEADER_FORMAT, 0, self.next_seq) 
            packet = header + chunk # construct full packet, header + payload
            # set up ACK waiting
            self.awaiting_ack = False
            self.awaiting_ack_seq = self.next_seq
            print(f"[Send] Sending packet with seq {self.next_seq}")
            self.socket.sendto(packet, (self.dst_ip, self.dst_port)) 
            # wait for ACK, timeout .25 secs
            start_time = time()
            while not self.awaiting_ack:
                sleep(0.01)
                if time() - start_time >= 0.25:
                    print(f"[Send] Timed out waiting for ACK for seq {self.awaiting_ack_seq}, resending")
                    # retransmit packet
                    self.socket.sendto(packet, (self.dst_ip, self.dst_port))
                    start_time = time() # reset time on retransmission
            print(f"[Send] ACK received for seq {self.next_seq}")
            self.next_seq += 1 # increment sequence number


    def recv(self) -> bytes:
        """Blocks (waits) if no data is ready to be read from the connection."""
        # your code goes here!  The code below should be changed!
        
        while True: 
            if self.expected_seq in self.recv_buffer:
                payload = self.recv_buffer.pop(self.expected_seq)
                print(f"[Recv] Delivering payload for seq {self.expected_seq}")
                self.expected_seq += 1
                return payload
            sleep(0.01)


    def close(self) -> None:
        """Cleans up. It should block (wait) until the Streamer is done with all
           the necessary ACKs and retransmissions"""
        # your code goes here, especially after you add ACKs and retransmissions.

        # use next seq num  for fin seq
        fin_seq = self.next_seq
        # construct fin header
        fin_header = struct.pack(self.HEADER_FORMAT, 2, fin_seq)
        self.awaiting_fin_ack = False
        self.awaiting_fin_ack_seq = fin_seq

        # send fin until fin ack is received
        while not self.awaiting_fin_ack:
            print("[Close] Sending FIN packet with seq {fin_seq}")
            self.socket.sendto(fin_header, (self.dst_ip, self.dst_port))
            start_time = time()
            while not self.awaiting_fin_ack and time() - start_time < 0.25:
                sleep(0.01)
            if not self.awaiting_fin_ack:
                print("[Close] Timeout waiting for FIN ACK, resending FIN")
            print("[Close] FIN ACK received. Waiting for FIN from remote.")

        start_time = time()
        while not self.received_fin and time() - start_time < 10:
            sleep(0.01)
        if self.received_fin:
            print("[Close] FIN from remote received. Waiting 2 seconds before shutdown.")
            sleep(2)
        else: 
            print("[Close] Did not receive FIN from remote within timeout.")

        self.closed = True
        self.socket.stoprecv()
