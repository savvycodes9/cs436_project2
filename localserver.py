import errno
import json
import socket
import sys
import threading
import time

# ---------- Config ----------
LOCAL_BIND = ("127.0.0.1", 21000)
AMAZON_ADDR = ("127.0.0.1", 22000)
DEFAULT_TTL = 60

# ---------- Helpers ----------
def serialize(message):
    return json.dumps(message, separators=(",", ":"))

def deserialize(wire):
    try:
        return json.loads(wire)
    except json.JSONDecodeError:
        return {}

class DNSTypes:
    name_to_code = {"A":0b1000,"AAAA":0b0100,"CNAME":0b0010,"NS":0b0001}
    code_to_name = {v:k for k,v in name_to_code.items()}
    @staticmethod
    def get_type_name(code:int): return DNSTypes.code_to_name.get(code)
    @staticmethod
    def get_type_code(name:str): return DNSTypes.name_to_code.get(name)

class UDPConnection:
    def __init__(self, timeout:int=1):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(timeout)
        self.is_bound = False
    def bind(self, address):
        if not self.is_bound:
            self.socket.bind(address); self.is_bound = True
    def send_message(self, message:str, address:tuple[str,int]):
        self.socket.sendto(message.encode(), address)
    def receive_message(self):
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
                return data.decode(), addr
            except socket.timeout:
                continue
            except OSError as e:
                if e.errno == errno.ECONNRESET:
                    print("Peer unreachable (ECONNRESET)."); continue
                raise
    def close(self): self.socket.close()

class RRTable:
    # record: {record_number,name,type,result,ttl,static}
    def __init__(self):
        self.records = []
        self.record_number = 0
        self.lock = threading.Lock()
        t = threading.Thread(target=self.__decrement_ttl, daemon=True); t.start()
    def add_record(self, name, rtype, result, ttl:int|None, is_static:bool):
        with self.lock:
            self.records.append({
                "record_number": self.record_number,
                "name": name,
                "type": rtype,
                "result": result,
                "ttl": None if is_static else int(ttl or 0),
                "static": 1 if is_static else 0
            })
            self.record_number += 1
    def get_record(self, name, rtype):
        with self.lock:
            target = (name.lower(), rtype.upper())
            for r in self.records:
                if r["name"].lower()==target[0] and r["type"].upper()==target[1]:
                    if r["static"]==1: return r
                    if isinstance(r["ttl"],int) and r["ttl"]>0: return r
            return None
    def display_table(self):
        with self.lock:
            print("record_number,name,type,result,ttl,static")
            for r in self.records:
                ttl = "None" if r["ttl"] is None else r["ttl"]
                print(f'{r["record_number"]},{r["name"]},{r["type"]},{r["result"]},{ttl},{r["static"]}')
    def __decrement_ttl(self):
        while True:
            with self.lock:
                for r in self.records:
                    if r["static"]==0 and isinstance(r["ttl"],int) and r["ttl"]>0:
                        r["ttl"] -= 1
                self.records = [r for r in self.records if r["static"]==1 or (isinstance(r["ttl"],int) and r["ttl"]>0)]
                for i,r in enumerate(self.records): r["record_number"]=i
                self.record_number = len(self.records)
            time.sleep(1)

# ---------- Authoritative seed for CSUSM ----------
def seed_authoritative_csusm(rr: RRTable):
    rr.add_record("www.csusm.edu","A","144.37.5.45",None,True)
    rr.add_record("my.csusm.edu","A","144.37.5.150",None,True)
    rr.add_record("amazone.com","NS","dns.amazone.com",None,True)
    rr.add_record("dns.amazone.com","A","127.0.0.1",None,True)
    # add more if your testcases expect them

# ---------- Server logic ----------
class LocalDNSServer:
    def __init__(self):
        self.rr = RRTable()
        seed_authoritative_csusm(self.rr)
        self.conn = UDPConnection(timeout=1)
        self.conn.bind(LOCAL_BIND)
        self.next_txid = 0
        # map upstream_txid -> (client_addr, client_txid)
        self.pending = {}

    def _new_txid(self):
        tx = self.next_txid & 0xFFFFFFFF
        self.next_txid = (tx + 1) & 0xFFFFFFFF
        return tx

    def _answer(self, client_addr, client_txid, name, rtype, ttl, result):
        resp = {
            "txid": client_txid,
            "flag": "0001",
            "answer": {"name": name, "type": rtype, "ttl": ttl, "result": result}
        }
        self.conn.send_message(serialize(resp), client_addr)
        self.rr.display_table()

    def serve_forever(self):
        print(f"Local DNS listening on {LOCAL_BIND[0]}:{LOCAL_BIND[1]}")
        while True:
            wire, addr = self.conn.receive_message()
            msg = deserialize(wire)
            if not isinstance(msg, dict): 
                continue
            flag = msg.get("flag")
            if flag == "0000":
                self._handle_query_from_client(msg, addr)
            elif flag == "0001":
                self._handle_response_from_amazon(msg)
            # else ignore

    def _handle_query_from_client(self, msg, client_addr):
        client_txid = msg.get("txid")
        q = msg.get("question", {})
        name = q.get("name","")
        rtype = q.get("type","A")

        # 1) Authoritative check (CSUSM)
        auth = self.rr.get_record(name, rtype)
        if auth and auth["static"]==1:
            self._answer(client_addr, client_txid, name, rtype, DEFAULT_TTL, auth["result"])
            return

        # 2) Cache check
        if auth and auth["static"]==0:
            ttl = auth["ttl"] if isinstance(auth["ttl"],int) else DEFAULT_TTL
            self._answer(client_addr, client_txid, name, rtype, ttl, auth["result"])
            return

        # 3) Forward to Amazon authoritative
        upstream_txid = self._new_txid()
        self.pending[upstream_txid] = (client_addr, client_txid, name, rtype)
        fwd = {"txid": upstream_txid, "flag":"0000", "question":{"name":name,"type":rtype}}
        self.conn.send_message(serialize(fwd), AMAZON_ADDR)

    def _handle_response_from_amazon(self, msg):
        upstream_txid = msg.get("txid")
        if upstream_txid not in self.pending:
            return
        client_addr, client_txid, name, rtype = self.pending.pop(upstream_txid)

        ans = msg.get("answer", {})
        result = ans.get("result","Record not found")
        ttl = ans.get("ttl", DEFAULT_TTL)

        # cache only valid results
        if result != "Record not found":
            self.rr.add_record(name=name, rtype=rtype, result=result, ttl=int(ttl), is_static=False)

        # forward to original client with their txid
        self._answer(client_addr, client_txid, name, rtype, ttl, result)

def main():
    srv = LocalDNSServer()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
    finally:
        srv.conn.close()

if __name__ == "__main__":
    main()