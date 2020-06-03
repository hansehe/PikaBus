FROM python:3.8-buster as dev

WORKDIR src

COPY docs/requirements.txt docs/requirements.txt
RUN pip install -r docs/requirements.txt

FROM dev as final

COPY . .

ENTRYPOINT sphinx-autobuild -b html --host 0.0.0.0 --port 8100 ./docs ./docs/_build