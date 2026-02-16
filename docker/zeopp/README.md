# Zeo++ Docker Image

Build:
  docker build -t zeopp:latest docker/zeopp/

Optional mirror override:
  docker build -t zeopp:latest docker/zeopp/ --build-arg ZEO_URL="https://github.com/mharanczyk/zeoplusplus/archive/refs/heads/master.tar.gz"

Test:
  docker run --rm -v /path/to/cif:/data zeopp:latest -ha -res /data/output.res /data/test.cif

Note: If the mirror is unavailable, check the official site http://www.zeoplusplus.org for latest source links.
