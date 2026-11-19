FROM busybox:1.36 AS tools

# No ENTRYPOINT, no CMD, no EXPOSE: there is nothing to run
FROM scratch
COPY --from=tools /bin/busybox /bin/busybox
