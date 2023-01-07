from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import rrdtool

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
                            'DEF:peak_amplitude=mixer.rrd:peak_amplitude:AVERAGE',
                            'DEF:rms_amplitude=mixer.rrd:rms_amplitude:AVERAGE',
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
                            'DEF:peak_amplitude_dbfs=mixer.rrd:peak_amplitude_dbfs:AVERAGE',
                            'DEF:rms_amplitude_dbfs=mixer.rrd:rms_amplitude_dbfs:AVERAGE',
                            'LINE1:peak_amplitude_dbfs#FF0000',
                            'LINE1:rms_amplitude_dbfs#0000FF')
    return Response(content=result['image'], media_type='image/png')

@app.post("/flush")
def flush():
    rrdtool.flushcached('--daemon', 'unix:/tmp/rrdcached.sock',
                        'mixer.rrd')
    return None