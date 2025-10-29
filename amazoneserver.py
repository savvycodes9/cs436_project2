import errno
import socket
import sys
import json
import time

def listen():
    try:
        while True:
            # Wait for query
            time.sleep(1)
            data, address = udp_connection.receive_message()
            time.sleep(1)
            
            # Check RR table for record
            msg = deserialize(data)

            # Validate the incoming JSON query
            if not isinstance(msg, dict) or msg.get("flag") != "0000" or "question" not in msg or "txid" not in msg:
                print(f"Invalid query format recieved from {address}")
                continue

            # Get query details from the JSON
            client_txid = msg.get("txid")
            question = msg.get("question", {})
            name = question.get("name")
            type_ = question.get("type")

            if not name or not type_:
                print(f"Invalid query (missing name/type) from {address}")
                continue
                
            record = rr_table.get_record(name, type_)
            time.sleep(1)
            
            # Build the JSON response
            response_msg = {
                "txid": client_txid,
                "flag": "0001"  # This is a response
            }

            if record is None:
                response_msg["answer"] = {
                    "name": name,
                    "type": type_,
                    "ttl": 0, # TTL doesn't matter for "not found"
                    "result": "Record not found"
                }
            else: 
                # Use the data from the found record
                response_msg["answer"] = {
                    "name": record["name"],
                    "type": record["type"],
                    # Use a default TTL if the static record has 'None'
                    "ttl": 60 if record["ttl"] is None else record["ttl"], 
                    "result": record["result"]
                }
            
            # Serialize the entire response dictionary and send it
            response_str = serialize(response_msg)
            udp_connection.send_message(response_str, address)
            
            # Display RR table
            print(f"\nHandled query for {name} from {address}")
            rr_table.display_table()
            
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        # Close UDP socket
        udp_connection.close()

def main():
    # Add initial records
    # These can be found in the test cases diagram
    global rr_table, udp_connection
    rr_table = RRTable()
    rr_table.add_record("shop.amazone.com", "A", "3.33.147.88", None, True)
    rr_table.add_record("cloud.amazone.com", "A", "15.197.140.28", None, True)

    amazone_dns_address = ("127.0.0.1", 22000)
    # Bind address to UDP socket
    udp_connection = UDPConnection()
    udp_connection.bind(amazone_dns_address)
    listen()


def serialize(message_dict):
    return json.dumps(message_dict)


def deserialize(data):
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None # Return None if JSON is invalid


class RRTable:
    def __init__(self):
        self.records = []
        self.record_number = 0

    def add_record(self, name, type_, result, ttl, static):
        self.records.append({
            "record_number" : self.record_number,
            "name": name, 
            "type": type_,
            "result": result,
            "ttl": ttl,
            "static": 1 if static else 0 
        })
        self.record_number += 1
        pass

    def get_record(self, name, type_):
        for record in self.records:
            if record["name"] == name and record["type"] == type_:
                return record
        return None

    def display_table(self): #, name, type_
        print("record_number, name, type, result, ttl, static")
        for r in self.records:
            print(f'{r["record_number"]}, {r["name"]},{r["type"]}, {r["result"]}, {r["ttl"]}, {r["static"]}')
            print("-" * 50)
        # Display the table in the following format (include the column names):
        # record_number,name,type,result,ttl,static
        pass


class DNSTypes:
    """
    A class to manage DNS query types and their corresponding codes.

    Examples:
    >>> DNSTypes.get_type_code('A')
    8
    >>> DNSTypes.get_type_name(0b0100)
    'AAAA'
    """

    name_to_code = {
        "A": 0b1000,
        "AAAA": 0b0100,
        "CNAME": 0b0010,
        "NS": 0b0001,
    }

    code_to_name = {code: name for name, code in name_to_code.items()}

    @staticmethod
    def get_type_code(type_name: str):
        """Gets the code for the given DNS query type name, or None"""
        return DNSTypes.name_to_code.get(type_name, None)

    @staticmethod
    def get_type_name(type_code: int):
        """Gets the DNS query type name for the given code, or None"""
        return DNSTypes.code_to_name.get(type_code, None)


class UDPConnection:
    """A class to handle UDP socket communication, capable of acting as both a client and a server."""

    def __init__(self, timeout: int = 1):
        """Initializes the UDPConnection instance with a timeout. Defaults to 1."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)
        self.is_bound = False

    def send_message(self, message: str, address: tuple[str, int]):
        """Sends a message to the specified address."""
        self.socket.sendto(message.encode(), address)

    def receive_message(self):
        """
        Receives a message from the socket.

        Returns:
            tuple (data, address): The received message and the address it came from.

        Raises:
            KeyboardInterrupt: If the program is interrupted manually.
        """
        while True:
            try:
                data, address = self.socket.recvfrom(4096)
                return data.decode(), address
            except socket.timeout:
                continue
            except OSError as e:
                if e.errno == errno.ECONNRESET:
                    print("Error: Unable to reach the other socket. It might not be up and running.")
                else:
                    print(f"Socket error: {e}")
                self.close()
                sys.exit(1)
            except KeyboardInterrupt:
                raise

    def bind(self, address: tuple[str, int]):
        """Binds the socket to the given address. This means it will be a server."""
        if self.is_bound:
            print(f"Socket is already bound to address: {self.socket.getsockname()}")
            return
        self.socket.bind(address)
        self.is_bound = True

    def close(self):
        """Closes the UDP socket."""
        self.socket.close()


if __name__ == "__main__":
    main()
