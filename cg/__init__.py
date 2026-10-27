"""LECGI Connection Grouper.

Reads structural framing drawings (PDF), identifies steel connections, assigns
loads (posted on drawings, or 50% of beam UDL capacity per AISC 360-22), groups
similar connections by worst case, marks the groups on the drawings and issues
a connection group schedule on the LECGI letterhead.

Connection DESIGN is not performed - groups are handed to RISA Connection /
IDEA StatiCa.
"""

__version__ = "0.1.0"
