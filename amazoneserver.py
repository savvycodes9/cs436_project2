import errno
import socket
import sys


def listen():
    try:
        while True:
            
            # Wait for query
            data, address = udp_connection.receive_message()
            # Check RR table for record
            name, type_ = deserialize(data)
            if not name or not type_:
                print("Invalid query format recieved.")
                continue
            record = rr_table.get_record(name, type_)
        
            # If not found, add "Record not found" in the DNS response
            # Else, return record in DNS response
            if record is None:
                response = f"{name}, {type_}, Record not found"
            else: 
                response = serialize(record)
            # The format of the DNS query and response is in the project description
            udp_connection.send_message(response, address)
            # Display RR table
            rr_table.display_table()
            pass
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        # Close UDP socket
        udp_connection.close()
        pass


def main():
    # Add initial records
    # These can be found in the test cases diagram
    global rr_table, udp_connection
    rr_table = RRTable()
    rr_table.add_record("example.com", "A", "1.2.3.4", 3600, True)
    rr_table.add_record("example.com", "AAAA", "abcd::1", 3600, True)

    amazone_dns_address = ("127.0.0.1", 22000)
    # Bind address to UDP socket
    udp_connection = UDPConnection()
    udp_connection.bind(amazone_dns_address)
    listen()


def serialize():
    return f'{record["name"]}, {record["type"]}, {record["result"]}, {record["ttl"]}, {record["static"]}'
    # Consider creating a serialize function
    # This can help prepare data to send through the socket
    pass


def deserialize():
    parts = data.split(",")
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]
    # Consider creating a deserialize function
    # This can help prepare data that is received from the socket
    pass


class RRTable:
    def __init__(self):
        self.records = []
        self.record_number = 0

    def add_record(self, name, type_, result, ttl, static):
        self.record_nume +=1
        self.records.append({
            "record_number" : self.record_number,
            "name": name, 
            "type": type_,
            "result": result,
            "ttl": ttl,
            "static": static 

        })
        pass

    def get_record(self, name, type_):
        for record in self.records:
            if record["name"] == name and record["type"] == type_:
                return record
            return None
        pass

    def display_table(self, name, type_):
        print("record_number, name, type, result, ttl, static")
        for r in self.records:
            print(f'{r["records_number"]}, {r["name"]},{r["type"]}, {r["result"]}, {r["ttl"]}, {r["static"]}')
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
