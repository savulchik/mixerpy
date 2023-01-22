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
import soundfile as sf
from datetime import datetime, timedelta
from dataclasses import dataclass


SAMPLERATE = 44100
SAMPLE_DTYPE = np.int16
AMPLITUDE_MAX_VALUE = 32767
CHANNELS = 1

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, stream=sys.stdout)
app = typer.Typer()
mixer_dir = os.path.dirname(os.path.abspath(__file__))

@dataclass
class Measurement:
    epoch_seconds: int
    peak_amplitude: np.int16
    peak_amplitude_dbfs: np.float64
    rms_amplitude: np.float64
    rms_amplitude_dbfs: np.float64


def process_block(epoch_seconds: int, block: np.ndarray) -> Measurement:
    peak_amplitude = min(np.amax(np.abs(block)), AMPLITUDE_MAX_VALUE)
    peak_amplitude_dbfs = round(20 * math.log10(peak_amplitude / AMPLITUDE_MAX_VALUE), 2) if peak_amplitude > 0 else -np.inf
    rms_amplitude = round(np.sqrt(np.mean(np.square(block, dtype=np.int64))), 2)
    rms_amplitude_dbfs = round(20 * math.log10(rms_amplitude / AMPLITUDE_MAX_VALUE), 2) if rms_amplitude > 0 else -np.inf
    return Measurement(epoch_seconds,
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
    start_ns = time.monotonic_ns()
    audio_file.write(np.concatenate(blocks))
    end_ns = time.monotonic_ns()
    elapsed_ns = end_ns - start_ns
    logging.info(f'Written {len(blocks)} audio blocks to {audio_file.name}, elapsed ms: {int(elapsed_ns / 1_000_000)}')


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
           audio_blocks_write_number: int = 10):
    logging.info(f'Using {rrd_file} via {rrdcached} for storage')

    if not os.path.exists(rrd_file):
        create_rrd(rrd_file, rrdcached, step_seconds=block_duration_seconds)

    logging.info(f'Using {get_input_device_info(device_index)} for recording')

    with sd.InputStream(samplerate=SAMPLERATE,
                        device=device_index,
                        dtype=SAMPLE_DTYPE,
                        channels=CHANNELS,
                        latency='low') as stream:
        block_size = SAMPLERATE * block_duration_seconds
        audio_duration = timedelta(minutes=audio_duration_minutes)

        while True:
            audio_start = datetime.now()
            audio_file_path = get_audio_file_path(audio_dir, audio_start, audio_format)
            os.makedirs(os.path.dirname(audio_file_path), exist_ok=True)

            with sf.SoundFile(file=audio_file_path,
                              mode='w',
                              samplerate=SAMPLERATE,
                              channels=CHANNELS) as audio_file:
                logging.info(f'Writing audio to {audio_file}')
                blocks = []
                audio_end = audio_start + audio_duration
                while datetime.now() < audio_end:
                    block, _ = stream.read(frames=block_size)
                    block_time_epoch_seconds = int(time.time())
                    block = block.reshape(-1)
                    start_ns = time.monotonic_ns()
                    blocks.append(block)
                    measurement = process_block(block_time_epoch_seconds, block)
                    record_measurement(rrd_file, rrdcached, measurement)

                    if len(blocks) >= audio_blocks_write_number:
                        write_blocks(audio_file, blocks)
                        blocks = []

                    end_ns = time.monotonic_ns()
                    elapsed_ns = end_ns - start_ns
                    logging.info(f'{measurement}, elapsed ms: {int(elapsed_ns / 1_000_000)}')

                if len(blocks) > 0:
                    write_blocks(audio_file, blocks)

                audio_file.flush()


if __name__ == "__main__":
    app()
