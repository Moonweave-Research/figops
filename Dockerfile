FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG RENV_BOOTSTRAP_VERSION=1.1.7

RUN apt-get update && apt-get install -y --no-install-recommends \
    r-base \
    r-base-dev \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    fontconfig \
    fonts-liberation \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/graph_making_hub

COPY requirements.txt requirements.txt
COPY requirements-lock.txt requirements-lock.txt
COPY renv.lock renv.lock

RUN pip install --no-cache-dir -r requirements-lock.txt

RUN RENV_BOOTSTRAP_VERSION="$RENV_BOOTSTRAP_VERSION" Rscript -e "version <- Sys.getenv('RENV_BOOTSTRAP_VERSION'); urls <- c(sprintf('https://cloud.r-project.org/src/contrib/renv_%s.tar.gz', version), sprintf('https://cloud.r-project.org/src/contrib/Archive/renv/renv_%s.tar.gz', version)); installed <- FALSE; for (url in urls) { tryCatch({ install.packages(url, repos = NULL, type = 'source'); installed <- TRUE }, error = function(e) NULL); if (installed) break }; if (!installed) stop(sprintf('failed to install renv %s', version))"
RUN Rscript -e "renv::restore(lockfile = 'renv.lock', prompt = FALSE)"

COPY . .

CMD ["python", "orchestrator.py", "--help"]
