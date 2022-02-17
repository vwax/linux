FROM debian:bullseye

# Kernel build
RUN apt-get update && apt-get -y install \
    bc \
    build-essential \
    flex \
    bison \
    rsync \
    kmod

# Running roadtests
RUN apt-get update && apt-get -y install \
     python3.9 \
     libpython3.9-dev \
     python3 \
     device-tree-compiler

# Development and debugging
RUN apt-get update && apt-get -y install \
     uml-utilities \
     telnetd \
     python3-pip
COPY requirements.txt /tmp/
RUN pip install --requirement /tmp/requirements.txt
