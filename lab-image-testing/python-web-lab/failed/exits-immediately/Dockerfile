ARG BASE=vlab-test/python-web-lab:passed
FROM ${BASE}

# The command finishes on its own, so the container stops right after it starts.
# Setting ENTRYPOINT also drops the CMD inherited from the base image.
ENTRYPOINT ["python", "-c", "print('setup done'); raise SystemExit(3)"]
