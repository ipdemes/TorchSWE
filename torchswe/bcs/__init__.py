#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2021 Pi-Yueh Chuang <pychuang@pm.me>
#
# Distributed under terms of the BSD 3-Clause license.

"""This subpackage contain boundary-condition-related functions.
"""
import os as _os
from operator import itemgetter as _itemgetter
from torchswe.utils.config import Config as _Config
from torchswe.utils.config import BCConfig as _BCConfig
from torchswe.utils.data import Topography as _Topography
from torchswe.utils.data import States as _States
import logging

logger = logging.getLogger("torchswe.bcs")

if "USE_CUPY" in _os.environ and _os.environ["USE_CUPY"] == "1":
    from ._cupy_outflow import outflow_bc_factory  # pylint: disable=no-name-in-module
    from ._cupy_linear_extrap import linear_extrap_bc_factory  # pylint: disable=no-name-in-module
    from ._cupy_const_val import const_val_bc_factory  # pylint: disable=no-name-in-module
    from ._cupy_inflow import inflow_bc_factory  # pylint: disable=no-name-in-module
elif (
    ("LEGATE_MAX_DIM" in _os.environ and "LEGATE_MAX_FIELDS" in _os.environ) or
    ("USE_TORCH" in _os.environ and _os.environ["USE_TORCH"] == "1")
):
    from .cunumeric_linear_extrap import linear_extrap_bc_factory  # pylint: disable=no-name-in-module
    from .cunumeric_const_val import const_val_bc_factory  # pylint: disable=no-name-in-module
else:
    from ._cython_outflow import outflow_bc_factory  # pylint: disable=no-name-in-module
    from ._cython_linear_extrap import linear_extrap_bc_factory  # pylint: disable=no-name-in-module
    from ._cython_const_val import const_val_bc_factory  # pylint: disable=no-name-in-module
    from ._cython_inflow import inflow_bc_factory  # pylint: disable=no-name-in-module


def init_bc(states: _States, topo: _Topography, config: _Config):
    """ This is supposed to take care of the initialization of all
    boundaries and variables.

    Returns: List[BCConfig]
        A list of BCConfig which when invoked updates the boundary 
        conditions for all variables and boundaries
    """

    bcs = config.bc
    vectorize_bc = config.params.vectorize_bc
    orientations = ["west", "east", "south", "north"]
    funcs = []

    def bc_helper(bctp, bcv, components, states, topo):
        logger.info("Ghost cell update for ornt %s and BC %s", ornt, bctp)

        # linear extrapolation BC
        if bctp == "extrap":
            funcs.append(linear_extrap_bc_factory(ornt, components, states, topo))
        # constant, i.e., Dirichlet
        elif bctp == "const":
            funcs.append(const_val_bc_factory(ornt, components, states, topo, bcv))
        else:
            print("ERROR: Unsupported boundary condition.")

    for ornt, bc in zip(orientations, _itemgetter(*orientations)(bcs)):
        # same bc along this orientation, so we can vectorize 
        if vectorize_bc and len(set(bc.types)) == 1 and len(set(bc.values)) == 1:
            components = -1 
            bc_helper(bc.types[0], bc.values[0], components, states, topo)
        else:
            for component, (bctp, bcv) in enumerate(zip(bc.types, bc.values)):
                bc_helper(bctp, bcv, component, states, topo)

    return funcs


def setup_bc(states: _States, topo: _Topography, config: _Config):

    funcs = init_bc(states, topo, config)

    # this is the function that will be retuned by this function factory
    def updater(soln: _States):
        for func in funcs:  # if funcs is an empty list, this will skip it
            if func is not None:
                func()
        return soln

    # store the functions as an attribute for debug
    updater.funcs = funcs

    return updater

def get_ghost_cell_updaters(states: _States, topo: _Topography, bcs: _BCConfig):
    """A function factory returning a function that updates all ghost cells.

    Arguments
    ---------
    states : torchswe.mpi.data.States
        The States instance that will be updated in the simulation.
    topo : torchswe.tuils.data.Topography
        Topography instance. Some boundary conditions require topography elevations.
    bcs : torchswe.utils.config.BCConfig
        The configuration instance of boundary conditions.

    Returns
    -------
    A callable with signature `torchswe.utils.data.States = func(torchswe.utils.data.States)`.

    Notes
    -----
    The resulting functions modify the values in solution in-place. The return of this function is
    the same object as the one in input arguments. We return it just to comform the coding style.
    """

    bcs.check()
    funcs = []  # can be either a list or ordered dict, cannot be an unordered dict
    orientations = ["west", "east", "south", "north"]

    for ornt, bc in zip(orientations, _itemgetter(*orientations)(bcs)):

        # special case: periodic BC
        # -------------------------
        # In MPI cases, periodic boundaries will be handled by internal exchange stage
        # Also, we're using Cartcomm, so periodic ranks are already configured in the beginning
        if bc.types[0] == "periodic":
            continue  # no need to continue this iteration as other components should be periodic

        # all other types of BCs
        # ----------------------
        for i, (bctp, bcv) in enumerate(zip(bc.types, bc.values)):

            logger.info("Ghost cell update for ornt %s and BC %s", ornt, bctp)

            # constant extrapolation BC (outflow)
            if bctp == "outflow":
                funcs.append(outflow_bc_factory(ornt, i, states, topo))

            # linear extrapolation BC
            elif bctp == "extrap":
                funcs.append(linear_extrap_bc_factory(ornt, i, states, topo))

            # constant, i.e., Dirichlet
            elif bctp == "const":
                funcs.append(const_val_bc_factory(ornt, i, states, topo, bcv))

            # inflow, i.e., constant non-conservative variables
            elif bctp == "inflow":
                funcs.append(inflow_bc_factory(ornt, i, states, topo, bcv))

            # this shouldn't happen because pydantic should have catched the error
            else:
                raise ValueError(f"{bctp} is not recognized.")

    # check the data model in case neighbors changed due to periodic BC
    states.check()

    # this is the function that will be retuned by this function factory
    def updater(soln: _States):
        for func in funcs:  # if funcs is an empty list, this will skip it
            func()
        return soln

    # store the functions as an attribute for debug
    updater.funcs = funcs

    return updater
