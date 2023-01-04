import sounddevice as sd
import numpy as np
import time
import rrdtool
import os
import logging
import sys

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, stream=sys.stdout)
samplerate = 44100
block_duration_seconds = 1
blocksize = int(samplerate * block_duration_seconds)
rrd_dir = os.path.dirname(os.path.abspath(__file__))
rrd_file = os.path.join(rrd_dir, 'mixer.rrd')
logging.info(f'Writing to {rrd_file}')

if not os.path.exists(rrd_file):
	rrdtool.create(
		rrd_file, 
		'--step', '1s',
		'DS:amplitude:GAUGE:1m:0:32767',
		'RRA:AVERAGE:0.5:1s:1day')

with sd.InputStream(
	samplerate=samplerate, 
	dtype=np.int16,
	channels=1,
	latency='low') as stream:
	while True:
		block, _ = stream.read(frames=blocksize)
		start_ns = time.monotonic_ns()
		block = block.reshape(-1)
		rms_amplitude = np.sqrt(np.mean(np.square(block)))
		end_ns = time.monotonic_ns()
		elapsed_ns = end_ns - start_ns
		rrdtool.update(rrd_file, f'N:{rms_amplitude}')
		logging.info(f'RMS: {rms_amplitude:.2f}, elapsed ms: {int(elapsed_ns / 1_000_000)}')
