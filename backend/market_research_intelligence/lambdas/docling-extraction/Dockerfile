FROM public.ecr.aws/lambda/python:3.13

WORKDIR ${LAMBDA_TASK_ROOT}

# ---- system dependencies ----
RUN dnf update -y && \
    dnf install -y \
        gcc gcc-c++ make \
        wget tar git \
        libjpeg-devel \
        libpng-devel \
        libtiff-devel \
        zlib-devel \
        autoconf automake libtool \
        poppler-utils \
        python3-devel \
        mesa-libGL \
        glib2-devel \
        shadow-utils \
    && /usr/sbin/groupadd -r appuser \
    && /usr/sbin/useradd -r -g appuser appuser \
    && dnf remove -y shadow-utils \
    && dnf clean all && rm -rf /var/cache/dnf

# ---- build leptonica ----
RUN cd /tmp && \
    wget https://github.com/danbloomberg/leptonica/releases/download/1.86.0/leptonica-1.86.0.tar.gz && \
    tar -xzf leptonica-1.86.0.tar.gz && \
    cd leptonica-1.86.0 && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    echo "/usr/local/lib" > /etc/ld.so.conf.d/local.conf && \
    /sbin/ldconfig && \
    rm -rf /tmp/leptonica*

# ---- build tesseract ----
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

RUN cd /tmp && \
    git clone --branch 5.3.0 --depth 1 https://github.com/tesseract-ocr/tesseract.git && \
    cd tesseract && \
    ./autogen.sh && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    /sbin/ldconfig && \
    rm -rf /tmp/tesseract

# ---- tessdata ----
RUN mkdir -p /usr/local/share/tessdata && \
    wget -O /usr/local/share/tessdata/eng.traineddata \
        https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata && \
    wget -O /usr/local/share/tessdata/osd.traineddata \
        https://github.com/tesseract-ocr/tessdata_fast/raw/main/osd.traineddata

# Install tesserocr Python binding
RUN pip install tesserocr

# Set cache directories to /tmp (Lambda writable)
ENV TESSDATA_PREFIX=/usr/local/share/tessdata
ENV TESSERACT_PATH=/usr/local/bin/tesseract
ENV TRANSFORMERS_CACHE=/tmp/transformers
ENV HF_HOME=/tmp/huggingface
ENV TORCH_HOME=/tmp/torch
ENV NUMBA_CACHE_DIR=/tmp/numba_cache

# Copy requirements file
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install PyTorch CPU-only from official index (avoids dependency confusion with --extra-index-url)
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu
# Install remaining dependencies from PyPI
RUN pip install --no-cache-dir -r requirements.txt

# Copy Lambda handler
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# Switch to non-root user for security compliance
USER appuser

CMD ["lambda_function.lambda_handler"]
