#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module provides an API to communicate directly with 
the OWON VDS1022 oscilloscope.
"""

import binascii
import bisect
import collections
import datetime
import functools
import gc
import glob
import json
import logging
import os.path as path
import signal
import struct
import sys
import threading
import time

from array import array
from copy import copy, deepcopy
from math import floor, ceil, log2, log10, copysign, sqrt, pi

assert sys.version_info >= (3, 5), "requires Python 3.5 or newer"

try:
    from usb.backend import libusb0, libusb1
    from usb.core import USBError
    import numpy as np
except ImportError as ex:
    raise ImportError('Missing dependencies. Required: '
                      'pyusb numpy pandas bokeh') from ex

__all__ = (
    'VDS1022',
    'CHANNELS',
    'CH1', 'CH2', 'EXT',
    'DC', 'AC',
    'VOLT_RANGES',
    'SAMPLING_RATES',
    'EDGE', 'SLOPE', 'PULSE',
    'AUTO', 'NORMAL', 'ONCE',
    'RISE', 'FALL',
    'RISE_SUP', 'RISE_EQU', 'RISE_INF',
    'FALL_SUP', 'FALL_EQU', 'FALL_INF',
)

_dir = path.dirname(__file__)
_logger = logging.getLogger('vds1022')


DEBUG = False

MACHINE_NAME = 'VDS1022'

FIRMWARE_DIR = path.normpath(_dir + r'/fwr')

CHANNELS = 2  #: Number of channels

CH1 = 0  #: Channel 1
CH2 = 1  #: Channel 2
EXT = 2  #: External TTL input/output (Multi)

MULTI_OUT = 0  # Multi channel mode - trigger out
MULTI_PF  = 1   # Multi channel mode - pass/fail out
MULTI_IN  = 2   # Multi channel mode - trigger in

AC  = 0  #: Coupling - Alternating Current
DC  = 1  #: Coupling - Direct Current
GND = 2  #: Coupling - Ground

VOLT_RANGES = (
    50e-3, 100e-3, 200e-3, 500e-3, 1, 2, 5, 10, 20, 50
)  #: Volt ranges from 50mV to 50V for 10 divs

SAMPLING_RATES = (
    2.5, 5, 12.5, 25, 50, 125, 250, 500, 
    1.25e3, 2.5e3, 5e3, 12.5e3, 25e3, 50e3, 125e3, 250e3, 500e3, 
    1.25e6, 2.5e6, 5e6, 12.5e6, 25e6, 50e6, 100e6,
)  #: Sampling rates from 2.5 S/s to 100 MS/s

EDGE  = 0  #: Trigger mode - Edge
VIDEO = 1  #: Trigger mode - Video
SLOPE = 2  #: Trigger mode - Slope
PULSE = 3  #: Trigger mode - Pulse

RISE_SUP = 0  #: Trigger condition - Pulse/Slope Rise Width >
RISE_EQU = 1  #: Trigger condition - Pulse/Slope Rise Width =
RISE_INF = 2  #: Trigger condition - Pulse/Slope Rise Width <
FALL_SUP = 3 - 128  #: Trigger condition - Pulse/Slope Fall Width >
FALL_EQU = 4 - 128  #: Trigger condition - Pulse/Slope Fall Width =
FALL_INF = 5 - 128  #: Trigger condition - Pulse/Slope Fall Width <

RISE = RISE_SUP  #: Trigger condition - Edge Rise
FALL = FALL_SUP  #: Trigger condition - Edge Fall

AUTO   = 0  #: Sweep mode - Auto
NORMAL = 1  #: Sweep mode - Normal
ONCE   = 2  #: Sweep mode - Once

ATTENUATION_THRESHOLD = 6  # voltbase threshold to reduce the voltage input.
ROLLMODE_THRESHOLD = 2500  # sampling rate for switching to roll mode (slow move).

# ADC (Analog-to-digital converter)
FRAME_SIZE = 5211  # frame size [ 11 headers + 100 trigger + 5100 ADC ]
ADC_SIZE   = 5100  # ADC size [ 50 pre samples + 5000 samples + 50 post samples ]
ADC_MAX    = +125  # max sample value
ADC_MIN    = -125  # min sample value
ADC_RANGE  = 250   # sample max - min amplitude
SAMPLES    = 5000  # number of pertinent samples in a frame

# CALIBRATION
GAIN = 0  # Gain (correction applyed for a measured signal)
AMPL = 1  # Zero amplitude (correction applied for a 0v signal with no voltage offset)
COMP = 2  # Zero compensation (correction applied for a 0v signal with an offset voltage)
HTP_ERR = 11  # Horizontal trigger position correction

# USB
USB_VENDOR_ID  = 0x5345
USB_PRODUCT_ID = 0x1234
USB_INTERFACE  = 0
USB_TIMEOUT    = 200

FLASH_SIZE = 2002


# Command
#   Send (little endian)
#     Offset  Size   Field
#     0       4      address
#     4       1      value size (1, 2 or 4)
#     5       -      value (1, 2 or 4 bytes)
#   Receive 5 bytes (little endian)
#     Offset  Size   Field
#     0       1      status char (Null:0, D:68, E:69, G:71, S:83, V:86)
#     1       4      value

# Command READ_FLASH
#   Send (little endian)
#     Offset  Size   Field
#     0       4      address (0x01b0)
#     4       1      value size (1)
#     5       1      value (1)
#   Receive 2002 bytes (little endian)
#     Offset  Size        Field             Value
#     0       uint16      Flash header      0x55AA or 0xAA55
#     2       uint32      Flash version     2
#     6       uint16[10]  CH1 Gain          for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     26      uint16[10]  CH2 Gain          for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     46      uint16[10]  CH1 Amplitude     for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     66      uint16[10]  CH2 Amplitude     for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     86      uint16[10]  CH1 Compensation  for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     106     uint16[10]  CH2 Compensation  for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     206     byte        OEM               0 or 1
#     207     char*       Device version    null terminated string - ASCII encoded
#             char*       Device serial     null terminated string - ASCII encoded
#             byte[100]   Localizations     0 or 1 for zh_CN, zh_TW, en, fr, es, ru, de, pl, pt_BR, it, ja, ko_KR
#             uint16      Phase fine        0-255  ???

# Command GET_DATA
#   Send (little endian)
#     Offset  Size  Field
#     0       4     address (0x1000)
#     4       1     value size (2)
#     5       1     channel 1 state ( OFF:0x04 ON:0x05 )
#     6       1     channel 2 state ( OFF:0x04 ON:0x05 )
#   Receive 5 bytes starting with 'E' if not ready
#   Receive 5211 bytes for channel 1 if ON and ready
#     Offset  Size  Field
#     0       1     channel (CH1=0x00 CH2=0x01)
#     1       4     time_sum (used by frequency meter)
#     5       4     period_num (used by frequency meter)
#     9       2     cursor (samples count from the right)
#     11      100   ADC trigger buffer (only used with small time bases)
#     111     5100  ADC buffer ( 50 pre + 5000 samples + 50 post )
#   Receive 5211 bytes for channel 2 if ON and ready


class CMD:

    class Cmd:

        def __init__(self, name, address, struct):
            self.name    = name             #: str: command name for debug
            self.address = address          #: str: command address (4 bytes)
            self.size    = struct.size - 5  #: int: value size
            self.struct  = struct           #: Struct: command structure for packing

        def pack(self, arg):
            try:
                return array('B', self.struct.pack(self.address, self.size, arg))
            except Exception as ex:
                raise ValueError('Failed to pack %s %s into %s' % (
                    self.name, hex(arg), self.struct.format)) from ex

        def log(self, arg, ret, buffer):
            if DEBUG:
                if ret == 5:
                    # 5 bytes response : status (1 char), value (u32 or 4 [A-Z] chars)
                    spec = '<c4s' if all(65 <= c <= 90 for c in buffer[1:5]) else '<cI'
                    status, value = struct.unpack_from(spec, buffer)
                    _log("[ %s %s ] %s %s", self.name, hex(arg), status, value)
                else:
                    # 5211 bytes response
                    _log("[ %s %s ] %s bytes", self.name, hex(arg), ret)


    BI   = struct.Struct('<BI')  # u8, u32
    IBB  = struct.Struct('<IBB')  # u32, u8, u8
    IBH  = struct.Struct('<IBH')  # u32, u8, u16
    IBI  = struct.Struct('<IBI')  # u32, u8, u32
    BIIH = struct.Struct('<BIIH')  # u8, u32, u32, u16
    D, E, G, S, V = 68, 69, 71, 83, 86

    READ_FLASH        =  Cmd('READ_FLASH'           , 0x01b0, IBB)  # read_flash
    WRITE_FLASH       =  Cmd('WRITE_FLASH'          , 0x01a0, IBB)  # write_flash
    QUERY_FPGA        =  Cmd('QUERY_FPGA'           , 0x0223, IBB)  # FPGA_DOWNLOAD_QUERY_ADD
    LOAD_FPGA         =  Cmd('LOAD_FPGA'            , 0x4000, IBI)  # FPGA_DOWNLOAD_ADD
    EMPTY             =  Cmd('EMPTY'                , 0x010c, IBB)  # EMPTY_ADD
    GET_MACHINE       =  Cmd('GET_MACHINE'          , 0x4001, IBB)  # MACHINE_TYPE_ADD
    GET_DATA          =  Cmd('GET_DATA'             , 0x1000, IBH)  # GETDATA_ADD
    GET_TRIGGERED     =  Cmd('GET_TRIGGERED'        ,   0x01, IBB)  # TRG_D_ADD
    GET_VIDEOTRGD     =  Cmd('GET_VIDEOTRGD'        ,   0x02, IBB)  # VIDEOTRGD_ADD
    SET_MULTI         =  Cmd('SET_MULTI'            ,   0x06, IBH)  # SYNCOUTPUT_ADD
    SET_PEAKMODE      =  Cmd('SET_PEAKMODE'         ,   0x09, IBB)  # SAMPLE_ADD
    SET_ROLLMODE      =  Cmd('SET_ROLLMODE'         ,   0x0a, IBB)  # SLOWMOVE_ADD
    SET_CHL_ON        =  Cmd('SET_CHL_ON'           ,   0x0b, IBB)  # CHL_ON_ADD
    SET_FORCETRG      =  Cmd('SET_FORCETRG'         ,   0x0c, IBB)  # FORCETRG_ADD
    SET_PHASEFINE     =  Cmd('SET_PHASEFINE'        ,   0x18, IBH)  # PHASE_FINE
    SET_TRIGGER       =  Cmd('SET_TRIGGER'          ,   0x24, IBH)  # TRG_ADD
    SET_VIDEOLINE     =  Cmd('SET_VIDEOLINE'        ,   0x32, IBH)  # VIDEOLINE_ADD
    SET_TIMEBASE      =  Cmd('SET_TIMEBASE'         ,   0x52, IBI)  # TIMEBASE_ADD
    SET_SUF_TRG       =  Cmd('SET_SUF_TRG'          ,   0x56, IBI)  # SUF_TRG_ADD
    SET_PRE_TRG       =  Cmd('SET_PRE_TRG'          ,   0x5a, IBH)  # PRE_TRG_ADD
    SET_DEEPMEMORY    =  Cmd('SET_DEEPMEMORY'       ,   0x5c, IBH)  # DM_ADD
    SET_RUNSTOP       =  Cmd('SET_RUNSTOP'          ,   0x61, IBB)  # RUNSTOP_ADD
    GET_DATAFINISHED  =  Cmd('GET_DATAFINISHED'     ,   0x7a, IBB)  # datafinished_ADD
    GET_STOPPED       =  Cmd('GET_STOPPED'          ,   0xb1, IBB)  # CHECK_STOP_ADD
    SET_CHANNEL       = (Cmd('SET_CHANNEL_CH1'      , 0x0111, IBB),
                         Cmd('SET_CHANNEL_CH2'      , 0x0110, IBB))
    SET_ZERO_OFF      = (Cmd('SET_ZERO_OFF_CH1'     , 0x010a, IBH),
                         Cmd('SET_ZERO_OFF_CH2'     , 0x0108, IBH))
    SET_VOLT_GAIN     = (Cmd('SET_VOLT_GAIN_CH1'    , 0x0116, IBH),
                         Cmd('SET_VOLT_GAIN_CH2'    , 0x0114, IBH))
    SET_SLOPE_THRED   = (Cmd('SET_SLOPE_THRED_CH1'  ,   0x10, IBH),
                         Cmd('SET_SLOPE_THRED_CH2'  ,   0x12, IBH))
    SET_EDGE_LEVEL    = (Cmd('SET_EDGE_LEVEL_CH1'   ,   0x2e, IBH),
                         Cmd('SET_EDGE_LEVEL_CH2'   ,   0x30, IBH))
    SET_TRG_HOLDOFF   = (Cmd('SET_TRG_HOLDOFF_CH1'  ,   0x26, IBH),
                         Cmd('SET_TRG_HOLDOFF_CH2'  ,   0x2a, IBH))
    SET_TRG_CDT_EQU_H = (Cmd('SET_TRG_CDT_EQU_H_CH1',   0x32, IBH),  # FPGA <= V2
                         Cmd('SET_TRG_CDT_EQU_H_CH2',   0x3a, IBH))  # FPGA <= V2
    SET_TRG_CDT_EQU_L = (Cmd('SET_TRG_CDT_EQU_L_CH1',   0x36, IBH),  # FPGA <= V2
                         Cmd('SET_TRG_CDT_EQU_L_CH2',   0x3e, IBH))  # FPGA <= V2
    SET_TRG_CDT_GL    = (Cmd('SET_TRG_CDT_GL_CH1'   ,   0x42, IBH),
                         Cmd('SET_TRG_CDT_GL_CH2'   ,   0x46, IBH))
    SET_TRG_CDT_HL    = (Cmd('SET_TRG_CDT_HL_CH1'   ,   0x44, IBH),  # FPGA >= V3
                         Cmd('SET_TRG_CDT_HL_CH2'   ,   0x48, IBH))  # FPGA >= V3
    SET_FREQREF       = (Cmd('SET_FREQREF_CH1'      ,   0x4a, IBB),
                         Cmd('SET_FREQREF_CH2'      ,   0x4b, IBB))



class _FlashStream:

    def __init__(self, data):
        self.buffer = bytearray(data)
        self.position = 0

    def seek(self, position):
        self.position = position

    def read(self, spec):
        # read structure
        res = struct.unpack_from(spec, self.buffer, self.position)
        self.position += struct.calcsize(spec)
        return res if len(res) > 1 else res[0]

    def write(self, spec, *values):
        # write structure
        struct.pack_into(spec, self.buffer, self.position, *values)
        self.position += struct.calcsize(spec)

    def read_str(self):
        # read null terminated string
        end = self.buffer.index(0, self.position)
        txt = self.buffer[self.position: end].decode('ASCII')
        self.position = end + 1
        return txt

    def write_str(self, text):
        # write ASCII null terminated string
        buf = text.encode('ASCII') + b'\0'
        self.buffer[self.position: self.position + len(buf)] = buf
        self.position += len(buf)



_min = lambda a, b: b if b < a else a

_max = lambda a, b: b if b > a else a

_clip = lambda x, lo, hi: lo if x < lo else hi if x > hi else x

_rms = lambda y: sqrt(np.square(y, dtype=np.float32).mean())

_find_ge = lambda arr, x: bisect.bisect_left(arr, x)

_find_le = lambda arr, x: bisect.bisect_right(arr, x) - 1

_imax = lambda arr: np.argmax(arr)  # maximum index

_iavg = lambda arr: np.average(range(1, len(arr) + 1), weights=arr) - 1  # weighted index

_items = lambda x: x if isinstance(x, (tuple, list)) else (x, )

_bits = lambda arr: sum(1 << i for i, x in enumerate(arr) if x)

_u8 = lambda x: x & 0xff

_u16 = lambda lsb, msb: lsb & 0xff | (msb & 0xff) << 8

_swap16 = lambda x: (x & 0xff00) >> 8 | (x & 0x00ff) << 8

_to_precision = lambda x, n: round(x, -int(floor(log10(abs(x or 1)))) + (n - 1))


def _iexp10(value, limit):
    """ To unsigned integer mantissa and base-10 exponent.  """
    m, e = value, 0
    while m > limit:
        m, e = m / 10, e + 1
    return round(m), e


def _rfft(data, window, size):

    size  = 2 ** int(log2(_min(size or len(data), 4096)))   # power of 2
    trim  = (len(data) - size) >> 1
    data  = data[trim: -trim or None]
    scale = 2 / size

    if window is not None:
        win   = window(size)
        data  *= win
        scale /= win.mean()

    return np.fft.rfft(data), scale


def _quad_iterp(yy, i):
    """ Quadratic interpolation of 3 adjacent points
    https://www.dsprelated.com/freebooks/sasp/Quadratic_Interpolation_Spectral_Peaks.html
    """
    yi = yy[i]
    yp = yy[i - 1] if i > 0 else yy[i + 1]
    yn = yy[i + 1] if i + 1 < len(yy) else yy[i - 1]
    x  = i + 0.5 * (yp - yn) / (yp - 2 * yi + yn)
    y  = yi - 0.25 * (yp - yn) * (x - i)
    return x, y


def _printf(spec, *args):
    print(spec % args)


def _log(spec, *args):
    if DEBUG:
        print(spec % args)


def _log_calibration(calibration):
    values = ' '.join(format(x / 10, '5') for x in VOLT_RANGES)
    _log('# VOLTBASE: %s', values)

    for i, name in enumerate(('GAIN', 'AMPL', 'COMP')):
        for chl in range(CHANNELS):
            values = ' '.join(format(x, '5') for x in calibration[i][chl])
            _log('# %s CH%s: %s', name, chl + 1, values)


class _parse:

    SCALLING = { 'M':1e6, 'k':1e3, 'm':1e-3, 'u':1e-6, 'n':1e-9 }

    def __new__(cls, txt):
        r = cls.SCALLING.get(txt[-1])
        return float(txt[:-1]) * r if r else float(txt)

    def _wrapper(fn):
        @functools.wraps(fn)
        def wrapper(**kwargs):
            for k, v in kwargs.items():
                try:
                    return fn(v) if isinstance(v, str) else v
                except Exception as ex:
                    raise ValueError('Invalid argument %s=%s' % (k, v)) from ex
        return wrapper

    @_wrapper
    def constant(arg):
        assert arg in __all__
        return globals()[arg]

    @_wrapper
    def ratio(arg):
        return float(arg.replace('%', 'e-2'))

    @_wrapper
    def factor(arg):
        return float(arg.strip('Xx'))

    @_wrapper
    def seconds(arg):
        return _parse(arg.rstrip('s'))

    @_wrapper
    def volts(arg):
        return _parse(arg.rstrip('Vv'))

    @_wrapper
    def freq(arg):
        return _parse(arg.rstrip('Hz'))



class Frame:
    """ Hold the samples of a channel. """

    def __init__(self, device, channel, buffer, offset, frequency):
        vr = device.voltrange[channel] * device.probe[channel]
        self.buffer = buffer  # array('b'): ADC raw samples (8 bits signed)
        self.channel = channel  #: int: 0:`CH1` or 1:`CH2`
        self.frequency = frequency  #: float: Measured frequency (Hz).
        self.sx = 1 / device.sampling_rate  # float: X scale, seconds per ADC sample
        self.sy = vr / ADC_RANGE            # float: Y scale, volts per ADC sample
        self.tx = offset / device.sampling_rate     # float: X translate, seconds
        self.ty = vr * -device.voltoffset[channel]  # float: Y translate, volts


    @property
    def _points(self):
        buf = self.buffer
        if isinstance(buf, array) and buf.itemsize == 1:
            buf = np.frombuffer(buf, np.int8)
            buf.clip(ADC_MIN, ADC_MAX, out=buf)
            self.buffer = buf
        return buf


    @property
    def size(self):
        """ int: Number of samples . """
        return len(self.buffer)


    @property
    def name(self):
        """ str: Either 'CH1' or 'CH2' . """
        return 'CH' + str(self.channel + 1)


    @property
    def ylim(self):
        """ tuple: (Lower limit, Upper limit) . """
        half = ADC_RANGE * self.sy / 2
        return self.ty - half,  self.ty + half


    @property
    def xlim(self):
        """ tuple: (Left limit, Right limit) . """
        n = len(self.buffer)
        x1 = self.tx
        x2 = self.tx + self.sx * n

        if n < SAMPLES and abs(x2) < 1e-08:  # if roll mode and origine on the right
            x1 -= self.sx * (SAMPLES - n)  # pad left

        return x1, x2


    def slice(self, start, stop=None):
        """ Returns a subset of this Frame.

        Args:
            start (`float` ): Start time (second)
            stop  (`float` ): Stop time (second)
        """
        start = _parse.seconds(start=start)
        stop  = _parse.seconds(stop=stop)

        size = self.size
        i = _clip(round((start - self.tx) / self.sx), 0, size - 1)
        j = _clip(round(((stop or size) - self.tx) / self.sx), 0, size - 1)

        frame = copy(self)
        frame.tx += i * self.sx
        frame.buffer = frame.buffer[i: j]

        return frame


    def __getitem__(self, index):
        """ Returns the y value at index."""
        return self.buffer[index] * self.sy + self.ty


    def x(self):
        """
        Returns:
            numpy.ndarray: 1D Numpy array of x values in second.
        """
        num = len(self.buffer)
        if num:
            start = self.tx
            # TODO check if it needs num - 1 on stop for continuous mode
            # stop = start + (num - 1) * self.sx
            stop = start + num * self.sx
            return np.linspace(start, stop, num, dtype=np.float32)
        return np.empty(0, dtype=np.float32)


    def y(self):
        """
        Returns:
            numpy.ndarray: 1D Numpy array of y values in volt.
        """
        ys = self._points * np.float32(self.sy) + np.float32(self.ty)
        return ys


    def clipped(self):
        """
        Returns:
            bool: True if the signal is clipped, False otherwise.
        """
        pts = self._points
        return pts.itemsize == 1 and int(pts.max()) >= ADC_MAX or int(pts.min()) <= ADC_MIN


    def xy(self):
        """
        Returns:
            tuple: Two 1D Numpy arrays of x and y values in second and volt ( xs, ys ) .
        """
        return self.x(), self.y()


    def percentile(self, *q):
        """
        Args:
            q (float): Percentiles between 0 and 100 inclusive.
        Returns:
            tuple: Voltage for each given percentile.
        """
        values = np.percentile(self._points, q)
        return tuple(float(v) * self.sy + self.ty for v in values)


    def median(self):
        """
        Returns:
            float: Median voltage.
        """
        v = float(np.median(self._points))
        return round(v * self.sy + self.ty, 3)


    def min(self):
        """
        Returns:
            float: Minimum voltage.
        """
        v = float(self._points.min())
        return round(v * self.sy + self.ty, 3)


    def max(self):
        """
        Returns:
            float: Maximum voltage.
        """
        v = float(self._points.max())
        return round(v * self.sy + self.ty, 3)


    def avg(self):
        """
        Returns:
            float: Average voltage.
        """
        v = float(self._points.mean())
        return round(v * self.sy + self.ty, 3)


    def rms(self):
        """
        Returns:
            float: RMS voltage.
        """
        yy = self._points + np.float32(self.ty / self.sy)
        return round(_rms(yy) * self.sy, 3)


    def std(self):
        """
        Returns:
            float: Standard deviation.
        """
        ys = self._points + np.float32(self.ty / self.sy)
        return round(ys.std() * self.sy, 3)


    def freq(self, period=360, start=-1/2):
        """ Main frequency and Phase. Phase is relative to center of frame.

        Args:
            period (float): Optional range over which the phase wraps (360, 2*pi).
            start   (bool): Optional phase start ratio. Defaults to -1/2.
        Returns:`
            tuple: Frequency, Phase within [ start*period, (start+1)*period ]
        """

        ys = self._points
        ys = ys - np.float32(ys.mean())  # remove DC component

        if ys.max() > 15:
            ii = np.nonzero((ys[1:] >= 0) & (ys[:-1] < 0))[0]  # indexes of positive crossings

            if ii.size > 1:
                size  = np.diff(ii).max() * 0.8                               # threshold period size
                ii    = ii[np.nonzero(np.diff(ii, prepend=-size) > size)[0]]  # filter crossings
                size  = np.mean(np.diff(ii))                                  # average period size     
                freq  = 1 / (size * self.sx)                                  # frequency
                ratio = np.mean((1 + len(ys)/2 + ii) % size) / size           # phase ratio of period
                phase = (ratio - start + 1) % 1.0 + start                     # wrap [-0.5, +0.5]
                return freq, -phase * period + 0

        return None, None


    def _get_levels(self):
        points = self._points + 128
        counts = np.bincount(points, minlength=256)
        m = np.dot(counts, range(256)) // len(points)
        lo = np.argmax(counts[:m + 1]) - 128
        hi = np.argmax(counts[m:]) + m - 128
        return lo, hi


    def levels(self):
        """
        Returns:
            tuple: Vbase, Vtop.
        """
        lo, hi = self._get_levels()
        lower = lo * self.sy + self.ty
        upper = hi * self.sy + self.ty
        return lower, upper


    def amp(self):
        """
        Returns:
            float: Vamp.
        """
        lo, hi = self.levels()
        return hi - lo


    def to_ttl(self, ratio_low=0.2, ratio_high=0.4):
        """ Convert to TTL levels (0 or 1)

        Args:
            ratio_low  (float): amplitude ratio for low level.
            ratio_high (float): amplitude ratio for high level.
        Returns:
            ndarray: 1D Numpy array of 0 and 1.
        """
        lo, hi = self._get_levels()
        points = self._points

        if (hi - lo) < 16:
            lo = _min(lo, -self.ty / self.sy)  # Vbase to 0v if Vtop == Vbase
            if (hi - lo) < 16:
                return np.zeros(points.size, np.int8)  # no signal

        ttl = points > int(lo + (hi - lo) * ratio_high)
        nlo = points > int(lo + (hi - lo) * ratio_low)

        for i in range(1, len(ttl)):
            ttl[i] = ttl[i] or nlo[i] and ttl[i - 1]  # n-1 if neither high or low

        return ttl.astype(np.int8)


    def describe(self):
        """ Generate descriptive statistics.

            | Size  : Number of samples
            | Vavg  : Average voltage
            | Vrms  : RMS voltage
            | Vamp  : Amplitude (Vtop - Vbase)
            | Vbase : Most prevalent lower voltage
            | Vtop  : Most prevalent upper voltage
            | Vpp   : Peak to Peak (Vmax - Vmin)
            | Vmin  : minimum
            | Vmax  : maximum
            | Frequency : Frequency (hertz)
            | Period    : Signal period (second)
            | Phase     : Phase shift from center (degree)
            | Crest     : Crest factor (Vmax / Vrms)

        Returns:
            `DataFrame`
        """
        import pandas

        y = self.y()
        vmin = round(y.min(), 3)
        vmax = round(y.max(), 3)
        vpp  = round(vmax - vmin, 3)
        vavg = round(y.mean(), 3)
        vrms = round(_rms(y), 3)
        vbase, vtop = ( round(v, 3) for v in self.levels() )
        vamp = round(vtop - vbase, 3)
        # freq = round(self.frequency, 3) if self.frequency else None
        freq, phase = self.freq(period=360)
        freq   = freq and round(freq, 3)
        phase  = freq and round(phase, 3)
        period = freq and round(1 / freq, 3)
        crest  = freq and round(vmax / vrms, 3)

        k = 'Size Vavg Vrms Vamp Vbase Vtop Vpp Vmin Vmax Frequency Period Phase Crest'.split(' ')
        v = ( self.size, vavg, vrms, vamp, vbase, vtop, vpp, vmin, vmax, freq, period, phase, crest )

        return pandas.DataFrame({ self.name: v }, index=k)


    # def thd(self, window=np.blackman, size=None):
    #     """ Compute the total harmonic distortion.

    #     Args:
    #         window (func): optional, defaults to `numpy.hamming` .
    #         size    (int): optional, defaults to closest power of 2.
    #     Returns:
    #         float: THD.
    #     """
    #     pts = self._points + np.float32(self.ty / self.sy)  # raw adc points at offset
    #     ft, scale = _rfft(pts, window, size)

    #     ftm = np.abs(ft) * scale  # magnitude
    #     ftm[0] = 0  # clear DC component
    #     ftm_max = ftm.max()

    #     thd = ((np.square(ftm).sum() - ftm_max ** 2.0) ** 0.5) / ftm_max

    #     return thd


    def spectrum(self, window=np.blackman, size=None):
        """ Compute the magnitude and phase spectrum.

        Args:
            window  (func): optional, defaults to `numpy.hamming` .
            size     (int): optional, fft size.
        Returns:
            tuple: ( frequencies (Hz), magnitudes (Vmax), phases (-1+1) ).
        """

        ft, scale = _rfft(self.y(), window, size)
        ftx = np.linspace(0, 1 / 2 / self.sx, len(ft))  # frequencies (Hz)
        ftm = np.abs(ft) * scale                        # magnitudes (Vmax)
        ftp = ( np.angle(ft) / pi + 2.5 ) % 2 - 1       # phases from center (-1+1)

        return ftx, ftm, ftp


    def components(self, threshold=0.01, window=np.blackman, size=None):
        """ Component frequencies.

        Args:
            threshold (float): optional, from 1% to 100%
            window     (func): optional, defaults to `numpy.hamming`
            size        (int): optional, fft size

        Returns:
            list: [ ( frequency (Hz), magnitude (Vmax), phase (-1+1) ), ... ]
        """
        dy = _parse.ratio(threshold=threshold) * ADC_MAX

        pts = self._points + np.float32(self.ty / self.sy)
        ft, scale = _rfft(pts, window, size)

        ft_mag = np.abs(ft) * scale  # magnitude (points)
        ft_avg = np.convolve(ft_mag, np.ones(10)).flatten()  # rolling average on 10 points
        ii = np.nonzero(np.diff(ft_avg, prepend=0) > dy)[0]  # indexes of dy > threshold
        ii = ii[np.nonzero(np.diff(ii, prepend=0) > 1)[0]]   # indexes separated by at least 1
        ii = [ _max(0, i-2) + _imax(ft_mag[i-2: i+5]) for i in ii ]  # indexes of maximum

        if not ii:
            return tuple()

        xx, mm = zip(*( _quad_iterp(ft_mag, i) for i in ii ))  # interpolate magnitudes

        frequencies = [ round(x / len(ft) / 2 / self.sx)     for x in xx ]  # Hz
        magnitudes  = [ self.sy * m                          for m in mm ]  # Vmax
        phases      = [ (np.angle(ft[i]) / pi + 2.5) % 2 - 1 for i in ii ]  # -1+1

        return tuple(zip(frequencies, magnitudes, phases))


    def filter(self, ratio=0.1):
        """ Filters the samples in-place.

            ratio (float): optional, from 0 to 1, where 1 is the Nyquist frequency.

        Returns:
            Frame: this instance
        """
        from scipy import signal

        ratio = _parse.ratio(ratio)
        wn = 1 / (ratio * len(self.buffer) / 2)
        b, a = signal.butter(3, wn)
        self.buffer = signal.filtfilt(b, a, self.buffer, padlen=200)

        return self


    def decode_uart(self, baud=None, bits=8, parity=None, msb=False):
        """ Decode UART samples .

        Returns:
            list: [ UART(start=, value=, ...), ... ]
        """
        from vds1022 import decoder
        return decoder.decode_uart((self,), baud, bits, parity, msb)


    def decode_wire(self):
        """ Decode 1 WIRE samples .

        Returns:
            list: [ WIRE(start=, value=, ...), ... ]
        """
        from vds1022 import decoder
        return decoder.decode_wire(self)


    def plot(self, backend='bokeh', **kwargs):
        """ Draw the samples in a chart (bokeh by default).
        Aditional keyworded arguments are forwarded to the plotting backend.
        Available backend: bokeh, matplotlib, hvplot, holoviews

        Args:
            backend   (str): Optional plotting backend. Defaults to `bokeh`.
            width   (float): Optional width of the plot in pixels. Defaults to 700.
            height  (float): Optional height of the plot in pixels. Defaults to 300.
            xlabel    (str): Optional horizontal label. Defaults to None.
            ylabel    (str): Optional vertical label. Defaults to None.
            xy_mode  (bool): Optional X-Y mode. Defaults to false.
            color    (list): Optional color for each channel. ex: ['#1f77b4', '#ff7f0e']
            legend   (list): Optional name each curve. ex: ['Channel 1', 'Channel 2']
            kwargs   (dict): keyworded arguments for the backend library
        """

        frames = ( self if i == self.channel else None for i in range(CHANNELS) )
        Frames(frames, 0).plot(**kwargs)



class Frames(tuple):
    """ Holds the channels frame (`Frame` `CH1`, `Frame` `CH2`) .

    Examples:
        >>> ch1, ch2 = frames  # destructuring not `None` entries
        >>> ch1 = frames[CH1]  # by index
        >>> ch1 = frames.ch1   # by attribute
    """

    def __new__(cls, frames, clock):
        return tuple.__new__(cls, frames)


    def __init__(self, frames, clock):
        self.clock = clock   #: float: clock from performance counter in seconds.


    def __repr__(self):
        return repr(self.to_dataframe())


    def __iter__(self):
        return ( f for f in tuple.__iter__(self) if f )


    def _repr_html_(self):
        return self.to_dataframe()._repr_html_()


    @property
    def ch1(self):
        """ `Frame`: Channel 1"""
        frame = self[0]
        assert frame is not None, "Channel 1 not set."
        return frame


    @property
    def ch2(self):
        """ `Frame`: Channel 2"""
        frame = self[1]
        assert frame is not None, "Channel 2 not set."
        return frame


    @property
    def ylim(self):
        """ tuple: (Lower limit, Upper limit) of all frames. """
        yy = [ ADC_RANGE * f.sy * r - f.ty for r in (-0.5, 0.5) for f in self ]
        return min(yy), max(yy)


    def x(self):
        """
        Returns:
            ndarray: 1D Numpy array of x values in second.
        """
        for f in self:
            return f.x()
        return np.empty(0, dtype=np.float32)


    def y(self):
        """
        Returns:
            tuple: 1D Numpy arrays of y values: ( ys, ... ) .
        """
        return tuple( f.y() for f in self )


    def xy(self):
        """
        Returns:
            tuple: 1D Numpy arrays of x and y values: ( xs, ys, ... ) .
        """
        return self.x(), *( f.y() for f in self )


    def time(self):
        """ `float`: acquisition time in seconds since the epoch."""
        clock = time.perf_counter()
        now = time.time()
        return now + (self.clock - clock)


    def datetime(self):
        """ `datetime`: acquisition datetime"""
        clock = time.perf_counter()
        now = datetime.datetime.now()
        return now + datetime.timedelta(seconds=self.clock - clock)


    def phase(self, period=360, start=-1/2):
        """ Phase shift between channel 1 and channel 2.

        Args:
            period (float): Optional range over which the phase wraps. Defaults to 360.
            start   (bool): Optional phase start ratio or angle. Defaults to -1/2.
        Returns:
            float: Phase within [ start*period, (start+1)*period ]
        """
        freq1, phase1 = self.ch1.freq(period=period, start=0)
        freq2, phase2 = self.ch2.freq(period=period, start=0)
        return (((phase2 - phase1) + period) % period) + (start * period) + 0


    def slice(self, start, stop):
        """ Extract a section of the samples at given times.

        Args:
            start (`float` ): Start time (second)
            stop  (`float` ): Stop time (second)
        Returns:
            `Frames`
        """
        start = _parse.seconds(start=start)
        stop  = _parse.seconds(stop=stop)

        items = [ None ] * len(self)
        dx = 0

        for frame in self:
            f = frame.slice(start, stop)
            dx = f.tx - frame.tx
            items[f.channel] = f

        return Frames(items, self.clock + dx)


    def diff(self):
        """ Substract channel 2 from channel 1.

        Returns:
            `Frames`
        """
        ch1, ch2 = self
        assert ch1.sy == ch2.sy, "Volt range different between channels"

        f = copy(ch1)
        f.buffer = ch1._points - (ch2._points + np.float32(ch2.ty / ch2.sy))
        f.frequency = None

        return Frames((f, None), self.clock)


    def power_factor(self):
        """ Power factor.

        Returns:
            `float`
        """
        y1 = self.ch1.y()
        y2 = self.ch2.y()
        pwr_P  = np.dot(y1, y2) / len(y1)  # real power
        pwr_S  = _rms(y1) * _rms(y2)       # apparent power
        pf     = float(pwr_P / pwr_S)      # power factor
        return pf


    def describe(self):
        """ Generate descriptive statistics.

            | Count : Number of samples
            | Vavg  : Average voltage
            | Vrms  : RMS voltage
            | Vamp  : Amplitude (Vtop - Vbase)
            | Vbase : Most prevalent lower voltage
            | Vtop  : Most prevalent upper voltage
            | Vpp   : Peak to Peak (Vmax - Vmin)
            | Vmin  : minimum
            | Vmax  : maximum
            | Period    : Signal period (second)
            | Frequency : Frequency (hertz)
            | Phase     : Phase shift (radian)

        Returns:
            `DataFrame`
        """
        import pandas
        return pandas.concat([ f.describe() for f in self ], axis=1)


    def plot(self, backend='bokeh', **kwargs):
        """ Draw the samples in a chart (bokeh by default).
        Aditional keyworded arguments are forwarded to the plotting backend.
        Available backend: bokeh, matplotlib, hvplot, holoviews

        Args:
            backend   (str): Optional plotting backend. Defaults to `bokeh`.
            width   (float): Optional width of the plot in pixels. Defaults to 700.
            height  (float): Optional height of the plot in pixels. Defaults to 300.
            xlabel    (str): Optional horizontal label. Defaults to None.
            ylabel    (str): Optional vertical label. Defaults to None.
            xy_mode  (bool): Optional X-Y mode. Defaults to false.
            color    (list): Optional color for each channel. ex: ['#1f77b4', '#ff7f0e']
            legend   (list): Optional name each curve. ex: ['Channel 1', 'Channel 2']
            kwargs   (dict): keyworded arguments for the backend library
        """

        if backend == 'bokeh':
            from vds1022 import plotter
            plotter.BokehChart(self, kwargs).show()
        elif backend == 'matplotlib':
            from vds1022 import plotter
            plotter.MatplotlibChart(self, kwargs).show()
        else:
            return self.to_dataframe().plot(backend=backend, **kwargs)


    def to_dataframe(self):
        """
        Returns:
            pandas.DataFrame: x and y values for each enabled channel: { 'CHx':ys, ... }, index=xs
        """
        import pandas
        xs = self.x()
        ys = { f.name: f.y() for f in self }
        df = pandas.DataFrame(ys, xs, copy=False)
        # TODO cutom plot on dataframe
        # df.plot = types.MethodType(plot, df)
        return df


    def to_numpy(self, axis=0):
        """
        Returns:
            ndarray: 2D Numpy array of x and y values (enabled channels only).
        """
        return np.stack(self.xy(), axis=axis)


    def to_dict(self):
        """
        Returns:
            list: [ { name:'CH1', x:[...], y:[...], ylim:(low, high) }, ... ]
        """
        xs = self.x()
        return [ { 'name': f.name,
                   'x': xs,
                   'y': f.y(),
                   'xlim': f.xlim,
                   'ylim': f.ylim
                 } for f in self ]


    def filter(self, ratio=0.1):
        """
            ratio (float): optional, from 0 to 1, where 1 is the Nyquist frequency.
        """
        for frame in self.frames:
            frame.filter(ratio)


    def decode_i2c(self):
        """ Decode I2C samples for CH1=scl CH2=sda .

        Returns:
            list: [ I2C(start=...), ... ]
        """
        from vds1022 import decoder
        return decoder.decode_i2c(self)


    def decode_uart(self, baud=None, bits=8, parity=None, msb=False):
        """ Decode UART samples for CH1=tx CH2=rx .

        Returns:
            list: [ UART(start=, ...), ... ]
        """
        from vds1022 import decoder
        return decoder.decode_uart(self, baud, bits, parity, msb)


    @classmethod
    def concat(cls, items):
        """ Concatenate multiple frames

        Args:
            items (`Frames` ): List of `Frames`
        Returns:
            `Frames`
        """
        frames = cls(map(copy, tuple.__iter__(items[0])), items[0].clock)  # clone first entry
        for frame in frames:  # concat buffers
            frame.buffer = np.concatenate([ item[frame.channel].buffer for item in items ])
        return frames



class Stream:

    def __init__(self, device, source):
        self._root   = self
        self._device = device
        self._source = source
        self._parent = None
        self._nodes  = []
        self._thread = threading.Thread(target=self._run, daemon=True)


    def map(self, func):
        """ Chain a function to process the data.

        Args:
            func (function)
        Returns:
            `Stream`
        """
        node = self.__new__(type(self))
        node._root   = self._root
        node._parent = self
        node._func   = func
        node._nodes  = []

        self._nodes.append(node)
        return node


    def _run(self):
        for data in self._source:
            self._emit(data)


    def _emit(self, data):
        for stream in self._nodes:
            data_new = stream._func(data)

            if data_new is not None:
                stream._emit(data_new)


    def _next(self):
        if self is self._root:
            return next(self._source)

        result = self._parent._next()
        if result is not None:
            return self._func(result)


    def agg(self, func):
        """ Chain an aggregate function to process a frame.

        Args:
            func (function): takes a `Frame` and return a `tuple` (xs, ys CHx, ...).
        Returns:
            `Stream`
        """
        self.clock = None

        def agg_frames(frames):
            if self.clock is None:
                self.clock = frames.clock
            return frames.clock - self.clock, *( func(f) for f in frames )

        return self.map(agg_frames)


    def avg(self):
        """ Chain the `Frame.avg` function to aggregate a frame.

        Returns:
            `Stream`
        """
        return self.agg(Frame.avg)


    def rms(self):
        """ Chain a `Frame.rms` function to aggregate a frame.

        Returns:
            `Stream`
        """
        return self.agg(Frame.rms)


    def sink(self, func):
        """ Chain a function and start the source.

        Args:
            func (function): Function to apply.
        """
        self.map(func)
        if not self._root._thread.is_alive():
            self._root._thread.start()


    def to_list(self):
        """ Chain a list and start the source.

        Returns:
            `list`
        """
        items = []
        self.sink(items.append)
        return items


    def plot(self, /, interval=1, rollover=None, **kwargs):
        """ Draw the data in a bokeh chart.

        Args:
            rollover  (int): Optional, maximum length of data to keep.
            width   (float): Optional, width of the plot in pixels. Defaults to 700.
            height  (float): Optional, height of the plot in pixels. Defaults to 300.
            xlabel    (str): Optional, horizontal label. Defaults to None.
            ylabel    (str): Optional, vertical label. Defaults to None.
            xy_mode  (bool): Optional, X-Y mode. Defaults to false.
            color    (list): Optional, color for each channel. ex: ['#1f77b4', '#ff7f0e']
            legend   (list): Optional, name each curve. ex: ['Channel 1', 'Channel 2']
            kwargs   (dict): keyworded arguments for the backend library
        """
        from vds1022 import plotter

        data = self._next()

        if isinstance(data, Frames):
            data = Frames.to_dict(data)
        elif isinstance(data, tuple):
            dev = self._root._device
            data = [ { 'name': 'CH' + str(chl + 1),
                       'x'   : data[0],
                       'y'   : data[1 + i],
                       'ylim': kwargs.get('ylim') or dev.ylim(chl)
                     } for i, chl in enumerate(dev.channels()) ]

        chart = plotter.BokehChart(data, kwargs, rollover)
        chart.show()
        self.sink(chart.update)
        return chart


    def to_dataframe(self):
        """ To pandas DataFrame .
        See https://streamz.readthedocs.io/en/latest/dataframes.html

        Returns:
            `streamz.DataFrame`
        """
        import pandas
        import streamz

        def to_dataframe(data):
            if isinstance(data, tuple):
                dev = self._root._device
                xs = data[0: 1]
                ys = { 'CH' + str(chl + 1): data[1 + i: 2 + i]
                       for i, chl in enumerate(dev.channels()) }
                return pandas.DataFrame(ys, xs, copy=False)
            elif isinstance(data, Frames):
                return Frames.to_dataframe(data)
            elif isinstance(data, pandas.DataFrame):
                return data

        stream = streamz.Stream()
        df = to_dataframe(self._next())
        sdf = stream.to_dataframe(example=df)
        stream.emit(df)
        self.map(to_dataframe).sink(stream.emit)
        return sdf



class VDS1022:
    """ Connect to the device (singleton).

    Args:
        firmware (str): Optional, fpga firmware location. Defaults to ``None``.
        flash    (str): Optional, flash file for recovery. Defaults to ``None``.
        debug   (bool): Optional, to monitor the commands. Defaults to ``False``.
    """

    _instance = None


    def __new__(cls, firmware=None, flash=None, debug=False):        
        self = cls._instance

        global DEBUG
        DEBUG = debug

        if self is None or not self.stop():
            self = cls._instance = object.__new__(cls)
            self._handle = None

        return self


    def __init__(self, firmware=None, flash=None, debug=False):

        if self._handle:
            self._initialize()
            return

        # Device config from flash memory. Updated by _load_flash
        self.oem = None
        self.version = None  #: str: Hardware version.
        self.serial = None  #: str: Hardware serial.
        self.locales = None
        self.phasefine = None
        self.vfpga = None  # firmware version number

        # Calibration from local file 'VDS1022xxxxxxxx.json' or flash memory
        self.calibration = None
        self.calibration_path = None

        # USB
        self._usb = None
        self._handle = None
        self._ep_write = None
        self._ep_read = None
        self._failures = 0
        self._clock = 0
        self._buffer = array('b', bytes(6000))

        # Synchronization / waiter
        self._lock = threading.Lock()
        self._stop = threading.Event()

        # Pending commands
        self._queue = collections.OrderedDict()

        # connect device
        if not self._connect():
            raise USBError("USB device %4X:%4X not found or locked by another application." % (
                USB_VENDOR_ID, USB_PRODUCT_ID))

        # initialize device
        self._load_flash(flash)

        if not flash:
            self._load_calibration()

        self._load_fpga(firmware or FIRMWARE_DIR)

        self._initialize()

        # Background thread to keep the USB connexion alive
        def run():
            while self._handle:
                clock = self._clock

                if self._stop.wait(3):
                    time.sleep(0.01)
                elif self._clock == clock:
                    try:
                        with self._lock:
                            self._send(CMD.SET_RUNSTOP, 1)  # [ 0:run, 1:stop ]
                    except USBError:
                        _logger.warning('Lost connection to device.')
                        self.dispose()
                        return

        threading.Thread(target=run, daemon=True).start()


    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_value, traceback):
        self.dispose()


    def _initialize(self):

        self._stop.clear()
        self._queue.clear()

        # default settings        CH1    CH2
        self.on               = [ False, False ]  # channel 1 on/off state, channel 2 on/off state
        self.probe            = [ 10   , 10    ]  # ratio of probe
        self.coupling         = [ DC   , DC    ]  # DC: direct current, AC: Alternating Current
        self.voltrange        = [ 2    , 2     ]  # 2 volts for 10 divisions (doesn't account for the probe rate)
        self.voltoffset       = [ 0    , 0     ]  # ratio of vertical range from -0.5 to +0.5 ( -0.1 = -1div )
        self.rollmode         = None   # auto-activates if sampling rate < ROLLMODE_THRESHOLD
        self.sweepmode        = None   # trigger sweep mode. None, AUTO, NORMAL, ONCE
        self.peakmode         = False  # peak mode. odd samples are max, even are min
        self.sampling_rate    = None   # sampling frequency (samples per second)
        self.trigger_position = 0      # trigger position from 0 to 1.

        self._push(CMD.SET_CHL_ON, 0)  #  b0:CH1, b1:CH2  [0=OFF 1=ON]
        self._push(CMD.SET_PHASEFINE, self.phasefine)  # ???
        self._push(CMD.SET_PEAKMODE, 0)  # [ 0:off  1:on ]
        self._push(CMD.SET_DEEPMEMORY, ADC_SIZE)  # ADC size
        self._push(CMD.SET_PRE_TRG, ADC_SIZE)  # pre-trigger size to max
        self._push(CMD.SET_SUF_TRG, 0)  # post-trigger size to min
        self._push(CMD.SET_MULTI, 0)  # [ 0:Out  1:PassFail  2:In ]
        self._push(CMD.SET_TRIGGER, 0)  # CH1, EDGE, RISE

        for chl in range(CHANNELS):
            self._push(CMD.SET_TRG_HOLDOFF[chl], 0x8002)  # 100ns
            self._push(CMD.SET_EDGE_LEVEL[chl], _u16(127, -128))  # disable triggering
            self._push(CMD.SET_FREQREF[chl], 20)  # freq meter
            self._push_channel(chl)

        self._push_sampling(250e3, False, False)


    def stop(self):
        """ Stop all operations.

        Returns:
            bool: `True` if succeed, `False` otherwise.
        """
        if self._handle:
            self._stop.set()

            with self._lock:
                self._queue.clear()
                try:
                    self._send(CMD.SET_RUNSTOP, 1)  # [ 0:run, 1:stop ]
                    self._stop.clear()
                    return True
                except USBError as ex:
                    _logger.error("Stop command failed")

                self._release()


    def dispose(self):
        """ Disconnect the device and release resources. """
        self._stop.set()

        with self._lock:
            self._queue.clear()
            self._release()


    def _connect(self):
        usb = libusb1.get_backend() or libusb0.get_backend()

        for dev in usb.enumerate_devices():
            desc = usb.get_device_descriptor(dev)

            if desc.idVendor == USB_VENDOR_ID and desc.idProduct == USB_PRODUCT_ID:
                try:
                    intf = usb.get_interface_descriptor(dev, USB_INTERFACE, 0, 0)
                    addrs = [ intf.endpoint[i].bEndpointAddress for i in range(intf.bNumEndpoints) ]

                    self._usb = usb
                    self._handle = usb.open_device(dev)
                    self._ep_write = next( x for x in addrs if x & 0x80 == 0 )
                    self._ep_read  = next( x for x in addrs if x & 0x80 != 0 )

                    usb.claim_interface(self._handle, USB_INTERFACE)

                    if self._send(CMD.GET_MACHINE, CMD.V) == 1:  # 0:Error 1:VDS1022 3:VDS2052
                        return True

                except USBError as ex:
                    if DEBUG:
                        print(ex)

                self._release()


    def _release(self):
        if self._handle:
            try:
                self._usb.release_interface(self._handle, USB_INTERFACE)
            except: pass
            try:
                self._usb.close_device(self._handle)
            except: pass

        self._usb = self._handle = self._ep_write = self._ep_read = None


    def _bulk_write(self, buffer):
        gc.collect(0)  # prevents long gc and timeout between write and read
        self._usb.bulk_write(self._handle, self._ep_write, USB_INTERFACE, buffer, USB_TIMEOUT)
        self._clock = time.perf_counter()


    def _bulk_read(self, buffer, size=None):
        ret = self._usb.bulk_read(self._handle, self._ep_read, USB_INTERFACE, buffer, USB_TIMEOUT)
        assert size is None or ret == size, "Expected response length of %s, got %d" % (size, ret)
        self._failures = 0
        return ret


    def _send(self, cmd, arg):
        while True:
            try:
                self._bulk_write(cmd.pack(arg))
                ret = self._bulk_read(self._buffer, 5)
                cmd.log(arg, ret, self._buffer)
                status, value = CMD.BI.unpack_from(self._buffer)
                return value
            except USBError as ex:
                self._on_usb_err(ex)


    def _on_usb_err(self, ex):
        self._failures += 1
        if self._failures > 2:
            raise ex
        self._stop.wait(0.01 * self._failures)


    def _push(self, cmd, arg):
        self._queue.pop(cmd, None)  # remove the command if already in queue
        self._queue[cmd] = arg


    def _submit(self):
        n = len(self._queue)
        while self._queue:
            self._send(*self._queue.popitem(False))
        return n


    def send(self, cmd, arg):
        """ Execute a command.

        Args:
            cmd (Cmd): command
            arg (int): argument
        Returns:
            int
        """
        with self._lock:
            self._queue.pop(cmd, None)
            while self._queue:
                self._send(*self._queue.popitem(False))
            return self._send(cmd, arg)


    def wait(self, seconds):
        """ Suspend execution for the given number of seconds.

        Args:
            seconds (float)
        """
        with self._lock:
            self._submit()
            if self._stop.wait(seconds):
                raise KeyboardInterrupt()


    def _load_calibration(self):

        for fpath in glob.glob(self.calibration_path):
            with open(fpath, 'r') as f:
                try:
                    self.calibration = json.load(f)['cals']
                except json.JSONDecodeError as ex:
                    _logger.error('Failed to load local calibration')
                    pass

                if DEBUG:
                    _log("Load " + path.basename(self.calibration_path))
                    _log_calibration(self.calibration)

                return True


    def _save_calibration(self):

        with open(self.calibration_path, 'w') as f:
            json.dump({'cals': self.calibration}, f, indent=4)


    def save_flash(self, fname):
        """ Save the device flash memory to a file.

        Args:
            fname (str): Output file name.
        """
        with open(fname, 'wb') as f:
            f.write(self.read_flash())
        _printf("Saved flash to\n%s", path.abspath(fname))


    def read_flash(self):
        """ Return a dump of the device flash memory.

        Returns:
            array('B'): array of unsigned bytes
        """
        with self._lock:
            assert len(self._buffer) > FLASH_SIZE

            self._bulk_write(CMD.READ_FLASH.pack(1))
            ret = self._bulk_read(self._buffer, FLASH_SIZE)
            CMD.READ_FLASH.log(1, ret, self._buffer)

            return self._buffer[:FLASH_SIZE]


    def write_flash(self, source):
        """ Overwrite the device flash memory with data from a file or array of bytes.

        Args:
            source (str or bytes): File path or bytes.
        """
        if isinstance(source, str):
            with open(source, 'rb') as f:
                return self.write_flash(f.read())

        self.save_flash('%s-flash-%s.bin' % (self.serial, int(time.time())))

        with self._lock:

            buffer = array('B', source)
            assert len(buffer) == FLASH_SIZE, "Bad flash size. Expected %d bytes" % FLASH_SIZE
            assert tuple(buffer[:2]) in ((0x55, 0xAA), (0xAA, 0x55)), "Bad flash header"
            assert self._send(CMD.QUERY_FPGA, 0) == 1, "Firmware not loaded"

            buffer[:2] = array('B', (0x55, 0xAA))

            self._send(CMD.WRITE_FLASH, 1)
            self._bulk_write(buffer)
            self._bulk_read(buffer, 5)
            assert buffer[0] == CMD.S, "Bad response status: " + chr(buffer[0])

        _printf("Done overwriting Flash memory.")


    def sync_flash(self):
        """ Overwrite the device flash memory with the data and calibration
        of this instance. It automatically creates a backup of the 
        flash before attempting to overwriting it.
        """
        writer = _FlashStream(b'\xff' * FLASH_SIZE)
        writer.write('<HI', 0x55AA, 2)  # flash header, version

        writer.seek(6)
        for cal in (GAIN, AMPL, COMP):
            for chl in range(CHANNELS):
                writer.write('<10H', *self.calibration[cal][chl])

        writer.seek(206)
        writer.write('<B', self.oem)
        writer.write_str(self.version.upper())
        writer.write_str(self.serial.upper())
        writer.write('<100B', *self.locales)
        writer.write('<H', self.phasefine)

        self.write_flash(writer.buffer)
        self._save_calibration()


    def _load_flash(self, fname=None):

        if fname is None:
            buffer = self.read_flash()
        else:
            with open(fname, 'rb') as f:
                buffer = f.read()

        reader = _FlashStream(buffer)

        flash_header, flash_version = reader.read('<HI')
        assert flash_header in (0x55AA, 0xAA55), "Bad flash header: 0x%X" % flash_header
        assert flash_version == 2, "Bad flash version: %d" % flash_version

        reader.seek(6)
        self.calibration = [ [ list(reader.read('<10H')) for _ in range(CHANNELS) ]
                             for _ in (GAIN, AMPL, COMP) ]

        reader.seek(206)
        self.oem       = reader.read('<B')      # 1
        self.version   = reader.read_str()      # V2.5
        self.serial    = reader.read_str()      # VDS1022I1809215
        self.locales   = reader.read('<100B')   # 1 1 1 1 1 1 1 1 1 1 1 1 ...
        self.phasefine = reader.read('<H')      # 0

        ver = self.version.upper()

        if ver.startswith("V2.7.0"):
            self.vfpga = 3
        elif ver.startswith("V2.4.623") or ver.startswith("V2.6.0"):
            self.vfpga = 2
        elif ver.startswith("V2.") or ver.startswith("V1."):
            self.vfpga = 1
        elif ver.startswith("V"):
            self.vfpga = int(ver[1:ver.index(".")])
        else:
            raise ValueError("Bad device version: %s" % self.version)

        self.calibration_path = path.join(_dir, self.serial + '-cals.json')

        if DEBUG:
            crc32 = binascii.crc32(reader.buffer[2:]) & 0xFFFFFFFF
            _log("# oem=%s version=%s serial=%s phasefine=%s crc32=%08X" % (
                    self.oem, self.version, self.serial, self.phasefine, crc32))
            _log_calibration(self.calibration)


    def _load_fpga(self, source):

        with self._lock:

            if self._send(CMD.QUERY_FPGA, 0) == 1:  # 0:Missing  1:Loaded
                return

            if path.isdir(source):
                source = path.join(source, 'VDS1022_FPGAV%s_*.bin' % self.vfpga)

            paths = glob.glob(source)
            assert paths, 'Firmware not found at %s' % source

            with open(paths[-1], 'rb') as f:
                dump = f.read()

            if DEBUG:
                crc32 = binascii.crc32(dump) & 0xFFFFFFFF
                _log("Load firmware %s (CRC32=%08X)" % (path.basename(paths[-1]), crc32))

            frame_size = self._send(CMD.LOAD_FPGA, len(dump))
            assert frame_size > 0, "Bad frame_size: " + frame_size

            header = struct.Struct('<I')
            payload_size = frame_size - header.size
            frame_count = ceil(len(dump) / payload_size)

            for i, start in enumerate(range(0, len(dump), payload_size)):
                print(" loading firmware part %s/%s" % (i + 1, frame_count), end='\r')

                self._bulk_write(array('B', header.pack(i) + dump[start: start + payload_size]))
                self._bulk_read(self._buffer, 5)
                status, value = CMD.BI.unpack_from(self._buffer)
                assert status == CMD.S, "\nBad status: " + chr(status)
                assert value == i, "\nBad part id. Expected %s, got %s" % (i, value)

            print(' ' * 50, end='\r')


    def set_channel(self, channel, range=20, offset=0.5, probe=10, coupling=DC):
        """ Configure a channel.

        Args:
            channel  (int, str): Channel: `CH1`, `CH2`
            range    (int, str): Volt range at the probe for 10 divs. Defaults to ``20v``
            offset      (float): Optional volt zero offset [0 to 1]. Defaults to ``1/2``
            probe    (int, str): Optional probe ratio (ex: 10 or 'x10'). Defaults to ``10``
            coupling (int, str): Coupling: `DC`, `AC`, `GND`
        Examples:
            >>> dev.set_channel(CH2, range='10v', offset=2/10, probe='10x')
        """
        chl       = _parse.constant(channel=channel)
        coupling  = _parse.constant(coupling=coupling)
        voltrange = _parse.volts(range=range)
        offset    = _parse.ratio(offset=offset)
        probe     = _parse.factor(probe=probe)

        assert chl in (CH1, CH2), "Parameter channel out of range: %s" % chl
        assert 0 <= offset <= 1, "Parameter offset out of range: %s" % offset
        assert probe >= 1, "Parameter probe out of range: %s" % probe

        vr_ask = round(voltrange / probe, 3)
        vr_new = VOLT_RANGES[_find_ge(VOLT_RANGES, vr_ask)]
        if vr_new != vr_ask:
            _printf("%sv range not available, selecting %sv range.", voltrange, vr_new * probe)

        self.on[chl] = True
        self.coupling[chl] = coupling
        self.voltrange[chl] = vr_new
        self.voltoffset[chl] = offset - 0.5
        self.probe[chl] = probe

        self._push_channel(chl)


    def channels(self):
        """
        Returns:
            iter: Iterator of the enabled channels.
        """
        return (i for i, on in enumerate(self.on) if on)


    def _push_channel(self, chl):

        vb = VOLT_RANGES.index(self.voltrange[chl])
        pos0 = ADC_RANGE * self.voltoffset[chl]
        attenuate = vb >= ATTENUATION_THRESHOLD
        cal_comp = self.calibration[COMP][chl][vb]
        cal_ampl = self.calibration[AMPL][chl][vb]
        cal_gain = self.calibration[GAIN][chl][vb]

        zero_arg = _clip(round(cal_comp - pos0 * cal_ampl / 100), 0, 4095)
        self._push(CMD.SET_ZERO_OFF[chl], zero_arg)  # set offset, doesn't clear samples

        gain_arg = _clip(cal_gain, 0, 4095)
        self._push(CMD.SET_VOLT_GAIN[chl], gain_arg)  # set voltbase and clear samples

        # SET_CHANNEL
        #  b0  : not defined [ 0 ]
        #  b1  : input attenuation [ 0:OFF 1:ON ] (relay to reduce the input voltage)
        #  b2-3: bandwidth limit [ 0 ]
        #  b4  : not defined [ 0 ]
        #  b5-6: channel coupling [ 0:DC 1:AC 2:GND ]
        #  b7  : channel on/off [ 0:OFF 1:ON ]
        chl_arg = attenuate << 1 | self.coupling[chl] << 5 | self.on[chl] << 7
        self._push(CMD.SET_CHANNEL[chl], chl_arg)  # set channel and clear samples


    def set_multi(self, state):
        """ Set the output TTL state of the MULTI port.

        Args:
            state (int): 0:Low 0v  1:Hi 5v
        """
        # SET_MULTI
        #  b0-1 : Multi mode [ 0:Trigger Out  1:Pass/Fail Out  2:Trigger In ]
        #  b8   : Pass/Fail output state  [ 0:TTL low 0v  1:TTL hi 5v ]
        multi_arg = MULTI_PF | bool(state) << 8
        self.send(CMD.SET_MULTI, multi_arg)


    def set_sampling(self, rate, roll=None, peak=False):
        """ Configure the sampling rate

        Args:
            rate (int,str): Sampling rate, from 2.5 to 100M samples per second.
            roll    (bool): Optional, sets the roll mode. Defaults to sampling rate >= 2500
            peak    (bool): Optional, enables or disables peak mode sampling.
        """
        rate = _parse.freq(rate=rate)
        assert SAMPLING_RATES[0] <= rate <= SAMPLING_RATES[-1], "Parameter rate out of range"
        self._push_sampling(rate, roll, peak)


    def set_timerange(self, range, roll=None, peak=False):
        """ Configure the sampling rate for 5000 samples for a given time range.

        Args:
            range (float,str): Frame duration in seconds from 50e-6 (50us) to 2000 (2000s)
            roll       (bool): Optional, sets the roll mode. Defaults to timerange >= 2s
            peak       (bool): Optional, enables or disables peak mode sampling.
        """
        timerange = _parse.seconds(range=range)
        rate = SAMPLES / timerange
        assert SAMPLING_RATES[0] <= rate <= SAMPLING_RATES[-1], "Parameter range out of range"
        self._push_sampling(rate, roll, peak)


    def _push_sampling(self, rate, roll, peak):

        prescaler = _max(1, round(SAMPLING_RATES[-1] / _max(3, rate)))
        sr = SAMPLING_RATES[-1] / prescaler
        rm = sr < ROLLMODE_THRESHOLD if roll is None else roll

        if sr != self.sampling_rate:
            self.sampling_rate = sr
            self._push(CMD.SET_TIMEBASE, prescaler)

        if rm != self.rollmode:
            self.rollmode = rm
            self._push(CMD.SET_ROLLMODE, rm & 1)
            # adding +3 to fix bad samples at the end when roll mode is on.
            self._push(CMD.SET_DEEPMEMORY, ADC_SIZE + (3 if rm else 0))

        if peak is not None and peak != self.peakmode:
            self.peakmode = peak
            self._push(CMD.SET_PEAKMODE, peak & 1)  # [ 0:off  1:on ]

        if rm:
            self.trigger_position = 1  # sets origine on the right


    def set_trigger(self,
                    source,
                    mode=EDGE,
                    condition=RISE,
                    position=0.5,
                    level=0,
                    width=30e-9,
                    holdoff=100e-9,
                    sweep=ONCE):
        """ Configure a trigger.

        Args:
            source      (int): Channel index: `CH1` `CH2` `EXT` .
            mode       (mode): Mode index: `EDGE` `PULSE` `SLOPE` .
            condition   (int): Edge: `RISE`, `FALL` .
                               Slop/Pulse: `RISE_SUP`, `RISE_EQU`, `RISE_INF`, 
                                           `FALL_SUP`, `FALL_EQU`, `FALL_INF` .
            position  (float): Optional horizontal trigger position from 0 to 1.
                               Defaults to ``1/2`` .
            level (float,str): Optional trigger level in volt. Pair of hi and low if SLOPE mode.
                               Defaults to ``0v`` .
            width     (float): Optional condition width in second for PULSE/SLOPE mode only.
                               Defaults to ``30ns``.
            holdoff   (float): Optional time in second before the next trigger can occur.
                               Defaults to ``100ns``.
            sweep       (int): Optional sweep mode: `AUTO`, `NORMAL`, `ONCE`.
                               Defaults to `ONCE`.
        Examples:
            >>> dev.set_trigger(CH1, EDGE, RISE, position=1/2, level='2.5v')
            >>> dev.set_trigger(CH1, PULSE, RISE_SUP, position=1/2, level='2.5v', width='2ms')
            >>> dev.set_trigger(CH1, SLOPE, RISE_SUP, position=1/2, level=('1v', '4v'), width='20ms')
        """

        chl       = _parse.constant(source=source)
        mode      = _parse.constant(mode=mode)
        condition = _parse.constant(condition=condition)
        position  = _parse.ratio(position=position)
        levels    = [ _parse.volts(level=v) for v in _items(level) ]
        width     = _parse.seconds(width=width)
        holdoff   = _parse.seconds(holdoff=holdoff)
        sweep     = _parse.constant(sweep=sweep)

        self.sweepmode = sweep

        # alternate mode if previous command is SET_TRIGGER and channel is not external
        alternate = chl != EXT \
                    and bool(self._queue) \
                    and next(reversed(self._queue)) is CMD.SET_TRIGGER

        # external channel
        multi = (MULTI_OUT, MULTI_IN)[chl == EXT]
        self._push(CMD.SET_MULTI, multi)  # [ 0:Trigger Out  1:Pass/Fail Out  2:Trigger In ]

        # number of samples before and after trigger
        #            | max left  |   center   | max right
        #  position  |    0      |    0.5     |    1
        #  pre, post | 50, 5050  | 2550, 2550 | 5050, 50
        htp = round(SAMPLES * _clip(0.5 - position, -0.5, 0.5))
        self._push(CMD.SET_PRE_TRG, (ADC_SIZE >> 1) - htp - HTP_ERR)
        self._push(CMD.SET_SUF_TRG, (ADC_SIZE >> 1) + htp + HTP_ERR)
        self.trigger_position = position

        if chl == EXT:
            assert mode == EDGE, "Trigger mode not supported with external channel: %s" % mode
        else:
            # edge/pulse/slope level
            vr = self.probe[chl] * self.voltrange[chl]
            lvls = [ round((v / vr + self.voltoffset[chl]) * ADC_RANGE) for v in levels ]
            if mode in (EDGE, PULSE):
                assert len(lvls) == 1, "Parameter level requires 1 value only"
                v = lvls[0] + (10 if condition < 0 else 0)  # +10 if fall condition
                assert ADC_MIN + 10 <= v <= ADC_MAX, "Parameter level not in range: %s" % levels[0]
                self._push(CMD.SET_EDGE_LEVEL[chl], _u16(v, v - 10))  # trigger level
                self._push(CMD.SET_FREQREF[chl], _u8(v - 5))  # freq meter
            elif mode == SLOPE:
                assert len(lvls) == 2, "Parameter level requires 2 values"
                assert ADC_MIN <= lvls[0] <= ADC_MAX, "Parameter level[0] not in range %s" % levels[0]
                assert ADC_MIN <= lvls[1] <= ADC_MAX, "Parameter level[1] not in range %s" % levels[1]
                self._push(CMD.SET_SLOPE_THRED[chl], _u16(max(lvls), min(lvls)))
                self._push(CMD.SET_FREQREF[chl], _u8(sum(lvls) // 2))  # freq meter

            # pulse/slope width
            if mode in (PULSE, SLOPE):
                if self.vfpga < 3:  # if old boards
                    m, e = _iexp10(width * 1e8, 1023)  # to 10th ns, 10bits mantissa, base10 exponent
                    if condition in (RISE_EQU, FALL_EQU):
                        self._push(CMD.SET_TRG_CDT_EQU_H[chl], int(m * 1.05) << 6 | e & 7)
                        self._push(CMD.SET_TRG_CDT_EQU_L[chl], int(m * 0.95))
                    else:
                        self._push(CMD.SET_TRG_CDT_GL[chl], m)
                        self._push(CMD.SET_TRG_CDT_EQU_H[chl], e)
                else:  # newer boards
                    m = width * 1e8  # sec to 10th of ns
                    self._push(CMD.SET_TRG_CDT_GL[chl], int(m % 65536))
                    self._push(CMD.SET_TRG_CDT_HL[chl], int(m / 65536))

        # holdoff time
        m, e = _iexp10(holdoff * 1e8, 1023)  # to 10th ns, 10bits mantissa, base10 exponent
        self._push(CMD.SET_TRG_HOLDOFF[chl % CHANNELS], _swap16(m << 6 | e & 7))

        # trigger settings
        # bit 0 : source [ 0:channel 1:external/multi ]
        # bit 15: type [ 0:single 1:alternate ]
        trg = (chl == EXT) & 1 | (alternate & 1) << 15

        if alternate:
            # bit 14  : channel [ 0:CH1 1:CH2 ]
            # bit 13,8: mode [ 0:edge 1:video 2:slope 3:pulse ]
            trg |= (chl & 1) << 14 | (mode & 2) << 7 | (mode & 1) << 13
        else:
            # bit 13  : channel [ 0=CH1 1=CH2 ]
            # bit 8,14: mode [ 0:edge 1:video 2:slope 3:pulse ]
            trg |= (chl & 1) << 13 | (mode & 2) << 13 | (mode & 1) << 8

        if mode == EDGE:
            # bit 9    : coupling [ AC:0 ]
            # bit 10,11: sweep if not alternate [ 0:Auto 1:Normal 2:Once ]
            # bit 12   : condition [ 0:raise 1:fall ]
            trg |= (condition < 0) << 12 | (not alternate and sweep & 3) << 10
        elif mode in (PULSE, SLOPE):
            # bit 5,6,7: condition [ 0:Rise> 1:Rise= 2:Rise< 3:Fall> 4:Fall= 5:Fall< ]
            # bit 10,11: sweep if not alternate [ 0:Auto 1:Normal 2:Once ]
            trg |= (condition & 7) << 5 | (not alternate and sweep & 3) << 10
        else:
            raise NotImplementedError("Trigger mode not supported: " + str(mode))

        self._push(CMD.SET_TRIGGER, trg)


    def get_triggered(self):
        """
        Returns:
            int: Trigger state: ``CH1:bit0`` ``CH2:bit2`` ``EXT:bit1-bit2``.
        """
        trg_d = self.send(CMD.GET_TRIGGERED, 0)
        return trg_d & _bits(self.on)


    def force_trigger(self):
        """ Force trigger. """
        self.send(CMD.SET_FORCETRG, 0x3)


    def ylim(self, channel=None):
        """ Lower/upper bounds for the voltage axis.

        Args:
            channel (int): Optional channel: `CH1`, `CH2`. Defaults to `None`.
        Returns:
            tuple: (lower, upper)
        """
        if channel is None:
            yy = [ self.voltrange[chl] * self.probe[chl] * (r - self.voltoffset[chl])
                   for r in (-0.5, 0.5)
                   for chl, on in enumerate(self.on) if on ]
            return min(yy), max(yy)
        else:
            chl = _parse.constant(channel=channel)
            voltrange = self.voltrange[chl] * self.probe[chl]
            ty = voltrange * -self.voltoffset[chl]
            return ty - voltrange / 2, ty + voltrange / 2


    def xlim(self):
        """ Left/right bounds for the time axis.

        Returns:
            tuple: (left, right)
        """
        timerange = SAMPLES / self.sampling_rate
        tx = timerange * (0.5 - self.trigger_position)
        return tx - timerange / 2, tx + timerange / 2


    def plot(self, freq=3, autorange=False, autosense=False, **kwargs):
        """ Live plotting.

        Args:
            freq       (int): Refresh frequency. Defaults to 3Hz.
            autorange (bool): Optional, auto adjusts the voltrange. Defaults to False.
            autosense (bool): Optional, auto adjusts the trigger level to 50%. Defaults to `False`.
            kwargs    (dict): keyworded arguments for the backend library
        """
        from vds1022 import plotter

        fetch = self.fetch_iter(freq, autorange, autosense)
        frames = next(fetch)
        chart = plotter.BokehChart(frames, kwargs).show()

        if self.sweepmode != ONCE:

            def run():
                for frames in fetch:
                    chart.update(frames)

            threading.Thread(target=run, daemon=True).start()


    def stream(self, freq=3, autorange=False):
        """ To stream non continuous frames of 5000 points.
        The frames are pulled at an interval defined by freq.

        Args:
            freq     (float): Optional, acquisition frequency. Defaults to 3Hz.
            autorange (bool): Optional, auto adjusts the voltrange and offset. Defaults to ``False``.
        Returns:
            `Stream`
        Example:
            Stream plotting of RMS voltage

            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022()
            >>> dev.set_channel(CH1, range='10v', coupling=DC, offset=1/10, probe='x1')
            >>> dev.set_channel(CH2, range='10v', coupling=DC, offset=1/10, probe='x1')
            >>> dev.stream(freq=3).rms().plot()

            Stream plotting with customised aggregation

            >>> def to_rms(frames):
            >>>     x = frames.time
            >>>     return [ dict(name=f.name, x=x, y=f.rms(), ylim=f.ylim) for f in frames ]
            >>>
            >>> dev.stream(freq=1).map(to_rms).plot()

            Streaming to a function

            >>> src = dev.stream(freq=1).rms().sink(print)
        """
        fetch = self.fetch_iter(freq, autorange)
        return Stream(self, fetch)


    def fetch(self, autorange=False):
        """ Acquire a sampling frame for each enabled channel.

        Args:
            autorange (float): Optional, auto adjusts the voltrange. Defaults to False.
        Returns:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        Examples:
            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022()
            >>> dev.set_timerange('100ms')
            >>> dev.set_channel(CH1, range='10v', coupling=AC, offset=1/2, probe='x10')
            >>> dev.set_channel(CH2, range='20v', coupling='DC', offset=1/2, probe='x10')
            >>> dev.set_trigger(CH1, mode=EDGE, condition=RISE, sweep=ONCE)
            >>> frames = dev.fetch()
            >>> print(frames)
        """
        return next(self.fetch_iter(3, autorange, False))


    def fetch_iter(self, freq=3, autorange=False, autosense=False):
        """Generator to acquire multiple sampling frames.

        Args:
            freq     (float): Optional, iteration frequency. Defaults to `3Hz`.
            autorange (bool): Optional, auto adjusts the voltrange and offset. Defaults to `False`.
            autosense (bool): Optional, auto adjusts the trigger level to 50%. Defaults to `False`.
        Yields:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        Examples:
            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022(debug=False)
            >>> dev.set_timerange('10ms')
            >>> dev.set_channel(CH1, range='20v', coupling=DC, offset=5/10, probe='x10')
            >>> dev.set_channel(CH2, range='20v', coupling=DC, offset=1/10, probe='x10')
            >>> dev.set_trigger(CH1, EDGE, RISE, level='2v', position=1/2, sweep=AUTO)
            >>>
            >>> for frames in dev.fetch_iter(freq=3, autosense=True, autorange=False):
            >>>     print(frames)
            >>>     break
        """
        assert not (autosense and self.sweepmode), "autosense not supported with NORMAL/ONCE sweep mode"

        with self._lock:
            if not any(self.on):
                self.on[CH1] = True

            buffer  = self._buffer
            delay   = _max(0, 1 / freq - 0.05) if freq else 0
            start   = FRAME_SIZE - SAMPLES - (0 if self.rollmode else 50)  # right or center
            points  = np.frombuffer(buffer, np.int8, SAMPLES, offset=start)
            frames  = [ None ] * CHANNELS
            changed = False
            wait    = 0
            clock   = 0

            #     self._push(CMD.SET_CHL_ON, _bits(self.on)  # [ 0:off 1:on ]
            #     self._push(CMD.SET_RUNSTOP, 0)  # [ 0:run, 1:stop ]

        while True:
            with self._lock:

                if self._submit() > 5:
                    wait = 0.25  # initial time for freq meter
                else:
                    wait = _clip(delay - self._clock + clock, 0, delay)

                while True:
                    if self._stop.wait(wait):
                        return

                    if self.sweepmode :  # ONCE or NORMAL
                        if not self._send(CMD.GET_DATAFINISHED, 0) \
                            or not self._send(CMD.GET_TRIGGERED, 0):
                            wait = 0.06
                            continue

                    for chl, time_sum, period_num, cursor in self._pull_data(self.on, buffer):
                        assert self.rollmode or cursor >= SAMPLES, "Bad cursor: %d" % cursor

                        if autorange or autosense:
                            pt_min = int(points.min())
                            pt_max = int(points.max())
                            if autorange:  # adjust volt range and volt offset
                                if self._adjust_range(chl, pt_min, pt_max):
                                    continue
                            if autosense:  # adjust trigger level and frequency meter level
                                self._adjust_sense(chl, pt_min, pt_max)

                        cursor = SAMPLES - _clip(cursor, 0, SAMPLES)  # invert cursor from right to left
                        offset = cursor - (SAMPLES * self.trigger_position)  # samples to trigger origin
                        frequency = time_sum and period_num / time_sum * SAMPLING_RATES[-1]  # frequency meter
                        frames[chl] = Frame(self, chl, buffer[start + cursor: start + SAMPLES], offset, frequency)

                    if self._submit() > 2:  # if sent _adjust_range commands
                        wait = 0.2
                        continue

                    break

            clock = self._clock
            yield Frames(frames, clock)


    def _pull_data(self, chl_on, buffer):

        # b0-7:CH1  b8-15:CH2  [ 0x04:OFF 0x05:ON ]
        arg  = int.from_bytes(((4, 5)[on] for on in chl_on), 'little')
        n    = sum(chl_on)
        wait = 0  # wait 0ms if first attempt, 60ms otherwise

        i = 0
        while i < n:
            try:
                self._bulk_write(CMD.GET_DATA.pack(arg))

                i = 0
                while i < n:
                    ret = self._bulk_read(buffer)
                    CMD.GET_DATA.log(arg, ret, buffer)

                    if ret != FRAME_SIZE:  # if EBUSY
                        assert i == 0 and ret == 5
                        if self._stop.wait(wait):
                            return
                        wait = 0.06
                        break

                    yield CMD.BIIH.unpack_from(buffer)
                    i += 1

            except USBError as ex:
                self._on_usb_err(ex)


    def _adjust_range(self, chl, pt_min, pt_max):

        vb = VOLT_RANGES.index(self.voltrange[chl])
        offset = round(ADC_RANGE * self.voltoffset[chl])
        lo = _min(offset, pt_min) if pt_min > ADC_MIN else (pt_min << 2) 
        hi = _max(offset, pt_max) if pt_max < ADC_MAX else (pt_max << 2) 
        amp = abs(hi - lo)

        if amp < 30 or amp >= ADC_RANGE:
            vr = amp * 1.2 * VOLT_RANGES[vb] / ADC_RANGE
            vb_new = _find_ge(VOLT_RANGES, vr)  # volt range greater or equal

            if vb != vb_new or amp >= 30:
                scale = VOLT_RANGES[vb] / VOLT_RANGES[vb_new]
                mid = (hi - offset + lo - offset) / 2 * _min(scale, 10)
                self.voltoffset[chl] = _clip(-mid / ADC_RANGE, -0.4, 0.4)
                self.voltrange[chl] = VOLT_RANGES[vb_new]
                self._push_channel(chl)
                return True


    def _adjust_sense(self, chl, pt_min, pt_max):

        offset = round(ADC_RANGE * self.voltoffset[chl])
        lo = _min(offset, pt_min)
        hi = _max(offset, pt_max)
        mid = _clip((lo + hi) >> 1, -100, 100)
        self._push(CMD.SET_EDGE_LEVEL[chl], _u16(mid + 10, mid))  # trigger sense level
        self._push(CMD.SET_FREQREF[chl], _u8(mid))  # freq meter sense level


    def read(self, duration, pre=None):
        """ Acquire continuous samples for a defined time from the start or on a trigger.
        The maximum sampling rate is arround 100Kbs/s.
        Raise an error if samples are missing.

        Args:
            duration (float): Time from start or post-trigger time if a trigger is set (second).
            pre      (float): Optional pre-trigger time (second).
        Returns:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        Example:
            Acquire continuous samples on a trigger:

            >>> dev = VDS1022()
            >>> dev.set_sampling('10k')  # 1K samples per seconds * 10 samples
            >>> dev.set_channel(CH1, DC, range='10v', offset=2/10, probe='x10')
            >>> dev.set_trigger(CH1, EDGE, FALL, level='2.5v')
            >>> frames = dev.read('1s')
            >>> frames
        """
        duration = _parse.seconds(duration=duration)
        pre = _parse.seconds(pre=pre) if pre else 0

        queue = collections.deque()
        clock_start = None
        clock_end = None

        if self.sweepmode == ONCE:
            for frames in self.read_iter():
                queue.append(frames)
                now = frames.clock

                if clock_start is None:
                    clock_start = now

                if clock_end is None:
                    with self._lock:
                        if self._send(CMD.GET_TRIGGERED, 0):
                            clock_end = now + duration

                    while queue and now - queue[0].clock > pre:
                        queue.popleft()

                elif now > clock_end:
                    return Frames.concat(queue)
        else:
            for frames in self.read_iter():
                queue.append(frames)

                if clock_end is None:
                    clock_end = frames.clock + duration

                if frames.clock > clock_end:
                    return Frames.concat(queue)


    def read_iter(self):
        """ Generator to retrieve consecutive samples.

        Yields:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        """
        with self._lock:

            self.rollmode = True
            self.trigger_position = 0

            if not any(self.on):
                self.on[CH1] = True  # turn on CH1 if all channels are off

            buffer   = self._buffer
            adc_size = ADC_SIZE + 20  # cursor becomes circular with ADC_SIZE + 20
            cmd_arg  = int.from_bytes(((4, 5)[on] for on in self.on), 'little')
            cmd_get  = CMD.GET_DATA.pack(cmd_arg)
            chl_cnt  = sum(self.on)  # number of used channels
            delay    = _clip(ADC_SIZE / self.sampling_rate / 4 - 0.035 * chl_cnt, 0, 1)
            maxtime  = ADC_SIZE / self.sampling_rate
            clock    = self._clock + 5  # init higher value
            frames   = [ None ] * CHANNELS
            cursors  = [ 20 ] * CHANNELS  # 20 to account for ADC_SIZE + 20
            offset   = 0
            size     = 0

            self._push(CMD.SET_SUF_TRG, 0)  # post-trigger size
            self._push(CMD.SET_PRE_TRG, adc_size)  # pre-trigger size
            self._push(CMD.SET_DEEPMEMORY, adc_size)  # ADC size for 1 channel
            self._push(CMD.SET_ROLLMODE, 1)  # [ 0:off 1:on ]
            # self._push(CMD.SET_CHL_ON, _bits(self.on))  # [ 0:off 1:on ]
            # self._push(CMD.SET_RUNSTOP, 0)  # [ 0:run, 1:stop ]
            self._submit()

            # wait 600ms for the trigger to clear itself
            for _ in range(6):
                if self._stop.wait(0.1):
                    return
                if not self._send(CMD.GET_TRIGGERED, 0):
                    break

        while True:
            with self._lock:
                if self._stop.wait(delay):
                    return

                self._bulk_write(cmd_get)

                for _ in range(chl_cnt):
                    ret = self._bulk_read(buffer)
                    assert ret == FRAME_SIZE, 'Bad frame size: %s' % ret

                    chl, _, _, cursor = CMD.BIIH.unpack_from(buffer)
                    size = (cursor - cursors[chl] + adc_size) % adc_size  # count new samples
                    assert size > 0, "Bad cursor %d: " % cursor

                    cursors[chl] = cursor
                    frames[chl] = Frame(self, chl, buffer[FRAME_SIZE - size: FRAME_SIZE], offset, None)

                assert self._clock - clock < maxtime, "Missed some samples! Reduce the sampling rate"
                clock = self._clock
                offset += size

            yield Frames(frames, clock)


    def autoset(self):
        """ Auto adjusts the range and timebase.

        """
        with self._lock:

            points  = np.frombuffer(self._buffer, np.int8, SAMPLES, FRAME_SIZE - SAMPLES - 50)
            rate    = SAMPLING_RATES[-1]
            tries   = 0
            hits    = 0

            self.on[:] = (True, ) * CHANNELS  # activate all channels
            self.sweepmode = AUTO
            self.trigger_position = 1/2

            self._push_sampling(25000, False, False)  # 25K samples per second
            self._push(CMD.SET_PEAKMODE, 1)  # [ 0:off  1:on ]
            self._push(CMD.SET_MULTI, 0)  # [ 0:TrgOut  1:PassFail  2:TrgIn ]
            self._push(CMD.SET_PRE_TRG, (ADC_SIZE >> 1) - HTP_ERR )  # htp at half
            self._push(CMD.SET_SUF_TRG, (ADC_SIZE >> 1) + HTP_ERR )  # htp at half
            self._push(CMD.SET_TRIGGER, 0xc000)  # Alternate CH1 and CH2

            for chl in range(CHANNELS):
                self.voltoffset[chl] = 0  # clear offset
                self._push(CMD.SET_TRG_HOLDOFF[chl], 0x8002)  # 100ns
                self._push(CMD.SET_EDGE_LEVEL[chl], _u16(20, 10))  # trigger level
                self._push(CMD.SET_FREQREF[chl], _u8(12))  # freq meter
                self._push_channel(chl)

            # self._push(CMD.SET_CHL_ON, _bits(self.on))  # [ 0:off 1:on ]
            # self._push(CMD.SET_RUNSTOP, 0)  # [ 0:run, 1:stop ]

            while tries < 10 and hits < self.on.count(True):
                tries += 1
                self._submit()

                if self._stop.wait(0.2):
                    return

                for chl, time_sum, period_num, cursor in self._pull_data(self.on, self._buffer):

                    vb = VOLT_RANGES.index(self.voltrange[chl])
                    offset = round(ADC_RANGE * self.voltoffset[chl])
                    lo = _min(offset, int(points.min()))
                    hi = _max(offset, int(points.max()))
                    amp = _max(abs(lo), abs(hi)) << 1

                    if hi >= ADC_MAX or lo <= ADC_MIN:
                        vb_new = (vb + len(VOLT_RANGES)) >> 1
                    elif amp < 16:
                        self.on[chl] = False
                        continue
                    else:
                        vb_new = _find_ge(VOLT_RANGES, amp * 1.1 * VOLT_RANGES[vb] / ADC_RANGE)
                        scale = VOLT_RANGES[vb] / VOLT_RANGES[vb_new]
                        level = _clip(round((hi + lo) / 2 * scale), -100, 100)
                        self._push(CMD.SET_EDGE_LEVEL[chl], _u16(level + 10, level))
                        self._push(CMD.SET_FREQREF[chl], _u8(level))  # freq meter

                    _log("CH%s  voltrange:%sv -> %sv  amplitude:%s"
                        , chl + 1, self.voltrange[chl], VOLT_RANGES[vb_new], amp)

                    if vb_new == vb:
                        hits += 1
                    else:
                        hits = 0
                        self.voltrange[chl] = VOLT_RANGES[vb_new]
                        self._push_channel(chl)

                    if period_num > 1 and amp > 20:
                        period = time_sum / period_num / SAMPLING_RATES[-1]
                        rate_new = SAMPLING_RATES[_find_le(SAMPLING_RATES, SAMPLES / (period * 3))]
                        if rate_new != self.sampling_rate and rate_new < rate:
                            _log("CH%s  rate:%s -> %s  period:%s"
                                , chl + 1, self.sampling_rate, rate_new, period)
                            self._push_sampling(rate_new, False, None)
                            rate = rate_new
                            hits = 0

            trg = self._send(CMD.GET_TRIGGERED, 0)
            self._push(CMD.SET_TRIGGER, (0x0000, 0x2000)[trg == 2])  # CH1 or CH2
            self._push(CMD.SET_PEAKMODE, 0)

            return self


    def calibrate(self):
        """ Auto adjust the zero offset and zero amplitude (not the gain).
        The calibration is then saved to 'VDS1022xxxxxxxx-cals.json'.
        Probes must be disconnected.
        """
        with self._lock:

            self._initialize()

            calibration = deepcopy(self.calibration)
            points = np.frombuffer(self._buffer, np.int8, SAMPLES, FRAME_SIZE - SAMPLES - 50)

            for cals in calibration[COMP]:
                cals[:] = ( _clip(x, 500 , 600) for x in cals )  # clip zero-compensation

            for cals in calibration[AMPL]:
                cals[:] = ( _clip(x, 100 , 200) for x in cals )  # clip zero-amplitude

            for vb in reversed(range(len(VOLT_RANGES))):
                if not self._calibrate(points, calibration, COMP, vb, 0, 0):
                    return False

            for vb in range(len(VOLT_RANGES)):
                if not self._calibrate(points, calibration, AMPL, vb, -100, -100):
                    return False

            self.calibration = calibration
            self._save_calibration()
            self._initialize()
            self._submit()

            _printf('Saved calibration to\n%s', self.calibration_path)


    def _calibrate(self, points, calibration, ical, vb, pos0, target):

        name = ('Gain', 'Ampl', 'Comp')[ical]
        states = tuple([ 0 ] * 4 for _ in range(CHANNELS))  # hits, steps, cal_prev, err_prev
        on = [ True ] * CHANNELS

        for chl in range(CHANNELS):
            coupling  = DC if ical == GAIN else AC
            attenuate = vb >= ATTENUATION_THRESHOLD
            chl_arg   = (attenuate & 1) << 1 | (coupling & 3) << 5 | 1 << 7
            self._push(CMD.SET_CHANNEL[chl], chl_arg)

        for i in range(10):
            for chl in range(CHANNELS):
                cal_ampl = calibration[AMPL][chl][vb]
                cal_comp = calibration[COMP][chl][vb]
                cal_gain = calibration[GAIN][chl][vb]
                zero_off = round(cal_comp - pos0 * cal_ampl / 100)
                self._push(CMD.SET_ZERO_OFF[chl], zero_off)
                self._push(CMD.SET_VOLT_GAIN[chl], cal_gain)

            self._submit()

            if self._stop.wait(0.25):
                return False

            for chl, _, _, _ in self._pull_data(on, self._buffer):
                hits, steps, cal_prev, err_prev = states[chl]

                cal   = calibration[ical][chl][vb]
                err   = float(np.mean(points)) - target
                hits  = hits + 1 if steps == 1 and abs(err) < 2 else 0
                scale = steps / _max(0.5, abs(err_prev - err)) if steps else 1

                # _log("CH%s %s %4sv  err:%+6.2f  cal:%4s  steps:%3s  scale:%3.1f" % (
                #         chl + 1, name, VOLT_RANGES[vb], err, cal, steps, scale))

                if hits < 3:
                    ceiling = steps - 1 if abs(err) < 10 else 100
                    steps = _max(1, _min(ceiling, ceil(abs(err) * scale)))
                    correction = round(copysign(steps, err if target <= 0 else -err))
                    calibration[ical][chl][vb] = cal + correction
                    states[chl][:] = hits, steps, cal, err
                else:
                    on[chl] = False  # turn off data for this channel
                    if abs(err_prev) < abs(err):
                        calibration[ical][chl][vb] = cal_prev
                    _printf("%s %4sv CH%d : %s -> %s", name, VOLT_RANGES[vb], chl + 1,
                            self.calibration[ical][chl][vb], calibration[ical][chl][vb])

            if not any(on):
                return True

        raise Exception("Failed to calibrate CH%d %s" % (chl + 1, name))



# def _signal_handler(signal, frame):
#     if VDS1022._instance:
#         VDS1022._instance.stop()
#     raise KeyboardInterrupt()


# signal.signal(signal.SIGINT, _signal_handler)
# signal.signal(signal.SIGTERM, _signal_handler)


if __name__ == '__main__':

    with VDS1022(debug=False) as dev:
        dev.calibrate()

        dev.set_timerange('20ms')
        dev.set_channel(CH1, range='10v', coupling='DC', offset=1/10, probe='x10')

        for frames in dev.fetch_iter(autorange=False):
            print('Vrms:%s' % frames.ch1.rms(), end='\r')
            time.sleep(1)
