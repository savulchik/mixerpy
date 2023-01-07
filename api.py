from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import rrdtool
from pydantic import BaseSettings
import os


rrd_dir = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    rrdcached: str = 'unix:/tmp/rrdcached.sock'
    rrd_file: str = os.path.join(rrd_dir, 'mixer.rrd')


settings = Settings()
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url='static/index.html')

@app.get("/graph/amplitude")
def graph_amplitude(width: str, height: str, start: str, end: str, zoom: str) -> Response:
    result = rrdtool.graphv('-',
                            '--start', start,
                            '--end', end,
                            '--width', width,
                            '--height', height,
                            f'DEF:peak_amplitude={settings.rrd_file}:peak_amplitude:AVERAGE',
                            f'DEF:rms_amplitude={settings.rrd_file}:rms_amplitude:AVERAGE',
                            'LINE1:peak_amplitude#FF0000',
                            'LINE1:rms_amplitude#0000FF')
    return Response(content=result['image'], media_type='image/png')

@app.get("/graph/amplitude_dbfs")
def graph_amplitude(width: str, height: str, start: str, end: str, zoom: str) -> Response:
    result = rrdtool.graphv('-',
                            '--start', start,
                            '--end', end,
                            '--width', width,
                            '--height', height,
                            f'DEF:peak_amplitude_dbfs={settings.rrd_file}:peak_amplitude_dbfs:AVERAGE',
                            f'DEF:rms_amplitude_dbfs={settings.rrd_file}:rms_amplitude_dbfs:AVERAGE',
                            'LINE1:peak_amplitude_dbfs#FF0000',
                            'LINE1:rms_amplitude_dbfs#0000FF')
    return Response(content=result['image'], media_type='image/png')

@app.post("/flush")
def flush():
    rrdtool.flushcached('--daemon', settings.rrdcached,
                        settings.rrd_file)
    return None