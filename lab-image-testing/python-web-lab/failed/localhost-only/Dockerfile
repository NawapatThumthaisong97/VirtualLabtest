ARG BASE=vlab-test/python-web-lab:passed
FROM ${BASE}

# Flask listens on 127.0.0.1 only: nothing outside the container can reach port 5000
ENV FLASK_HOST=127.0.0.1
