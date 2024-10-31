# 333CA Dumitrascu Filip-Teodor
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

def parse_config_file(sw_id, vlan_table):
    with open(f"./configs/switch{sw_id}.cfg") as fin:
        lines = fin.readlines()

    # first line int the file is the switch priority
    sw_priority = int(lines[0].strip())

    # next ones are "interface vlanid" format 
    for line in lines[1:]:
        intrf_name, vlan_id = line.strip().split()

        # trunk interfaces
        if vlan_id == 'T':
            vlan_table[intrf_name] = vlan_id
        else:
            vlan_table[intrf_name] = int(vlan_id)
    
    return sw_priority

def parse_bpdu_frame(data, recv_intrf, own_brd_id, root_brd_id, root_pth_cost,
                     intrfs, intrfs_sts, vlan_table, root_intrf):
    recv_name = get_interface_name(recv_intrf)
    was_root = (own_brd_id == root_brd_id)

    dest_mac, src_mac, bpdu_own_brd_id, bpdu_root_brd_id, \
    bpdu_root_pth_cost = struct.unpack("!6s6sIII", data)

    if bpdu_root_brd_id < root_brd_id:
        root_brd_id = bpdu_root_brd_id
        root_pth_cost = bpdu_root_pth_cost + 10
        root_intrf = recv_intrf

        if was_root:
            for i in intrfs:
                i_name = get_interface_name(i)

                if vlan_table[i_name] == 'T' and i != recv_intrf:
                    intrfs_sts[i_name] = "blocking"
        
        if intrfs_sts[recv_name] == "blocking":
            intrfs_sts[recv_name] = "listening"

        bpdu, bpdu_length = create_bpdu(own_brd_id, root_brd_id, root_pth_cost)
        
        for i in intrfs:
            i_name = get_interface_name(i)

            if vlan_table[i_name] == 'T' and i != recv_intrf:
                send_to_link(i, bpdu_length, bpdu)
    
    elif bpdu_root_brd_id == root_brd_id:
        if recv_intrf == root_intrf and bpdu_root_pth_cost + 10 < root_pth_cost:
            root_pth_cost = bpdu_root_pth_cost + 10

        elif recv_intrf != root_intrf:
            if bpdu_root_pth_cost > root_pth_cost:
                if intrfs_sts[get_interface_name(recv_intrf)] != "listening":
                    intrfs_sts[get_interface_name(recv_intrf)] == "listening"

    elif bpdu_own_brd_id == own_brd_id:
        intrfs_sts[recv_name] = "blocking"

    if own_brd_id == root_brd_id:
        for i in intrfs:
            intrfs_sts[get_interface_name(i)] = "listening"


def is_unicast(mac):
    # checks if the most significant byte is even
    return int(mac.split(":")[0], 16) % 2 == 0 

def is_bpdu(mac):
    # checks if the dest mac address identifies a bpdu frame 
    return mac == "01:80:c2:00:00:00"


def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def add_vlan_tag(length, data, vlan_id):
    return length + 4, data[0:12] + create_vlan_tag(vlan_id) + data[12:]

def remove_vlan_tag(length, data):
    return length - 4, data[0:12] + data[16:]

def create_bpdu(own_brd_id, root_brd_id, root_pth_cost):
    bpdu_data = struct.pack("01:80:c2:00:00:00", get_switch_mac(), own_brd_id,
                            root_brd_id, root_pth_cost)
    
    return bpdu_data, len(bpdu_data)


def send_bdpu_every_sec(own_brd_id, root_brd_id, root_pth_cost, intrfs,
                        vlan_table):
    while True:
        if own_brd_id == root_brd_id:
            bpdu, length = create_bpdu(own_brd_id, root_brd_id, root_pth_cost)

            for i in intrfs:
                if vlan_table[get_interface_name(i)] == 'T':
                    send_to_link(i, length, bpdu)

        time.sleep(1)

def forward_frame(dest_intrf, length, data, vlan_id, vlan_table, recv_intrf,
                  intrfs_sts):
    recv_name = get_interface_name(recv_intrf)
    dest_name = get_interface_name(dest_intrf)

    # recv_intrf and dest_intrf are both access
    if vlan_id == -1 and vlan_table[dest_name] != 'T':
        if vlan_table[recv_name] != vlan_table[dest_name]:
            return
    
    # recv_intrf is access and dest_intrf is trunk
    if vlan_id == -1 and vlan_table[dest_name] == 'T':
        # if intrfs_sts[dest_name] == "blocking":
        #     return
        length, data = add_vlan_tag(length, data, vlan_table[recv_name])

    # recv_intrf is trunk and dest_intrf is access
    if vlan_id != -1 and vlan_table[dest_name] != 'T':
        if vlan_id != vlan_table[dest_name]:
            return
        length, data = remove_vlan_tag(length, data)

    # recv_intrf and dest_intrf are both trunk
    # if vlan_id != -1 and vlan_table[dest_name] == 'T':
    #     if intrfs_sts[dest_name] == "blocking":
    #         return

    send_to_link(dest_intrf, length, data)

def main():
    mac_table = {}
    vlan_table = {}
    intrfs_sts = {}
    
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    sw_id = sys.argv[1]
    intrfs = range(0, wrapper.init(sys.argv[2:]))

    sw_priority = parse_config_file(sw_id, vlan_table)

    # all trunk ports(between switches) are set on blocking and
    # the access ones(between a switch and a host) are set on listening
    for i in intrfs:
        i_name = get_interface_name(i)

        intrfs_sts[i_name] = "listening" if vlan_table[i_name] != 'T' \
            else "blocking"

    own_brd_id = sw_priority
    root_brd_id = own_brd_id
    root_pth_cost = 0
    root_intrf = -1

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec, 
                         args=(own_brd_id, root_brd_id, root_pth_cost, intrfs,
                               vlan_table))
    t.start()

    while True:
        recv_intrf, data, length = recv_from_any_link()
        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        mac_table[src_mac] = recv_intrf

        if is_unicast(dest_mac):
            if dest_mac in mac_table:
                forward_frame(mac_table[dest_mac], length, data, vlan_id,
                              vlan_table, recv_intrf, intrfs_sts)

            else:
                for i in intrfs:
                    if i != recv_intrf:
                        forward_frame(i, length, data, vlan_id, vlan_table, 
                                      recv_intrf, intrfs_sts)

        elif is_bpdu(dest_mac):
            parse_bpdu_frame(data, recv_intrf, own_brd_id, root_brd_id,
                             root_pth_cost, intrfs, intrfs_sts, vlan_table,
                             root_intrf)

        else: # is broadcast
            for i in intrfs:
                if i != recv_intrf:
                    forward_frame(i, length, data, vlan_id, vlan_table,
                                  recv_intrf, intrfs_sts)

if __name__ == "__main__":
    main()
