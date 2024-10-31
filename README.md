1 2 3
# Network Switch implementation
##### Contributor: Dumitrascu Filip-Teodor 333CA

## Content
1.[MAC table](#mac-table)

2.[VLAN](#vlan)

3.[STP](#stp)


## MAC table
The content addressable memory table (all mac-port mappings) for the switch
is stored in a hashmap `mac_table` that maps the mac address to the
corresponding port. The process of switching frames takes place as follows:
When a frame is received, the `src_mac` is stored with the interface on which
the frame was received in the switch table and the following decision is taken
depending on the `dest_mac` address:
- If `dest_mac` is the broadcast address (`FF:FF:FF:FF:FF:FF`) the frame is
sent on all the other ports.
- If `dest_mac` is a unicast address, the switch searches the table for the
interface on which it should send the frame to reach the destination. If it
finds the interface for the `dest_mac`, it sends the frame on that
interface. If not, it sends the frame on all the other ports.


## VLAN
The switch configuration file is parsed and each mapping between the switch
interface and a `vlan_id` is stored in a hashmap `vlan_table`. Upon receiving
a frame, the switch parses the header and determines the ethertype. (If the
ethertype is 802.1Q, the header contains the 4 bytes of the vlan and the
`vlan_id` variable gets the vlan id of the `recv_intrf`). After `recv_intrf` is
decided (via mac_table), the following cases are handled before sending the frame: 
- If `vlan_id` is left -1 it means that `recv_intrf` is an access interface.
    - In this way, if `dest_intrf` is also an access interface, it will
    stop sending the packet only if the two interfaces do not have the same
    vlan id. 
    - Otherwise, `dest_intrf` is a trunk interface, and the 4 bytes
    containing the vlan id must be added to the header.

- If `vlan_id` has changed, it means that `recv_intrf` is a trunk interface
and the header contains the 4 vlan bytes.
    - If the `dest_intrf` is an access interface, again it will only stop 
    sending the packet when the two interfaces do not have the same vlan id and
    will remove the 4 vlan bytes from the header.
    - Otherwise, the `dest_intrf` is also a trunk interface and nothing
    extra needs to be checked.


## STP
The status of each interface ("blocking"/"listening") is stored in a hashmap
`intrfs_sts`. In order to keep redundancy only at the physical level (in case
of backup for a link) and prevent storm broadcasts, at the logical level a stp
tree (a kind of minimal spanning tree) must be implemented. To do this the
following steps are followed:
- Initially, all trunk interfaces are set to blocking and all access interfaces
are set to listening. Also, every switch is considered to be the root bridge.
- Second by second another thread (not the main one) sends a bpdu frame if the
switch is a root bridge.
- On receiving, if the frame is bpdu, (dest_mac == `"01:80:c2:00:00:00"`)
it is parsed and the trunk interfaces status are updated/maintained.
- Root interface are considered the interfaces that have the minimal path to
the root bridge. The root bridge can be updated as requiered, always looking
for the one with the lowest switch priority. The designated interfaces are the
ones with importance in order for other switches to send data to the root bridge
and the last interfaces are the blocked ones. They cause the broadcast storms,
so there status is set to blocking.
