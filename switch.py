#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, \
                    get_interface_name

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def parse_config_file(switch_id, vlan_configs):
    with open(f"./configs/switch{switch_id}.cfg") as fin:
        lines = fin.readlines()

    # first line int the file is the switch priority
    switch_priority = int(lines[0].strip())

    # next ones are "interface vlanid" format 
    for line in lines[1:]:
        interface_name, vlan_id = line.strip().split()

        # trunk interfaces
        if vlan_id == 'T':
            vlan_configs[interface_name] = vlan_id
        else:
            vlan_configs[interface_name] = int(vlan_id)
    
    return switch_priority

def is_unicast(mac):
    # checks if the most significant byte is even
    return int(mac.split(":")[0], 16) % 2 == 0 

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def add_vlan_tag(length, data, vlan_id):
    return length + 4, data[0:12] + create_vlan_tag(vlan_id) + data[12:]

def remove_vlan_tag(length, data):
    return length - 4, data[0:12] + data[16:]

def send_bdpu_every_sec():
    while True:
        time.sleep(1)

def forward_frame(dest_interface, length, data, vlan_id, vlan_configs,
                  recv_interface):
    dest_name = get_interface_name(dest_interface)
    recv_name = get_interface_name(recv_interface)

    if vlan_id == -1: # recv port is access
        if vlan_configs[dest_name] != 'T': # send port is access
            if vlan_configs[recv_name] != vlan_configs[dest_name]:
                return
        else: # send port is trunk
            length, data = add_vlan_tag(length, data, vlan_configs[recv_name])

    else: # recv port is trunk
        if vlan_configs[dest_name] != 'T': # send port is access
            if vlan_configs[dest_name] != vlan_id:
                return
            length, data = remove_vlan_tag(length, data)

    send_to_link(dest_interface, length, data)

def main():
    mac_table = {}
    vlan_configs = {}
    
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]
    interfaces = range(0, wrapper.init(sys.argv[2:]))

    switch_priority = parse_config_file(switch_id, vlan_configs)

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()

    while True:
        recv_interface, data, length = recv_from_any_link()
        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        mac_table[src_mac] = recv_interface

        if is_unicast(dest_mac):
            if dest_mac in mac_table:
                forward_frame(mac_table[dest_mac], length, data, vlan_id,
                              vlan_configs, recv_interface)

            else:
                for i in interfaces:
                    if i != recv_interface:
                        forward_frame(i, length, data, vlan_id, vlan_configs, 
                                      recv_interface)

        else:
            for i in interfaces:
                if i != recv_interface:
                    forward_frame(i, length, data, vlan_id, vlan_configs,
                                  recv_interface)

if __name__ == "__main__":
    main()
