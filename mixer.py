import sounddevice as sd
import queue
import numpy as np
import time
import rrdtool
import os


samplerate = 44100
block_duration_seconds = 1
rrd_file = 'mixer.rrd'

blocks = queue.SimpleQueue()

def callback(indata: np.ndarray, frames: int, time, status: sd.CallbackFlags) -> None:
	blocks.put_nowait(indata)

if not os.path.exists(rrd_file):
	rrdtool.create(
		rrd_file, 
		'--step', '1s',
		'DS:amplitude:GAUGE:1m:0:1', 
		'RRA:AVERAGE:0.5:1s:1day')

with sd.InputStream(
	samplerate=samplerate, 
	blocksize=int(samplerate * block_duration_seconds),
	channels=1,
	callback=callback) as stream:
	while True:
		block = blocks.get()
		max_aplitude = np.amax(block)
		print(f'Max amplitude: {max_aplitude}')
		rrdtool.update(rrd_file, f'N:{max_aplitude}')
