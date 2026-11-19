FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

RUN pip install flask==3.1.0 jupyterlab==4.3.4 \
 && useradd --create-home --uid 1000 --shell /bin/bash student

COPY --chmod=755 start-lab.sh /usr/local/bin/start-lab

USER student
WORKDIR /home/student/lab
COPY --chown=student:student lab/ ./

EXPOSE 5000 8888
ENTRYPOINT ["start-lab"]
CMD ["--notebook-dir=/home/student/lab"]
