1 2 3
# Network Switch implementation
##### Contributor: Dumitrascu Filip-Teodor 333CA

## Content
1.[MAC table](#mac-table)

2.[VLAN](#vlan)

3.[STP](#stp)


## MAC table
The content addressable memory table (all mac-port associations) for the switch
is stored in a hashmap `mac_table` that maps the mac address to the
corresponding port. The process of switching frames takes place as follows.
When a frame is received, the `src_mac` is stored with the interface on which
the frame was received in the switch table and the following decision is taken depending on the destination mac address:
- If `dest_mac` is the broadcast address (`FF:FF:FF:FF:FF:FF`) the frame is
sent on all the other ports.
- If `dest_mac` is a unicast address, the switch searches the table for the
interface on which it should send the frame to reach the destination. If it
finds the interface for the destination mac, it sends the frame on that
interface. If not, it sends the frame on all the other ports.


## VLAN
The switch configuration file is parsed and each association between the switch interface and a vlan id is stored in a hashmap `vlan_table`. Upon receiving a frame, the switch parses the header and determines the ethertype. (If the
ethertype is 802.1Q, the header contains the 4 bytes of the vlan and the
`vlan_id` variable gets the vlan id of the `recv_intrf`). After `recv_intrf` is decided, the following cases are handled before sending the frame: 
- If `vlan_id` is left -1 it means that `recv_intrf` is an access interface.
    - In this way, if `dest_intrf` is also an access interface, it will
    stop sending the packet only if the two interfaces do not have the same
    vlan id. 
    - Otherwise, `dest_intrf` is a trunk interface, and the 4 bytes
    containing the vlan id must be appended to the header.

- If `vlan_id` has changed, it means that `recv_intrf` is a trunk interface
and the header contains the 4 vlan bytes.
    - If the `dest_intrf` is an access interface, again it will only stop sending the packet when the two interfaces do not have the same vlan id and will remove the 4 vlan bytes in the header.
    - Otherwise, the `dest_intrf` is also a trunk interface and nothing
    extra needs to be checked.

## STP
