#!/usr/bin/env python
import math

import scipy.signal
import sounddevice as sd
import numpy as np
import time
import rrdtool
import os
import logging
import sys
import typer
from typing import Optional
import soundfile as sf
from datetime import datetime
from dataclasses import dataclass
from stopwatch import Stopwatch
import splweighting

SAMPLERATE = 44100
SAMPLE_DTYPE = np.int16
AMPLITUDE_MAX_VALUE = 32767
CHANNELS = 1

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO, stream=sys.stdout)
app = typer.Typer()
mixer_dir = os.path.dirname(os.path.abspath(__file__))

@dataclass
class Measurement:
    epoch_seconds: int
    overflowed: bool
    peak_amplitude: np.int16
    peak_amplitude_dbfs: np.float64
    rms_amplitude: np.float64
    rms_amplitude_dbfs: np.float64


def process_block(epoch_seconds: int,
                  overflowed: bool,
                  block: np.ndarray) -> Measurement:
    peak_amplitude = min(np.amax(np.abs(block)), AMPLITUDE_MAX_VALUE)
    peak_amplitude_dbfs = round(20 * math.log10(peak_amplitude / AMPLITUDE_MAX_VALUE), 2) if peak_amplitude > 0 else -np.inf
    rms_amplitude = round(np.sqrt(np.mean(np.square(block, dtype=np.float64))), 2)
    rms_amplitude_dbfs = round(20 * math.log10(rms_amplitude / AMPLITUDE_MAX_VALUE), 2) if rms_amplitude > 0 else -np.inf
    return Measurement(epoch_seconds,
                       overflowed,
                       peak_amplitude,
                       peak_amplitude_dbfs,
                       rms_amplitude,
                       rms_amplitude_dbfs)


def get_input_device_info(device_index: Optional[int]) -> dict:
    return sd.query_devices(device_index, kind='input') if device_index is not None else sd.query_devices(kind='input')


def get_audio_file_path(base_dir: str, audio_start: datetime, audio_format: str) -> str:
    date_dir = os.path.join(base_dir, audio_start.date().isoformat())
    file_name = f"{audio_start.isoformat(sep=' ', timespec='seconds')}.{audio_format}"
    return os.path.join(date_dir, file_name)


def create_rrd(rrd_file: str,
               rrdcached: str,
               step_seconds: int):
    rrdtool.create(rrd_file,
                   '--daemon', rrdcached,
                   '--step', step_seconds,
                   '--no-overwrite',
                   f'DS:peak_amplitude:GAUGE:1m:0:{AMPLITUDE_MAX_VALUE}',
                   'DS:peak_amplitude_dbfs:GAUGE:1m:U:0',
                   f'DS:rms_amplitude:GAUGE:1m:0:{AMPLITUDE_MAX_VALUE}',
                   'DS:rms_amplitude_dbfs:GAUGE:1m:U:0',
                   f'RRA:AVERAGE:0.5:{step_seconds}:4w')


def record_measurement(rrd_file: str,
                       rrdcached: str,
                       measurement: Measurement):
    parts = [measurement.epoch_seconds,
             measurement.peak_amplitude,
             measurement.peak_amplitude_dbfs,
             measurement.rms_amplitude,
             measurement.rms_amplitude_dbfs]
    rrdtool.update(rrd_file,
                   '--daemon', rrdcached,
                   '--skip-past-updates',
                   ':'.join(map(str, parts)))


def write_blocks(audio_file: sf.SoundFile,
                 blocks: list[np.ndarray]):
    write_time = Stopwatch()
    audio_file.write(np.concatenate(blocks))
    write_time.stop()
    logging.info(f'Written {len(blocks)} audio blocks to {audio_file.name}, elapsed: {write_time}')


@app.command()
def list_devices():
    print(sd.query_devices())
    return


@app.command()
def record(device_index: Optional[int] = None,
           rrdcached: str = 'unix:/tmp/rrdcached.sock',
           rrd_file: str = os.path.join(mixer_dir, 'mixer.rrd'),
           audio_dir: str = os.path.join(mixer_dir, 'audio'),
           audio_duration_minutes: int = 5,
           block_duration_seconds: int = 1,
           audio_format: str = 'flac',
           audio_blocks_write_number: int = 5,
           latency: float = 2.0):
    logging.info(f'Using {rrd_file} via {rrdcached} for storage')

    if not os.path.exists(rrd_file):
        create_rrd(rrd_file, rrdcached, step_seconds=block_duration_seconds)

    logging.info(f'Using {get_input_device_info(device_index)} for recording')

    block_size = SAMPLERATE * block_duration_seconds
    b, a = splweighting.a_weighting_coeffs_design(SAMPLERATE)

    def a_weighting(block: np.ndarray) -> np.ndarray:
        return scipy.signal.lfilter(b, a, block)

    with sd.InputStream(samplerate=SAMPLERATE,
                        device=device_index,
                        dtype=SAMPLE_DTYPE,
                        channels=CHANNELS,
                        latency=latency) as audio_input_stream:
        audio_duration_seconds = audio_duration_minutes * 60
        last_block_time_epoch_seconds = 0

        while True:
            audio_file_path = get_audio_file_path(audio_dir, audio_start=datetime.now(), audio_format=audio_format)
            os.makedirs(os.path.dirname(audio_file_path), exist_ok=True)

            with sf.SoundFile(file=audio_file_path,
                              mode='w',
                              samplerate=SAMPLERATE,
                              channels=CHANNELS) as audio_file:
                logging.info(f'Writing audio to {audio_file}')
                blocks = []
                recording_start_seconds = audio_input_stream.time

                def recording_duration_seconds() -> int:
                    return audio_input_stream.time - recording_start_seconds

                while recording_duration_seconds() <= audio_duration_seconds:
                    block_read_time = Stopwatch()
                    block, overflowed = audio_input_stream.read(frames=block_size)
                    block_time_epoch_seconds = int(time.time())
                    block_read_time.stop()

                    block_processing_time = Stopwatch()
                    block = block.reshape(-1)
                    blocks.append(block)
                    a_weighted_block = a_weighting(block)
                    measurement = process_block(block_time_epoch_seconds, overflowed, a_weighted_block)

                    if block_time_epoch_seconds > last_block_time_epoch_seconds:
                        record_measurement(rrd_file, rrdcached, measurement)
                        last_block_time_epoch_seconds = block_time_epoch_seconds

                    if len(blocks) >= audio_blocks_write_number:
                        write_blocks(audio_file, blocks)
                        blocks = []

                    block_processing_time.stop()

                    log_level = logging.ERROR if overflowed else logging.INFO
                    logging.log(log_level, f'{measurement}, read: {block_read_time}, process: {block_processing_time}')

                if len(blocks) > 0:
                    write_blocks(audio_file, blocks)

                audio_file.flush()


if __name__ == "__main__":
    app()
