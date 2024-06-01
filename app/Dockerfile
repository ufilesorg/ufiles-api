FROM python:3.11-slim as fast-base

WORKDIR /app

COPY requirements.txt requirements2.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir -r requirements2.txt

RUN adduser --disabled-password --gecos '' user && mkdir /app/logs && chown -R user:user /app/logs

FROM fast-base as fast-server

USER user
COPY . .

CMD ["python", "-m" ,"debugpy", "--listen", "0.0.0.0:3000", "-m", "app"]
# CMD [ "python","app.py" ]