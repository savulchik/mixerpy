from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import rrdtool
from pydantic import BaseSettings
import os
import logging
import sys

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, stream=sys.stdout)
rrd_dir = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    rrdcached: str = 'unix:/tmp/rrdcached.sock'
    rrd_file: str = os.path.join(rrd_dir, 'mixer.rrd')


settings = Settings()
logging.info(f'Using {settings}')

app = FastAPI()
app.mount('/static', StaticFiles(directory='static', html=True), name='static')
app.mount('/audio', StaticFiles(directory='audio'), name='audio')

@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url='static/')

@app.get("/graph/amplitude")
def graph_amplitude(width: str, height: str, start: str, end: str, zoom: str) -> Response:
    result = rrdtool.graphv('-',
                            '--start', start,
                            '--end', end,
                            '--width', width,
                            '--height', height,
                            '--title', 'Amplitude',
                            '--right-axis', '1:0',
                            f'DEF:peak_amplitude={settings.rrd_file}:peak_amplitude:AVERAGE',
                            f'DEF:rms_amplitude={settings.rrd_file}:rms_amplitude:AVERAGE',
                            f'CDEF:peak_amplitude_trend=peak_amplitude,180,TRENDNAN',
                            f'CDEF:rms_amplitude_trend=rms_amplitude,180,TRENDNAN',
                            # 'LINE1:peak_amplitude#FF0000',
                            # 'LINE1:rms_amplitude#0000FF',
                            'LINE1:peak_amplitude_trend#FF0000',
                            'LINE1:rms_amplitude_trend#0000FF')
    return Response(content=result['image'], media_type='image/png')

@app.get("/graph/amplitude_dbfs")
def graph_amplitude(width: str, height: str, start: str, end: str, zoom: str) -> Response:
    result = rrdtool.graphv('-',
                            '--start', start,
                            '--end', end,
                            '--width', width,
                            '--height', height,
                            '--title', 'Amplitude',
                            '--vertical-label', 'dBFS',
                            '--right-axis', '1:0',
                            f'DEF:peak_amplitude_dbfs={settings.rrd_file}:peak_amplitude_dbfs:AVERAGE',
                            f'DEF:rms_amplitude_dbfs={settings.rrd_file}:rms_amplitude_dbfs:AVERAGE',
                            f'CDEF:peak_amplitude_trend_dbfs=peak_amplitude_dbfs,180,TRENDNAN',
                            f'CDEF:rms_amplitude_trend_dbfs=rms_amplitude_dbfs,180,TRENDNAN',
                            # 'LINE1:peak_amplitude_dbfs#FF0000',
                            # 'LINE1:rms_amplitude_dbfs#0000FF',
                            'LINE1:peak_amplitude_trend_dbfs#FF0000',
                            'LINE1:rms_amplitude_trend_dbfs#0000FF')
    return Response(content=result['image'], media_type='image/png')

@app.post("/flush")
def flush():
    rrdtool.flushcached('--daemon', settings.rrdcached,
                        settings.rrd_file)
    return None