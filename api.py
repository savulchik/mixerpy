from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import rrdtool

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url='static/index.html')

@app.get("/graph")
def graph(width: str, height: str, start: str, end: str, zoom: str) -> Response:
    result = rrdtool.graphv('-',
                            '--start', start,
                            '--end', end,
                            '--width', width,
                            '--height', height,
                            'DEF:amplitude=mixer.rrd:amplitude:AVERAGE',
                            'LINE1:amplitude#FF0000')
    return Response(content=result['image'], media_type='image/png')

@app.post("/flush")
def flush():
    rrdtool.flushcached('--daemon', 'unix:/tmp/rrdcached.sock',
                        'mixer.rrd')
    return None