FROM ubuntu:14.04

ENV DEBIAN_FRONTEND=noninteractive

RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    bzip2 \
    file \
    bc \
    cpio \
    libncurses5-dev \
    python3 \
    gawk \
    libc6:i386 \
    libstdc++6:i386 \
    zlib1g:i386 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
