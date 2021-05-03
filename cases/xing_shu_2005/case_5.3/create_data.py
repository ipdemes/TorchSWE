#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2020-2021 Pi-Yueh Chuang <pychuang@gwu.edu>
#
# Distributed under terms of the BSD 3-Clause license.

"""Create topography and I.C. file for case 5.3 in Xing and Shu (2005).

Note, the elevation data in the resulting NetCDF file is defined at vertices,
instead of cell centers. But the I.C. is defined at cell centers.
"""
import pathlib
import yaml
import numpy
from torchswe.utils.config import Config
from torchswe.utils.netcdf import write_cf


def main():
    """Main function"""
    # pylint: disable=invalid-name

    case = pathlib.Path(__file__).expanduser().resolve().parent

    with open(case.joinpath("config.yaml"), 'r') as f:
        config: Config = yaml.load(f, Loader=yaml.Loader)

    x = numpy.linspace(
        config.spatial.domain[0], config.spatial.domain[1],
        config.spatial.discretization[0]+1, dtype=numpy.float64)
    y = numpy.linspace(
        config.spatial.domain[2], config.spatial.domain[3],
        config.spatial.discretization[1]+1, dtype=numpy.float64)

    # 2D X, Y for temporarily use
    X, Y = numpy.meshgrid(x, y)

    # topogeaphy elevation
    B = 0.8 * numpy.exp(-5.*numpy.power(X-0.9, 2)-50.*numpy.power(Y-0.5, 2))

    # write topography file
    write_cf(
        case.joinpath(config.topo.file), {"x": x, "y": y},
        {config.topo.key: B}, options={config.topo.key: {"units": "m"}})

    # x and y for cell centers
    xc = (x[:-1] + x[1:]) / 2.
    yc = (y[:-1] + y[1:]) / 2.

    # I.C.: w
    w = numpy.ones_like(xc)
    w[(xc >= 0.05)*(xc <= 0.15)] += 0.01
    w = numpy.tile(w, (config.spatial.discretization[1], 1))

    # I.C.: hu & hv
    hu = numpy.zeros_like(xc)
    hv = numpy.zeros_like(xc)
    hu = numpy.tile(hu, (config.spatial.discretization[1], 1))
    hv = numpy.tile(hv, (config.spatial.discretization[1], 1))

    # write I.C. file
    write_cf(
        case.joinpath(config.ic.file), {"x": xc, "y": yc},
        dict(zip(config.ic.keys, [w, hu, hv])), options=dict(
            zip(config.ic.keys, [{"units": "m"}, {"units": "m2 s-1"}, {"units": "m2 s-1"}])))

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
