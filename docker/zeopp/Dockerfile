FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Build Voro++ 0.4.6
RUN wget -q https://github.com/chr1shr/voro/archive/refs/tags/v0.4.6.tar.gz -O voro.tar.gz && \
    tar xzf voro.tar.gz && \
    cd voro-0.4.6 && \
    make -j$(nproc) && \
    make install && \
    cd / && rm -rf voro-0.4.6 voro.tar.gz

# Build Zeo++ (LSMO mirror on GitHub)
RUN wget -q https://github.com/lsmo-epfl/zeo_plusplus/archive/refs/heads/master.tar.gz -O zeopp.tar.gz && \
    tar xzf zeopp.tar.gz && \
    cd zeo_plusplus-master && \
    make -j$(nproc) && \
    cp network /usr/local/bin/ && \
    cd / && rm -rf zeo_plusplus-master zeopp.tar.gz

WORKDIR /data
ENTRYPOINT ["network"]
