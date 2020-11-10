# See https://hub.docker.com/u/qmentasdk/ for more base images

# Install the SDK
FROM ubuntu:18.04

WORKDIR /root

RUN apt-get update -y && \
    apt-get install -y python3 python3-pip wget && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install qmenta-sdk-lib
RUN python3 -m qmenta.sdk.make_entrypoint /root/entrypoint.sh /root/

# Install your software requirements and run other config commands (may take several minutes)
ENV TZ=Europe/London
ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update -y && \
    apt-get install -y git g++ python libblas-dev liblapack-dev libeigen3-dev zlib1g-dev libqt5opengl5-dev \
    libqt5svg5-dev libgl1-mesa-dev libfftw3-dev libtiff5-dev libpng-dev graphviz cmake && \
    wget https://github.com/MRtrix3/mrtrix3/archive/3.0_RC3_latest.tar.gz && tar xvzf 3.0_RC3_latest.tar.gz && \
    cd mrtrix3-3.0_RC3_latest && ./configure -nogui && ./build && ./set_path && \
    wget https://github.com/ANTsX/ANTs/archive/v2.3.1.tar.gz && tar xvzf v2.3.1.tar.gz && \
    mkdir antsbin && cd antsbin && cmake ../ANTs-2.3.1 && make -j 4 && cd .. && \
    echo 'export PATH=~/antsbin/bin:$PATH' >> ~/.bashrc && source .bashrc && \
    pip3 install numpy dipy scipy nipype dmri-amico trampolino && \
    rm -rf /var/lib/apt/lists/*

# A virtual x framebuffer is required to generate PDF files with pdfkit
RUN echo '#!/bin/bash\nxvfb-run -a --server-args="-screen 0, 1024x768x24" /usr/bin/wkhtmltopdf -q $*' > /usr/bin/wkhtmltopdf.sh && \
    chmod a+x /usr/bin/wkhtmltopdf.sh && \
    ln -s /usr/bin/wkhtmltopdf.sh /usr/local/bin/wkhtmltopdf

# Copy the source files (only this layer will have to be built after the first time)
COPY tool.py report_template.html qmenta_logo.png /root/
