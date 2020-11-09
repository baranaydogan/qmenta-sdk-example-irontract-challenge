# See https://hub.docker.com/u/qmentasdk/ for more base images
FROM qmentasdk/minimal:latest

# Install your software requirements and run other config commands (may take several minutes)
ENV TZ=Europe/London
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update -y && \
    apt-get install -y git g++ ants python libeigen3-dev zlib1g-dev libqt5opengl5-dev libqt5svg5-dev libgl1-mesa-dev libfftw3-dev libtiff5-dev libpng-dev && \
    git clone https://github.com/MRtrix3/mrtrix3.git && cd mrtrix3 && ./configure -nogui && ./build && ./set_path && \
    pip install numpy dipy scipy nipype dmri-amico trampolino && \
    rm -rf /var/lib/apt/lists/*
    
# A virtual x framebuffer is required to generate PDF files with pdfkit
RUN echo '#!/bin/bash\nxvfb-run -a --server-args="-screen 0, 1024x768x24" /usr/bin/wkhtmltopdf -q $*' > /usr/bin/wkhtmltopdf.sh && \
    chmod a+x /usr/bin/wkhtmltopdf.sh && \
    ln -s /usr/bin/wkhtmltopdf.sh /usr/local/bin/wkhtmltopdf

# Copy the source files (only this layer will have to be built after the first time)
COPY tool.py report_template.html qmenta_logo.png /root/

