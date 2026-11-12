#!/bin/bash
source ../BaseStack/bin/setup_run.sh
PYTHONPATH=`pwd`/src/pysed2translate:`pwd`/scripts:${PYTHONPATH}
PYTHONPATH=`pwd`/src/pysed2translate/runtime:${PYTHONPATH}
PYTHONPATH=`pwd`/src/pysed2translate/capabilities:${PYTHONPATH}
export PYTHONPATH
source s2/bin/activate
