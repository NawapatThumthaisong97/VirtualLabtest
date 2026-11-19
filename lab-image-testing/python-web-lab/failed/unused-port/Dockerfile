ARG BASE=vlab-test/python-web-lab:passed
FROM ${BASE}

# Same as an EXPOSE inherited from a base image (e.g. FROM nginx): nothing listens on 80,
# and 80 sorts before 5000, so it becomes the port the readiness check waits for.
EXPOSE 80
