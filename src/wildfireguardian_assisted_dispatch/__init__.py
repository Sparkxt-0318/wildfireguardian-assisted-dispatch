"""WildfireGuardian assisted dispatch: synthetic-phase research kernel.

This package answers one question and nothing else:

    For a mobility-limited resident, at what dispatch times can a responder
    complete the entire base -> resident -> pickup -> safe destination mission
    under time-varying hazards?

Everything here is synthetic.  No real wildfire model, no real Korean road
network, no real WildfireGuardian routing integration.  See docs/SCOPE.md.
"""

from .version import __version__

__all__ = ["__version__"]
