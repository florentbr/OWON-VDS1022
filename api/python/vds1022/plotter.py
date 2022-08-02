#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This module provides an API to plot a signal in Jupyter.
"""

import numpy as np

__all__ = (
    'BokehChart',
    'MatplotlibChart'
)

_items = lambda x: x if hasattr(x, '__getitem__') else [ x ]


class BokehChart:

    _FORMATTER_X =\
        "var v=tick, n=-1;"\
        "if (v>=60) return ((v/60)|0)+':'+(+(100+v%60).toFixed(2)+'').substring(1);"\
        "for (; v && Math.abs(v)<0.5; ++n) v*=1e3;"\
        "return v && +v.toPrecision(5)+('mµnp'[n]||'')+'s';"

    _FORMATTER_Y =\
        "var v=tick, n=-1;"\
        "for (; v && Math.abs(v)<0.5; ++n) v*=1e3;"\
        "return v && +v.toPrecision(5)+('mµnp'[n]||'')+'v';"


    def __init__(self, data, opts, rollover=None):
        import bokeh.io, bokeh.plotting, bokeh.models, bokeh.models.tools

        self.xy_mode = opts.pop('xy_mode', False)

        if type(data).__name__ == 'Frames':
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
            lines = data  # array of dict

        labels = opts.pop('label', [ d.get('name', str(i)) for i, d in enumerate(lines) ])

        opts.setdefault('frame_width', opts.pop('width', 600))
        opts.setdefault('frame_height', opts.pop('height', 250))
        opts.setdefault('lod_interval', 0)
        opts.setdefault('x_axis_label', opts.pop('xlabel', None))
        opts.setdefault('y_axis_label', opts.pop('ylabel', None))
        opts.setdefault('color', ('#1f77b4', '#ff7f0e'))
        opts.setdefault('active_inspect', None)
        opts.setdefault('active_drag', None)
        opts.setdefault('active_multi', 'xbox_zoom')
        opts.setdefault('tools', 'xpan,xwheel_zoom,xzoom_in,xzoom_out,xbox_zoom,crosshair,save,reset')
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
            xs = _items(line['x'])
            ys = _items(line['y'])
            xlim = line.get('xlim')
            ylim = line.get('ylim')
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
        self.labels = labels
        self.data_source = ds
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

        source_cls = type(source)

        if source_cls is tuple:
            data = { (self.labels[i - 1] if i else 'x'): _items(item) 
                     for i, item in enumerate(source) }

        elif source_cls is dict:
            data = source

        elif source_cls.__name__ == 'Frames':
            if self.xy_mode:
                data = { 'x': source.ch1.y(), self.labels[0]: source.ch2.y() }
            else:
                data = { 'x': source.x() }
                for i, frame in enumerate(source):
                    data[self.labels[i]] = frame.y()

        elif source_cls.__name__ == 'DataFrame':
            data = { 'x': source.index.to_numpy(dtype=np.float32) }
            for i, col in enumerate(source):
                data[self.labels[i]] = source[col].to_numpy(dtype=np.float32)

        else:
            raise ValueError("Invalid argument source")

        if 0 < len(data['x']) < 10:
            self.data_source.stream(data, self.rollover)
        else:
            self.data_source.data = data

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

        if type(lines).__name__ == 'Frames':
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
            while x and abs(x) < 0.5:
                n, x = n + 1, x * 1e3
            return '{0:g}{1}s'.format(round(x, 4), ' mµnp'[n][:n]) if x else '0'

        def format_volt(x, pos):
            n = 0
            while x and abs(x) < 0.5:
                n, x = n + 1, x * 1e3
            return '{0:g}{1}v'.format(round(x, 4), ' mµnp'[n][:n]) if x else '0'

        dpi = plt.rcParams['figure.dpi']
        fig = plt.figure(figsize=(width / dpi, height / dpi), **fig_opts)
        ax = fig.add_subplot(111)

        ax.grid(True, which='major', linestyle='-', alpha=0.5)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

        for i, line in enumerate(lines):
            xs = _items(line.get('x'))
            ys = _items(line.get('y'))

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
        fig.axes[0].legend(handles=axlines
                            , loc='upper left'
                            , bbox_to_anchor=(0, 1.1)
                            , ncol=2
                            , frameon=False)

        plt.title(title)


    def show(self):
        return self



def _is_notebook():
    try:
        return get_ipython().__class__.__name__ == 'ZMQInteractiveShell'
    except NameError:
        return False
