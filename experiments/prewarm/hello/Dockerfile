# image เล็ก ๆ สำหรับ Experiment 1 (pre-pull ด้วย DaemonSet)
#
# v1 กับ v2 ต้องมี layer ต่างกันจริง ไม่งั้น pull ตัวที่ 2 จะได้ cache จากตัวแรกไปเลย วัดเวลาไม่ได้
# เลยใส่ไฟล์สุ่มขนาด PAD_MB ไว้ (สุ่ม = บีบอัดไม่ได้ ขนาดตอน pull ใกล้ PAD_MB จริง)
#
#   docker build --build-arg VERSION=v1 -t 100.127.74.48:5001/vlab/hello:v1 experiments/prewarm/hello
#   docker build --build-arg VERSION=v2 -t 100.127.74.48:5001/vlab/hello:v2 experiments/prewarm/hello
#
# ต้องมี /bin/sh กับ sleep เพราะ DaemonSet สั่ง container ให้นอนรอด้วย sh
FROM busybox:1.36

ARG VERSION=v1
ARG PAD_MB=50

RUN dd if=/dev/urandom of=/pad.bin bs=1M count=${PAD_MB} 2>/dev/null \
 && echo "hello ${VERSION}" > /hello.txt

CMD ["/bin/sh", "-c", "cat /hello.txt; while true; do sleep 3600; done"]
