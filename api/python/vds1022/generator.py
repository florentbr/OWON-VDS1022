import numpy as np
import pyaudio
import time
import threading

from math import ceil


pa = pyaudio.pa


FORMATS = {
    np.int8   : pa.paInt8,
    np.int16  : pa.paInt16,
    np.int32  : pa.paInt32,
    np.float32: pa.paFloat32 }


def _to_type(data, dtype):
    info = np.iinfo(dtype)
    return data.clip(info.min, info.max).astype(dtype)



class FStream:

    def __init__(self, samples, period, dtype):
        self.samples = _to_type(samples, dtype)
        self.period  = period
        self.index   = 0.0


    def read(self, size):
        start = round(self.index)
        self.index = (self.index + size) % self.period
        return self.samples[start: start + size]


    def add(self, samples, period):

        assert period < self.period

        a, b = self.samples, samples
        diff = len(a) - len(b)

        if diff > 0:
            a = a[:-abs(diff)]
        elif diff < 0:
            b = b[:-abs(diff)]

        self.samples = _to_type(a + b, a.dtype)



class Generator:

    _instance = None


    def __new__(cls, *args, **kwargs):
        self = cls._instance

        if self is None:
            self = cls._instance = object.__new__(cls)
        else:
            self.stop()

        return self


    def __init__(self, device=None, sample_rate=None, scale=1, size=16384, dtype=np.int16):

        pa.initialize()

        if device is None:
            device = pa.get_default_output_device()

        device_info = pa.get_device_info(device)

        self.default_sample_rate = int(device_info.defaultSampleRate)
        self.sample_rate = sample_rate
        self.dtype    = dtype
        self.max      = int(np.iinfo(dtype).max * 120 / 127)
        self.size     = size
        self.scale    = scale
        self.channels = int(device_info.maxOutputChannels)
        self.device   = device
        self.stream   = None
        self.frames   = { }
        self.lock     = threading.Lock()


    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


    def stop(self):
        if self.stream is not None:
            pa.close(self.stream)
            self.stream = None
            self.frames = None

        pa.terminate()


    def _set_sampling(self, freq):

        if self.sample_rate is None:

            self.sample_rate = self.default_sample_rate
            sample_rate = round(int(self.default_sample_rate / freq) * freq)

            while sample_rate <= 192000:
                try:
                    pa.is_format_supported(sample_rate,
                        output_device=self.device,
                        output_channels=self.channels,
                        output_format=FORMATS[self.dtype])

                    self.sample_rate = sample_rate
                    sample_rate <<= 1

                except ValueError:
                    break

            period = self.sample_rate / freq
            self.size = round(ceil(self.size / period) * period)


    def sine(self, freq, shift=0, scale=1, channel=None):

        self._set_sampling(freq)

        period  = self.sample_rate / freq
        start   = int(period * ((1.0 + shift) % 1))
        stop    = int(start + self.size + period * 2) - 1
        t       = np.arange(start, stop)
        samples = np.sin(2 * np.pi / period * t)

        self.add(samples, period, channel, scale)
        return self


    def square(self, freq, duty=0.5, shift=0, scale=1, channel=None):

        self._set_sampling(freq)

        period  = self.sample_rate / freq
        start   = int(period * ((1.0 + shift) % 1))
        stop    = int(start + self.size + period)
        t       = np.arange(start, stop)
        samples = 2 * (((t % period) < (period * duty)) - 0.5)

        self.add(samples, period, channel, scale)
        return self


    def sawtooth(self, freq, shift=0, scale=1, channel=None):

        self._set_sampling(freq)

        period  = self.sample_rate / freq
        start   = int(period * ((1.5 + shift) % 1))
        stop    = int(start + self.size + period)
        t       = np.arange(start, stop)
        samples = 2 / period * (t % period) - 1

        self.add(samples, period, channel, scale)
        return self


    def triangle(self, freq, shift=0, scale=1, channel=None):

        self._set_sampling(freq)

        period  = self.sample_rate / freq
        start   = int(period * ((1.75 + shift) % 1))
        stop    = start + int(self.size + period)
        t       = np.arange(start, stop)
        samples = np.abs(4 / period * (t % period) - 2) - 1

        self.add(samples, period, channel, scale)
        return self


    def sweep(self, duration, f0, f1, scale=1, channel=None):

        self._set_sampling(1 / duration)

        c = (f1 - f0) / duration  # chirp rate
        t = np.linspace(0, duration, self.size)
        samples = np.sin( 2*np.pi*c/2 * (t**2) + 2*np.pi*f0 * t )

        self.add(samples, self.size, channel, scale)

        return lambda : f0 + (c * t)


    def sweep_exp(self, duration, f0, f1, scale=1, channel=None):

        self._set_sampling(1 / duration)

        k = (f1 / f0) ** (1 / duration)  # rate of exponential change
        t = np.linspace(0, duration, self.size)
        samples = np.sin( 2*np.pi*f0/np.log(k) * ((k**t)-1) )

        self.add(samples, self.size, channel, scale)

        return lambda : f0 * (k ** t)


    def add(self, samples, period, channel=None, scale=1):

        self._set_sampling(1 / period)

        if channel is None:
            channel = len(self.frames)

        assert channel < self.channels
        assert len(samples) >= int(self.size)

        dac_samples = (self.max * self.scale * scale) * samples

        if channel in self.frames:
            self.frames[channel].add(dac_samples, period)
        else:
            self.frames[channel] = FStream(dac_samples, period, self.dtype)


    def to_dataframe(self):

        import pandas

        size = self.size
        ys = { ('CH%d' % chl): frame.samples[:size]
               for chl, frame in self.frames.items() }

        return pandas.DataFrame(ys, copy=False)


    def play(self, duration=None):

        if self.stream is not None:
            pa.close(self.stream)
            self.stream = None

        endtime = duration and duration + time.perf_counter()

        data = np.zeros((self.size, len(self.frames)), self.dtype)

        def callback(_, size, time_info, status):
            if endtime and time.perf_counter() > endtime:
                return None, pyaudio.paAbort
            with self.lock:
                for channel, frame in self.frames.items():
                    data[:,channel] = frame.read(size)
                return data, pyaudio.paContinue

        self.stream = pa.open(
            rate=int(self.sample_rate),
            channels=len(self.frames),
            format=FORMATS[self.dtype],
            input=False,
            output=True,
            input_device_index=None,
            output_device_index=self.device,
            frames_per_buffer=self.size,
            stream_callback=callback)

        pa.start_stream(self.stream)


    def plot(self, figsize=(10, 3)):
        import matplotlib.pyplot as plt

        frames = self.frames.values()
        size   = int(min(self.size, max(f.period for f in frames) * 2))
        stop   = size / self.sample_rate
        xs     = np.linspace(0, stop, size, endpoint=False)
        ys     = [ f.samples[:size] / self.max for f in frames ]

        plt.figure(figsize=figsize)
        plt.axes(ylabel='y(t)', xlabel='Time [s]')
        plt.ylim(-1.1, 1.1)
        plt.margins(x=0)
        plt.grid()

        for y in ys:
            plt.plot(xs, y)

        plt.show()


    @staticmethod
    def print_devices():

        pa.initialize()

        try:
            host_infos = [ pa.get_host_api_info(i) for i in range(pa.get_host_api_count()) ]
            default_output = pa.get_default_output_device()
            default_input  = pa.get_default_input_device()

            print('Output devices (default=%d)' % default_output)

            for host in host_infos:
                if host.deviceCount:
                    dev = pa.get_device_info(host.defaultOutputDevice)
                    print('%2d: %s CH, %5d Hz, %s, %s' % (
                        host.defaultOutputDevice, 
                        dev.maxOutputChannels,
                        dev.defaultSampleRate,
                        host.name,
                        dev.name.decode('utf-8')))

            # print('Input devices (default=%d)' % default_input)

            # for host in host_infos:
            #     if host.deviceCount:
            #         dev = pa.get_device_info(host.defaultInputDevice)
            #         print('%2d: %s CH, %5d Hz, %s, %s' % (
            #             host.defaultInputDevice, 
            #             dev.maxInputChannels,
            #             dev.defaultSampleRate,
            #             host.name,
            #             dev.name.decode('utf-8')))

        finally:
            pa.terminate()
