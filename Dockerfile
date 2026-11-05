FROM python:3.14-slim

WORKDIR /app

# Install CPU-only PyTorch before resolving project dependencies.
# This prevents pip from selecting a CUDA-enabled distribution.
RUN python -m pip install \
    --timeout 60 \
    --retries 2 \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch==2.15.0+cpu"

COPY pyproject.toml constraints.cpu.txt ./

RUN python -m pip install \
    --timeout 60 \
    --retries 2 \
    --constraint constraints.cpu.txt \
    .

COPY . .

RUN python -m pip check

EXPOSE 8000

CMD ["uvicorn", "scoring.api:app", "--host", "0.0.0.0", "--port", "8000"]
