# Zeo++ Docker Image

Build:
  docker build -t zeopp:latest docker/zeopp/

Test:
  docker run --rm -v /path/to/cif:/data zeopp:latest -ha -res /data/output.res /data/test.cif

Note: If the GitHub mirror is unavailable, check https://github.com/lsmo-epfl/zeo_plusplus for the latest URL.
The official site http://www.zeoplusplus.org may also work but is intermittently down.
