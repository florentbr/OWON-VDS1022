#!/usr/bin/env python3

"""
This module provides an API to communicate directly with the OWON VDS1022
oscilloscope.
"""

import binascii
import cmath
import collections
import functools
import gc
import glob
import json
import logging
import os.path as path
import signal
import sys
import threading
import time

from bisect import bisect_left
from array import array
from copy import copy, deepcopy
from math import floor, ceil, log10, copysign, sqrt
from struct import Struct, pack, unpack_from

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
    'TIMERANGES',
    'VOLTRANGES',
    'EDGE', 'SLOPE', 'PULSE',
    'AUTO', 'NORMAL', 'ONCE',
    'RISE', 'FALL',
    'RISE_SUP', 'RISE_EQU', 'RISE_INF', 'FALL_SUP', 'FALL_EQU', 'FALL_INF'
)

_dir = path.dirname(__file__)
_logger = logging.getLogger('vds1022')


DEBUG = False

MACHINE_NAME = 'VDS1022'

FIRMWARE_DIR = path.normpath(_dir + r'/../fwr')

CHANNELS = 2  #: Number of channels

CH1 = 0  #: Channel 1
CH2 = 1  #: Channel 2
EXT = 2  #: External TTL input/output (Multi)

MULTI_OUT = 0  # Multi channel mode - trigger out
MULTI_PF = 1   # Multi channel mode - pass/fail out
MULTI_IN = 2   # Multi channel mode - trigger in

AC = 0   #: Coupling - Alternating Current
DC = 1   #: Coupling - Direct Current
GND = 2  #: Coupling - Ground

VOLTRANGES = (
    50E-3, 100E-3, 200E-3, 500E-3, 1, 2, 5, 10, 20, 50
)  #: Volt ranges (10 divs)

TIMERANGES = (
    50e-6, 100e-6, 200e-6, 400e-6, 1e-3, 2e-3, 4e-3, 10e-3, 20e-3, 40e-3,
    100e-3, 200e-3, 400e-3, 1, 2, 4, 10, 20, 40, 100, 200, 400, 1000, 2000
)  #: Time ranges in second for a frame (20 divs)

EDGE = 0   #: Trigger mode - Edge
VIDEO = 1  #: Trigger mode - Video
SLOPE = 2  #: Trigger mode - Slope
PULSE = 3  #: Trigger mode - Pulse

RISE = 0     #: Trigger condition - Edge Rise
FALL = -125  #: Trigger condition - Edge Fall

RISE_SUP = 0     #: Trigger condition - Pulse/Slope Rise Width >
RISE_EQU = 1     #: Trigger condition - Pulse/Slope Rise Width =
RISE_INF = 2     #: Trigger condition - Pulse/Slope Rise Width <
FALL_SUP = -125  #: Trigger condition - Pulse/Slope Fall Width >
FALL_EQU = -124  #: Trigger condition - Pulse/Slope Fall Width =
FALL_INF = -123  #: Trigger condition - Pulse/Slope Fall Width <

AUTO = 0    #: Sweep mode - Auto
NORMAL = 1  #: Sweep mode - Normal
ONCE = 2    #: Sweep mode - Once

ATTENUATION_THRESHOLD = 5  # voltbase threshold in volt to switch a relay to reduce the voltage input.
ROLLMODE_THRESHOLD = 2  # timerange threshold in second for rolling mode (slow move).

SAMPLING_RATE = 100E6  # top sampling rate (samples/seconds)
SAMPLES = 5000  # number of samples in a frame

# ADC (Analog-to-digital converter)
READ_SIZE = 5211  # read size [ 11 headers + 100 trigger samples + 5100 samples ]
ADC_SIZE = 5100   # ADC buffer size [ 50 pre samples + 5000 samples (frame) + 50 post samples ]
ADC_MAX = +125    # max sample value
ADC_MIN = -125    # min sample value
ADC_RANGE = 250   # sample range

# CALIBRATION
GAIN = 0  # Gain (correction applyed for a measured signal)
AMPL = 1  # Zero amplitude (correction applied for a 0v signal with no voltage offset)
COMP = 2  # Zero compensation (correction applied for a 0v signal with an offset voltage)
HTP_ERR = 8  # Horizontal trigger position correction

USB_VENDOR_ID = 0x5345
USB_PRODUCT_ID = 0x1234
USB_INTERFACE = 0
USB_EP_WRITE = 0x3
USB_EP_READ = 0x81
USB_TIMEOUT = 200

FLASH_SIZE = 2002


# Flash memory - 2002 bytes - little endian
#  Offset  Type        Name              Value
#  ------  ----------  ----------------  -------------------------------------------------------------------
#  0       uint16      Flash header      0x55AA  [-86, 85]
#  2       uint32      Flash version     2
#     Factory calibration
#  6       uint16[10]  CH1 Gain          for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#  26      uint16[10]  CH2 Gain          for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#  46      uint16[10]  CH1 Amplitude     for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#  66      uint16[10]  CH2 Amplitude     for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#  86      uint16[10]  CH1 Compensation  for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#  106     uint16[10]  CH2 Compensation  for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#     Registry
#  206     byte        OEM               0 or 1
#          char*       Device version    null terminated string - ASCII encoded
#          char*       Device serial     null terminated string - ASCII encoded
#          byte[100]   Localizations     0 or 1 for zh_CN, zh_TW, en, fr, es, ru, de, pl, pt_BR, it, ja, ko_KR
#          uint16      Phase fine        0-255  ???
#     User calibration (no longer used. now stored in a file)
#  1006    uint16[10]  CH1 Gain          for [ 5mV 10mV 20mV 50mV 100mv 200mv 500mv 1v 2v 5v ]
#  ...

# Command: all except GET_DATA
#   Send (little endian)
#     Offset  Size   Field
#     0       4      address
#     4       1      value size (1, 2, 4)
#     5       -      value (1, 2 or 4 bytes)
#   Receive 5 bytes
#     Offset  Size   Field
#     0       1      status char (D:68, E:69, G:71, S:83, V:86)
#     1       4      value

# Command: GET_DATA
#   Send (little endian)
#     Offset  Size  Field
#     0       4     address
#     4       1     value size (2)
#     5       1     channel 1 state ( OFF:0x04 ON:0x05 )
#     6       1     channel 2 state ( OFF:0x04 ON:0x05 )
#   Receive 5 bytes starting with 'E' if not ready
#   Receive 5211 bytes for channel 1 if ON
#     Offset  Size  Field
#     0       1     channel (CH1=0x00 CH2=0x01)
#     1       4     time_sum (used by frequency meter)
#     5       4     period_num (used by frequency meter)
#     9       2     cursor (offset from the right)
#     11      100   ADC trigger buffer (seems to be only used with high sampling rates)
#     111     5100  ADC buffer ( 50 pre + 5000 samples + 50 post )
#   Receive 5211 bytes for channel 2 if ON
#     ...

class CMD:

    class Cmd:

        def __init__(self, name, address, size, status):
            self.name    = name     #: str: command name for debug
            self.address = address  #: str: command address (4 bytes)
            self.size    = size     #: int: payload size (1 byte)
            self.status  = status   #: int: expected response status (char)

        def pack(self, value):
            try:
                if isinstance(value, bytes):
                    assert len(value) == self.size
                    return array('B', pack('<IB', self.address, self.size) + value)
                else:
                    f = (None, '<IBB', '<IBH', None, '<IBI')[self.size]
                    return array('B', pack(f, self.address, self.size, value))
            except Exception as ex:
                raise ValueError('Failed to pack %s %s' % (self.name, _hex(value))) from ex

        def log(self, arg, ret=None):
            if DEBUG:
                print("[ %s %s ] %s" % (self.name, _hex(arg), ret and _hex(ret)))


    D, E, G, S, V = 68, 69, 71, 83, 86

    READ_FLASH        =  Cmd('READ_FLASH'           , 0x01b0, 1, S)
    WRITE_FLASH       =  Cmd('WRITE_FLASH'          , 0x01a0, 1, G)
    LOAD_FPGA         =  Cmd('LOAD_FPGA'            , 0x4000, 4, D)
    GET_MACHINE       =  Cmd('GET_MACHINE'          , 0x4001, 1, V)
    GET_DATA          =  Cmd('GET_DATA'             , 0x1000, 2, S)
    GET_FPGALOADED    =  Cmd('GET_FPGALOADED'       , 0x0223, 1, E)
    SET_EMPTY         =  Cmd('SET_EMPTY'            , 0x010c, 1, S)
    GET_TRIGGERED     =  Cmd('GET_TRIGGERED'        ,   0x01, 1, S)
    GET_VIDEOTRGD     =  Cmd('GET_VIDEOTRGD'        ,   0x02, 1, S)
    SET_MULTI         =  Cmd('SET_MULTI'            ,   0x06, 2, S)
    SET_PEAKMODE      =  Cmd('SET_PEAKMODE'         ,   0x09, 1, S)
    SET_ROLLMODE      =  Cmd('SET_ROLLMODE'         ,   0x0a, 1, S)
    SET_CHL_ON        =  Cmd('SET_CHL_ON'           ,   0x0b, 1, S)
    SET_FORCETRG      =  Cmd('SET_FORCETRG'         ,   0x0c, 1, S)
    SET_PHASEFINE     =  Cmd('SET_PHASEFINE'        ,   0x18, 2, S)
    SET_TRIGGER       =  Cmd('SET_TRIGGER'          ,   0x24, 2, S)
    SET_VIDEOLINE     =  Cmd('SET_VIDEOLINE'        ,   0x32, 2, S)
    SET_MULTIFREQ     =  Cmd('SET_MULTIFREQ'        ,   0x50, 1, S)
    SET_TIMEBASE      =  Cmd('SET_TIMEBASE'         ,   0x52, 4, S)
    SET_SUF_TRG       =  Cmd('SET_SUF_TRG'          ,   0x56, 4, S)
    SET_PRE_TRG       =  Cmd('SET_PRE_TRG'          ,   0x5a, 2, S)
    SET_DEEPMEMORY    =  Cmd('SET_DEEPMEMORY'       ,   0x5c, 2, S)
    SET_RUNSTOP       =  Cmd('SET_RUNSTOP'          ,   0x61, 1, S)
    GET_DATAFINISHED  =  Cmd('GET_DATAFINISHED'     ,   0x7a, 1, S)
    GET_STOPPED       =  Cmd('GET_STOPPED'          ,   0xb1, 1, S)
    SET_CHANNEL       = (Cmd('SET_CHANNEL_CH1'      , 0x0111, 1, S),
                         Cmd('SET_CHANNEL_CH2'      , 0x0110, 1, S))
    SET_ZERO_OFF      = (Cmd('SET_ZERO_OFF_CH1'     , 0x010a, 2, S),
                         Cmd('SET_ZERO_OFF_CH2'     , 0x0108, 2, S))
    SET_VOLT_GAIN     = (Cmd('SET_VOLT_GAIN_CH1'    , 0x0116, 2, S),
                         Cmd('SET_VOLT_GAIN_CH2'    , 0x0114, 2, S))
    SET_SLOPE_THRED   = (Cmd('SET_SLOPE_THRED_CH1'  ,   0x10, 2, S),
                         Cmd('SET_SLOPE_THRED_CH2'  ,   0x12, 2, S))
    SET_EDGE_LEVEL    = (Cmd('SET_EDGE_LEVEL_CH1'   ,   0x2e, 2, S),
                         Cmd('SET_EDGE_LEVEL_CH2'   ,   0x30, 2, S))
    SET_TRG_HOLDOFF   = (Cmd('SET_TRG_HOLDOFF_CH1'  ,   0x26, 2, S),
                         Cmd('SET_TRG_HOLDOFF_CH2'  ,   0x2a, 2, S),
                         Cmd('SET_TRG_HOLDOFF_EXT'  ,   0x26, 2, S))
    SET_TRG_CDT_EQU_H = (Cmd('SET_TRG_CDT_EQU_H_CH1',   0x32, 2, S),  # FPGA < V3
                         Cmd('SET_TRG_CDT_EQU_H_CH2',   0x3a, 2, S))  # FPGA < V3
    SET_TRG_CDT_EQU_L = (Cmd('SET_TRG_CDT_EQU_L_CH1',   0x36, 2, S),  # FPGA < V3
                         Cmd('SET_TRG_CDT_EQU_L_CH2',   0x3e, 2, S))  # FPGA < V3
    SET_TRG_CDT_GL    = (Cmd('SET_TRG_CDT_GL_CH1'   ,   0x42, 2, S),  # FPGA < V3
                         Cmd('SET_TRG_CDT_GL_CH2'   ,   0x46, 2, S))  # FPGA < V3
    SET_TRG_CDT_HL    = (Cmd('SET_TRG_CDT_HL_CH1'   ,   0x44, 2, S),  # FPGA >= V3
                         Cmd('SET_TRG_CDT_HL_CH2'   ,   0x48, 2, S))  # FPGA >= V3
    SET_FREQREF       = (Cmd('SET_FREQREF_CH1'      ,   0x4a, 1, S),
                         Cmd('SET_FREQREF_CH2'      ,   0x4b, 1, S))



class _FlashIO:

    def __init__(self, data):
        self.buffer = bytearray(data)
        self.position = 0

    def seek(self, position):
        self.position = position

    def read(self, arg=None):
        if arg is None:
            # read single byte
            res = self.buffer[self.position]
            self.position += 1
            return res
        elif isinstance(arg, int):
            # read n bytes
            res = self.buffer[self.position: self.position + arg]
            self.position += arg
            return res
        elif arg is str:
            # read null terminated string
            end = self.buffer.index(0, self.position)
            txt = self.buffer[self.position: end].decode('ASCII')
            self.position = end + 1
            return txt
        else:
            # read structure
            sta = Struct(arg)
            res = sta.unpack_from(self.buffer, self.position)
            self.position += sta.size
            return res if len(res) > 1 else res[0]

    def write(self, arg, *args):
        if args:
            # write structure
            sta = Struct(arg)
            sta.pack_into(self.buffer, self.position, *args)
            self.position += sta.size
        elif isinstance(arg, str):
            # write ASCII null terminated string
            buf = arg.encode('ASCII') + b'\0'
            self.buffer[self.position: self.position + len(buf)] = buf
            self.position += len(buf)
        elif isinstance(arg, int):
            # write single byte
            self.buffer[self.position] = arg
            self.position += 1
        else:
            # write bytes
            self.buffer[self.position: self.position + len(arg)] = arg
            self.position += len(arg)



class BokehChart:

    _FORMATTER_X =\
        "var v=tick, n=-1;"\
        "if (v>=60) return ((v/60)|0)+':'+(+(100+v%60).toFixed(2)+'').substring(1);"\
        "for (; v && !(v|0); ++n) v*=1e3;"\
        "return v && +v.toPrecision(5)+('mµnp'[n]||'')+'s';"

    _FORMATTER_Y =\
        "var v=tick, n=-1;"\
        "for (; v && !(v|0); ++n) v*=1e3;"\
        "return v && +v.toPrecision(5)+('mµnp'[n]||'')+'v';"


    def __init__(self, data, opts, rollover=None):
        import bokeh.io, bokeh.plotting, bokeh.models, bokeh.models.tools

        self.xy_mode = opts.pop('xy_mode', False)

        if isinstance(data, Frames):
            if self.xy_mode:
                opts.setdefault('tools', 'pan,wheel_zoom,zoom_in,zoom_out,box_zoom,save,reset')
                opts.setdefault('active_multi', 'box_zoom')
                opts.setdefault('width', 250)
                opts.setdefault('height', 250)
                opts.setdefault('xlabel', data[0].name)
                opts.setdefault('ylabel', data[1].name)
                lines = [{'name': 'XY',
                          'x'   : data[0].y(),
                          'y'   : data[1].y(),
                          'xlim': data[0].ylim,
                          'ylim': data[1].ylim }]
            else:
                lines = data.to_dict()
        else:
            lines = data

        labels = opts.pop('label', [ line['name'] for line in lines ])

        opts.setdefault('frame_width', opts.pop('width', 600))
        opts.setdefault('frame_height', opts.pop('height', 250))
        opts.setdefault('lod_interval', 0)
        opts.setdefault('x_axis_label', opts.pop('xlabel', None))
        opts.setdefault('y_axis_label', opts.pop('ylabel', None))
        opts.setdefault('color', ('#1f77b4', '#ff7f0e'))
        opts.setdefault('active_inspect', None)
        opts.setdefault('active_drag', None)
        opts.setdefault('active_multi', 'xbox_zoom')
        opts.setdefault('tools', 'xpan,xwheel_zoom,xzoom_in,xzoom_out,xbox_zoom,save,reset')
        opts.setdefault('legend_label', labels)
        opts.setdefault('output_backend', 'canvas')  # webgl or canvas

        axe_kw = set('alpha,color,muted,visible,legend_field,legend_group,legend_label'.split(','))
        fig_opts = { k:v for k,v in opts.items() if not (k in axe_kw or k.startswith('line_')) }
        axe_opts = [ { k:v[i] for k,v in opts.items() if k not in fig_opts }
                     for i in range(len(lines)) ]

        p = bokeh.plotting.Figure(**fig_opts)
        p.grid.grid_line_alpha = 0.5
        p.toolbar.logo = None

        ds = bokeh.models.ColumnDataSource(data={})
        y_range_name = 'default'
        y_range = p.y_range

        for i, line in enumerate(lines):
            xs = line['x']
            ys = line['y']
            xlim = line.get('xlim')
            ylim = line.get('ylim')
            if not hasattr(xs, '__len__'): xs = [ xs ]
            if not hasattr(ys, '__len__'): ys = [ ys ]
            ds.data['x'] = xs
            ds.data[labels[i]] = ys

            if not xlim:
                xlim = (xs[0] - 1e-9, xs[-1] + 1e-9) if len(xs) > 1 else (0, None)
            p.x_range.start, p.x_range.end = p.x_range.bounds = xlim

            if ylim:
                if i > 0 and (y_range.start != ylim[0] or y_range.end != ylim[1]):
                    y_range_name = 'y_range_' + str(i)
                    y_range = p.extra_y_ranges[y_range_name] = bokeh.models.DataRange1d()
                    p.add_layout(bokeh.models.LinearAxis(y_range_name=y_range_name), 'right')
                y_range.start, y_range.end = ylim

            pl = p.line('x', labels[i], source=ds, y_range_name=y_range_name, **axe_opts[i])
            y_range.renderers += (pl,)

        for ax in p.xaxis:
            ax.minor_tick_line_color = None
            ax.ticker.desired_num_ticks = 10
            code = (self._FORMATTER_X, self._FORMATTER_Y)[self.xy_mode]
            ax.formatter = bokeh.models.FuncTickFormatter(code=code)

        for ax in p.yaxis:
            ax.minor_tick_line_color = None
            ax.ticker.desired_num_ticks = 10
            ax.formatter = bokeh.models.FuncTickFormatter(code=self._FORMATTER_Y)

        lg = p.legend[0]
        lg.location = 'left'
        lg.click_policy = 'hide'
        lg.orientation = 'horizontal'
        lg.margin = 0
        lg.padding = 2
        lg.spacing = 30
        lg.border_line_width = 0
        p.add_layout(lg, 'above')

        p.select(type=bokeh.models.ZoomInTool).factor = 0.5
        p.select(type=bokeh.models.ZoomOutTool).factor = 1
        p.select(type=bokeh.models.ZoomOutTool).maintain_focus = False
        p.select(type=bokeh.models.WheelZoomTool).maintain_focus = False

        self.figure = p
        self.handle = None
        self.rollover = rollover


    def __call__(self, source):
        self.update(source)


    def show(self):
        import bokeh.io

        if _is_notebook():
            bokeh.io.output_notebook(hide_banner=True)
            self.handle = bokeh.io.show(self.figure, notebook_handle=True)
        else:
            self.handle = bokeh.io.show(self.figure)

        return self


    def update(self, source):
        import bokeh.io
        renderers = self.figure.renderers

        if isinstance(source, Frames):
            if self.xy_mode:
                data = { 'x': source.CH1.y(), renderers[0].glyph.y: source.CH2.y() }
            else:
                data = { 'x': source.x() }
                for i, frame in enumerate(source):
                    data[renderers[i].glyph.y] = frame.y()

        elif isinstance(source, list):
            xs = source[0]['x']
            data = { 'x': xs if hasattr(xs, '__len__') else [ xs ] }
            for i, line in enumerate(source):
                ys = line['y']
                data[renderers[i].glyph.y] = ys if hasattr(ys, '__len__') else [ ys ]

        elif type(source).__name__ == 'DataFrame':
            data = { 'x': source.index.to_numpy(dtype=np.float32) }
            for i, col in enumerate(source):
                data[renderers[i].glyph.y] = source[col].to_numpy(dtype=np.float32)

        else:
            raise ValueError("Invalid argument source")

        if 0 < len(data['x']) < 10:
            renderers[0].data_source.stream(data, self.rollover)
        else:
            renderers[0].data_source.data = data

        # TODO: rollover range
        # if self.rollover is not None and len(ds.data['x']) >= self.rollover:
        #     xr = self.figure.x_range
        #     x0 = ds.data['x'][0]
        #     xr.update(start=x0, end=None, bounds=(x0, None) )

        assert self.handle is not None
        bokeh.io.push_notebook(handle=self.handle)



class MatplotlibChart:


    def __init__(self, lines, opts):
        import matplotlib.pyplot as plt

        xy_mode = opts.pop('xy_mode', False)

        if isinstance(lines, Frames):
            if xy_mode:
                opts.setdefault('width', 300)
                opts.setdefault('height', 300)
                opts.setdefault('xlabel', lines[0].name)
                opts.setdefault('ylabel', lines[1].name)
                lines = [{'name': 'XY',
                          'x'   : lines[0].y(),
                          'y'   : lines[1].y(),
                          'xlim': lines[0].ylim,
                          'ylim': lines[1].ylim }]
            else:
                lines = lines.to_dict()

        labels = opts.pop('legend_label', tuple(line['name'] for line in lines))

        width = opts.pop('width', 700)
        height = opts.pop('height', 300)
        xlabel = opts.pop('xlabel', None)
        ylabel = opts.pop('ylabel', None)
        title = opts.pop('title', None)
        opts.setdefault('label', labels)
        opts.setdefault('color', ('#1f77b4', '#ff7f0e'))
        opts.setdefault('alpha', (0.8, 0.8))

        axe_kw = set('alpha,color,label,fmt'.split(','))
        fig_opts = { k:v for k,v in opts.items() if k not in axe_kw }
        axe_opts = [ { k:v[i] for k,v in opts.items() if k not in fig_opts }
                     for i in range(len(lines)) ]

        def format_time(x, pos):
            n = 0
            while x and not int(x):
                x *= 1e3
                n += 1
            return '{0:g}{1}s'.format(round(x, 4), ' mµnp'[n] if n else '') if x else '0'

        def format_volt(x, pos):
            n = 0
            while x and not int(x):
                x *= 1e3
                n += 1
            return '{0:g}{1}v'.format(round(x, 4), ' mµnp'[n] if n else '') if x else '0'

        dpi = plt.rcParams['figure.dpi']
        fig = plt.figure(figsize=(width / dpi, height / dpi), **fig_opts)
        ax = fig.add_subplot(111)

        ax.grid(True, which='major', linestyle='-', alpha=0.5)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

        for i, line in enumerate(lines):
            xs = line.get('x')
            ys = line.get('y')
            if not hasattr(xs, '__len__'): xs = [ xs ]
            if not hasattr(ys, '__len__'): ys = [ ys ]

            xlim = line.get('xlim')
            if xlim:
                ax.set_xlim(*xlim)
            elif len(xs) > 1:
                ax.set_xlim(_to_precision(xs[0], 5), _to_precision(xs[-1], 5))

            ylim = line.get('ylim')
            if ylim:
                if i > 0 and ax.get_ylim() != tuple(ylim):
                    ax = ax.twinx()
                ax.set_ylim(*ylim)

            ax.xaxis.set_major_locator(plt.MaxNLocator(10))
            ax.xaxis.set_major_formatter((format_time, format_volt)[xy_mode])
            ax.yaxis.set_major_locator(plt.MaxNLocator(10))
            ax.yaxis.set_major_formatter(format_volt)
            # ax.minorticks_on()
            ax.plot(xs, ys, **axe_opts[i])

        axlines = [ ln for ax in fig.axes for ln in ax.lines ]
        fig.axes[0].legend(handles=axlines, loc='upper left', bbox_to_anchor=(0, 1.1), ncol=2, frameon=False)

        plt.title(title)


    def show(self):
        return self



class _parse:

    SYMBOLS_RATIO = { 'm': 1e-3, 'u': 1e-6, 'n': 1e-9 }

    def _try_parse(f):
        @functools.wraps(f)
        def wrapper(**kwargs):
            for k, v in kwargs.items():
                try:
                    if isinstance(v, str):
                        return f(v)
                    return v
                except Exception as ex:
                    raise ValueError('Invalid argument %s=%s' % (k, v)) from ex
        return wrapper

    @_try_parse
    def constant(arg):
        assert arg in __all__
        return globals()[arg]

    @_try_parse
    def ratio(arg):
        return float(arg.replace('%', 'e-2'))

    @_try_parse
    def factor(arg):
        return float(arg.strip('xX'))

    @_try_parse
    def seconds(arg):
        txt = arg.strip('sS')
        r = _parse.SYMBOLS_RATIO.get(txt[-1])
        return float(txt[:-1]) * r if r else float(txt)

    @_try_parse
    def volts(arg):
        txt = arg.strip('vV')
        r = _parse.SYMBOLS_RATIO.get(txt[-1])
        return float(txt[:-1]) * r if r else float(txt)



def _clip(value, lower, upper):
    # Clips a value to lower/upper edges
    return lower if value < lower else upper if value > upper else value


def _hex(arg):
    if hasattr(arg, '__iter__'):
        return ' '.join(map(hex, arg))
    return hex(arg)


def _aslist(arg):
    if isinstance(arg, (list, tuple)):
        return arg
    return (arg, )


def _to_precision(x, n):
    return round(x, -int(floor(log10(abs(x or 1)))) + (n - 1))


def _iexp10(value, limit):
    # To unsigned integer mantissa and base-10 exponent.
    m, e = value, 0
    while m > limit:
        m /= 10.0
        e += 1
    return round(m), e


def _print_calibration(calibration):
    for i, name in enumerate(('Gain', 'Ampl', 'Comp')):
        for chl in range(CHANNELS):
            values = ' '.join(map(str, calibration[i][chl]))
            print(' * %s CH%s: %s' % (name, chl + 1, values))


def _is_notebook():
    try:
        return get_ipython().__class__.__name__ == 'ZMQInteractiveShell'
    except NameError:
        return False



class Frame:
    """ Hold the samples for an input channel. """

    def __init__(self, device, channel, buffer, offset, translate, frequency):
        voltrange = device.voltrange[channel] * device.proberatio[channel]
        self.buffer = buffer  # array('b'): ADC 8 bits raw samples
        self.offset = offset  # int: Start index in the buffer
        self.channel = channel  #: int: `CH1` or `CH2`
        self.frequency = frequency  #: float: Signal frequency (Hz).
        self.sx = 1 / device.sampling_rate  # float: X scale, seconds per ADC sample
        self.sy = voltrange / ADC_RANGE     # float: Y scale, volts per ADC sample
        self.tx = translate / device.sampling_rate         # float: X translate, seconds
        self.ty = voltrange * -device.voltoffset[channel]  # float: Y translate, volts


    @property
    def _points(self):
        return np.frombuffer(self.buffer, 'b', offset=self.offset)


    @property
    def count(self):
        """ int: number of samples . """
        return len(self.buffer) - self.offset


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
        return self.tx, self.tx + (self.count - 1) * self.sx


    def x(self):
        """
        Returns:
            numpy.ndarray: 1D Numpy array of x values in second.
        """
        num = len(self.buffer) - self.offset
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
        ys = self._points.clip(ADC_MIN, ADC_MAX) * np.float32(self.sy)
        if abs(self.ty) > 1e-3:
            ys += np.float32(self.ty)
        return ys


    def xy(self):
        """
        Returns:
            tuple: Two 1D Numpy arrays of x and y values in second and volt ( xs, ys ) .
        """
        return ( self.x(), self.y() )


    def percentile(self, *q):
        """
        Args:
            q (float): Percentiles between 0 and 100 inclusive.
        Returns:
            tuple: Voltage for each given percentile.
        """
        values = np.percentile(self._points, q)
        return tuple(float(v.clip(ADC_MIN, ADC_MAX)) * self.sy + self.ty for v in values)


    def median(self):
        """
        Returns:
            float: Median voltage.
        """
        v = float(np.median(self._points).clip(ADC_MIN, ADC_MAX))
        return round(v * self.sy + self.ty, 3)


    def min(self):
        """
        Returns:
            float: Minimum voltage.
        """
        v = float(self._points.min().clip(ADC_MIN, ADC_MAX))
        return round(v * self.sy + self.ty, 3)


    def max(self):
        """
        Returns:
            float: Maximum voltage.
        """
        v = float(self._points.max().clip(ADC_MIN, ADC_MAX))
        return round(v * self.sy + self.ty, 3)


    def mean(self):
        """
        Returns:
            float: Average voltage.
        """
        v = float(self._points.mean().clip(ADC_MIN, ADC_MAX))
        return round(v * self.sy + self.ty, 3)


    def rms(self):
        """
        Returns:
            float: RMS voltage.
        """
        ys = self._points
        if abs(self.ty) > 1e-3:
            ys = ys + np.float32(self.ty / self.sy)
        return round(sqrt(np.square(ys, dtype=np.float32).mean()) * self.sy, 3)


    def std(self):
        """
        Returns:
            float: Standard deviation.
        """
        ys = self._points
        if abs(self.ty) > 1e-3:
            ys = ys + np.float32(self.ty / self.sy)
        return round(ys.std() * self.sy, 3)


    def levels(self):
        """
        Returns:
            tuple: Vbase, Vtop.
        """
        points = self._points + 128
        counts = np.bincount(points, minlength=256)
        i = int(points.mean() + 0.5)
        v0 = _clip(np.argmax(counts[:i + 1]) - 128, -125, 125)
        v1 = _clip(np.argmax(counts[i:]) + i - 128, -125, 125)
        lower = round(v0 * self.sy + self.ty, 3)
        upper = round(v1 * self.sy + self.ty, 3)
        return lower, upper


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
            | Frequence : Frequence (hertz)
            | Phase     : Phase shift (radian)

        Returns:
            `DataFrame`
        """
        import pandas

        y = self.y()
        vmin = round(y.min(), 3)
        vmax = round(y.max(), 3)
        vpp  = vmax - vmin
        vavg = round(y.mean(), 3)
        vrms = round(sqrt(np.square(y, dtype=np.float32).mean()), 3)
        vbase, vtop = self.levels()
        vamp = vtop - vbase

        if vamp / (ADC_RANGE * self.sy) > 0.05 :
            yf = np.fft.rfft(y - vavg)
            i = np.absolute(yf).argmax()
            freq = i / ((len(self.buffer) - self.offset) * self.sx)
            phi = cmath.phase(yf[i]) + np.pi * (1.5 - sum(self.xlim) * freq)
            phase = round(cmath.phase(cmath.rect(1, phi)), 2)
            period = 1 / freq
        else:
            period = freq = phase = 0

        k = 'Count Vavg Vrms Vamp Vbase Vtop Vpp Vmin Vmax Period Frequency Phase'.split(' ')
        v = [ self.count, vavg, vrms, vamp, vbase, vtop, vpp, vmin, vmax, period, freq, phase ]
        return pandas.DataFrame({ self.name: v }, index=k)



class Frames(tuple):
    """ Holds the channels frame (`Frame` `CH1`, `Frame` `CH2`) .

    Examples:
        >>> ch1, ch2 = frames  # destructuring
        >>> ch1 = frames[CH1]  # by index
        >>> ch1 = frames.CH1   # by attribute
    """

    def __new__(cls, frames, pulltime):
        return tuple.__new__(cls, frames)


    def __init__(self, frames, pulltime):
        self.time = pulltime   #: float: Acquisition time in second


    def __repr__(self):
        return repr(self.to_dataframe())


    def __iter__(self):
        return ( f for f in tuple.__iter__(self) if f )


    def _repr_html_(self):
        return self.to_dataframe()._repr_html_()


    @property
    def CH1(self):
        return self[0]


    @property
    def CH2(self):
        return self[1]


    @property
    def ylim(self):
        """ tuple: (Lower limit, Upper limit) of all frames . """
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
            tuple: 1D Numpy arrays of x and y values: ( xs, ( ys or None, ys or None ) ) .
        """
        return self.x(), self.y()


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
            | Frequence : Frequence (hertz)
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
            BokehChart(self, kwargs).show()
        elif backend == 'matplotlib':
            MatplotlibChart(self, kwargs).show()
        else:
            return self.to_dataframe().plot(backend=backend, **kwargs)


    def to_dataframe(self):
        """
        Returns:
            pandas.DataFrame: x and y values for each enabled channel: { 'CHx':ys, ... }, index=xs
        """
        import pandas
        xs = self.x()
        ys = { f.name:f.y() for f in self }
        df = pandas.DataFrame(ys, pandas.Float64Index(xs, copy=False), copy=False)
        # TODO cutom plot on dataframe
        # df.plot = types.MethodType(plot, df)
        return df


    def to_dict(self):
        """
        Returns:
            list: [ { name:'CH1', x:[...], y:[...], ylim:(low, high) }, ... ]
        """
        xs = self.x()
        items = [ { 'name':f.name, 'x':xs, 'y':f.y(), 'ylim':f.ylim } for f in self ]
        return items


    @classmethod
    def concat(cls, items):
        """ Concatenate multiple frames

        Args:
            items (`Frames` ): List of `Frames`
        Returns:
            `Frames`
        """
        frameset = items[0]
        frames = [ copy(frame) for frame in tuple.__iter__(frameset) ]
        for frame in frames:
            if frame:
                frame.buffer = np.concatenate([ fs[frame.channel].buffer for fs in items ])
        return cls(frames, frameset.time)



class Stream:

    def __init__(self, source):
        self._source = source
        self._root = self
        self._parent = None
        self._nodes = []
        self._thread = threading.Thread(target=self._run, daemon=True)


    def _run(self):
        for data in self._source:
            self._emit(data)


    def _new_node(self, func):
        node = self.__new__(type(self))
        node._func = func
        node._root = self._root
        node._parent = self
        node._nodes = []
        self._nodes.append(node)
        return node


    def _emit(self, data):
        for stream in self._nodes:
            new_data = stream._func(data)
            stream._emit(new_data)


    def _next(self):
        if self is self._root:
            return next(self._source)
        return self._func(self._parent._next())


    def map(self, func):
        """ Chain a function to apply on the data.

        Args:
            func (function)
        Returns:
            `Stream`
        """
        return self._new_node(func)


    def agg(self, func):
        """ Chain an aggregate function to process y values.

        Args:
            func (str, function): Either 'rms', 'mean', 'min', 'max' or function.
        Returns:
            `Stream`
        """
        if isinstance(func, str):
            func = getattr(Frame, func)

        def agg_frames(frames):
            return [ { 'name': f.name,
                       'x'   : [ frames.time ],
                       'y'   : [ func(f) ],
                       'ylim': f.ylim
                     } for f in frames ]

        return self._new_node(agg_frames)


    def sink(self, func):
        """ Start the source and apply a function on every input.

        Args:
            func (function): Function to apply.
        """
        self._new_node(func)
        if not self._root._thread.is_alive():
            self._root._thread.start()


    def plot(self, /, rollover=None, **kwargs):
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
        data = self._next()
        chart = BokehChart(data, kwargs, rollover)
        self.sink(chart)
        return chart.show()


    def to_dataframe(self):
        """ To pandas DataFrame .
        See https://streamz.readthedocs.io/en/latest/dataframes.html

        Returns:
            `streamz.DataFrame`
        """
        import pandas
        import streamz

        def to_dataframe(data):
            if isinstance(data, pandas.DataFrame):
                return data
            elif isinstance(data, Frames):
                return Frames.to_dataframe(data)
            else:
                xs = next(entry for entry in data)['x']
                ys = { entry['name']: entry['y'] for entry in data }
                df = pandas.DataFrame(ys, pandas.Float64Index(xs, copy=False), copy=False)
                return df

        stream = streamz.Stream()
        df = to_dataframe(self._next())
        sdf = stream.to_dataframe(example=df)
        stream.emit(df)

        self._new_node(to_dataframe).sink(stream.emit)
        return sdf



class VDS1022:
    """ Connect to the device (singleton).

    Args:
        firmware (str): Optional, firmware location. Defaults to ``None``.
        debug   (bool): Optional, to monitor the commands. Defaults to ``False``.
    """

    _instance = None


    def __new__(cls, firmware=None, debug=False):
        self = cls._instance

        if self is None or not self.stop():
            self = cls._instance = object.__new__(cls)
            self._handle = None

        return self


    def __init__(self, firmware=None, debug=False):
        global DEBUG
        DEBUG = bool(debug)
        # logging.basicConfig(level="DEBUG")

        if self._handle:
            self._initialize()
            return

        # Device config from flash memory. Updated by _load_flash
        self.oem = None
        self.version = None  #: str: Hardware version.
        self.serial = None  #: str: Hardware serial.
        self.locales = None
        self.phasefine = None
        self.firmware = None  # firmware version number

        # Calibration from local file 'VDS1022xxxxxxxx.json' or flash memory
        self.calibration = None

        # USB
        self._usb = None
        self._handle = None
        self._failures = 0
        self._writetime = 0
        self._buffer = array('B', bytes(6000))

        # Synchronization / waiter
        self._lock = threading.Lock()
        self._stop = threading.Event()

        # Pending commands
        self._queue = collections.OrderedDict()

        # initialize device
        self._connect()
        self._load_flash()
        self._load_calibration()
        self._load_fpga(firmware or FIRMWARE_DIR)
        self._initialize()

        # Background thread to keep the USB connexion alive

        def run():
            while self._handle:
                lastwrite = self._writetime

                if self._stop.wait(3):
                    time.sleep(0.01)
                    continue

                if self._writetime == lastwrite:
                    try:
                        with self._lock:
                            self._send(CMD.GET_MACHINE, CMD.V)
                    except USBError:
                        _logger.error('Lost connection to device.')
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

        # default settings        CH1   CH2
        self.on               = [ False, False ]  # channel 1 on/off state, channel 2 on/off state
        self.coupling         = [ DC   , DC    ]  # DC: direct current, AC: Alternating Current
        self.voltrange        = [ 5    , 5     ]  # 5 volts for 10 divisions (doesn't account for the probe rate)
        self.voltoffset       = [ 0    , 0     ]  # ratio of vertical range from -0.5 to +0.5 ( -0.1 = -1div )
        self.proberatio       = [ 10   , 10    ]  # ratio of probe
        self.trigger_position = 0.5    # trigger position in a frame from 0 to 1.
        self.timerange        = 0.02   # time in second for a captured frame of 5000 samples
        self.sampling_rate    = 0      # calculated from timerange
        self.rollmode         = False  # auto-activates if timerange >= ROLLMODE_THRESHOLD
        self.sweepmode        = None   # trigger sweep mode. AUTO, NORMAL, ONCE

        self._push(CMD.SET_PHASEFINE, self.phasefine)  # ???
        self._push(CMD.SET_PEAKMODE, 0)  # [ 0:off  1:on ]
        self._push(CMD.SET_PRE_TRG, (ADC_SIZE >> 1) - HTP_ERR)  # pre-trigger size
        self._push(CMD.SET_SUF_TRG, (ADC_SIZE >> 1) + HTP_ERR)  # post-trigger size
        self._push(CMD.SET_MULTI, MULTI_IN)  # [ 0:Out  1:PassFail  2:In ]
        self._push(CMD.SET_TRIGGER, 1)  # MULTI_IN

        self._push_timerange(self.timerange, self.rollmode)

        for chl in range(CHANNELS):
            self._send(CMD.SET_EDGE_LEVEL[chl], 0x807f)  # 127,-128 to disable triggering while setting levels
            self._push_channel(chl)


    def stop(self):
        """ Stop all operations.

        Returns:
            bool: `True` if succeed, `False` otherwise.
        """

        if self._handle is None:
            return False

        self._stop.set()

        with self._lock:
            self._queue.clear()
            try:
                self._bulk_send(CMD.SET_RUNSTOP, 1)  # [ 0:run 1:stop ]
                self._stop.clear()
                return True
            except USBError:
                _logger.error("Stop command failed")

        self._release()
        return False


    def dispose(self):
        """ Disconnect and release the device. """
        self._stop.set()
        self._queue.clear()
        self._release()


    def _connect(self):
        _usb = self._usb = libusb1.get_backend() or libusb0.get_backend()

        for dev in _usb.enumerate_devices():
            desc = _usb.get_device_descriptor(dev)

            if desc.idVendor == USB_VENDOR_ID and desc.idProduct == USB_PRODUCT_ID:
                _handle = self._handle = _usb.open_device(dev)
                _usb.claim_interface(_handle, USB_INTERFACE)
                _usb.clear_halt(_handle, USB_EP_WRITE)
                _usb.clear_halt(_handle, USB_EP_READ)

                if self._send(CMD.GET_MACHINE, CMD.V) == 1:  # 0:Error 1:VDS1022 3:VDS2052
                    return True

                _usb.release_interface(_handle, USB_INTERFACE)
                _usb.close_device(_handle)
                self._handle = None

        raise USBError("USB device %s not found" % MACHINE_NAME)


    def _release(self):
        if self._handle:
            try:
                self._usb.release_interface(self._handle, USB_INTERFACE)
            except:
                pass
            try:
                self._usb.close_device(self._handle)
            except:
                pass
            self._handle = None
            self._usb = None


    def _bulk_write(self, buffer):
        self._usb.bulk_write(self._handle, USB_EP_WRITE, USB_INTERFACE, buffer, USB_TIMEOUT)
        self._writetime = time.perf_counter()


    def _bulk_read(self, buffer, size=None):
        ret = self._usb.bulk_read(self._handle, USB_EP_READ, USB_INTERFACE, buffer, USB_TIMEOUT)
        assert size is None or ret == size, "Expected response length of %s, got %d" % (size, ret)
        self._failures = 0
        return ret


    def _bulk_send(self, cmd, arg):
        self._bulk_write(cmd.pack(arg))
        self._bulk_read(self._buffer, 5)
        status, value = unpack_from('<BI', self._buffer)
        cmd.log(arg, value)
        assert status == cmd.status, "Unexpected response status: " + chr(status)
        return value


    def _send(self, cmd, arg):
        while True:
            try:
                return self._bulk_send(cmd, arg)
            except USBError as ex:
                self._on_usb_err(ex, cmd, arg)


    def _on_usb_err(self, ex, cmd, arg):
        self._failures += 1
        print("USB timeout")
        if self._failures > 2:
            raise ex
        self._stop.wait(0.01 * self._failures)


    def _push(self, cmd, arg=0):
        self._queue.pop(cmd, None)  # remove the command if already in queue
        self._queue[cmd] = arg


    def _submit(self):
        while self._queue:
            self._send(*self._queue.popitem(False))


    def _halt(self):
        self._stop.set()
        with self._lock:
            self._stop.clear()


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
            self._submit()
            return self._send(cmd, arg)


    def wait(self, seconds):
        """ Suspend execution for the given number of seconds.

        Args:
            seconds (float)
        """
        with self._lock:
            self._submit()
        if self._lock.wait(seconds):
            raise KeyboardInterrupt()


    def _load_calibration(self, fname=None):
        if fname is None:
            fname = _dir + path.sep + self.serial + '-cals.json'

        for fpath in glob.glob(fname):
            with open(fpath, 'r') as f:
                self.calibration = json.load(f)['cals']
                if DEBUG:
                    print("Load " + path.basename(fname))
                    _print_calibration(self.calibration)
                return

        self._save_calibration()


    def _save_calibration(self, fname=None):
        if fname is None:
            fname = _dir + path.sep + self.serial + '-cals.json'

        with open(fname, 'w') as f:
            json.dump({'cals': self.calibration}, f, indent=4)


    def read_flash(self):
        """ Return a dump of the device flash memory.

        Returns:
            array('B'): array of unsigned bytes
        """
        self._bulk_write(CMD.READ_FLASH.pack(1))
        self._bulk_read(self._buffer, FLASH_SIZE)
        CMD.READ_FLASH.log(1, FLASH_SIZE)
        return self._buffer[:FLASH_SIZE]


    def write_flash(self, source):
        """ Overwrite the device flash memory with data from a file or array of bytes.

        Args:
            source (str or bytes): File path or bytes.
        """

        if isinstance(source, str):
            with open(source, 'rb') as f:
                return self.write_flash(f.read())

        buffer = array('B', source)
        assert len(buffer) == FLASH_SIZE, "Bad flash size. Expected: %d bytes" % FLASH_SIZE
        assert buffer[0] == 0xAA and buffer[1] == 0x55, "Bad flash header. Expected: 0xAA 0x55"
        assert self._send(CMD.GET_FPGALOADED, 0) == 1, "Firmware not loaded"

        buffer[0] = 0x55
        buffer[1] = 0xAA
        self._send(CMD.WRITE_FLASH, 1)
        self._bulk_write(buffer)  # fails if the FPGA is not loaded
        self._bulk_read(buffer, 5)
        assert buffer[0] == CMD.S, "Bad response status: " + chr(buffer[0])


    def save_flash(self, fname=None):
        """ Save the device flash memory to a file.

        Args:
            fname (str): Optional, output file name. Defaults to local file.
        """
        if fname is None:
            fname = '%s-FLASH-%s.bin' % (self.serial or MACHINE_NAME, int(time.time()))

        print("Save flash memory to " + fname)
        with open(fname, 'wb') as f:
            f.write(self.read_flash())


    def _load_flash(self):

        reader = _FlashIO(self.read_flash())

        header, version = reader.read('<HI')
        assert header == 0x55AA, "Bad flash header %d" % header
        assert version == 2, "Bad flash version %d" % version

        reader.seek(6)
        self.calibration = [ [ list(reader.read('<10H')) for ch in range(CHANNELS) ]
                             for i in (GAIN, AMPL, COMP) ]
        reader.seek(206)
        self.oem       = reader.read()          # 1
        self.version   = reader.read(str)       # V2.5
        self.serial    = reader.read(str)       # VDS1022I1809215
        self.locales   = reader.read(100)[:12]  # 1 1 1 1 1 1 1 1 1 1 1 1
        self.phasefine = reader.read('<H')      # 0

        ver = self.version.upper()
        assert ver.startswith('V'), "Invalid version from flash: %s" % self.version

        if ver.startswith('V4'):
            self.firmware = 4
        elif ver.startswith('V3') or ver == 'V2.7.0':
            self.firmware = 3
        elif ver in ('V2.4.623', 'V2.6.0'):
            self.firmware = 2
        else:
            self.firmware = 1

        if DEBUG:
            crc32 = binascii.crc32(reader.buffer[2:]) & 0xFFFFFFFF
            print(" oem=%s version=%s serial=%s phasefine=%s crc32=%08X" % (
                    self.oem, self.version, self.serial, self.phasefine, crc32))
            _print_calibration(self.calibration)


    def sync_flash(self):
        """ Overwrite the device flash memory with the info and calibration
        of this instance.
        """

        writer = _FlashIO(b'\xff' * FLASH_SIZE)
        writer.write('<HI', 0x55AA, 2)

        writer.seek(6)
        for i in (GAIN, AMPL, COMP):
            for chl in range(CHANNELS):
                writer.write('<10H', *self.calibration[i][chl])

        writer.seek(206)
        writer.write(self.oem)
        writer.write(self.version.upper())
        writer.write(self.serial.upper())
        writer.write(bytes(self.locales) + b'\xff' * (100 - len(self.locales)))
        writer.write('<H', self.phasefine)

        self.write_flash(writer.buffer)


    def _load_fpga(self, source):

        if self._send(CMD.GET_FPGALOADED, 0) == 1:  # 0:Missing  1:Loaded
            return

        if path.isdir(source):
            source = path.join(source, 'VDS1022_FPGAV%s_*.bin' % self.firmware)

        paths = glob.glob(source)
        assert paths, 'Firmware not found at %s' % source

        with open(paths[-1], 'rb') as f:
            dump = f.read()

        if DEBUG:
            crc32 = binascii.crc32(dump) & 0xFFFFFFFF
            print("Load firmware %s (CRC32=%08X)" % (path.basename(paths[-1]), crc32))

        header = Struct('<I')
        size = self._send(CMD.LOAD_FPGA, len(dump)) - header.size
        count = ceil(len(dump) / size)

        for i in range(count):
            print(" loading firmware part %s/%s" % (i + 1, count), end='\r')
            buffer = header.pack(i) + dump[i * size: i * size + size]
            self._bulk_write(array('B', buffer))
            self._bulk_read(self._buffer, 5)
            status, value = unpack_from('<BI', self._buffer)
            assert status == CMD.S, "Bad response status: " + chr(status)
            assert value == i, "Bad response chunk id. Expected %s, got %s" % (i, value)

        print(' ' * 50, end='\r')


    def set_channel(self, channel, coupling, range, offset=0, probe=1, on=True):
        """ Configure a channel.

        Args:
            channel  (int, str): Channel: `CH1`, `CH2`
            coupling (int, str): Coupling: `DC`, `AC`, `GND`
            range    (int, str): Volt range for 10 divs from `VOLTRANGES`
            offset      (float): Optional volt offset [-0.5 to 0.5]. Defaults to ``0``.
            probe    (int, str): Optional probe ratio (ex: 10 or 'x10'). Defaults to ``1``.
            on           (bool): Optional, turn on/off the channel. Defaults to ``True``
        """

        chl      = _parse.constant(channel=channel)
        coupling = _parse.constant(coupling=coupling)
        range    = _parse.volts(range=range)
        offset   = _parse.ratio(offset=offset)
        probe    = _parse.factor(probe=probe)

        voltrange = VOLTRANGES[bisect_left(VOLTRANGES, round(range, 3))]
        if voltrange != range:
            print("Volt range %sV not available - selected %sV instead." % (range, voltrange))

        assert -0.5 <= offset <= 0.5, "Parameter offset out of range: %s" % offset

        self.on[chl] = bool(on)
        self.coupling[chl] = coupling
        self.voltrange[chl] = voltrange
        self.voltoffset[chl] = offset
        self.proberatio[chl] = probe

        self._push_channel(chl)


    def _push_channel(self, chl):

        vb = VOLTRANGES.index(self.voltrange[chl])
        pos0 = ADC_RANGE * self.voltoffset[chl]
        attenuate = self.voltrange[chl] >= ATTENUATION_THRESHOLD
        cal_comp = self.calibration[COMP][chl][vb]
        cal_ampl = self.calibration[AMPL][chl][vb]
        cal_gain = self.calibration[GAIN][chl][vb]

        zero_arg = _clip(round(cal_comp - pos0 * cal_ampl / 100), 0, 4095)
        self._push(CMD.SET_ZERO_OFF[chl], zero_arg)

        gain_arg = _clip(cal_gain, 0, 4095)
        self._push(CMD.SET_VOLT_GAIN[chl], gain_arg)

        # SET_CHANNEL
        #  b0  : not defined [ 0 ]
        #  b1  : input attenuation [ 0:OFF 1:ON ] (relay to reduce the input voltage)
        #  b2-3: bandwidth limit [ 0 ]
        #  b4  : not defined [ 0 ]
        #  b5-6: channel coupling [ 0:DC 1:AC 2:GND ]
        #  b7  : channel on/off [ 0:OFF 1:ON ]
        chl_arg = attenuate << 1 | self.coupling[chl] << 5 | self.on[chl] << 7
        self._push(CMD.SET_CHANNEL[chl], chl_arg)

        # SET_CHL_ON
        #  b0: bit 0 = CH1 [0=OFF 1=ON],  bit 1 = CH2 [0=OFF 1=ON]
        on_arg = sum(on << i for i, on in enumerate(self.on))
        self._push(CMD.SET_CHL_ON, on_arg)


    def set_channel_ext(self, state):
        """ Set the output TTL state of the multi channel EXT.

        Args:
            state (int): 0:Low  1:Hi 5v
        """
        # SET_MULTI
        #  b0: Multi mode [ 0:Trigger Out  1:Pass/Fail Out  2:Trigger In ]
        #  b1: Pass/Fail state  [ 0:TTL low 0v  1:TTL hi 5v ]
        multi_arg = MULTI_PF | (state & 1) << 8
        self.send(CMD.SET_MULTI, multi_arg)


    def set_peak_mode(self, enable=True):
        """ To enable or disable peak mode sampling

        Args:
            enable (bool)
        """
        self._push(CMD.SET_PEAKMODE, enable & 1)  # [ 0:off  1:on ]


    def set_sampling_rate(self, rate, rollmode=None):
        """ Configure the sampling rate

        Args:
            rate      (int): Sampling rate Ms/s, from 3 to 100e6
            rollmode (bool): Optional, sets roll mode. Defaults to sampling rate >= 2500 Ms/s
        """
        assert 3 <= rate <= SAMPLING_RATE, "Parameter rate out of range [ 1: 100e6 ]"
        timerange = SAMPLES / rate
        self._push_timerange(timerange, rollmode)


    def set_timerange(self, range, rollmode=None):
        """ Configure the sampling rate

        Args:
            timerange (float,str): Range in seconds from 50e-6 (50us) to 2000 (2000s)
            rollmode       (bool): Optional, sets roll mode. Defaults to timerange >= 2s
        """
        timerange = _parse.seconds(range=range)
        assert TIMERANGES[0] <= timerange <= TIMERANGES[-1], \
            "Parameter range not in range [ 50e-6: 2000 ]"
        self._push_timerange(timerange, rollmode)


    def _push_timerange(self, timerange, rollmode):

        sampling_rate = round(SAMPLES / timerange)
        sampling_factor = max(1, round(SAMPLING_RATE / sampling_rate))

        self.sampling_rate = round(SAMPLING_RATE / sampling_factor)
        self.timerange = SAMPLES / self.sampling_rate
        self.rollmode = self.timerange >= ROLLMODE_THRESHOLD if rollmode is None else rollmode

        self._push(CMD.SET_TIMEBASE, sampling_factor)
        self._push(CMD.SET_ROLLMODE, self.rollmode & 1)
        self._push(CMD.SET_DEEPMEMORY, ADC_SIZE)


    def set_trigger(self, source, mode, condition,
                    position=0.5,
                    level=0,
                    width=30e-9,
                    holdoff=100e-9,
                    alternate=False,
                    sweep=AUTO):
        """ Configure a trigger

        Args:
            source      (int): Channel index: `CH1` `CH2` `EXT` .
            mode       (mode): Mode index: `EDGE` `PULSE` `SLOPE` .
            condition   (int): Edge: `RISE`, `FALL` .
                               Slop/Pulse: `RISE_SUP`, `RISE_EQU`, `RISE_INF`, `FALL_SUP`, `FALL_EQU`, `FALL_INF` .
            position  (float): Optional horizontal trigger position from 0 to 1. Defaults to ``0.5`` .
            level (float,str): Optional trigger level in volt. Pair of hi and low if SLOPE mode. Defaults to ``0v`` .
            width     (float): Optional condition width in second for PULSE/SLOPE mode only. Defaults to ``30ns``.
            holdoff   (float): Optional time in second before the next trigger can occur. Defaults to ``100ns``.
            alternate  (bool): Optional alternate triggering for both CH1 and CH2. Defaults to ``False``.
            sweep       (int): Optional sweep mode: `AUTO`, `NORMAL`, `ONCE`.  Defaults to `AUTO`.
        Examples:
            >>> dev.set_trigger(CH1, EDGE, RISE, level='2.5v', sweep=ONCE)
            >>> dev.set_trigger(CH1, PULSE, RISE_SUP, level='2.5v', width='2ms', sweep=ONCE)
            >>> dev.set_trigger(CH1, SLOPE, RISE_SUP, level=('1v', '4v'), width='20ms', sweep=ONCE)
        """

        chl       = _parse.constant(source=source)
        mode      = _parse.constant(mode=mode)
        position  = _parse.ratio(position=position)
        levels    = [ _parse.volts(level=v) for v in _aslist(level) ]
        condition = _parse.constant(condition=condition)
        width     = _parse.seconds(width=width)
        holdoff   = _parse.seconds(holdoff=holdoff)
        sweep     = _parse.constant(sweep=sweep)

        # external channel
        multi = (MULTI_OUT, MULTI_IN)[chl == EXT]
        self._push(CMD.SET_MULTI, multi)  # [ 0:Trigger Out  1:Pass/Fail Out  2:Trigger In ]

        # number of samples before and after trigger
        #            | max left  |   center   | max right
        #  position  |    0      |    0.5     |    1
        #  pre, post | 50, 5050  | 2550, 2550 | 5050, 50
        htp = round(SAMPLES * _clip(position - 0.5, -0.5, 0.5))
        self._push(CMD.SET_PRE_TRG, (ADC_SIZE >> 1) - htp - HTP_ERR)
        self._push(CMD.SET_SUF_TRG, (ADC_SIZE >> 1) + htp + HTP_ERR)
        self.trigger_position = position

        # trigger settings
        # bit 0 : source [ 0:channel 1:external ]
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
            # bit 9    : ??? [ AC:0 ]
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
        self.sweepmode = sweep

        if chl == EXT:
            assert mode == EDGE, "Trigger mode not supported with external channel: %s" % mode
        else:
            # edge/pulse/slope level
            lvls = [ round((v / self.voltrange[chl] + self.voltoffset[chl]) * ADC_RANGE) for v in levels ]
            if mode in (EDGE, PULSE):
                assert len(lvls) == 1, "Parameter level requires 1 value only"
                v = lvls[0] + (10 if condition < 0 else 0)  # +10 if fall condition
                assert ADC_MIN + 10 <= v <= ADC_MAX, "Parameter level not in range: %s" % levels[0]
                self._push(CMD.SET_EDGE_LEVEL[chl], pack('bb', v, v - 10))
            elif mode == SLOPE:
                assert len(lvls) == 2, "Parameter level requires 2 values"
                assert ADC_MIN <= lvls[0] <= ADC_MAX, "Parameter level[0] not in range %s" % levels[0]
                assert ADC_MIN <= lvls[1] <= ADC_MAX, "Parameter level[1] not in range %s" % levels[1]
                self._push(CMD.SET_SLOPE_THRED[chl], pack('bb', max(lvls), min(lvls)))

            # pulse/slope width
            if mode in (PULSE, SLOPE):
                if self.firmware < 3:  # if fpga version < 3
                    m, e = _iexp10(width * 1e8, 1023)  # to 10th ns, 10bits mantissa, base10 exponent
                    if condition in (FALL_EQU, RISE_EQU):
                        self._push(CMD.SET_TRG_CDT_EQU_H[chl], int(m * 1.05) << 6 | e & 7)
                        self._push(CMD.SET_TRG_CDT_EQU_L[chl], int(m * 0.95))
                    else:
                        self._push(CMD.SET_TRG_CDT_GL[chl], m)
                        self._push(CMD.SET_TRG_CDT_EQU_H[chl], e)
                else:
                    m = width * 1e8  # sec to 10th of ns
                    self._push(CMD.SET_TRG_CDT_GL[chl], int(m % 65536))
                    self._push(CMD.SET_TRG_CDT_HL[chl], int(m / 65536))

        # holdoff time
        m, e = _iexp10(holdoff * 1e8, 1023)  # to 10th ns, 10bits mantissa, base10 exponent
        self._push(CMD.SET_TRG_HOLDOFF[chl], pack('>H', m << 6 | e & 7))

        # empty ???
        self._push(CMD.SET_EMPTY, 1)


    def get_triggered(self):
        """
        Returns:
            int: Trigger state of each channel: ``bit0:ch1`` ``bit2:ch2``. First two bits if `EXT` trigger.
        """
        trg_d = self.send(CMD.GET_TRIGGERED, 0)
        for i, on in enumerate(self.on):
            trg_d &= ~((on ^ 1) << i)
        return trg_d


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
            yy = [ self.voltrange[chl] * self.proberatio[chl] * (r - self.voltoffset[chl])
                   for r in (-0.5, 0.5)
                   for chl, on in enumerate(self.on) if on ]
            return min(yy), max(yy)
        else:
            chl = _parse.constant(channel=channel)
            voltrange = self.voltrange[chl] * self.proberatio[chl]
            ty = voltrange * -self.voltoffset[chl]
            return ty - voltrange / 2, ty + voltrange / 2


    def xlim(self):
        """ Left/right bounds for the time axis.

        Returns:
            tuple: (left, right)
        """
        timerange = self.timerange
        tx = timerange * (0.5 - self.trigger_position)
        return tx - timerange / 2, tx + timerange / 2


    def plot(self, freq=0.2, autorange=False, autosense=False, **kwargs):
        """ Live plotting.

        Args:
            freq     (float): Refresh interval (seconds). Defaults to 200ms.
            autorange (bool): Optional, auto adjusts the voltrange. Defaults to False.
            autosense (bool): Optional, auto adjusts the trigger level to 50%. Defaults to `False`.
            kwargs    (dict): keyworded arguments for the backend library
        """
        self._halt()

        source = self.pull_iter(freq, autorange, autosense)
        frames = next(source)
        chart = BokehChart(frames, kwargs).show()

        def run():
            for frames in source:
                chart.update(frames)

        threading.Thread(target=run, daemon=True).start()


    def stream(self, freq=0.2, autorange=False):
        """ To stream non continuous frames of 5000 points.
        The frames are pulled at an interval defined by freq.

        Args:
            freq     (float): Optional, pull interval (seconds). Defaults to 1s.
            autorange (bool): Optional, auto adjusts the voltrange and offset. Defaults to ``False``.
        Returns:
            `Stream`
        Example:
            Stream plotting of RMS voltage

            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022()
            >>> dev.set_timerange('10ms')
            >>> dev.set_channel(CH1, range='10v', coupling=DC, offset=0, probe='x1')
            >>> dev.set_channel(CH2, range='10v', coupling=DC, offset=0, probe='x1')
            >>> dev.stream(freq=1).agg('rms').plot()

            Stream plotting with customised aggregation

            >>> def to_rms(frames):
            >>>     x = frames.time
            >>>     return [ dict(name=f.name, x=x, y=f.rms(), ylim=f.ylim) for f in frames ]
            >>>
            >>> dev.stream(freq=1).map(to_rms).plot()

            Streaming to a function

            >>> src = dev.stream(freq=1).agg('rms').sink(print)
        """
        source = self.pull_iter(freq, autorange)
        stream = Stream(source)
        return stream


    def pull(self, delay=0.1, autorange=False):
        """ To acquire a sampling frame of 5000 points.

        Args:
            delay     (float): Wait time before pulling the samples. Defaults to 100ms.
            autorange (float): Optional, automatically adjusts the voltrange. Defaults to False.
        Returns:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        Examples:
            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022()
            >>> dev.set_timerange('100ms', rollmode=None)
            >>> dev.set_channel(CH1, range='10v', coupling=AC, offset=0, probe='x10')
            >>> dev.set_channel(CH2, range='20v', coupling='DC', offset=0, probe='x10')
            >>> dev.set_trigger(CH1, mode=EDGE, condition=RISE, alternate=False, sweep=ONCE)
            >>> frames = dev.pull()
            >>> print(frames)
        """
        return next(self.pull_iter(delay, autorange))


    def read(self, duration, pre=None):
        """ To acquire continuous samples for a defined time from the start or on a trigger.
        The maximum sampling rate is arround 100Kbs/s.
        It will raise an error if it misses some samples.

        Args:
            duration (float): Time from start in second or post-trigger time if a trigger is set.
            pre      (float): Optional pre-trigger time in second. Defauts to timerange if None.
        Returns:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        Example:
            Acquire continuous samples for a defined time:

            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022()
            >>> dev.set_timerange('100ms')
            >>> dev.set_channel(CH1, range='10v', coupling='DC', offset=-1/4, probe='x10')
            >>> frames = dev.read('5s')
            >>> frames

            Acquire continuous samples on a trigger:

            >>> dev = VDS1022()
            >>> dev.set_timerange('100ms')
            >>> dev.set_channel(CH1, range='10v', coupling='DC', offset=-1/4, probe='x10')
            >>> dev.set_trigger(CH1, mode=EDGE, condition=RISE, alternate=False, sweep=ONCE)
            >>> frames = dev.read('2s', pre='1s')
            >>> frames
        """
        duration = _parse.seconds(duration=duration)
        pre = _parse.seconds(pre=pre) if pre else 0
        freq = min(1, self.timerange / 2)
        items = collections.deque()
        starttime = None
        endtime = None

        self._halt()

        if self.sweepmode:
            for fs in self.read_iter(freq):
                items.append(fs)
                now = fs.time

                if starttime is None:
                    starttime = now

                if endtime is None:
                    if self.get_triggered():
                        endtime = now + max(0, duration - freq)
                        if DEBUG:
                            print("Triggered at %f seconds" % (now - starttime))

                    while items and now - items[0].time > pre:
                        items.popleft()

                elif now > endtime:
                    return Frames.concat(items)
        else:
            for fs in self.read_iter(freq):
                items.append(fs)
                if endtime is None:
                    endtime = fs.time + max(0, duration - freq)
                if fs.time > endtime:
                    return Frames.concat(items)


    def pull_iter(self, freq=0, autorange=False, autosense=False):
        """Generator to retrieve sampling frames.

        Args:
            freq     (float): Optional, wait time before pulling the next frame. Defaults to `0`.
            autorange (bool): Optional, auto adjusts the voltrange and offset. Defaults to `False`.
            autosense (bool): Optional, auto adjusts the trigger level to 50%. Defaults to `False`.
        Yields:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        Examples:
            >>> from vds1022 import *
            >>>
            >>> dev = VDS1022(debug=False)
            >>> dev.set_timerange('100ms', rollmode=None)
            >>> dev.set_channel(CH1, range='10v', coupling='DC', offset=0, probe='x10')
            >>> dev.set_channel(CH2, range='20v', coupling='DC', offset=0, probe='x10')
            >>> dev.set_trigger(CH1, mode=EDGE, condition=RISE, alternate=False, sweep=AUTO)
            >>>
            >>> for frames in dev.pull_iter(freq='500ms', autosense=True, autorange=False):
            >>>     print(frames)
            >>>     break
        """

        freq = _parse.seconds(freq=freq)
        freq = max(0, freq - 30e-3)

        self._halt()

        buffer = self._buffer
        cmd_arg = bytes((0x04, 0x05)[on] for on in self.on)  # 4:OFF 5:ON
        cmd_get = CMD.GET_DATA.pack(cmd_arg)
        channels = [ i for i, on in enumerate(self.on) if on ]
        frames = [ None ] * CHANNELS
        again = False
        starttime = None

        offset = READ_SIZE - SAMPLES
        if not self.rollmode:
            offset -= (ADC_SIZE - SAMPLES) >> 1  # from center instead right

        points = np.frombuffer(buffer, 'b', SAMPLES, offset=offset)

        with self._lock:
            self._submit()
            gc.collect()

        while again and not self._stop.is_set() or not self._stop.wait(freq):
            with self._lock:
                again = False

                if self.sweepmode:
                    if not self._send(CMD.GET_DATAFINISHED, 0):
                        continue
                    if not self._send(CMD.GET_TRIGGERED, 0):
                        continue

                try:
                    self._bulk_write(cmd_get)
                    pulltime = self._writetime

                    for chl in channels:
                        ret = self._bulk_read(buffer)
                        CMD.GET_DATA.log(cmd_arg, ret)
                        if ret != READ_SIZE:
                            again = True
                            break

                        channel, time_sum, period_num, cursor = unpack_from("<BIIH", buffer)
                        assert channel == chl, "Expected channel %d, got %s" % (chl, channel)
                        assert self.rollmode or cursor >= SAMPLES, "Invalid cursor %d" % cursor

                        zero = round(ADC_RANGE * self.voltoffset[chl])
                        vmin = min(zero, int(points.min()))
                        vmax = max(zero, int(points.max()))

                        if autorange:
                            vb = VOLTRANGES.index(self.voltrange[chl])
                            amp = abs(vmax - vmin)
                            mid = (vmax + vmin) / 2

                            if amp < 30 or vmax > 100 or vmin < -100:
                                if vmax >= ADC_MAX or vmin <= ADC_MIN:
                                    vbnew = (vb + len(VOLTRANGES)) >> 1
                                else:
                                    voltrange = amp * 1.3 * VOLTRANGES[vb] / ADC_RANGE
                                    vbnew = bisect_left(VOLTRANGES, voltrange)
                                    mid *= VOLTRANGES[vb] / VOLTRANGES[vbnew]

                                if vb != vbnew or amp >= 30:
                                    voltoffset = self.voltoffset[chl] - mid / ADC_RANGE
                                    self.voltoffset[chl] = _clip(voltoffset, -0.4, 0.4)
                                    self.voltrange[chl] = VOLTRANGES[vbnew]
                                    self._push_channel(chl)
                                    again = True
                                    continue

                        if autosense:
                            mid = (vmin + vmax) >> 1
                            self._push(CMD.SET_EDGE_LEVEL[chl], pack('bb', mid + 5, mid - 5))  # trigger sense level
                            self._push(CMD.SET_FREQREF[chl], mid & 0xff)  # freq meter sense level

                        # period = period_num and time_sum / period_num / SAMPLING_RATE
                        frequency = time_sum and period_num / time_sum * SAMPLING_RATE
                        start = max(0, min(SAMPLES, SAMPLES - cursor))
                        translate = start - SAMPLES * self.trigger_position  # points to trigger origin
                        data = buffer[offset: offset + SAMPLES]
                        frames[chl] = Frame(self, channel, data, start, translate, frequency)

                except USBError as ex:
                    self._on_usb_err(ex, CMD.GET_DATA, cmd_arg)
                    continue

                self._submit()

            if not again:
                if starttime is None:
                    starttime = pulltime
                yield Frames(frames, pulltime - starttime)
                gc.collect(0)  # prevents long GC during acquisition


    def read_iter(self, freq):
        """ Generator to retrieve consecutive samples.
        Continuous sampling if freq < timerange (100Ks/s max).

        Args:
            freq (float): Sleep time between readings.
        Yields:
            `Frames`: (`Frame` `CH1`, `Frame` `CH2`)
        """

        freq = _parse.seconds(freq=freq)

        self._halt()
        self.rollmode = True

        # In roll mode, the signal is corrupted at the end with a sampling rate over 50Ks/s.
        # To overcome this issue, the number of sample is reduced from 5000 to 4000.

        continuous = freq < self.timerange
        cmd_arg    = bytes((0x04, 0x05)[on] for on in self.on)
        cmd_get    = CMD.GET_DATA.pack(cmd_arg)
        channels   = tuple( i for i, on in enumerate(self.on) if on )
        length     = 4000 if self.sampling_rate > 20e3 else SAMPLES
        translate  = 0  # points to origin on the timeline
        frames     = [ None ] * CHANNELS
        cursors    = [ 0 ] * CHANNELS
        sleeptime  = _clip(freq - 35e-3 * len(channels), 0, 1)
        maxtime    = length / self.sampling_rate
        starttime  = None
        prevtime   = None
        buffer     = self._buffer

        with self._lock:
            self._push(CMD.SET_RUNSTOP, 0)  # [ 0:run 1:stop ]
            self._push(CMD.SET_ROLLMODE, 1)  # [ 0:off 1:on ]
            self._push(CMD.SET_DEEPMEMORY, 5120)  # cursor becomes circular at 5120, was 5100
            self._submit()
            gc.collect()

        while not self._stop.wait(sleeptime):
            with self._lock:
                self._bulk_write(cmd_get)
                pulltime = self._writetime

                if starttime is None:
                    starttime = prevtime = pulltime

                if not continuous:
                    translate = int((pulltime - starttime) * self.sampling_rate)

                for chl in channels:
                    ret = self._bulk_read(buffer)
                    assert ret == READ_SIZE

                    channel, time_sum, period_num, cursor = unpack_from('<BIIH', buffer)
                    assert channel == chl, "Unexpected channel in data"

                    if continuous:
                        assert pulltime - prevtime < maxtime, "Missed some samples! Reduce the sampling rate"
                        length = (cursor - cursors[chl] + 5120) % 5120
                        assert length > 0, "Zero length ADC cursor"
                        cursors[chl] = cursor

                    buf = buffer[READ_SIZE - length: READ_SIZE]
                    frames[chl] = Frame(self, chl, buf, 0, translate, 0)

                prevtime = pulltime
                translate += length
                yield Frames(frames, pulltime - starttime)
                gc.collect(0)  # prevents long GC during acquisition


    def calibrate(self):
        """ Auto adjust the zero offset and zero amplitude (not the gain).
        The calibration is then saved to 'VDS1022xxxxxxxx-cals.json'.
        Probes must be disconnected.
        """

        sampling_rate = 200e3
        timerange = ADC_SIZE / sampling_rate
        calibration = deepcopy(self.calibration)

        self._halt()

        with self._lock:
            self._push(CMD.SET_PEAKMODE, 0)  # [ 0:off  1:on ]
            self._push(CMD.SET_MULTI, MULTI_IN)  # [ 0:TrgOut  1:PassFail  2:TrgIn ]
            self._push(CMD.SET_TRIGGER, 1)  # External TTL EDGE Rise
            self._push(CMD.SET_TIMEBASE, round(SAMPLING_RATE / sampling_rate))
            self._push(CMD.SET_EMPTY, 1)
            self._push(CMD.SET_RUNSTOP, 0)  # [ 0:run 1:stop ]
            self._submit()

            for vb in reversed(range(len(VOLTRANGES))):
                for chl in range(CHANNELS):
                    calibration[COMP][chl][vb] = _clip(calibration[COMP][chl][vb], 500 , 600)
                    if not self._calibrate(calibration, timerange, chl, COMP, vb, 0, 0):
                        return

                for chl in range(CHANNELS):
                    calibration[AMPL][chl][vb] = _clip(calibration[AMPL][chl][vb], 100 , 200)
                    if not self._calibrate(calibration, timerange, chl, AMPL, vb, 110, 110):
                        return

        self.calibration = calibration
        _print_calibration(calibration)

        self._push(CMD.SET_TRIGGER, 0)
        self._push(CMD.SET_MULTI, MULTI_OUT)  # [ 0:TrgOut  1:PassFail  2:TrgIn ]
        self._push_timerange(self.timerange, self.rollmode)
        for chl in range(CHANNELS):
            self._push_channel(chl)

        self._save_calibration()


    def _calibrate(self, calibration, timerange, chl, ical, vb, pos0, target):

        coupling = DC if ical == GAIN else AC
        attenuate = VOLTRANGES[vb] >= ATTENUATION_THRESHOLD
        chl_arg = (attenuate & 1) << 1 | (coupling & 3) << 5 | 1 << 7
        self._send(CMD.SET_CHANNEL[chl], chl_arg)

        name = ('Gain', 'Ampl', 'Comp')[ical]
        cmd_arg = bytes((0x04, 0x05)[i == chl] for i in range(CHANNELS))  # 4:OFF 5:ON
        cmd_get = CMD.GET_DATA.pack(cmd_arg)
        buffer = self._buffer
        points = np.frombuffer(buffer, 'b', SAMPLES, offset=111+50)
        cal = cal_prev = calibration[ical][chl][vb]
        steps = 100
        scale = 1
        hits = 0
        err = 0

        for i in range(10):

            if not i or ical == GAIN:
                cal_gain = calibration[GAIN][chl][vb]
                self._send(CMD.SET_VOLT_GAIN[chl], cal_gain)

            if not i or ical != GAIN:
                cal_comp = calibration[COMP][chl][vb]
                cal_ampl = calibration[AMPL][chl][vb]
                zero_off = round(cal_comp - pos0 * cal_ampl / 100)
                self._send(CMD.SET_ZERO_OFF[chl], zero_off)

            if self._stop.wait(timerange):
                return False

            while True:
                try:
                    gc.collect(0)
                    self._bulk_write(cmd_get)
                    ret = self._bulk_read(buffer)
                    CMD.GET_DATA.log(cmd_arg, ret)
                    if ret == READ_SIZE:
                        break
                except USBError as ex:
                    self._on_usb_err(ex, CMD.GET_DATA, cmd_arg)

            err_prev = err
            err = float(np.mean(points)) - target
            diff = err_prev and abs(err_prev - err)
            hits += steps == 1 and abs(err) < 2

            if diff > 2:
                scale = steps / diff

            if DEBUG:
                print("CH%s %s err:%.2f cal:%s steps:%s scale:%.2f" % (
                        chl + 1, name, err, cal, steps, scale))

            if hits > 1:
                calibration[ical][chl][vb] = max(cal, cal_prev)
                print("CH%d %s %sV: %s" % (chl + 1, name, VOLTRANGES[vb], cal))
                gc.collect(0)
                return True

            cal_prev = cal
            steps = _clip(round(abs(err) * scale), 1, steps - 1)
            cal += int(copysign(steps, (err if target <= 0 else -err)))
            calibration[ical][chl][vb] = cal

        raise RuntimeError("Failed to calibrate CH%d" % (chl + 1))


    def autoset(self):
        """ Adjust the range and timebase of each enabled channel. """

        self._halt()

        with self._lock:
            self._push(CMD.SET_ROLLMODE, 0)
            self._push(CMD.SET_PEAKMODE, 1)  # [ 0:off  1:on ]
            self._push(CMD.SET_MULTI, MULTI_OUT)  # [ 0:TrgOut  1:PassFail  2:TrgIn ]
            self._push(CMD.SET_PRE_TRG, (ADC_SIZE >> 1) - HTP_ERR )  # htp at 0 (half)
            self._push(CMD.SET_SUF_TRG, (ADC_SIZE >> 1) + HTP_ERR )  # htp at 0 (half)
            self._push(CMD.SET_TRIGGER, 0xc000)  # Alt mode
            self._push(CMD.SET_RUNSTOP, 0)  # [ 0:run 1:stop ]
            self._push_timerange(0.2, rollmode=False)

            for chl, on in enumerate(self.on):
                if on and not self._autoset(chl):
                    break

            self._push(CMD.SET_PEAKMODE, 0)


    def _autoset(self, chl):

        cmd_arg = bytes((0x04, 0x05)[i == chl] for i in range(CHANNELS))  # [ 4:OFF 5:ON ]
        cmd_get = CMD.GET_DATA.pack(cmd_arg)
        buffer = self._buffer
        points = np.frombuffer(buffer, 'b', SAMPLES, 111 + 50)
        vb = VOLTRANGES.index(self.voltrange[chl])
        vb_pre = vb
        level = 25
        tries = 0
        hits = 0

        while tries < 10 and hits < 3:
            tries += 1
            print("Adjust CH%s try:%s hits:%s voltrange:%sv timerange:%ss" % (
                    chl + 1, tries, hits, VOLTRANGES[vb], self.timerange))

            self.coupling[chl] = DC
            self.voltoffset[chl] = 0
            self.voltrange[chl] = VOLTRANGES[vb]

            gc.collect(0)
            self._push_channel(chl)
            self._push(CMD.SET_EDGE_LEVEL[chl], pack('bb', level + 5, level - 5))
            self._push(CMD.SET_FREQREF[chl], pack('b', level))
            self._push(CMD.SET_EMPTY, 1)
            self._submit()

            if self._stop.wait(self.timerange):
                return False

            while True:
                try:
                    gc.collect(0)
                    self._bulk_write(cmd_get)
                    ret = self._bulk_read(buffer)
                    if ret == READ_SIZE:
                        break
                except USBError as ex:
                    self._on_usb_err(ex, CMD.GET_DATA, cmd_arg)

            channel, time_sum, period_num, cursor = unpack_from("<BIIH", buffer)
            assert channel == chl, "Invalid channel %d" % channel

            zero = round(ADC_RANGE * self.voltoffset[chl])
            vmax = max(zero, int(points.max()))
            vmin = min(zero, int(points.min()))
            amp = max(abs(vmax), abs(vmin)) << 1
            vb_pre = vb

            if vmax >= ADC_MAX or vmin <= ADC_MIN:
                vb = (vb + len(VOLTRANGES)) >> 1
            else:
                voltrange = amp * 1.05 * VOLTRANGES[vb] / ADC_RANGE
                vb = bisect_left(VOLTRANGES, voltrange)
                scale = VOLTRANGES[vb_pre] / VOLTRANGES[vb]
                level = round((vmax + vmin) / 2 * scale)

            if DEBUG:
                sy = self.voltrange[chl] / ADC_RANGE
                print("CH%s voltrange:%sv  next:%sv  min:%sv  max:%sv" % (
                        chl + 1,
                        self.voltrange[chl],
                        VOLTRANGES[vb],
                        vmin * sy,
                        vmax * sy))

            if period_num:
                period = time_sum / period_num / SAMPLING_RATE
                timerange = TIMERANGES[bisect_left(TIMERANGES, period * 3.5)]
                if timerange != self.timerange:
                    self._push_timerange(timerange, False)
                    if DEBUG:
                        print("CH%s  timerange:%ss  next:%ss  period:%ss" % (
                                chl + 1, self.timerange, timerange, period))
                    continue

            hits += vb == vb_pre

        return True


# def _signal_handler(signal, frame):
#     if VDS1022._instance:
#         VDS1022._instance.stop()
#     raise KeyboardInterrupt()


# signal.signal(signal.SIGINT, _signal_handler)
# signal.signal(signal.SIGTERM, _signal_handler)


if __name__ == '__main__':

    with VDS1022(debug=False) as dev:
        dev.calibrate()

        dev.set_timerange('20ms', rollmode=False)
        dev.set_channel(CH1, range='10v', coupling='DC', offset=-0.4, probe='x10')

        for frames in dev.pull_iter(autorange=False):
            print('Vrms:%s' % frames.CH1.rms(), end='\r')
            time.sleep(1)
