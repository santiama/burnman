from __future__ import absolute_import
# This file is part of BurnMan - a thermoelastic and thermodynamic toolkit for the Earth and Planetary Sciences
# Copyright (C) 2012 - 2017 by the BurnMan team, released under the GNU
# GPL v2 or later.


import scipy.optimize as opt
from . import equation_of_state as eos
from ..tools import bracket
import warnings
import numpy as np

# Try to import the jit from numba.  If it is
# not available, just go with the standard
# python interpreter
try:
    from numba import jit
except ImportError:
    def jit(fn):
        return fn


@jit
def _delta_PoverK_from_P(PoverK, pressure, K_0, Kprime_0, Kprime_inf):
    return PoverK - (pressure/K_0)*np.power((1. - Kprime_inf*PoverK), Kprime_0/Kprime_inf) # eq. 58

@jit
def _delta_PoverK_from_V(PoverK, V, V_0, K_0, Kprime_0, Kprime_inf):
    Kprime_ratio = Kprime_0 / Kprime_inf
    return ( np.log( V_0 / V ) +
             Kprime_ratio / Kprime_inf * np.log(1. - Kprime_inf * PoverK) +
             (Kprime_ratio - 1.) * PoverK ) # eq. 61

def _PoverK_from_P(pressure, params):
    """
    Calculates the pressure:bulk modulus ratio
    from a given pressure using brentq optimization
    """
    args = (pressure, params['K_0'],
            params['Kprime_0'], params['Kprime_inf'])
    return opt.brentq(_delta_PoverK_from_P, -1., 1./params['Kprime_inf'], args=args)

    
def _PoverK_from_V(volume, params):
    """
    Calculates the pressure:bulk modulus ratio
    from a given volume using brentq optimization
    """
    args = (volume, params['V_0'], params['K_0'],
            params['Kprime_0'], params['Kprime_inf'])
    return opt.brentq(_delta_PoverK_from_V, -1., 1./params['Kprime_inf'], args=args)

def bulk_modulus(pressure, params):
    """
    Returns the bulk modulus at a given pressure
    """
    PoverK = _PoverK_from_P(pressure, params)
    K = params['K_0']*np.power((1. - params['Kprime_inf']*PoverK), -
                               params['Kprime_0']/params['Kprime_inf'])
    return K

def shear_modulus(pressure, params):
    """
    Shear modulus not currently implemented for this equation of state
    """
    return 0.


class RKprime(eos.EquationOfState):

    """
    Class for the isothermal reciprocal K-prime equation of state 
    detailed in :cite:`StaceyDavis2004`.  This equation of state is
    a development of work by :cite:`Keane1954` and :cite:`Stacey2000`, 
    making use of the fact that :math:`K'` typically varies smoothly
    as a function of :math:`P/K`, and is thermodynamically required to
    exceed 5/3 at infinite pressure. 
    This equation of state has no temperature dependence. 
    """

    def volume(self, pressure, temperature, params):
        """
        Returns volume :math:`[m^3]` as a function of pressure :math:`[Pa]`.
        """
        Kprime_ratio = params['Kprime_0']/params['Kprime_inf']
        PoverK = _PoverK_from_P(pressure, params)
        
        V = params['V_0'] * np.exp( Kprime_ratio/params['Kprime_inf'] *
                                    np.log(1. - params['Kprime_inf'] * PoverK) +
                                    (Kprime_ratio - 1.) * PoverK ) # Eq. 61

        return V

    def pressure(self, temperature, volume, params):
        """
        Returns pressure :math:`[Pa]` as a function of volume :math:`[m^3]`.
        """
        PoverK = _PoverK_from_V(volume, params)
        return ( params['K_0'] * PoverK *
                 np.power(1. - params['Kprime_inf'] * PoverK,
                          -params['Kprime_0']/params['Kprime_inf']) )

    def isothermal_bulk_modulus(self, pressure, temperature, volume, params):
        """
        Returns isothermal bulk modulus :math:`K_T` :math:`[Pa]` as a function of pressure :math:`[Pa]`,
        temperature :math:`[K]` and volume :math:`[m^3]`.
        """
        return bulk_modulus(pressure, params)

    def adiabatic_bulk_modulus(self, pressure, temperature, volume, params):
        """
        Returns adiabatic bulk modulus :math:`K_s` of the mineral. :math:`[Pa]`.
        """
        return bulk_modulus(pressure, params)

    def shear_modulus(self, pressure, temperature, volume, params):
        """
        Returns shear modulus :math:`G` of the mineral. :math:`[Pa]`
        """
        return shear_modulus(pressure, params)

    def heat_capacity_v(self, pressure, temperature, volume, params):
        """
        Since this equation of state does not contain temperature effects, simply return a very large number. :math:`[J/K/mol]`
        """
        return 1.e99

    def heat_capacity_p(self, pressure, temperature, volume, params):
        """
        Since this equation of state does not contain temperature effects, simply return a very large number. :math:`[J/K/mol]`
        """
        return 1.e99

    def thermal_expansivity(self, pressure, temperature, volume, params):
        """
        Since this equation of state does not contain temperature effects, simply return zero. :math:`[1/K]`
        """
        return 0.

    def grueneisen_parameter(self, pressure, temperature, volume, params):
        """
        Since this equation of state does not contain temperature effects, simply return zero. :math:`[unitless]`
        """
        return 0.

    def validate_parameters(self, params):
        """
        Check for existence and validity of the parameters.
        The value for :math:`K'_{\infty}` is thermodynamically bounded
        between 5/3 and :math:`K'_0` :cite:`StaceyDavis2004`.
        """

        if 'P_0' not in params:
            params['P_0'] = 0.

        # If G and Gprime are not included this is presumably deliberate,
        # as we can model density and bulk modulus just fine without them,
        # so just add them to the dictionary as nans
        if 'G_0' not in params:
            params['G_0'] = float('nan')
        if 'Gprime_0' not in params:
            params['Gprime_0'] = float('nan')

        # Check that all the required keys are in the dictionary
        expected_keys = ['V_0', 'K_0', 'Kprime_0', 'Kprime_inf', 'G_0', 'Gprime_0']
        for k in expected_keys:
            if k not in params:
                raise KeyError('params object missing parameter : ' + k)

        # Finally, check that the values are reasonable.
        if params['P_0'] < 0.:
            warnings.warn('Unusual value for P_0', stacklevel=2)
        if params['V_0'] < 1.e-7 or params['V_0'] > 1.e-3:
            warnings.warn('Unusual value for V_0', stacklevel=2)
        if params['K_0'] < 1.e9 or params['K_0'] > 1.e13:
            warnings.warn('Unusual value for K_0', stacklevel=2)
        if params['Kprime_0'] < 0. or params['Kprime_0'] > 10.:
            warnings.warn('Unusual value for Kprime_0', stacklevel=2)
        if params['Kprime_inf'] < 5./3. or params['Kprime_inf'] > params['Kprime_0']:
            warnings.warn('Unusual value for Kprime_inf', stacklevel=2) # eq. 17
        if params['G_0'] < 0.0 or params['G_0'] > 1.e13:
            warnings.warn('Unusual value for G_0', stacklevel=2)
        if params['Gprime_0'] < -5. or params['Gprime_0'] > 10.:
            warnings.warn('Unusual value for Gprime_0', stacklevel=2)

