"""Post-hoc test of a temporal persistence rule on the cloud replay's 10-minute detections:
keep a detection at scan t only if the same pixel or a neighbour also fired at t-10 or t+10 min.
Writes filtered copies to data/detections_persist/ (same layout) for eval_pod.py --cloud."""
import glob
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import ndimage

from saanjh import gk2a

SHAPE = (gk2a.WIN[1] - gk2a.WIN[0], gk2a.WIN[3] - gk2a.WIN[2])
src, dst = "data/detections", "data/detections_persist"


def mask(path):
    m = np.zeros(SHAPE, bool)
    if os.path.exists(path):
        d = pd.read_csv(path)
        m[d.i, d.j] = True
    return m


for day_dir in sorted(glob.glob(f"{src}/20[0-9]*")):
    day = os.path.basename(day_dir)
    os.makedirs(f"{dst}/{day}", exist_ok=True)
    for f in sorted(glob.glob(f"{day_dir}/*.csv")):
        t = datetime.strptime(day + os.path.basename(f)[:4], "%Y%m%d%H%M")
        near = np.zeros(SHAPE, bool)
        for dt in (-10, 10):
            u = t + timedelta(minutes=dt)
            near |= mask(f"{src}/{u:%Y%m%d}/{u:%H%M}.csv")
        near = ndimage.binary_dilation(near)
        d = pd.read_csv(f)
        d[near[d.i, d.j]].to_csv(f"{dst}/{day}/{os.path.basename(f)}", index=False)
print("done")
