#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module provides an API to decode a signal.
"""

import math
import numpy as np


__all__ = (
    'decode_i2c',
    'decode_uart'
)


def decode_i2c(frames):
    """ Decode I2C messages.

    Returns:
        list: [ I2C(...), ... ]
    """
    results = []
    x_scale = frames[0].sx  # x scale, seconds per ADC sample
    x_trans = frames[0].tx  # x translate, seconds

    # Convert ADC level to logic level 0, 1
    scl = frames[0].to_ttl()
    sda = frames[1].to_ttl()

    # Compute [n+1]-[n] so that 0=no change, 1=rise, -1=fall
    scl_diff = (scl[1:] - scl[:-1])
    sda_diff = (sda[1:] - sda[:-1])

    # Get indexes of start/stop edges 
    edges = [ i for i in range(len(sda_diff))
              if sda_diff[i] and scl[i] and not scl_diff[i] ]

    for j, start in enumerate(edges):  # sda start stop edges
        if sda_diff[start] < 0:  # sda fall for start or re-start 
            try:
                stop = edges[j + 1]  # re-start or stop
            except IndexError:
                stop = len(scl_diff)  # in case stop is missing

            # read each bit on clk fall between start and stop
            mbits = [ sda[i] for i in range(start, stop) if scl_diff[i] < 0 ]

            # payload bits to bytes, msb first (without START, ACK, NACK, STOP)
            mbytes = [ _pack_msb(mbits, i, 8) for i in range(1, len(mbits), 9) ]

            # message start/stop time relative to trigger (seconds)
            x_start = x_trans + x_scale * start
            x_stop  = x_trans + x_scale * stop

            if len(mbytes):
                msg = I2C(x_start, x_stop, bytes(mbits), bytes(mbytes))
                results.append(msg)

    return results


class I2C:

    def __init__(self, start, stop, mbits, mbytes):
        self.start = start           #: Start time (s)
        self.stop  = stop            #: Stop time (s)
        self.addr  = mbytes[0] >> 1  #: Address
        self.rw    = mbytes[0] & 1   #: Read:1 Write:0
        self.data  = mbytes[1:]      #: Data
        self.ack   = mbits[9::9]     #: List of ACK/NACK

    def __str__(self):
        s_start = _format_time(self.start)
        s_addr  = format(self.addr, '02X')
        s_rw    = ['R', 'W'][self.rw]
        s_data  = ''.join(map(lambda x: '\\x%02X' % x, self.data))
        s_ack   = ''.join(map(lambda x: '\\%d' % x, self.ack))
        return "I2C(start=%s, addr=0x%s, rw=%s, data=b'%s', ack=b'%s')" % (
            s_start, s_addr, s_rw, s_data, s_ack)

    def __repr__(self):
        return self.__str__()



def decode_uart(frames, baud=None, bits=8, parity=None, msb=False):
    """ Decode UART messages .

    Returns:
        list: [ UART(...), ... ]
    """
    inputs = []
    pulse_pts = 1e6

    for frame in frames:
        # Convert ADC level to logic level 0, 1
        data = frame.to_ttl()
        # Compute [n+1]-[n] so that 0=no change, 1=rise, -1=fall
        diff = data[1:] - data[:-1]
        # Get indexes of all edges
        edges = np.nonzero(diff)[0]
        # Get minimum pulse width
        pulse_pts = min(pulse_pts, (edges[1:] - edges[:-1]).min() or 1e6)

        inputs.append((frame, data, diff, edges))

    if not baud:
        if pulse_pts < 1e6:
            baud = round(1 / (pulse_pts * frame.sx))
        else:
            baud = 9600
        print('Setting decoding to %s bauds (pulse=%s)' % (
                baud, _format_time(1 / baud)))

    results = []

    # number of bits (START DATA PARITY STOP)
    size = 1 + bits + (0 if parity is None else 1) + 1
    last = -1 if parity is None else -2

    for frame, data, diff, edges in inputs:

        # points per bit
        bit_pts = 1 / baud / frame.sx

        p = 0
        for start in edges:
            if start >= p:
                p = start + 1 + bit_pts * 0.4  # jump to center of first bit
                try:
                    # read center of bits at a fixed period
                    mbits = [ data[round(p + i * bit_pts)] for i in range(0, size) ]
                except IndexError:
                    continue

                if not mbits[0] and mbits[-1]:
                    # decode if first is low and last is high
                    cs = (parity or 0) & 1
                    val = 0
                    for b in mbits[1:last] if msb else mbits[last-1:0:-1]:
                        val = (val << 1) | b
                        cs ^= b

                    # check parity bit if any (True if matches)
                    err = parity is not None and cs != mbits[-2]

                    # message start/stop time relative to trigger (seconds)
                    x_start = frame.tx + frame.sx * start
                    x_stop  = x_start + frame.sx * size

                    msg = UART(frame.channel, x_start, x_stop, val, err)
                    results.append(msg)

                    # jump to center of last bit
                    p = start + bit_pts * (size - 0.4)

    results.sort(key=lambda x: x.start)
    return results


class UART:

    def __init__(self, chl, start, stop, val, err):
        self.chl   = chl     #: int: Channel index
        self.start = start   #: float: Start time (s)
        self.stop  = stop    #: float: End time (s)
        self.value = val     #: int: Value
        self.error = err     #: bool: True if parity missmatch

    def __str__(self):
        s_start = _format_time(self.start)
        s_chl = ('CH1', 'CH2')[self.chl]
        if self.error:
            msg = 'UART(channel=%s, start=%s, value=error!)'
            return msg % (s_chl, s_start, )
        else:
            msg = 'UART(channel=%s, start=%s, value=0x%02X)'
            return msg % (s_chl, s_start, self.value)

    def __repr__(self):
        return self.__str__()



def decode_wire(frame):
    """ Decode 1 WIRE messages.

    Returns:
        list: [ WIRE(...), ... ]
    """
    results = []
    x_scale = frame.sx  # x scale, seconds per ADC sample
    x_trans = frame.tx  # x translate, seconds
    channel = frame.channel

    # Convert ADC level to logic level 0, 1
    ttl = frame.to_ttl()
    # Compute [n+1]-[n] so that 0=no change, 1=rise, -1=fall
    diff = ttl[1:] - ttl[:-1]
    # Get indexes of all edges
    edges = np.nonzero(diff)[0]
    # Get indexes of all falling edges
    edges_fall = np.where(diff == -1)[0]
    # Get points per bit
    bit_pts = (edges_fall[1:] - edges_fall[:-1]).min()
    bit_half_pts = bit_pts / 2

    value = 0
    n = 0

    for i, start in enumerate(edges):

        # continue if not falling edge
        if diff[start] != -1:
            continue

        # next rising edge if any
        try:
            pts = edges[i + 1] - start
            if pts > bit_pts:   # reset
                n = 0
                continue
        except IndexError:
            break

        # unpack bit
        n += 1
        bit = int(pts < bit_half_pts)
        value = (value >> 1) | (bit << 7)  # to 8 bits lsb first

        if n == 1:  # if first bit
            x_start = x_trans + x_scale * (1 + start)
        elif n == 8:  # if last bit
            n = 0
            x_stop = x_trans + x_scale * (1 + start + bit_pts)
            msg = WIRE(channel, x_start, x_stop, value)
            results.append(msg)

    return results


class WIRE:

    def __init__(self, chl, start, stop, value):
        self.chl   = chl     #: int: Channel index
        self.start = start   #: float: Start time (s)
        self.stop  = stop    #: float: End time (s)
        self.value = value   #: int: Value

    def __str__(self):
        s_start = _format_time(self.start)
        s_chl = ('CH1', 'CH2')[self.chl]
        msg = 'WIRE(channel=%s, start=%s, value=0x%02X)'
        return msg % (s_chl, s_start, self.value)

    def __repr__(self):
        return self.__str__()



def _pack_msb(bits, start, count):
    v = 0
    for b in bits[start: start + count]:
        v = (v << 1) | b
    shift = start + count - len(bits)
    return (v << shift) if shift > 0 else v


def _format_time(x, ndigits=4):
    n = 0
    while x and abs(x) < 0.1:
        x *= 1e3
        n += 1
    return format(round(x, ndigits), 'g') + ' mµnp'[n][:n] + 's' if x else '0'
