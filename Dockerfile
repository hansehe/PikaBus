FROM python:3.6-slim as dev

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

FROM dev as final

COPY . .

ENV RUNNING_IN_CONTAINER=true

ENTRYPOINT python -m unittest discover -p *Test*.py