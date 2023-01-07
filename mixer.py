#!/usr/bin/env python
import math

import sounddevice as sd
import numpy as np
import time
import rrdtool
import os
import logging
import sys
import typer
from typing import Optional

app = typer.Typer()

def get_input_device_info(device_index: Optional[int]) -> dict:
    return sd.query_devices(device_index, kind='input') if device_index is not None else sd.query_devices(kind='input')

@app.command()
def list_devices():
    print(sd.query_devices())
    return


@app.command()
def record(device_index: Optional[int] = None,
           rrdcached: str = 'unix:/tmp/rrdcached.sock'):
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, stream=sys.stdout)
    samplerate = 44100
    block_duration_seconds = 1
    blocksize = int(samplerate * block_duration_seconds)
    rrd_dir = os.path.dirname(os.path.abspath(__file__))
    rrd_file = os.path.join(rrd_dir, 'mixer.rrd')
    logging.info(f'Writing to {rrd_file}')
    logging.info(f'Using {get_input_device_info(device_index)} for recording')

    if not os.path.exists(rrd_file):
        rrdtool.create(
            rrd_file,
            '--daemon', rrdcached,
            '--step', '1s',
            '--no-overwrite',
            'DS:peak_amplitude:GAUGE:1m:0:32767',
            'DS:peak_amplitude_dbfs:GAUGE:1m:U:0',
            'DS:rms_amplitude:GAUGE:1m:0:32767',
            'DS:rms_amplitude_dbfs:GAUGE:1m:U:0',
            'RRA:AVERAGE:0.5:1s:4w')

    with sd.InputStream(
            samplerate=samplerate,
            device=device_index,
            dtype=np.int16,
            channels=1,
            latency='low') as stream:
        while True:
            block, _ = stream.read(frames=blocksize)
            block_time_epoch_seconds = int(time.time())
            start_ns = time.monotonic_ns()
            block = block.reshape(-1)
            amplitude_max_value = 32767
            peak_amplitude = min(np.amax(np.abs(block)), amplitude_max_value)
            rms_amplitude = np.sqrt(np.mean(np.square(block, dtype=np.int64)))
            peak_amplitude_dbfs = 20 * math.log10(peak_amplitude / amplitude_max_value) if peak_amplitude > 0 else -np.inf
            rms_amplitude_dbfs = 20 * math.log10(rms_amplitude / amplitude_max_value) if rms_amplitude > 0 else -np.inf
            rrdtool.update(rrd_file,
                           '--daemon', rrdcached,
                           '--skip-past-updates',
                           f'{block_time_epoch_seconds}:{peak_amplitude}:{peak_amplitude_dbfs}:{rms_amplitude}:{rms_amplitude_dbfs}')
            end_ns = time.monotonic_ns()
            elapsed_ns = end_ns - start_ns
            logging.info(f'{block_time_epoch_seconds}:{peak_amplitude}:{peak_amplitude_dbfs:.2f}:{rms_amplitude:.2f}:{rms_amplitude_dbfs:.2f}, elapsed ms: {int(elapsed_ns / 1_000_000)}')


if __name__ == "__main__":
    app()
