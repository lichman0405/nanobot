FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Build Zeo++ from active mirror and its bundled Voro++ dependency
ARG ZEO_URL=https://github.com/mharanczyk/zeoplusplus/archive/refs/heads/master.tar.gz
RUN wget -q "$ZEO_URL" -O zeopp.tar.gz && \
    tar xzf zeopp.tar.gz && \
    cd zeoplusplus-* && \
    make -C voro++/src -j$(nproc) && \
    make -j$(nproc) && \
    cp network /usr/local/bin/ && \
    cd / && rm -rf zeoplusplus-* zeopp.tar.gz

WORKDIR /data
ENTRYPOINT ["network"]
