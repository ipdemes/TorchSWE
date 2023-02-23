#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2020-2021 Pi-Yueh Chuang <pychuang@gwu.edu>
#
# Distributed under terms of the BSD 3-Clause license.

"""Finite-volume scheme from Kurganov and Petrova, 2007.
"""
from __future__ import annotations as _annotations  # allows us not using quotation marks for hints
from typing import TYPE_CHECKING as _TYPE_CHECKING  # indicates if we have type checking right now
if _TYPE_CHECKING:  # if we are having type checking, then we import corresponding classes/types
    from torchswe.utils.misc import DummyDict
    from torchswe.utils.config import Config
    from torchswe.utils.data import States

# pylint: disable=wrong-import-position, ungrouped-imports
from torchswe import nplike as _nplike
from torchswe.kernels import get_discontinuous_flux as _get_discontinuous_flux
from torchswe.kernels import central_scheme as _central_scheme
from torchswe.kernels import get_local_speed as _get_local_speed
from torchswe.kernels import reconstruct as _reconstruct


def prepare_rhs(states: States, runtime: DummyDict, config: Config):
    """Get the right-hand-side of a time-marching step for SWE.

    Arguments
    ---------
    states : torchswe.utils.data.States
    runtime : torchswe.utils.misc.DummyDict
    config : torchswe.utils.config.Config

    Returns:
    --------
    states : torchswe.utils.data.States
        The same object as the input. Updated in-place. Returning it just for coding style.
    max_dt : float
        A scalar indicating the maximum time-step size if we consider CFL to be one. Note, it
        does not mean this time-step size is safe. Whether it's safe or not depending on the
        allowed CFL of the implemented scheme.
    """

    # reconstruct conservative and non-conservative quantities at cell interfaces
    states = _reconstruct(states, runtime, config)

    # get local speed at cell faces
    states = _get_local_speed(states)

    # get discontinuous PDE flux at cell faces
    states = _get_discontinuous_flux(states)

    # get common/continuous numerical flux at cell faces
    states = _central_scheme(states)

    # aliases
    if not config.params.allow_async:
        dy, dx = states.domain.delta
    else:
        dy, dx = states.domain.delta_array

    # get right-hand-side contributed by spatial derivatives
    states.s = \
        (states.face.x.cf[:, :, :-1] - states.face.x.cf[:, :, 1:]) / dx + \
        (states.face.y.cf[:, :-1, :] - states.face.y.cf[:, 1:, :]) / dy

    # add explicit source terms in-place to states.S
    for func in runtime.sources:
        states = func(states, runtime, config)

    # add stiff source terms to states.SS (including reset it to zero first)
    for func in runtime.stiff_sources:
        states = func(states, runtime, config)

    if not config.params.allow_async:
        # obtain the maximum safe dt
        amax = _nplike.max(_nplike.maximum(states.face.x.plus.a, -states.face.x.minus.a))
        bmax = _nplike.max(_nplike.maximum(states.face.y.plus.a, -states.face.y.minus.a))

        with _nplike.errstate(divide="ignore"):
            max_dt = _nplike.minimum(dx/amax, dy/bmax)  # may be a `inf` (but never `NaN`)
    else:
        max_dt = config.temporal.dt

    return states, max_dt
