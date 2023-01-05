#!/usr/bin/env python

import sounddevice as sd
import numpy as np
import time
import rrdtool
import os
import logging
import sys
import typer
from typing import Optional, Union

app = typer.Typer()

def get_input_device_info(device_index: Optional[int]) -> dict:
    return sd.query_devices(device_index, kind='input') if device_index is not None else sd.query_devices(kind='input')

@app.command()
def list_devices():
    print(sd.query_devices())
    return


@app.command()
def record(device_index: Optional[int] = None):
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
            '--step', '1s',
            'DS:amplitude:GAUGE:1m:0:32767',
            'RRA:AVERAGE:0.5:1s:1day')

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
            rms_amplitude = np.sqrt(np.mean(np.square(block)))
            end_ns = time.monotonic_ns()
            elapsed_ns = end_ns - start_ns
            rrdtool.update(rrd_file, f'{block_time_epoch_seconds}:{rms_amplitude}')
            logging.info(f'RMS:{block_time_epoch_seconds}:{rms_amplitude:.2f}, elapsed ms: {int(elapsed_ns / 1_000_000)}')


if __name__ == "__main__":
    app()
