import errno
import json
import socket
import sys
import threading
import time


def handle_request():
    # Check RR table for record
    global rr_table, udp_conn, next_txid, current_hostname, current_query_code

    hostname = current_hostname
    qtype_name = DNSTypes.get_type_name(current_query_code)

    cached = rr_table.get_record(hostname, qtype_name)
    if cached is not None:
        rr_table.display_table()
        return

    # If not found, ask the local DNS server, then save the record if valid
    local_dns_address = ("127.0.0.1", 21000)

    # The format of the DNS query and response is in the project description
    txid = next_txid & 0xFFFFFFFF
    next_txid = (txid + 1) & 0xFFFFFFFF

    query_msg = {
        "txid": txid,
        "flag": "0000",  # query
        "question": {"name": hostname, "type": qtype_name},
    }

    udp_conn.send_message(serialize(query_msg), local_dns_address)

    try:
        wire, _addr = udp_conn.receive_message()
        resp = deserialize(wire)

        # basic validation
        if not isinstance(resp, dict) or resp.get("flag") != "0001" or resp.get("txid") != txid:
            rr_table.display_table()
            return

        ans = resp.get("answer", {})
        result = ans.get("result", "Record not found")
        ttl = ans.get("ttl", 0)
        name = ans.get("name", hostname)
        rtype = ans.get("type", qtype_name)

        if result != "Record not found":
            rr_table.add_record(name=name, rtype=rtype, result=result, ttl=int(ttl), is_static=False)

    except socket.timeout:
        # no response; just fall through to display
        pass

    # Display RR table
    rr_table.display_table()


def main():
    try:
        # init globals used by handle_request()
        global rr_table, udp_conn, next_txid, current_hostname, current_query_code
        rr_table = RRTable()
        udp_conn = UDPConnection(timeout=3)
        next_txid = 0
        current_hostname = ""
        current_query_code = DNSTypes.get_type_code("A")

        while True:
            input_value = input("Enter the hostname (or type 'quit' to exit) ")
            if input_value.lower() == "quit":
                break

            hostname = input_value
            query_code = DNSTypes.get_type_code("A")

            # For extra credit, let users decide the query type (e.g. A, AAAA, NS, CNAME)
            # This means input_value will be two values separated by a space
            parts = input_value.strip().split()
            if len(parts) == 2:
                hostname = parts[0]
                qname = parts[1].upper()
                qc = DNSTypes.get_type_code(qname)
                if qc is not None:
                    query_code = qc

            current_hostname = hostname
            current_query_code = query_code

            handle_request()

    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        # Close UDP socket
        try:
            udp_conn.close()
        except Exception:
            pass


def serialize(message=None):
    # Consider creating a serialize function
    # This can help prepare data to send through the socket
    if isinstance(message, str):
        return message
    return json.dumps(message, separators=(",", ":"))


def deserialize(wire=None):
    # Consider creating a deserialize function
    # This can help prepare data that is received from the socket
    try:
        return json.loads(wire)
    except (json.JSONDecodeError, TypeError):
        return wire


class RRTable:
    def __init__(self):
        # self.records = ?
        self.records = []
        self.record_number = 0

        # Start the background thread
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self.__decrement_ttl, daemon=True)
        self.thread.start()

    def add_record(self, name: str, rtype: str, result: str, ttl: int, is_static: bool):
        with self.lock:
            rec = {
                "id": self.record_number,
                "name": name,
                "type": rtype,
                "result": result,
                "ttl": None if is_static else max(0, int(ttl)),
                "static": 1 if is_static else 0,
            }
            self.records.append(rec)
            self.record_number += 1

    def get_record(self, name: str, rtype: str):
        with self.lock:
            name_lc = name.lower()
            for rec in self.records:
                if rec["name"].lower() == name_lc and rec["type"].upper() == rtype.upper():
                    if rec["static"] == 1:
                        return rec
                    if isinstance(rec["ttl"], int) and rec["ttl"] > 0:
                        return rec
            return None

    def display_table(self):
        with self.lock:
            # Display the table in the following format (include the column names):
            # record_number,name,type,result,ttl,static
            print("record_number,name,type,result,ttl,static")
            for rec in self.records:
                ttl_field = "None" if rec["ttl"] is None else rec["ttl"]
                print(f'{rec["id"]},{rec["name"]},{rec["type"]},{rec["result"]},{ttl_field},{rec["static"]}')

    def __decrement_ttl(self):
        while True:
            with self.lock:
                # Decrement ttl
                for rec in self.records:
                    if rec["static"] == 0 and isinstance(rec["ttl"], int) and rec["ttl"] > 0:
                        rec["ttl"] -= 1
                self.__remove_expired_records()
            time.sleep(1)

    def __remove_expired_records(self):
        # This method is only called within a locked context

        # Remove expired records
        self.records = [
            rec for rec in self.records
            if rec["static"] == 1 or (isinstance(rec["ttl"], int) and rec["ttl"] > 0)
        ]
        # Update record numbers
        for idx, rec in enumerate(self.records):
            rec["id"] = idx
        self.record_number = len(self.records)


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